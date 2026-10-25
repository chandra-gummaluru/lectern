"""Teaching teams: the people who work on a course offering with its owner.

A course offering (e.g. csc258/f26) lives in one account's files: its owner's. The owner can add
others to its team, each as

  coordinator  everything the owner can do with that offering (its course page, evaluations,
               gradebook, exams, accommodation requests, its team), except remove the owner
  instructor   runs one or more activity groups (groups.json: the activities they run): adds and
               changes the activities and announcements for their groups (lectures.json,
               announcements.json, and the files of activities), and nothing else of anyone's
  ta           sees the gradebook and exams and enters marks for anyone (grades.json's "marks",
               nothing else); can't change activities, announcements, evaluations, settings or
               students, publish the course page, see accommodation requests, or change the team
  staff        sees what a TA sees, and decides accommodation requests (any group's); changes
               nothing else (not even marks); can leave the team

(Before activity groups, "instructor" meant what coordinator does now: those members became coordinators.)

Members reach the owner's files for that offering only, through the same store API as the owner
(/api/store/<owner handle>.<pub|priv>/…, see store.py), so every rule here is enforced on the server.

Adding someone: an instructor gives an email and a role, and that email gets a link (#join=…) to
accept: signed in to the account with that email, or by making one (so Lectern stays closed to the
public: only people an instructor of a real offering asked can join, and only that offering). Nobody
joins without accepting, and the answer is the same whether or not the email has an account. A link
works once, for 7 days, and only while whoever sent it is still an instructor of the offering.

  GET  /api/teams/mine                         the offerings shared with you, and your role in each
  GET  /api/teams/<owner>/<course>/<term>      the team (and, for instructors, waiting invitations)
  POST /api/teams/<owner>/<course>/<term>/add       { email, role }        instructors
  POST /api/teams/<owner>/<course>/<term>/role      { user, role }         instructors
  POST /api/teams/<owner>/<course>/<term>/remove    { user }               instructors; anyone: themselves
  POST /api/teams/<owner>/<course>/<term>/uninvite  { id }                 instructors
  POST /api/teams/join/check   { token }                     what it's for, and whether to sign in or make an account
  POST /api/teams/join         { token }                     (signed in, as that email) join
  POST /api/teams/join/create  { token, name, handle, password }   make the account and join
"""
import json
import os
import re
import time

from flask import Blueprint, g, jsonify, make_response

from . import db, mailer, security as sec
from .auth import (Refusal, _EMAIL, body, handle_problem, handles, limit, limiter, link_base, log, need_https, norm_email,
                   signed_in, start_session, suggest_handle, text, user_json, pages_base)

teams_bp = Blueprint("teams", __name__)

ROLES = ("coordinator", "instructor", "ta", "staff")
LEAD = ("owner", "coordinator")   # who may do everything with an offering (and change its team)
ROLE_NAME = {"owner": "owner", "coordinator": "coordinator", "instructor": "instructor", "ta": "TA", "staff": "staff"}
A_ROLE = {"coordinator": "a coordinator", "instructor": "an instructor", "ta": "a TA", "staff": "staff"}
_SLUG = re.compile(r"^[\w.-]{1,64}$")


def offering_of(path):
    """A file's course offering (its first two folders), or None for a file outside any."""
    parts = str(path).split("/")
    return "/".join(parts[:2]) if len(parts) >= 3 else None


def clean_offering(o):
    parts = str(o or "").strip("/").split("/")
    if len(parts) != 2 or not all(_SLUG.match(p) and p[0] not in "._" for p in parts):
        raise Refusal(400, "Which course offering?")
    return "/".join(parts)


def owner_by_handle(handle):
    u = db.one("SELECT * FROM users WHERE handle = ?", (str(handle or "").lower(),))
    if not u or u["disabled"]:
        raise Refusal(404, "No such course offering.")
    return u


def runs_section(gr, user_id):
    """Whether someone runs a section (groups.json): it lists them (its "people", set on their page in the
    teaching team), or, in an older file, one of its meeting times does."""
    if not isinstance(gr, dict):
        return False
    me = str(user_id)
    if isinstance(gr.get("people"), list):
        return me in [str(p) for p in gr["people"]]
    return any(isinstance(x, dict) and me in [str(p) for p in (x.get("people") or [])] for x in (gr.get("items") or []))


def my_groups(user_id, owner_id, offering):
    """The sections someone runs (groups.json), by id."""
    from .store import Repo
    raw = Repo(owner_id, "priv").read(f"{offering}/groups.json")
    try:
        d = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        d = {}
    out = set()
    for gr in (d.get("groups") if isinstance(d, dict) and isinstance(d.get("groups"), list) else []):
        if runs_section(gr, user_id):
            out.add(str(gr.get("id")))
    return out


def _json(b):
    try:
        return json.loads(b.decode("utf-8")) if b else None
    except (ValueError, UnicodeDecodeError):
        return None


def _gs(x):
    """An activity's or announcement's activity groups (older ones had one, "group")."""
    gs = x.get("groups") if isinstance(x.get("groups"), list) else ([x.get("group")] if x.get("group") else [])
    return [str(g) for g in gs]


def within_groups(path, old, new, mine, lectures=None):
    """An instructor's change to lectures.json or announcements.json: only to the ones for their groups.
    Leaving out every activity (or announcement) for one of `mine`, before and after, nothing else may differ."""
    a, b = _json(old) or {}, _json(new)
    ours_ = lambda gs: bool(gs) and all(x in mine for x in gs)   # for their groups only (not everyone's, or others' too)
    if not isinstance(b, dict):
        return False
    if path.endswith("/lectures.json"):
        def rest(d):
            ws = []
            for w in (d.get("weeks") if isinstance(d.get("weeks"), list) else []):
                if isinstance(w, dict):
                    # (an activity's label and type are its numbering: adding one renumbers the others)
                    ws.append({**w, "cards": [{k: v for k, v in c.items() if k not in ("label", "kind")} if isinstance(c, dict) else c
                                              for c in (w.get("cards") or []) if not (isinstance(c, dict) and ours_(_gs(c)))]})
            return {**d, "weeks": ws}
        return json.dumps(rest(a), sort_keys=True) == json.dumps(rest(b), sort_keys=True)
    groups = {}   # an announcement about an activity is for that activity's group
    for w in ((lectures or {}).get("weeks") or []):
        for c in ((w or {}).get("cards") or []) if isinstance(w, dict) else []:
            if isinstance(c, dict):
                groups[str(c.get("id"))] = _gs(c)
    def ours(x):
        on = str(x.get("on") or "")
        return ours_(groups.get(on[4:], []) if on.startswith("act:") else _gs(x))
    def rest(d):
        return {**d, "items": [x for x in (d.get("items") if isinstance(d.get("items"), list) else []) if not (isinstance(x, dict) and ours(x))]}
    return json.dumps(rest(a), sort_keys=True) == json.dumps(rest(b), sort_keys=True)


def role_of(viewer_id, owner_id, offering):
    """owner | coordinator | instructor | ta | staff | None."""
    if viewer_id == owner_id:
        return "owner"
    r = db.one("SELECT role FROM members WHERE owner_id = ? AND offering = ? AND user_id = ?", (owner_id, offering, viewer_id))
    return r["role"] if r else None


def roles_in(viewer_id, owner_id):
    """{offering: role} for every offering of owner's that viewer is on the team of."""
    return {r["offering"]: r["role"] for r in db.all_("SELECT offering, role FROM members WHERE owner_id = ? AND user_id = ?", (owner_id, viewer_id))}


# ── What a member may do with the owner's files ──────────────────────
class Access:
    """viewer's access to owner's files (one area: pub or priv)."""
    def __init__(self, viewer_id, owner_id, area):
        self.viewer, self.owner, self.area = viewer_id, owner_id, area
        self.own = viewer_id == owner_id
        self.roles = {} if self.own else roles_in(viewer_id, owner_id)

    def any(self):
        return self.own or bool(self.roles)

    def role(self, path):
        if self.own:
            return "owner"
        o = offering_of(path)
        return self.roles.get(o) if o else None

    def can_read(self, path):
        r = self.role(path)
        if r in LEAD or (r == "staff"):   # staff decide accommodation requests
            return True
        if r in ("instructor", "ta"):   # not the students' accommodation requests (they can hold medical details)
            return not (self.area == "priv" and path.split("/")[2:] == ["accommodations.json"])
        return False

    def can_see_folder(self, path):
        """A folder in the tree: shown if it holds (or is) an offering the viewer may read."""
        if self.own:
            return True
        parts = path.split("/")
        return any(o == path or o.startswith(path + "/") or (len(parts) >= 2 and "/".join(parts[:2]) == o) for o in self.roles)

    def may_upload(self, size):
        """A save's pieces (uploads) into this area: only where the role can write something.
        A TA writes only a gradebook (priv), so only that size of thing."""
        if self.own or any(r in ("coordinator", "instructor") for r in self.roles.values()):
            return
        if self.area == "priv" and "ta" in self.roles.values() and size <= TA_UPLOAD:
            return
        raise Refusal(403, "As staff you can look, but not change anything." if "staff" in self.roles.values() else "As a TA you can only save marks.", "ta")

    def may_change(self, path, deleting=False):
        """Early check, as a save is put together (the full check is check_write, when it lands)."""
        r = self.role(path)
        if r in LEAD:
            return
        o = offering_of(path)
        if r == "ta" and self.area == "priv" and not deleting and path == f"{o}/grades.json":
            return
        if r == "instructor" and ((self.area == "priv" and not deleting and path in (f"{o}/lectures.json", f"{o}/announcements.json"))
                                  or (self.area == "pub" and path.startswith(f"{o}/lectures/"))):
            return
        if r == "instructor":
            raise Refusal(403, "As an instructor you can change your groups' activities and announcements, and nothing else.", "ta")
        if r == "staff":
            raise Refusal(403, "As staff you can look, but not change anything.", "ta")
        raise Refusal(403, "As a TA you can only save marks." if r == "ta" else "You're not on this course offering's teaching team.", "ta" if r == "ta" else "not-member")

    def check_write(self, path, old, new):
        """What to write for this change (old/new: bytes or None): new as it is, or for a TA's gradebook,
        the gradebook as it was with the TA's marks in it. Raises a Refusal if viewer may not change it."""
        r = self.role(path)
        if r in LEAD:
            return new
        o = offering_of(path)
        if r == "instructor":
            if self.area == "pub" and path.startswith(f"{o}/lectures/") and new is not None:
                return new   # an activity's file
            if self.area == "priv" and path in (f"{o}/lectures.json", f"{o}/announcements.json") and new is not None:
                from .store import Repo
                mine = my_groups(self.viewer, self.owner, o)
                lec = _json(Repo(self.owner, "priv").read(f"{o}/lectures.json")) if path.endswith("announcements.json") else None
                if mine and within_groups(path, old, new, mine, lec):
                    return new
                raise Refusal(403, "As an instructor you can change only the activities and announcements for your activity groups "
                                   "(the ones you run an activity of)." if mine else "You don't run an activity in any activity group yet: a coordinator sets that.", "ta")
            raise Refusal(403, "As an instructor you can change your groups' activities and announcements, and nothing else.", "ta")
        if r == "ta" and self.area == "priv" and path == f"{o}/grades.json" and old is not None and new is not None:
            merged = with_marks(old, new)
            if merged is not None:
                return merged
        if r == "staff":
            raise Refusal(403, "As staff you can look, but not change anything.", "ta")
        if r == "ta":
            raise Refusal(403, "As a TA you can enter marks, but not change evaluations, students, settings, exams or the course page. "
                               "Undo those changes (or ask an instructor), then save again.", "ta")
        raise Refusal(403, "You're not on this course offering's teaching team.", "not-member")


TA_UPLOAD = 4 * 1024 * 1024
STATUSES = {"missed", "aiv", "excused", "deferred"}
TA_MAY_CLEAR = 25          # marks a TA's one save may remove (clearing typos), so a TA can't wipe the gradebook


def _mark(m):
    """One mark, as a TA may set it: points, not submitted, a status. Anything else is dropped."""
    if not isinstance(m, dict):
        return None
    out = {}
    p = m.get("pts")
    if isinstance(p, (int, float)) and not isinstance(p, bool) and -1e6 < p < 1e6 and p == p:
        out["pts"] = p
    elif p is None and "pts" in m:
        out["pts"] = None
    if isinstance(m.get("missed"), bool):
        out["missed"] = m["missed"]
    if m.get("status") in STATUSES:
        out["status"] = m["status"]
    return out or None


def with_marks(old, new):
    """The gradebook old, with new's marks (and nothing else of new's), as bytes; None if either isn't one.
    (The Grade Builder tidies a gradebook as it opens it, so a TA's save differs in other ways too, harmlessly;
    taking only the marks is what keeps a TA to marks.) Marks are for the gradebook's own students and
    evaluations; a mark the TA didn't change is kept exactly; a changed one keeps only what a mark has."""
    try:
        a, b = json.loads(old), json.loads(new)
    except ValueError:
        return None
    if not isinstance(a, dict) or not isinstance(b, dict) or not isinstance(b.get("marks"), dict):
        return None
    students = {str(s.get("num")) for s in a.get("students") or [] if isinstance(s, dict)}
    evals = {str(e.get("id")) for e in a.get("evals") or [] if isinstance(e, dict)}
    was = a.get("marks") if isinstance(a.get("marks"), dict) else {}
    marks = {}
    for s, row in b["marks"].items():
        if s not in students or not isinstance(row, dict):
            continue
        before = was.get(s) if isinstance(was.get(s), dict) else {}
        for e, m in row.items():
            if e not in evals:
                continue
            keep = before.get(e) if m == before.get(e) else _mark(m)
            if keep is not None:
                marks.setdefault(s, {})[e] = keep
    gone = sum(1 for s, row in was.items() if isinstance(row, dict) for e in row if e not in marks.get(s, {}))
    if gone > TA_MAY_CLEAR:
        raise Refusal(403, f"That would remove {gone} marks at once. A TA can clear a few marks at a time; ask an instructor for more.", "ta")
    a["marks"] = marks
    return (json.dumps(a, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# ── The API ──────────────────────────────────────────────────────────
def _where(owner, course, term):
    o = owner_by_handle(owner)
    off = clean_offering(f"{course}/{term}")
    role = role_of(g.user["id"], o["id"], off)
    if not role:
        raise Refusal(404, "No such course offering.")
    return o, off, role


def _instructor(role):
    if role not in LEAD:
        raise Refusal(403, "Only the offering's coordinators can change its team.")


def offering_url(owner, off):
    base = link_base()
    return f"{base}#/~{owner['handle']}/{off}" if base else ""


@teams_bp.get("/api/teams/mine")
@signed_in
def mine():
    rows = db.all_("""SELECT m.offering, m.role, u.handle, u.name, u.email FROM members m JOIN users u ON u.id = m.owner_id
                      WHERE m.user_id = ? AND u.disabled = 0 ORDER BY m.offering""", (g.user["id"],))
    return jsonify(shared=[{"owner": r["handle"], "ownerName": r["name"] or r["email"], "offering": r["offering"], "role": r["role"]} for r in rows])


@teams_bp.get("/api/teams/<owner>/<course>/<term>")
@signed_in
def team(owner, course, term):
    o, off, role = _where(owner, course, term)
    people = [{"id": o["id"], "name": o["name"], "email": o["email"], "role": "owner"}]
    people += [{"id": r["id"], "name": r["name"], "email": r["email"], "role": r["role"]} for r in db.all_(
        "SELECT u.id, u.name, u.email, m.role FROM members m JOIN users u ON u.id = m.user_id WHERE m.owner_id = ? AND m.offering = ? ORDER BY m.role, u.name",
        (o["id"], off))]
    invites = []
    if role in LEAD:
        invites = [{"id": r["token_hash"][:16], "email": r["email"], "role": r["role"], "expires": r["expires"]} for r in db.all_(
            "SELECT * FROM team_invites WHERE owner_id = ? AND offering = ? AND used = 0 AND expires > ? ORDER BY created", (o["id"], off, time.time()))]
    return jsonify(you=role, me=g.user["id"], people=people, invites=invites)


JOIN_DAYS = 7
LIMITS = {"add": (30, 3600)}


def offering_exists(owner_id, off):
    """A real course offering: it has a gradebook or a course page."""
    root = db.data_dir()
    c, t = off.split("/")
    return (os.path.isfile(os.path.join(root, "files", str(owner_id), "priv", c, t, "grades.json"))
            or any(os.path.isfile(os.path.join(root, "files", str(owner_id), "pub", c, t, f)) for f in ("course.json", "info.html")))


def new_accounts_allowed(email):
    """May a team invitation make a new account for this email? LECTERN_TEAM_DOMAINS (e.g.
    utoronto.ca,mail.utoronto.ca) limits it to those domains; unset, any email an instructor invites."""
    doms = [d.strip().lower().lstrip("@") for d in os.environ.get("LECTERN_TEAM_DOMAINS", "").split(",") if d.strip()]
    host = email.rsplit("@", 1)[-1].lower()
    return not doms or any(host == d or host.endswith("." + d) for d in doms)


@teams_bp.post("/api/teams/<owner>/<course>/<term>/add")
@signed_in
def add(owner, course, term):
    """Ask someone to join: an email with a link to accept. The same answer whether or not they have an account."""
    o, off, role = _where(owner, course, term)
    _instructor(role)
    if not offering_exists(o["id"], off):
        raise Refusal(409, "Save this offering's gradebook or course page first, then add its team.")
    if not limiter.ok(f"team-add:{g.user['id']}", *LIMITS["add"]):
        raise Refusal(429, "That's a lot of invitations at once. Wait a while, then try again.", "rate")
    d = body()
    email, new_role = norm_email(text(d, "email")), text(d, "role", 20)
    if new_role not in ROLES:
        raise Refusal(400, "Choose coordinator, instructor, TA or staff.")
    if not _EMAIL.match(email):
        raise Refusal(400, "Enter an email address.")
    if email == o["email"] or db.one("SELECT 1 FROM members m JOIN users u ON u.id = m.user_id WHERE m.owner_id = ? AND m.offering = ? AND u.email = ?", (o["id"], off, email)):
        raise Refusal(409, f"{email} is already on this team.")
    base = link_base()
    if not base:
        raise Refusal(503, "Set LECTERN_APP_URL on the server first: links in emails use only that address.")
    tok = sec.new_token()
    with db.transaction() as c:   # a new invitation replaces an earlier one for the same email and offering (only)
        c.execute("DELETE FROM team_invites WHERE owner_id = ? AND offering = ? AND email = ? AND used = 0", (o["id"], off, email))
        c.execute("INSERT INTO team_invites (token_hash, owner_id, offering, email, role, created_by, created, expires) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (sec.token_hash(tok), o["id"], off, email, new_role, g.user["id"], time.time(), time.time() + JOIN_DAYS * 86400))
    link = f"{base}#join={tok}"
    who = g.user["name"] or g.user["email"]
    course_name = off.replace("/", " ").upper()
    emailed = mailer.send_later(email, f"Join the teaching team for {course_name} on Lectern",
                                f"Hello,\n\n{who} ({g.user['email']}) has asked you to join the teaching team for {course_name} on Lectern, "
                                f"as {A_ROLE[new_role]}.\n\nTo accept, open this link within {JOIN_DAYS} days:\n\n{link}\n\n"
                                "If you weren't expecting this, ignore it: nothing happens unless you accept.\n")
    log(g.user["id"], "team-invite", f"{o['handle']}/{off} {email} {new_role}")
    # The link is shown only when it couldn't be emailed (so it can be sent another way).
    return jsonify(ok=True, emailed=emailed, **({} if emailed else {"link": link}))


@teams_bp.post("/api/teams/<owner>/<course>/<term>/role")
@signed_in
def change_role(owner, course, term):
    o, off, role = _where(owner, course, term)
    _instructor(role)
    d = body()
    uid, new_role = int(d.get("user") or 0), text(d, "role", 20)
    if new_role not in ROLES:
        raise Refusal(400, "Choose coordinator, instructor, TA or staff.")
    if db.run("UPDATE members SET role = ? WHERE owner_id = ? AND offering = ? AND user_id = ?", (new_role, o["id"], off, uid)).rowcount != 1:
        raise Refusal(404, "They're not on this team.")
    if new_role != "coordinator":   # their waiting invitations stop working too
        db.run("DELETE FROM team_invites WHERE owner_id = ? AND offering = ? AND created_by = ? AND used = 0", (o["id"], off, uid))
    log(g.user["id"], "team-role", f"{o['handle']}/{off} {uid} {new_role}")
    return jsonify(ok=True)


@teams_bp.post("/api/teams/<owner>/<course>/<term>/remove")
@signed_in
def remove(owner, course, term):
    o, off, role = _where(owner, course, term)
    uid = int(body().get("user") or 0)
    if uid != g.user["id"]:
        _instructor(role)
    if uid == o["id"]:
        raise Refusal(400, "The owner can't be removed: the offering is in their files.")
    if db.run("DELETE FROM members WHERE owner_id = ? AND offering = ? AND user_id = ?", (o["id"], off, uid)).rowcount != 1:
        raise Refusal(404, "They're not on this team.")
    db.run("DELETE FROM team_invites WHERE owner_id = ? AND offering = ? AND created_by = ? AND used = 0", (o["id"], off, uid))
    log(g.user["id"], "team-remove", f"{o['handle']}/{off} {uid}")
    return jsonify(ok=True)


@teams_bp.post("/api/teams/<owner>/<course>/<term>/uninvite")
@signed_in
def uninvite(owner, course, term):
    o, off, role = _where(owner, course, term)
    _instructor(role)
    which = text(body(), "id", 40)
    db.run("DELETE FROM team_invites WHERE substr(token_hash, 1, 16) = ? AND owner_id = ? AND offering = ? AND used = 0", (which, o["id"], off))
    return jsonify(ok=True)


# ── Accepting ────────────────────────────────────────────────────────
def _join_row(tok):
    limit("token")
    r = db.one("SELECT * FROM team_invites WHERE token_hash = ?", (sec.token_hash(tok),)) if tok and len(tok) < 200 else None
    gone = Refusal(410, "That invitation has expired, was already used, or was cancelled. Ask for a new one.", "expired")
    if not r or r["used"] or r["expires"] < time.time():
        raise gone
    # Only while whoever sent it can still add people, as that role, to an offering that's still there.
    sender = role_of(r["created_by"], r["owner_id"], r["offering"])
    owner = db.one("SELECT * FROM users WHERE id = ?", (r["owner_id"],))
    by = db.one("SELECT disabled FROM users WHERE id = ?", (r["created_by"],))
    if sender not in LEAD or not owner or owner["disabled"] or not by or by["disabled"] or not offering_exists(owner["id"], r["offering"]):
        raise gone
    return r, owner


def _claim(c, r, user_id):
    if c.execute("UPDATE team_invites SET used = ? WHERE token_hash = ? AND used = 0", (time.time(), r["token_hash"])).rowcount != 1:
        raise Refusal(410, "That invitation was already used.", "expired")
    c.execute("INSERT INTO members (owner_id, offering, user_id, role, added_by, added) VALUES (?, ?, ?, ?, ?, ?) "
              "ON CONFLICT(owner_id, offering, user_id) DO UPDATE SET role = excluded.role",
              (r["owner_id"], r["offering"], user_id, r["role"], r["created_by"], time.time()))


@teams_bp.post("/api/teams/join/check")
@handles
def join_check():
    """What the invitation is for. (Not whether the email has an account: the page offers both signing in
    and making one, so a link doesn't tell whoever holds it that.)"""
    r, owner = _join_row(text(body(), "token"))
    return jsonify(ok=True, email=r["email"], offering=r["offering"], role=r["role"], owner=owner["handle"],
                   ownerName=owner["name"] or owner["email"], handle=suggest_handle(r["email"]), pages=pages_base(),
                   canCreate=new_accounts_allowed(r["email"]))


@teams_bp.post("/api/teams/join")
@signed_in
def join():
    r, owner = _join_row(text(body(), "token"))
    if g.user["email"] != r["email"]:
        raise Refusal(403, f"This invitation is for {r['email']}. Sign out, then sign in as {r['email']} to accept it.", "other-email")
    if g.user["id"] == owner["id"]:
        raise Refusal(400, "It's your own course offering.")
    with db.transaction() as c:
        _claim(c, r, g.user["id"])
    log(g.user["id"], "team-joined", f"{owner['handle']}/{r['offering']} {r['role']}")
    return jsonify(ok=True, owner=owner["handle"], offering=r["offering"], role=r["role"])


@teams_bp.post("/api/teams/join/create")
@handles
def join_create():
    """No account for that email yet: make one (not an admin), and join."""
    need_https()
    d = body()
    r, owner = _join_row(text(d, "token"))
    name, handle = text(d, "name", 120).strip(), text(d, "handle", 64).strip().lower()
    pw = text(d, "password", sec.MAX_PASSWORD)
    if not name:
        raise Refusal(400, "Enter your name.", "name")
    bad = handle_problem(handle) or sec.password_problem(pw, r["email"], name)
    if bad:
        raise Refusal(400, bad, "weak")
    if not new_accounts_allowed(r["email"]):
        raise Refusal(403, "Lectern isn't taking new accounts for that email address. Ask your Lectern admin.", "domain")
    t = time.time()
    try:
        with db.transaction() as c:
            if c.execute("SELECT 1 FROM users WHERE email = ?", (r["email"],)).fetchone():
                raise Refusal(409, "There's already an account for that email: sign in to accept.", "exists")
            uid = c.execute("INSERT INTO users (email, handle, name, pw_hash, pw_changed, is_admin, created) VALUES (?, ?, ?, ?, ?, 0, ?)",
                            (r["email"], handle, name, sec.hash_password(pw), t, t)).lastrowid
            _claim(c, r, uid)
    except db.sqlite3.IntegrityError:
        raise Refusal(409, "That name is taken. Choose another.", "handle")
    log(uid, "account-created", f"team {owner['handle']}/{r['offering']}")
    u = db.one("SELECT * FROM users WHERE id = ?", (uid,))
    return start_session(make_response(jsonify(ok=True, user=user_json(u), team={"owner": owner["handle"], "offering": r["offering"]})), u)
