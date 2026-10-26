"""Discussions on the course page: posts (a title and a body) on an evaluation, an activity or an announcement,
with nested comments, upvotes (no downvotes), and the teaching team's pins, endorsements and removals.

Only people in the course take part: students signed in to the course page (students.py), and the offering's
teaching team signed in to Lectern. A student posts under their name, or anonymous to classmates: then
classmates see their course alias ("Anonymous Heron", the same in every discussion of the course) and the
teaching team sees who it is.

  GET  /api/hub/<handle>/<course>/<term>/discussion?t=<target>     a discussion: its posts and comments, as this viewer sees them
  GET  /api/hub/<handle>/<course>/<term>/discussion/counts         {target: posts} for the whole course page
  POST /api/hub/<handle>/<course>/<term>/discussion                { t, parent?, title?, body, anon? }
  POST /api/hub/<handle>/<course>/<term>/discussion/<id>/vote      { on }
  POST /api/hub/<handle>/<course>/<term>/discussion/<id>/moderate  { pin? | endorse? | remove? }   the teaching team
  POST /api/hub/<handle>/<course>/<term>/discussion/<id>/delete    its author

A target is "eval:<id>", "act:<id>" or "ann:<id>". Bodies are plain text, with mentions written as tokens the
server turns into each viewer's names: @{p:<post id>} (whoever wrote that post, as they wrote it: by name or
anonymously), @{u:<user id>} (someone on the teaching team) and @{s:<student number>} (a student, by name: only
the teaching team writes these, and a classmate who's anonymous in the discussion is shown by their alias).
"""
import random
import re
import time

from flask import Blueprint, jsonify, request

from . import db
from .auth import Refusal, body, current, handles, limiter, text

discuss_bp = Blueprint("discuss", __name__)

STAFF = {"owner", "coordinator", "instructor", "ta", "staff"}
ROLE = {"owner": "Instructor", "coordinator": "Coordinator", "instructor": "Instructor", "ta": "TA", "staff": "Staff"}
_TARGET = re.compile(r"^(eval|act|ann):[\w.:-]{1,80}$")
_TOKEN = re.compile(r"@\{([pus]):([\w.@+-]{1,120})\}")
MAX_TITLE, MAX_BODY = 200, 10000
ANIMALS = ("Heron", "Otter", "Lynx", "Fox", "Owl", "Badger", "Wren", "Marten", "Hare", "Finch", "Beaver", "Crane", "Ibis",
           "Lark", "Puffin", "Raven", "Seal", "Stoat", "Swift", "Tern", "Vole", "Wolf", "Yak", "Bison", "Cougar", "Dingo",
           "Egret", "Gecko", "Hawk", "Koala", "Lemur", "Moose", "Newt", "Ocelot", "Panda", "Quail", "Robin", "Sparrow",
           "Tapir", "Urchin", "Viper", "Walrus", "Zebra", "Alpaca", "Bobcat", "Cardinal", "Dolphin", "Falcon", "Gazelle")


# ── Who's looking ────────────────────────────────────────────────────
def _viewer(handle, course, term):
    """(owner, offering, viewer): someone on the teaching team, or a signed-in student; else a Refusal."""
    from .students import _offering, roster, student_of
    from .teams import role_of
    o, off = _offering(handle, course, term)
    u, _ = current()
    role = role_of(u["id"], o["id"], off) if u else None
    if role in STAFF:
        return o, off, {"kind": "staff", "key": f"u:{u['id']}", "id": str(u["id"]), "name": u["name"] or u["email"], "role": role}
    email = student_of(o["id"], off)
    if not email:
        raise Refusal(401, "Sign in to the course page to see its discussions.", "signed-out")
    s = roster(o["id"], off).get(email) or {}
    return o, off, {"kind": "student", "key": f"s:{email}", "id": email, "num": s.get("num", ""), "name": _name(s) or email}


def _key(row):
    """Whose a post is, as a voter key: "s:<email>" or "u:<user id>"."""
    return ("u:" if row["author_kind"] == "staff" else "s:") + row["author"]


def _name(s):
    return " ".join(x for x in (s.get("first"), s.get("last")) if x).strip()


def _people(o, off):
    """Who's in the course: students by email ({num, name}), and the teaching team by user id ({name, role})."""
    from .students import roster
    students = {e: {"num": s.get("num", ""), "name": _name(s) or e} for e, s in roster(o["id"], off).items()}
    team = {str(o["id"]): {"name": o["name"] or o["handle"], "role": "owner"}}
    for r in db.all_("SELECT u.id, u.name, u.email, m.role FROM members m JOIN users u ON u.id = m.user_id WHERE m.owner_id = ? AND m.offering = ?", (o["id"], off)):
        team[str(r["id"])] = {"name": r["name"] or r["email"], "role": r["role"]}
    return students, team


def alias_of(owner_id, off, email):
    """A student's anonymous name in this course: made once ("Anonymous <animal>"), then kept."""
    r = db.one("SELECT alias FROM discussion_aliases WHERE owner_id = ? AND offering = ? AND email = ?", (owner_id, off, email))
    if r:
        return r["alias"]
    taken = {x["alias"] for x in db.all_("SELECT alias FROM discussion_aliases WHERE owner_id = ? AND offering = ?", (owner_id, off))}
    free = [f"Anonymous {a}" for a in ANIMALS if f"Anonymous {a}" not in taken]
    alias = random.choice(free) if free else f"Anonymous {random.choice(ANIMALS)} {len(taken) + 1}"
    with db.transaction() as c:
        c.execute("INSERT OR IGNORE INTO discussion_aliases (owner_id, offering, email, alias) VALUES (?, ?, ?, ?)", (owner_id, off, email, alias))
    return db.one("SELECT alias FROM discussion_aliases WHERE owner_id = ? AND offering = ? AND email = ?", (owner_id, off, email))["alias"]


# ── A discussion, as this viewer sees it ─────────────────────────────
def _who(o, off, row, viewer, students, team, aliases):
    """How a post's author shows to the viewer: {name, real?, anon, team, role?, you}."""
    you = _key(row) == viewer["key"]
    if row["author_kind"] == "staff":
        t = team.get(row["author"]) or {"name": "The teaching team", "role": "staff"}
        return {"name": t["name"], "team": True, "role": ROLE.get(t["role"], "Staff"), "anon": False, "you": you}
    s = students.get(row["author"]) or {"name": "A student"}
    if row["anon"]:
        a = aliases.get(row["author"]) or alias_of(o["id"], off, row["author"])
        return {"name": a, "anon": True, "team": False, "you": you, **({"real": s["name"]} if viewer["kind"] == "staff" else {})}
    return {"name": s["name"], "anon": False, "team": False, "you": you}


def _names(o, off, rows, viewer, students, team, aliases):
    """The text each mention token in these posts shows to the viewer."""
    by_id = {r["id"]: r for r in rows}
    out = {}
    for r in rows:
        for k, v in _TOKEN.findall(r["body"]):
            tok = f"{k}:{v}"
            if tok in out:
                continue
            if k == "p":
                p = by_id.get(int(v)) if v.isdigit() else None
                if not p:
                    p = db.one("SELECT * FROM discussion_posts WHERE id = ? AND owner_id = ? AND offering = ?", (int(v), o["id"], off)) if v.isdigit() else None
                if p:
                    w = _who(o, off, p, viewer, students, team, aliases)
                    out[tok] = {"name": w["name"], **({"real": w["real"]} if w.get("real") else {})}
            elif k == "u" and v in team:
                out[tok] = {"name": team[v]["name"]}
            elif k == "s":
                e = next((e for e, s in students.items() if s["num"] == v), None)
                if e:
                    # A classmate anonymous in this discussion is shown to students by their alias.
                    anon_here = any(r2["author"] == e and r2["anon"] for r2 in rows) and not any(r2["author"] == e and not r2["anon"] for r2 in rows)
                    if anon_here and viewer["kind"] != "staff":
                        out[tok] = {"name": aliases.get(e) or alias_of(o["id"], off, e)}
                    else:
                        out[tok] = {"name": students[e]["name"]}
    return out


def _thread(o, off, target, viewer):
    rows = db.all_("SELECT * FROM discussion_posts WHERE owner_id = ? AND offering = ? AND target = ? ORDER BY created", (o["id"], off, target))
    students, team = _people(o, off)
    aliases = {r["email"]: r["alias"] for r in db.all_("SELECT email, alias FROM discussion_aliases WHERE owner_id = ? AND offering = ?", (o["id"], off))}
    votes = {}
    for v in db.all_("SELECT post_id, voter FROM discussion_votes WHERE post_id IN (SELECT id FROM discussion_posts WHERE owner_id = ? AND offering = ? AND target = ?)", (o["id"], off, target)):
        votes.setdefault(v["post_id"], []).append(v["voter"])
    staff = viewer["kind"] == "staff"
    posts = []
    for r in rows:
        gone = bool(r["removed_by"]) or bool(r["deleted"])
        p = {"id": r["id"], "parent": r["parent_id"], "at": r["created"], "votes": len(votes.get(r["id"], [])), "voted": viewer["key"] in votes.get(r["id"], []),
             "pinned": bool(r["pinned"]), "endorsed": (team.get(r["endorsed_by"]) or {}).get("name", "") if r["endorsed_by"] else "",
             "removed": bool(r["removed_by"]), "deleted": bool(r["deleted"])}
        if gone and not staff:   # what's left of it: its place in the thread (its comments stay)
            p.update(title="", body="", who=None)
        else:
            p.update(title=r["title"], body=r["body"], who=_who(o, off, r, viewer, students, team, aliases))
        posts.append(p)
    names = _names(o, off, rows, viewer, students, team, aliases)
    me = {"kind": viewer["kind"], "name": viewer["name"], **({"alias": alias_of(o["id"], off, viewer["id"])} if viewer["kind"] == "student" else {"role": ROLE.get(viewer["role"], "Staff")})}
    # Who can be mentioned: the teaching team, and (for the teaching team) every student by name.
    people = [{"tok": f"u:{k}", "name": t["name"], "role": ROLE.get(t["role"], "Staff")} for k, t in team.items()]
    if staff:
        people += [{"tok": f"s:{s['num']}", "name": s["name"]} for s in students.values() if s["num"]]
    return {"posts": posts, "names": names, "me": me, "people": people}


def _target(t):
    t = str(t or "").strip()
    if not _TARGET.match(t):
        raise Refusal(400, "That isn't something that can have a discussion.")
    return t


@discuss_bp.get("/api/hub/<handle>/<course>/<term>/discussion")
@handles
def thread(handle, course, term):
    o, off, viewer = _viewer(handle, course, term)
    return jsonify(_thread(o, off, _target(request.args.get("t")), viewer))


@discuss_bp.get("/api/hub/<handle>/<course>/<term>/discussion/counts")
@handles
def counts(handle, course, term):
    o, off, viewer = _viewer(handle, course, term)
    rows = db.all_("SELECT target, COUNT(*) AS n FROM discussion_posts WHERE owner_id = ? AND offering = ? AND parent_id IS NULL AND removed_by = '' AND deleted = 0 GROUP BY target", (o["id"], off))
    return jsonify(counts={r["target"]: r["n"] for r in rows})


def _clean(t, viewer, students):
    """What was written: plain text; mention tokens kept only if this viewer may write them."""
    t = str(t or "").replace("\r\n", "\n").strip()

    def keep(m):
        k, v = m.group(1), m.group(2)
        if k == "s" and viewer["kind"] != "staff":
            return ""
        return m.group(0)
    return _TOKEN.sub(keep, t)


@discuss_bp.post("/api/hub/<handle>/<course>/<term>/discussion")
@handles
def post(handle, course, term):
    o, off, viewer = _viewer(handle, course, term)
    d = body()
    target = _target(d.get("t"))
    if not limiter.ok(f"discuss:{viewer['key']}", 30, 600):
        raise Refusal(429, "That's a lot of posts. Wait a few minutes, then try again.", "rate")
    parent = d.get("parent")
    if parent is not None:
        p = db.one("SELECT * FROM discussion_posts WHERE id = ? AND owner_id = ? AND offering = ? AND target = ?", (int(parent) if str(parent).isdigit() else -1, o["id"], off, target))
        if not p:
            raise Refusal(404, "That post isn't there any more.")
        parent = p["id"]
    title = text(d, "title", MAX_TITLE + 50).strip() if parent is None else ""
    msg = _clean(text(d, "body", MAX_BODY + 500), viewer, None)
    if parent is None and not title:
        raise Refusal(400, "Give your post a title.")
    if not msg:
        raise Refusal(400, "Write something first.")
    if len(title) > MAX_TITLE or len(msg) > MAX_BODY:
        raise Refusal(400, f"That's too long: a title up to {MAX_TITLE} characters, and up to {MAX_BODY} in all.")
    anon = 1 if viewer["kind"] == "student" and d.get("anon") else 0
    kind = "staff" if viewer["kind"] == "staff" else "student"
    with db.transaction() as c:
        pid = c.execute("""INSERT INTO discussion_posts (owner_id, offering, target, parent_id, author_kind, author, anon, title, body, created)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (o["id"], off, target, parent, kind, viewer["id"], anon, title, msg, time.time())).lastrowid
    if anon:
        alias_of(o["id"], off, viewer["id"])
    return jsonify(id=pid, **_thread(o, off, target, viewer)), 201


def _post(o, off, pid):
    p = db.one("SELECT * FROM discussion_posts WHERE id = ? AND owner_id = ? AND offering = ?", (pid, o["id"], off))
    if not p:
        raise Refusal(404, "That post isn't there any more.")
    return p


@discuss_bp.post("/api/hub/<handle>/<course>/<term>/discussion/<int:pid>/vote")
@handles
def vote(handle, course, term, pid):
    o, off, viewer = _viewer(handle, course, term)
    p = _post(o, off, pid)
    if body().get("on"):
        db.run("INSERT OR IGNORE INTO discussion_votes (post_id, voter) VALUES (?, ?)", (pid, viewer["key"]))
    else:
        db.run("DELETE FROM discussion_votes WHERE post_id = ? AND voter = ?", (pid, viewer["key"]))
    return jsonify(_thread(o, off, p["target"], viewer))


@discuss_bp.post("/api/hub/<handle>/<course>/<term>/discussion/<int:pid>/moderate")
@handles
def moderate(handle, course, term, pid):
    o, off, viewer = _viewer(handle, course, term)
    if viewer["kind"] != "staff":
        raise Refusal(403, "Only the teaching team can do that.")
    p, d = _post(o, off, pid), body()
    if "pin" in d:
        if p["parent_id"] is not None:
            raise Refusal(400, "Only posts can be pinned, not comments.")
        db.run("UPDATE discussion_posts SET pinned = ? WHERE id = ?", (1 if d["pin"] else 0, pid))
    if "endorse" in d:
        db.run("UPDATE discussion_posts SET endorsed_by = ? WHERE id = ?", (viewer["id"] if d["endorse"] else "", pid))
    if "remove" in d:
        db.run("UPDATE discussion_posts SET removed_by = ? WHERE id = ?", (viewer["id"] if d["remove"] else "", pid))
    return jsonify(_thread(o, off, p["target"], viewer))


@discuss_bp.post("/api/hub/<handle>/<course>/<term>/discussion/<int:pid>/delete")
@handles
def delete(handle, course, term, pid):
    o, off, viewer = _viewer(handle, course, term)
    p = _post(o, off, pid)
    if _key(p) != viewer["key"]:
        raise Refusal(403, "You can delete only your own posts.")
    db.run("UPDATE discussion_posts SET deleted = 1 WHERE id = ?", (pid,))
    return jsonify(_thread(o, off, p["target"], viewer))
