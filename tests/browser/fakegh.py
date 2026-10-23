"""The browser walkthroughs were written against a fake GitHub. Lectern now keeps everything on its own
server, so this keeps their shape and runs them against the real thing (harness.Server, one per process):

    gh = FakeGitHub()                                       # a fresh account (chandra@utoronto.ca, an admin)
    gh.add(Repo("chandra-gummaluru/courses-private", True, {...}))   # → its private files ("priv")
    gh.add(Repo("chandra-gummaluru/courses", False, {...}))          # → its public files ("pub")
    gh.attach(ctx)                                          # the browser context is signed in
    page.goto(BASE + "#/csc258/f26/course")
    gh.repos[PRIV].commits[gh.repos[PRIV].head]["files"]   # what's saved now

A repository whose name ends in -private is the private files; the first other one is the public files
(any more are ignored).
"""
import os
import shutil
import time

from harness import Server

_srv = None


def server():
    global _srv
    if _srv is None:
        _srv = Server().__enter__()
    return _srv


BASE = server().base


class Repo:
    def __init__(self, full, private, files=None):
        self.full, self.private, self.files = full, private, dict(files or {})


class _View:
    """gh.repos[name]: .head and .commits[head]["files"] (what's saved now), .log (save messages)."""
    def __init__(self, gh, area):
        self.gh, self.area = gh, area
        self.head = "now"

    @property
    def commits(self):
        return {"now": {"files": server().files(self.area)}}

    @property
    def log(self):
        from server import db
        return [r["message"] for r in db.all_("SELECT message FROM commits WHERE user_id = ? AND repo = ? ORDER BY at", (server().user["id"], self.area))]


class FakeGitHub:
    def __init__(self):
        from server import db
        srv = server()
        db.run("DELETE FROM users")
        shutil.rmtree(os.path.join(srv.dir, "files"), ignore_errors=True)
        srv.account()
        self.repos, self.calls, self._pub = {}, [], None

    def add(self, repo):
        area = "priv" if repo.full.lower().endswith("-private") else "pub"
        if area == "pub":
            if self._pub:
                return
            self._pub = repo.full
        files = {p: v for p, v in repo.files.items() if not p.startswith(".")}
        if files:
            server().put(area, files)
        self.repos[repo.full] = _View(self, area)

    def attach(self, ctx):
        """Sign the browser context in: a session for the account, as its cookie."""
        from server import db, security
        tok = security.new_token()
        t = time.time()
        db.run("INSERT INTO sessions (id_hash, user_id, created, last_seen, expires) VALUES (?, ?, ?, ?, ?)",
               (security.token_hash(tok), server().user["id"], t, t, t + 86400))
        ctx.add_cookies([{"name": "lectern_session", "value": tok, "url": BASE, "httpOnly": True, "sameSite": "Lax"}])
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())

    def handle(self, route):
        raise RuntimeError("Lectern no longer calls GitHub: use gh.attach(ctx) instead of ctx.route(..., gh.handle)")
