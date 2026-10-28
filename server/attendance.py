"""Attendance: who was there for an evaluation (an exam, a test), taken by the teaching team holding students' ID cards up to a phone's camera.

Anyone on the offering's team takes it, at any time, several at once. Each starts a session (with a note:
the room, or the last names they're taking), scans students' ID cards (or finds a student by hand), and
stops it: so each session has its own count, and the evaluation its total.

  A scan       what's printed on the card (read with OCR, in the browser): its student number, or its names →
               the student on the class list. The scanner shows who it is; Correct records them.
  Once each    a student is in once per evaluation (the database refuses a second), however many people are
               scanning: the second is told who entered them, and when.

Kept in the database (db.py's attendance tables, not the offering's files): it's written by many people at once.

  GET  /api/attendance?owner&offering&e                  the evaluation, its total and its sessions
  POST /api/attendance/start   {owner, offering, e, note}  a new session (yours)
  POST /api/attendance/stop    {owner, offering, session}
  POST /api/attendance/delete  {owner, offering, session}   instructors: a session, and who it put in
  GET  /api/attendance/student?owner&offering&num          a student's attendance: each evaluation it was taken for,
                                                           and whether they were in (when, and who entered them)
  GET  /api/attendance/search?owner&offering&e&q          students by name or number
  POST /api/attendance/identify {owner, offering, e, text} whose student ID it is, by what's printed on it (the scanner reads
                                                           it, OCR): its student number, or its first and last names
  POST /api/attendance/mark    {owner, offering, e, session, student, hand?}  they're in
"""
import functools
import re
import time

from flask import Blueprint, g, jsonify, request

from . import db
from .auth import signed_in
from .accommodations import Refusal, _book, _offering, _owner, _eval_id, _err
from .store import StoreError

attendance_bp = Blueprint("attendance", __name__)


MAX_NOTE = 120
ROLES = ("owner", "coordinator", "instructor", "ta", "staff")


def team_api(fn):
    """Signed in to Lectern; a refusal is the error it says."""
    @signed_in
    @functools.wraps(fn)
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except Refusal as x:
            return _err(x)
        except StoreError as x:
            return _err(Refusal(x.status, str(x)))
    return run


def _team(d, need=ROLES):
    """The offering, its owner and the viewer's role: anyone on its teaching team (or, need: those roles)."""
    from .teams import role_of
    o = _offering(d.get("offering"))
    owner = _owner(d.get("owner")) if d.get("owner") else g.user["id"]
    role = role_of(g.user["id"], owner, o)
    if role not in ROLES:
        raise Refusal(404 if not role else 403, "Only the offering's teaching team can take attendance.")
    if role not in need:
        raise Refusal(403, "Only the offering's instructors can do that.")
    g.att_role = role
    return owner, o


LEADS = ("owner", "coordinator", "instructor")


def _ev(book, e):
    ev = next((x for x in book.get("evals") or [] if x.get("id") == e), None)
    if not ev:
        raise Refusal(404, "That evaluation isn't in the gradebook.")
    return ev


def _students(book):
    return [s for s in book.get("students") or [] if not s.get("dropped")]


def _who(s):
    f = s.get("f") or {}
    email = next((v for k, v in f.items() if "mail" in k.lower() and v), "")
    return {"num": str(s.get("num") or ""), "first": s.get("first") or "", "last": s.get("last") or "", "email": email}


def _in(owner, o, e, num):
    r = db.one("SELECT by_name, at FROM attendance WHERE owner_id = ? AND offering = ? AND eval = ? AND student = ?", (owner, o, e, num))
    return {"by": r["by_name"], "at": r["at"]} if r else None


def _args():
    return request.get_json(silent=True) if request.method == "POST" else request.args


def _book_of(owner, o):
    try:
        return _book(owner, o)
    except Refusal as x:
        raise Refusal(x.status, "This offering has no gradebook yet." if x.status == 404 else str(x))


@attendance_bp.get("/api/attendance")
@team_api
def overview():
    d = _args()
    owner, o = _team(d)
    e = _eval_id(d.get("e"))
    book = _book_of(owner, o)
    ev = _ev(book, e)
    S = db.all_("""SELECT s.id, s.user_id, s.user_name, s.note, s.started, s.stopped,
                          (SELECT COUNT(*) FROM attendance a WHERE a.session_id = s.id) AS n
                   FROM attendance_sessions s WHERE s.owner_id = ? AND s.offering = ? AND s.eval = ? ORDER BY s.started""", (owner, o, e))
    total = db.one("SELECT COUNT(*) AS n FROM attendance WHERE owner_id = ? AND offering = ? AND eval = ?", (owner, o, e))["n"]
    return jsonify(eval={"id": e, "name": ev.get("name") or e, "title": ev.get("title") or ""}, total=total, enrolled=len(_students(book)), canDelete=g.att_role in LEADS,
                   sessions=[{"id": s["id"], "by": s["user_name"], "mine": s["user_id"] == g.user["id"], "note": s["note"], "started": s["started"],
                              "stopped": s["stopped"], "count": s["n"]} for s in S])


@attendance_bp.post("/api/attendance/start")
@team_api
def start():
    d = _args() or {}
    owner, o = _team(d)
    e = _eval_id(d.get("e"))
    _ev(_book_of(owner, o), e)
    note = re.sub(r"\s+", " ", str(d.get("note") or "")).strip()[:MAX_NOTE]
    now = time.time()
    # One session at a time each: starting again stops the one still going.
    db.run("UPDATE attendance_sessions SET stopped = ? WHERE owner_id = ? AND offering = ? AND user_id = ? AND stopped = 0", (now, owner, o, g.user["id"]))
    db.run("INSERT INTO attendance_sessions (owner_id, offering, eval, user_id, user_name, note, started) VALUES (?, ?, ?, ?, ?, ?, ?)",
           (owner, o, e, g.user["id"], g.user["name"] or g.user["email"], note, now))
    sid = db.one("SELECT id FROM attendance_sessions WHERE owner_id = ? AND offering = ? AND user_id = ? ORDER BY id DESC LIMIT 1", (owner, o, g.user["id"]))["id"]
    return jsonify(ok=True, session={"id": sid, "note": note, "started": now, "count": 0})


def _session(owner, o, sid, e=None):
    s = db.one("SELECT * FROM attendance_sessions WHERE id = ? AND owner_id = ? AND offering = ?", (int(sid or 0), owner, o))
    if not s or s["user_id"] != g.user["id"] or (e and s["eval"] != e):
        raise Refusal(404, "That session isn't yours, or isn't there any more.", "no-session")
    return s


@attendance_bp.post("/api/attendance/stop")
@team_api
def stop():
    d = _args() or {}
    owner, o = _team(d)
    s = _session(owner, o, d.get("session"))
    if not s["stopped"]:
        db.run("UPDATE attendance_sessions SET stopped = ? WHERE id = ?", (time.time(), s["id"]))
    n = db.one("SELECT COUNT(*) AS n FROM attendance WHERE session_id = ?", (s["id"],))["n"]
    return jsonify(ok=True, count=n)


@attendance_bp.post("/api/attendance/delete")
@team_api
def delete_session():
    d = _args() or {}
    owner, o = _team(d, LEADS)
    s = db.one("SELECT * FROM attendance_sessions WHERE id = ? AND owner_id = ? AND offering = ?", (int(d.get("session") or 0), owner, o))
    if not s:
        raise Refusal(404, "That session isn't there any more.")
    with db.transaction():
        n = db.run("DELETE FROM attendance WHERE session_id = ?", (s["id"],)).rowcount
        db.run("DELETE FROM attendance_sessions WHERE id = ?", (s["id"],))
    return jsonify(ok=True, removed=n)


@attendance_bp.get("/api/attendance/student")
@team_api
def of_student():
    d = request.args
    owner, o = _team(d)
    num = str(d.get("num") or "")
    taken = [r["eval"] for r in db.all_("SELECT DISTINCT eval FROM attendance_sessions WHERE owner_id = ? AND offering = ?", (owner, o))]
    got = {r["eval"]: {"at": r["at"], "by": r["by_name"], "how": r["how"]} for r in db.all_(
        "SELECT eval, at, by_name, how FROM attendance WHERE owner_id = ? AND offering = ? AND student = ?", (owner, o, num))}
    return jsonify(evals={e: {"in": got.get(e)} for e in taken})


@attendance_bp.get("/api/attendance/search")
@team_api
def search():
    d = request.args
    owner, o = _team(d)
    e = _eval_id(d.get("e"))
    q = re.sub(r"\s+", " ", str(d.get("q") or "")).strip().lower()
    if len(q) < 2:
        return jsonify(students=[])
    words = [w.strip(",") for w in q.split(" ") if w.strip(",")]
    out = []
    for s in _students(_book_of(owner, o)):
        hay = f"{s.get('num') or ''} {s.get('first') or ''} {s.get('last') or ''} {s.get('utorid') or ''}".lower()
        if all(w in hay for w in words):
            w = _who(s)
            out.append({**w, "already": _in(owner, o, e, w["num"])})
            if len(out) >= 8:
                break
    return jsonify(students=out)


def _fold(x):
    import unicodedata
    x = unicodedata.normalize("NFKD", str(x or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", x).strip()


def _near(a, b):
    """a and b the same word, but for one letter read wrong (OCR), for words of 5 letters or more."""
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:i] + t[i + 1:] == s for i in range(len(t)))


def identify_text(book, text):
    """The students a card's printed text could be, best first: [(score, student)]. Its student number is enough
    (OCR reads O for 0 and so on, so those are read as digits); else their last name and first name."""
    T = _fold(text)
    words = T.split()
    fix = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "S": "5", "B": "8"})
    # Numbers as read: words that are mostly digits (a letter or two misread), and all of them run together
    # (a number read with spaces in it).
    nums = [re.sub(r"\D", "", w.translate(fix)) for w in words if sum(c.isdigit() for c in w) >= max(3, len(w) - 2)]
    runs = set(n for n in nums if len(n) >= 6) | {"".join(nums)}
    out = []
    for s in _students(book):
        num = re.sub(r"\D", "", str(s.get("num") or ""))
        score = 0
        if len(num) >= 6 and any(num in r for r in runs):
            score += 100
        last, first = _fold(s.get("last")).split(), _fold(s.get("first")).split()
        if last and all(any(_near(x, w) for w in words) for x in last):
            score += 45
        if first and any(any(_near(x, w) for w in words) for x in first):
            score += 30
        if score >= 45:
            out.append((score, s))
    out.sort(key=lambda x: -x[0])
    return out


@attendance_bp.post("/api/attendance/identify")
@team_api
def identify():
    d = _args() or {}
    owner, o = _team(d)
    e = _eval_id(d.get("e"))
    text = str(d.get("text") or "")[:4000]
    # Only a card's number, or both its names: one name alone is too easy to read in a busy picture.
    hits = [h for h in identify_text(_book_of(owner, o), text) if h[0] >= 75]
    if not hits:
        return jsonify(students=[])
    best = hits[0][0]
    # Sure: a number, or both names, and nobody else as good.
    sure = best >= 75 and (len(hits) == 1 or hits[1][0] < best)
    return jsonify(sure=sure, students=[{**_who(s), "score": sc, "already": _in(owner, o, e, str(s.get("num") or ""))} for sc, s in hits[:5]])


@attendance_bp.post("/api/attendance/mark")
@team_api
def mark():
    d = _args() or {}
    owner, o = _team(d)
    e = _eval_id(d.get("e"))
    sess = _session(owner, o, d.get("session"), e)
    if sess["stopped"]:
        raise Refusal(409, "This session has stopped: start a new one.", "stopped")
    num = str(d.get("student") or "")
    s = next((x for x in _students(_book_of(owner, o)) if str(x.get("num")) == num), None)
    if not s:
        raise Refusal(404, "That student isn't on the class list.", "not-enrolled")
    w = _who(s)
    who = g.user["name"] or g.user["email"]
    with db.transaction():
        got = db.run("""INSERT INTO attendance (owner_id, offering, eval, student, session_id, by_name, how, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT DO NOTHING""", (owner, o, e, num, sess["id"], who, "hand" if d.get("hand") else "scan", time.time())).rowcount
    if not got:
        a = _in(owner, o, e, num)
        by = f" by {a['by']}" if a and a["by"] else ""
        return jsonify(error=f"This student was already entered{by}.", code="already", student=w, already=a), 409
    n = db.one("SELECT COUNT(*) AS n FROM attendance WHERE session_id = ?", (sess["id"],))["n"]
    return jsonify(ok=True, student=w, count=n)
