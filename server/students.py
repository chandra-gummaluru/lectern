"""Students: each course offering's own class list, and students signing in to that course's page.

The class list is the gradebook's students (<course>/<term>/grades.json in the private files): Lectern →
the offering → Students adds them, one at a time or from a class list, and the gradebook shows them for
marks. Each enrolled student (not dropped) with an email can sign in; an instructor can email them the
course page's link. A student opens the course page and signs in to that course: their email, then a
one-time code Lectern emails them. A student session is for that one course page only (it isn't a
Lectern account and opens nothing else).

  GET  /api/students/<owner>/<course>/<term>            who has signed in, been sent the link (the team)
  POST /api/students/<owner>/<course>/<term>/invite     { email? | emails }  instructors: email the link

  GET  /c/<handle>/<course>/<term>/sign-in              the course's sign-in page
  POST /api/hub/<handle>/<course>/<term>/code           { email }          a code, if they're on the list
  POST /api/hub/<handle>/<course>/<term>/verify         { email, code }    signed in
  POST /api/hub/<handle>/<course>/<term>/sign-out

Codes: 6 random digits, kept only as a keyed hash, good for 10 minutes and one use, and cancelled after
5 wrong tries. Asking for one always answers the same, on the list or not, so the page never says who's in
the course; and it's rate-limited per email and per address. The session cookie is HttpOnly, Secure (over
HTTPS) and SameSite, one per course, for 120 days.
"""
import re
import secrets
import threading
import time

from flask import Blueprint, abort, g, jsonify, make_response, render_template, request

from . import db, mailer, security as sec
from .auth import Refusal, body, handles, ip, limiter, signed_in, text
from .core import app_url, link_base

students_bp = Blueprint("students", __name__)

CODE_MINUTES = 10
MAX_TRIES = 5
SESSION_DAYS = 120
_EMAIL = re.compile(r"^[^\s@,;<>]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_SLUG = re.compile(r"^[\w.-]{1,64}$")
LIMITS = {"code-email": (5, 3600), "code-ip": (30, 3600), "verify-ip": (40, 600), "verify-email": (15, 600)}


def _limit(kind, key):
    n, w = LIMITS[kind]
    if not limiter.ok(f"st-{kind}:{key}", n, w):
        raise Refusal(429, "Too many tries. Wait a few minutes, then try again.", "rate")


def norm(e):
    return str(e or "").strip().lower()


# ── The offering, and who's asking ──────────────────────────────────
def _offering(handle, course, term):
    if not (_SLUG.match(course or "") and _SLUG.match(term or "")):
        raise Refusal(404, "No such course offering.")
    o = db.one("SELECT id, handle, name, disabled FROM users WHERE handle = ?", (str(handle or "").lower(),))
    if not o or o["disabled"]:
        raise Refusal(404, "No such course offering.")
    return o, f"{course}/{term}"


def _staff(owner, course, term, lead=True):
    from .teams import role_of
    o, off = _offering(owner, course, term)
    r = role_of(g.user["id"], o["id"], off)
    if r not in (("owner", "coordinator") if lead else ("owner", "coordinator", "instructor", "ta", "staff")):
        raise Refusal(403, "Only the course's instructors can change its class list." if r in ("ta", "staff") else "You're not on this course offering's teaching team.")
    return o, off


def roster(owner_id, off):
    """{email: student} for the enrolled students (not dropped) of the gradebook, each with an email."""
    from .store import Repo
    import json
    raw = Repo(owner_id, "priv").read(f"{off}/grades.json")
    try:
        book = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        return {}
    out = {}
    for x in (book.get("students") if isinstance(book, dict) and isinstance(book.get("students"), list) else []):
        if not isinstance(x, dict) or x.get("dropped"):
            continue
        f = x.get("f") if isinstance(x.get("f"), dict) else {}
        e = norm(f.get("email") or x.get("email"))
        if _EMAIL.match(e) and len(e) <= 254:
            out[e] = {"num": str(x.get("num") or ""), "first": str(x.get("first") or ""), "last": str(x.get("last") or ""),
                      "groups": [str(g) for g in (x.get("groups") if isinstance(x.get("groups"), list) else [])]}
    return out


def on_list(owner_id, off, email):
    return norm(email) in roster(owner_id, off)


def _note(owner_id, off, email, col, t):
    """Keep when a student was sent the link (invited) or last signed in (last_in)."""
    assert col in ("invited", "last_in")
    with db.transaction() as c:
        c.execute("INSERT OR IGNORE INTO course_students (owner_id, offering, email, added) VALUES (?, ?, ?, ?)", (owner_id, off, email, t))
        c.execute(f"UPDATE course_students SET {col} = ? WHERE owner_id = ? AND offering = ? AND email = ?", (t, owner_id, off, email))


def cookie_name(owner_id, off):
    return "lst-" + sec.mac(f"{owner_id}/{off}", "student-cookie")[:16]


def student_of(owner_id, off):
    """The signed-in student (their email) for this course page, or None."""
    tok = request.cookies.get(cookie_name(owner_id, off))
    if not tok or len(tok) > 200:
        return None
    s = db.one("SELECT * FROM student_sessions WHERE id_hash = ?", (sec.token_hash(tok),))
    if not s or s["owner_id"] != owner_id or s["offering"] != off or s["expires"] < time.time():
        return None
    if not on_list(owner_id, off, s["email"]):   # taken off the class list (or dropped)
        db.run("DELETE FROM student_sessions WHERE id_hash = ?", (s["id_hash"],))
        return None
    if time.time() - s["last_seen"] > 3600:
        db.run("UPDATE student_sessions SET last_seen = ? WHERE id_hash = ?", (time.time(), s["id_hash"]))
    return s["email"]


def course_name(owner_id, course, term):
    from .hub import about_of, page_data
    a, p = about_of(owner_id, course, term) or {}, page_data(owner_id, course, term) or {}
    code = course.upper()
    title = a.get("title") or p.get("title") or ""
    return f"{code}: {title}" if title else code


def hub_url(o, off, base=None):
    return f"{base or app_url()}c/{o['handle']}/{off}/"


def _mail(owner_id, off, to, subject, text_):
    from .classmail import settings_for
    cfg = settings_for(owner_id, off)
    if mailer.keep:
        return mailer.send(to, subject, text_, cfg=cfg)
    threading.Thread(target=mailer.send, args=(to, subject, text_), kwargs={"cfg": cfg}, daemon=True).start()
    return bool(cfg.get("host"))


def _invite(o, off, email, name):
    base = link_base() or app_url()
    return _mail(o["id"], off, email, f"{name}: the course page",
                 f"You're in {name}. Its course page is here:\n\n  {hub_url(o, off, base)}\n\n"
                 f"To see everything on it, sign in there with this email ({email}): Lectern emails you a code.\n")


# ── The class list (the team) ────────────────────────────────────────
@students_bp.get("/api/students/<owner>/<course>/<term>")
@signed_in
def class_list(owner, course, term):
    """When each student was sent the link and last signed in, by email; the course page's link; and whether email goes out.
    (Who's on the class list is the gradebook's: the offering's Students card reads and changes it.)"""
    o, off = _staff(owner, course, term, lead=False)
    rows = db.all_("SELECT email, invited, last_in FROM course_students WHERE owner_id = ? AND offering = ?", (o["id"], off))
    return jsonify(state={r["email"]: {"invited": r["invited"], "last_in": r["last_in"]} for r in rows}, link=hub_url(o, off), email=mailer.configured())


@students_bp.post("/api/students/<owner>/<course>/<term>/invite")
@signed_in
def invite(owner, course, term):
    """Email the course page's link: to one student ({email}), some ({emails: [...]}), or everyone on the class list ({})."""
    o, off = _staff(owner, course, term)
    d, on = body(), roster(o["id"], off)
    want = [norm(d.get("email"))] if d.get("email") else [norm(x) for x in d.get("emails")] if isinstance(d.get("emails"), list) else list(on)
    want = [x for x in dict.fromkeys(want) if x in on]
    if not want:
        raise Refusal(404, "They're not on the class list (enrolled, with an email).")
    if not (mailer.configured() or mailer.keep):
        raise Refusal(400, "Email isn't set up on this server, so the link can't go out: share it yourself.")
    name, t, sent = course_name(o["id"], course, term), time.time(), 0
    for e in want[:5000]:
        if _invite(o, off, e, name):
            sent += 1
            _note(o["id"], off, e, "invited", t)
    return jsonify(invited=sent)


# ── Signing in to a course page (students) ───────────────────────────
@students_bp.get("/c/<handle>/<course>/<term>/sign-in")
def sign_in_page(handle, course, term):
    from .hub import page_or_blank
    try:
        o, off = _offering(handle, course, term)
    except Refusal:
        abort(404)
    if page_or_blank(o["id"], course, term) is None:
        abort(404)
    return render_template("hub-signin.html", course=course_name(o["id"], course, term), api=f"/api/hub/{o['handle']}/{off}", back=f"/c/{o['handle']}/{off}/")


@students_bp.post("/api/hub/<handle>/<course>/<term>/code")
@handles
def send_code(handle, course, term):
    o, off = _offering(handle, course, term)
    e = norm(text(body(), "email"))
    if not _EMAIL.match(e):
        raise Refusal(400, "Enter your email address.")
    _limit("code-ip", ip())
    _limit("code-email", f"{o['id']}/{off}/{e}")
    if on_list(o["id"], off, e):
        code, t = f"{secrets.randbelow(10 ** 6):06d}", time.time()
        with db.transaction() as c:
            c.execute("DELETE FROM student_codes WHERE owner_id = ? AND offering = ? AND email = ?", (o["id"], off, e))
            c.execute("DELETE FROM student_codes WHERE expires < ?", (t,))
            c.execute("INSERT INTO student_codes (owner_id, offering, email, code_mac, expires, tries, created) VALUES (?, ?, ?, ?, ?, 0, ?)",
                      (o["id"], off, e, sec.mac(f"{o['id']}/{off}/{e}/{code}", "student-code"), t + CODE_MINUTES * 60, t))
        name = course_name(o["id"], course, term)
        _mail(o["id"], off, e, f"{code} is your code for {name}",
              f"Your code to sign in to {name}'s course page:\n\n  {code}\n\nIt works once, for {CODE_MINUTES} minutes.\n"
              f"If you didn't ask for it, you can ignore this email.\n")
    # The same answer either way: the page never says who's in the course.
    return jsonify(sent=True, minutes=CODE_MINUTES)


@students_bp.post("/api/hub/<handle>/<course>/<term>/verify")
@handles
def verify(handle, course, term):
    o, off = _offering(handle, course, term)
    d = body()
    e, code = norm(text(d, "email")), re.sub(r"\D", "", str(d.get("code") or ""))[:6]
    _limit("verify-ip", ip())
    _limit("verify-email", f"{o['id']}/{off}/{e}")
    row = db.one("SELECT * FROM student_codes WHERE owner_id = ? AND offering = ? AND email = ?", (o["id"], off, e))
    wrong = Refusal(400, "That code isn't right, or it has expired. Check it, or get a new one.", "bad-code")
    if not row or row["expires"] < time.time() or len(code) != 6:
        raise wrong
    if not sec.same(row["code_mac"], sec.mac(f"{o['id']}/{off}/{e}/{code}", "student-code")):
        if row["tries"] + 1 >= MAX_TRIES:
            db.run("DELETE FROM student_codes WHERE owner_id = ? AND offering = ? AND email = ?", (o["id"], off, e))
        else:
            db.run("UPDATE student_codes SET tries = tries + 1 WHERE owner_id = ? AND offering = ? AND email = ?", (o["id"], off, e))
        raise wrong
    if not on_list(o["id"], off, e):
        raise wrong
    tok, t = sec.new_token(), time.time()
    name = cookie_name(o["id"], off)
    with db.transaction() as c:
        c.execute("DELETE FROM student_codes WHERE owner_id = ? AND offering = ? AND email = ?", (o["id"], off, e))
        old = request.cookies.get(name)
        if old:
            c.execute("DELETE FROM student_sessions WHERE id_hash = ?", (sec.token_hash(old),))
        c.execute("DELETE FROM student_sessions WHERE expires < ?", (t,))
        c.execute("INSERT INTO student_sessions (id_hash, owner_id, offering, email, created, last_seen, expires) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (sec.token_hash(tok), o["id"], off, e, t, t, t + SESSION_DAYS * 86400))
    _note(o["id"], off, e, "last_in", t)
    resp = make_response(jsonify(ok=True, back=f"/c/{o['handle']}/{off}/"))
    resp.set_cookie(name, tok, max_age=SESSION_DAYS * 86400, path="/", secure=request.is_secure, httponly=True, samesite="Lax")
    return resp


@students_bp.post("/api/hub/<handle>/<course>/<term>/seen")
@handles
def seen(handle, course, term):
    """A signed-in student has seen these announcements (the course page showed them): they're not New any more."""
    o, off = _offering(handle, course, term)
    email = student_of(o["id"], off)
    if not email:
        raise Refusal(401, "Sign in to the course page first.", "signed-out")
    ids = [str(x)[:80] for x in (body().get("ids") or []) if isinstance(x, str) and x.strip()][:200]
    t = time.time()
    with db.transaction() as c:
        for a in ids:
            c.execute("INSERT OR IGNORE INTO announcements_seen (owner_id, offering, email, ann_id, at) VALUES (?, ?, ?, ?, ?)", (o["id"], off, email, a, t))
    return jsonify(ok=True)


@students_bp.post("/api/hub/<handle>/<course>/<term>/sign-out")
@handles
def sign_out(handle, course, term):
    o, off = _offering(handle, course, term)
    name = cookie_name(o["id"], off)
    tok = request.cookies.get(name)
    if tok:
        db.run("DELETE FROM student_sessions WHERE id_hash = ?", (sec.token_hash(tok),))
    resp = make_response(jsonify(ok=True))
    resp.delete_cookie(name, path="/")
    return resp
