"""Accommodation requests: students ask from the course page; instructors decide in Lectern.

An evaluation takes requests when its gradebook entry (grades.json) says so:

  "accom": { "standard": "The makeup … counts for 12.5% …",   the standard accommodation: the evaluation's
                                                              missed-work policy in words (Grades writes it on save)
             "approval": true,                   students must ask for it (an instructor approves)
             "alternate": true }                 students may ask for something else instead

The course page's Request Accommodation button opens /request?r=<the instructor's handle>&o=<course/term>&e=<eval id>,
a small form served from here. It calls, in turn:

  GET  /api/accommodations/evaluation   what can be asked for (no student details needed)
  POST /api/accommodations/verify       is this student in the course? (email, identifier, first and
                                        last name must all match the gradebook, email included)
  POST /api/accommodations/submit       record the request and email the student a receipt

Requests are kept in the instructor's private files beside the gradebook, <course>/<term>/accommodations.json
(store.py): students never sign in, so the server reads the gradebook and records the request itself.
Lectern's Accommodations page reads that file, and the instructor's decision goes through

  POST /api/accommodations/decide       (signed in) approve or reject, save, email

which saves the change in the signed-in instructor's own files and emails the student.
"""
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, render_template, request

from . import db, mailer
from .auth import signed_in
from .security import Limiter
from .store import Repo, StoreError

accom_bp = Blueprint('accommodations', __name__)

FILE = "accommodations.json"
FORMAT = "lectern-accommodations/1"
MAX_DETAILS = 4000
MAX_PER_STUDENT = 10       # requests per student per evaluation

_HANDLE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
_SLUG = re.compile(r"^[\w.-]{1,64}$")


class Refusal(Exception):
    """A request we turn down, with what to tell the person."""
    def __init__(self, status, message, code=""):
        super().__init__(message)
        self.status, self.code = status, code


def _err(e):
    return jsonify(error=str(e), code=getattr(e, "code", "")), e.status


# ── Where things are ─────────────────────────────────────────────────
def _owner(r):
    """The link's r= (the instructor's handle, as in their course pages' address) → their account id."""
    r = str(r or "").strip().strip("/").lower()
    if "/" in r:   # a course page saved before Lectern had its own accounts (r=owner/repo)
        raise Refusal(400, "This link is from an older course page. Ask your instructor to open the course page in Lectern and save it again.")
    if not _HANDLE.match(r):
        raise Refusal(400, "This link is missing its course.")
    u = db.one("SELECT id, disabled FROM users WHERE handle = ?", (r,))
    if not u or u["disabled"]:
        raise Refusal(404, "This course isn't taking accommodation requests.")
    return u["id"]


def _offering(o):
    parts = str(o or "").strip("/").split("/")
    if len(parts) != 2 or not all(_SLUG.match(p) and p[0] not in "._" for p in parts):
        raise Refusal(400, "This link is missing its course.")
    return "/".join(parts)


def _eval_id(e):
    e = str(e or "")
    if not _SLUG.match(e):
        raise Refusal(400, "This link is missing its evaluation.")
    return e


# ── The gradebook, read as the app (cached briefly: one page view makes a few calls) ──
_books = {}
_books_lock = threading.Lock()
BOOK_TTL = 20


def _book(uid, o):
    key = (uid, o)
    with _books_lock:
        hit = _books.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
    try:
        text, _ = Repo(uid, "priv").read_text(f"{o}/grades.json")
    except StoreError as e:
        raise Refusal(e.status, str(e))
    if text is None:
        raise Refusal(404, "This course isn't taking accommodation requests.")
    try:
        book = json.loads(text)
    except ValueError:
        raise Refusal(502, "This course's gradebook couldn't be read.")
    with _books_lock:
        _books[key] = (time.time() + BOOK_TTL, book)
    return book


def _zone():
    """The course's time zone: dates and times in the gradebook are local times there."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(os.environ.get("LECTERN_TIMEZONE") or "America/Toronto")
    except Exception:
        return None   # no time zone data: the server's own clock


def deadline_of(a):
    """When requests close, as a timestamp (None: no deadline). by is YYYY-MM-DD, byTime HH:MM (default 23:59)."""
    by, at = str(a.get("by") or ""), str(a.get("byTime") or "") or "23:59"
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", by):
        return None
    try:
        if not re.match(r"^\d{1,2}:\d{2}$", at):
            at = "23:59"
        dt = datetime.strptime(by + " " + at, "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    z = _zone()
    return (dt.replace(tzinfo=z) if z else dt.astimezone()).timestamp() + 59   # through the end of that minute


clock = time.time   # tests replace this


def accom_of(ev):
    """An evaluation's accommodation options, cleaned up."""
    a = (ev or {}).get("accom") or {}
    standard = str(a.get("standard") or "").strip()
    out = {"standard": standard, "approval": bool(a.get("approval")) and bool(standard), "alternate": bool(a.get("alternate")),
           "by": "", "byTime": "", "closed": False}
    end = deadline_of(a)
    if end is not None:
        out.update(by=a["by"], byTime=str(a.get("byTime") or "") or "23:59", closed=clock() > end)
    return out


def when_text(date, at):
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return date
    return f"{d.strftime('%A, %B')} {d.day}, {d.year}" + (f", {at}" if at else "")


def _evaluation(book, e, open_only=False):
    ev = next((x for x in book.get("evals") or [] if x.get("id") == e), None)
    a = accom_of(ev)
    if not ev or not (a["approval"] or a["alternate"]):
        raise Refusal(404, "This evaluation isn't taking accommodation requests.")
    if open_only and a["closed"]:
        raise Refusal(410, f"The deadline to request an accommodation for {ev.get('name') or 'this evaluation'} has passed ({when_text(a['by'], a['byTime'])}).", "closed")
    return ev, a


def _course(book):
    c = book.get("course") or {}
    return str(c.get("code") or "").strip(), str(c.get("term") or "").strip()


def _id_label(book):
    return str(((book.get("fields") or {}).get("idLabel")) or "Student Identifier")


def _email_fields(book):
    return [f.get("id") for f in ((book.get("fields") or {}).get("custom") or [])
            if f.get("id") == "email" or re.search(r"e-?mail", str(f.get("label") or ""), re.I)]


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().casefold()


def find_student(book, email, sid, first, last):
    """The enrolled student these details belong to, and their email on file; else a Refusal."""
    fids = _email_fields(book)
    if not fids:
        raise Refusal(409, "This course can't take requests yet: its class list has no email addresses. Please contact your instructor.", "no-email")
    want = [_norm(x) for x in (email, sid, first, last)]
    if not all(want):
        raise Refusal(400, "Fill in all four: your email, " + _id_label(book).lower() + ", first name and last name.")
    for s in book.get("students") or []:
        if s.get("dropped"):
            continue
        if _norm(s.get("num")) != want[1] or _norm(s.get("first")) != want[2] or _norm(s.get("last")) != want[3]:
            continue
        for fid in fids:
            on_file = str(((s.get("f") or {}).get(fid)) or "").strip()
            if on_file and _norm(on_file) == want[0]:
                return s, on_file
    raise Refusal(404, f"We couldn't find you in this course. Use the email, {_id_label(book).lower()} and name your instructor has for you, spelled the same way.", "not-found")


# ── Too many tries from one place ────────────────────────────────────
limiter = Limiter()
LIMITS = {"verify": (20, 600), "submit": (10, 600)}


def _client_ip():
    return request.remote_addr or "?"   # behind a proxy, core.py's ProxyFix makes this the student's address


def _limit(kind):
    n, w = LIMITS[kind]
    if not limiter.ok(f"{kind}:{_client_ip()}", n, w):
        raise Refusal(429, "Too many tries. Wait a few minutes, then try again.")


# ── Students: CORS, so a course page could call these itself too ─────
@accom_bp.after_request
def _cors(resp):
    if request.path.startswith("/api/accommodations/") and request.path != "/api/accommodations/decide":
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@accom_bp.get("/request")
def request_page():
    """The form students fill in (the course page links here)."""
    return render_template("request.html", institution=os.environ.get("LECTERN_INSTITUTION", "University of Toronto"))


def _where(args):
    uid = _owner(args.get("r"))
    o = _offering(args.get("o"))
    e = _eval_id(args.get("e"))
    return uid, o, e


def _public_info(book, ev, a):
    code, term = _course(book)
    return {
        "course": {"code": code, "term": term},
        "evaluation": {"id": ev.get("id"), "name": ev.get("name") or "", "type": "test" if ev.get("type") == "test" else "assignment",
                       "date": ev.get("date") or "", "time": ev.get("time") or ""},
        "idLabel": _id_label(book),
        "standard": {"text": a["standard"], "approval": a["approval"]} if a["standard"] else None,
        "alternate": a["alternate"],
        "deadline": {"date": a["by"], "time": a["byTime"], "text": when_text(a["by"], a["byTime"]), "passed": a["closed"]} if a["by"] else None,
    }


@accom_bp.get("/api/accommodations/evaluation")
def evaluation():
    try:
        uid, o, e = _where(request.args)
        book = _book(uid, o)
        ev, a = _evaluation(book, e)
        return jsonify(_public_info(book, ev, a))
    except Refusal as x:
        return _err(x)


def _body():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        raise Refusal(400, "Something went wrong with the form. Reload the page and try again.")
    return d


@accom_bp.post("/api/accommodations/verify")
def verify():
    try:
        d = _body()
        _limit("verify")
        uid, o, e = _where(d)
        book = _book(uid, o)
        ev, a = _evaluation(book, e, open_only=True)
        s, _ = find_student(book, d.get("email"), d.get("id"), d.get("first"), d.get("last"))
        return jsonify(ok=True, first=s.get("first") or "", **_public_info(book, ev, a))
    except Refusal as x:
        return _err(x)


# ── The requests file ────────────────────────────────────────────────
def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(text):
    if not text:
        return {"format": FORMAT, "requests": []}
    try:
        d = json.loads(text)
    except ValueError:
        raise Refusal(502, f"{FILE} couldn't be read.")
    if not isinstance(d, dict) or not isinstance(d.get("requests"), list):
        raise Refusal(502, f"{FILE} couldn't be read.")
    return d


def _dump(d):
    return json.dumps(d, indent=1, ensure_ascii=False) + "\n"


def _update(uid, o, change, message, author=""):
    """Read the requests file, change it, write it back; again if someone else wrote in between."""
    path = f"{o}/{FILE}"
    repo = Repo(uid, "priv")
    for _ in range(4):
        try:
            text, sha = repo.read_text(path)
            d = _parse(text)
            out = change(d)
            if repo.write_text(path, _dump(d), sha, message(out) if callable(message) else message, author):
                return out
        except StoreError as e:
            raise Refusal(e.status, str(e))
    raise Refusal(503, "Lectern is busy with other requests. Try again in a moment.")


def _what(r):
    if r["kind"] == "standard":
        return f"the standard accommodation: {r.get('standard') or ''}"
    return f"an alternate accommodation:\n\n{_quote(r.get('details') or '')}"


def _quote(text):
    return "\n".join("    " + line for line in str(text).splitlines() or [""])


def _course_line(r):
    return " ".join(x for x in (r.get("course"), f"({r['term']})" if r.get("term") else "") if x)


def receipt_email(r):
    code = r.get("course") or "Your course"
    body = f"""Hi {r['first']},

We've received your request for an accommodation for {r['evalName']} in {_course_line(r)}.

You asked for {_what(r)}

Your instructor will review it, and you'll get another email when it's approved or rejected. If you need another accommodation, make a new request the same way.

Reference: {r['id']}
"""
    return f"{code}: accommodation request received ({r['evalName']})", body


def decision_email(r):
    code = r.get("course") or "Your course"
    ok = r["status"] == "approved"
    body = f"""Hi {r['first']},

Your request for an accommodation for {r['evalName']} in {_course_line(r)} has been {"approved" if ok else "rejected"}.

You asked for {_what(r)}
"""
    if r.get("note"):
        body += f"\nA note from your instructor:\n\n{_quote(r['note'])}\n"
    if not ok:
        body += "\nIf you need a different accommodation, you can make a new request from the course page.\n"
    body += f"\nReference: {r['id']}\n"
    return f"{code}: accommodation for {r['evalName']} {'approved' if ok else 'rejected'}", body


@accom_bp.post("/api/accommodations/submit")
def submit():
    try:
        d = _body()
        _limit("submit")
        uid, o, e = _where(d)
        book = _book(uid, o)
        ev, a = _evaluation(book, e, open_only=True)
        s, email = find_student(book, d.get("email"), d.get("id"), d.get("first"), d.get("last"))
        kind = d.get("kind")
        details = str(d.get("details") or "").strip()
        if kind == "standard" and not a["approval"]:
            raise Refusal(400, "The standard accommodation can't be requested for this evaluation.")
        if kind == "alternate" and not a["alternate"]:
            raise Refusal(400, "An alternate accommodation isn't available for this evaluation.")
        if kind not in ("standard", "alternate"):
            raise Refusal(400, "Choose what you're asking for.")
        if kind == "alternate" and not details:
            raise Refusal(400, "Say what you need.")
        if len(details) > MAX_DETAILS:
            raise Refusal(400, f"That's too long: keep it under {MAX_DETAILS} characters.")
        code, term = _course(book)
        rec = {
            "id": "r-" + secrets.token_hex(4), "eval": e, "evalName": ev.get("name") or e, "kind": kind,
            "standard": a["standard"] if kind == "standard" else "", "details": details,
            "student": s.get("num"), "first": s.get("first") or "", "last": s.get("last") or "", "email": email,
            "course": code, "term": term,
            "status": "pending", "submitted": _now(), "decided": "", "decidedBy": "", "note": "",
        }

        def add(f):
            mine = [x for x in f["requests"] if x.get("student") == rec["student"] and x.get("eval") == e]
            if len(mine) >= MAX_PER_STUDENT:
                raise Refusal(429, "You've made a lot of requests for this evaluation. Please contact your instructor.", "too-many")
            if kind == "standard":
                dup = next((x for x in f["requests"] if x.get("student") == rec["student"] and x.get("eval") == e
                            and x.get("kind") == "standard" and x.get("status") in ("pending", "approved")), None)
                if dup:
                    raise Refusal(409, "You've already asked for the standard accommodation for this evaluation"
                                  + (": it's been approved." if dup["status"] == "approved" else ", and it's waiting for your instructor."), "duplicate")
            f["requests"].append(rec)
            f["format"] = FORMAT
            return rec

        _update(uid, o, add, f"Accommodation request from {rec['student']} for {rec['evalName']}", "student")
        subject, body = receipt_email(rec)
        emailed = mailer.send(email, subject, body)
        return jsonify(ok=True, id=rec["id"], email=email, emailed=emailed), 201
    except Refusal as x:
        return _err(x)


# ── Instructors ──────────────────────────────────────────────────────
@accom_bp.post("/api/accommodations/decide")
@signed_in
def decide():
    """Approve or reject one request in your own course: saved in your files, then emailed."""
    try:
        d = _body()
        o = _offering(d.get("offering"))
        rid = str(d.get("id") or "")
        decision = d.get("decision")
        note = str(d.get("note") or "").strip()[:MAX_DETAILS]
        if decision not in ("approved", "rejected"):
            raise Refusal(400, "Approve or reject.")
        who = g.user["name"] or g.user["email"]

        def apply(f):
            r = next((x for x in f["requests"] if x.get("id") == rid), None)
            if not r:
                raise Refusal(404, "That request isn't there any more.")
            r.update(status=decision, decided=_now(), decidedBy=who, note=note)
            return dict(r)

        r = _update(g.user["id"], o, apply,
                    lambda r: f"{'Approve' if decision == 'approved' else 'Reject'} accommodation request from {r['student']} for {r['evalName']}",
                    g.user["email"])
        subject, body = decision_email(r)
        emailed = bool(r.get("email")) and mailer.send(r["email"], subject, body)
        return jsonify(ok=True, request=r, emailed=emailed)
    except Refusal as x:
        return _err(x)
