"""Each account's files, kept on this server, and its published course pages.

An account has two areas, as it had two repositories on GitHub:

  pub    course pages and their files: published at /p/<handle>/<course>/<term>/info.html
  priv   grades, exams and accommodation requests: only ever seen by the account (and, for
         accommodation requests, by the server on the students' behalf)

The three builders already save with a handful of GitHub's REST calls (list the files, read one,
then blobs → tree → commit → move the branch), so the server answers those same calls, at

  /api/store/<pub|priv>/…     (scope.js sends the builders' calls for "lectern/pub" and "lectern/priv" here)

with the signed-in account's own files. Saving works like GitHub's: a save names the version it
started from, and if something else was saved in between it's refused (422), so two tabs can't
quietly overwrite each other. Every version a save replaces or deletes is kept under
<data dir>/history/, so nothing saved is ever lost.

Files are at <data dir>/files/<account id>/<pub|priv>/<path>. A save's files are written while it
holds the database's write lock (db.transaction), so saves never interleave, even across processes.
"""
import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime, timezone

from flask import Blueprint, Response, abort, g, jsonify, request

from . import db
from .auth import signed_in

store_bp = Blueprint("store", __name__)

REPOS = ("pub", "priv")
BRANCH = "main"
OBJECT_TTL = 86400          # a save's pieces wait this long to be used
MEMBER_PENDING = 32 * 1024 * 1024   # a teaching team member's uploads waiting to be saved, at most
_BAD = re.compile(r'[\x00-\x1f\\:*?"<>|]')


class StoreError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def quota_bytes():
    try:
        return int(float(os.environ.get("LECTERN_QUOTA_MB") or 2048) * 1024 * 1024)
    except ValueError:
        return 2048 * 1024 * 1024


def clean_path(p):
    """A safe relative path (a/b/c.ext), or a StoreError. No .., no hidden files, nothing absolute."""
    p = str(p or "")
    parts = p.split("/")
    if not p or p.startswith("/") or len(p) > 1000 or len(parts) > 12:
        raise StoreError(400, "Bad file name.")
    for s in parts:
        if not s or s in (".", "..") or s.startswith(".") or len(s) > 200 or _BAD.search(s) or s != s.strip():
            raise StoreError(400, f"Bad file name: {p}")
    return "/".join(parts)


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_sha_cache = {}
_sha_lock = threading.Lock()


class Repo:
    def __init__(self, user_id, name):
        if name not in REPOS:
            raise StoreError(404, "Not Found")
        self.uid, self.name = int(user_id), name
        base = db.data_dir()
        self.root = os.path.join(base, "files", str(self.uid), name)
        self.hist = os.path.join(base, "history", str(self.uid), name)

    # ── Reading ──
    def head(self):
        r = db.one("SELECT head FROM repos WHERE user_id = ? AND repo = ?", (self.uid, self.name))
        if r:
            return r["head"]
        h = secrets.token_hex(20)
        db.run("INSERT OR IGNORE INTO repos (user_id, repo, head) VALUES (?, ?, ?)", (self.uid, self.name, h))
        return db.one("SELECT head FROM repos WHERE user_id = ? AND repo = ?", (self.uid, self.name))["head"]

    def _abs(self, path):
        full = os.path.normpath(os.path.join(self.root, *clean_path(path).split("/")))
        if not full.startswith(os.path.normpath(self.root) + os.sep):
            raise StoreError(400, "Bad file name.")
        return full

    def read(self, path):
        try:
            with open(self._abs(path), "rb") as f:
                return f.read()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            return None

    def stat(self, path):
        try:
            st = os.stat(self._abs(path))
        except (FileNotFoundError, NotADirectoryError):
            return None
        return st if os.path.isfile(self._abs(path)) else None

    def sha_of(self, full, st):
        key = (full, st.st_size, st.st_mtime_ns)
        with _sha_lock:
            hit = _sha_cache.get(key)
        if hit:
            return hit
        with open(full, "rb") as f:
            s = blob_sha(f.read())
        with _sha_lock:
            if len(_sha_cache) > 100000:
                _sha_cache.clear()
            _sha_cache[key] = s
        return s

    def walk(self):
        """Every folder and file: GitHub's tree entries."""
        out = []
        if not os.path.isdir(self.root):
            return out
        for d, dirs, files in os.walk(self.root):
            dirs[:] = sorted(x for x in dirs if not x.startswith("."))
            rel = os.path.relpath(d, self.root).replace(os.sep, "/")
            rel = "" if rel == "." else rel
            for x in dirs:
                out.append({"path": f"{rel}/{x}" if rel else x, "mode": "040000", "type": "tree", "sha": "0" * 40})
            for x in sorted(files):
                if x.startswith(".") or x.endswith(".lectern-tmp"):
                    continue
                full = os.path.join(d, x)
                st = os.stat(full)
                out.append({"path": f"{rel}/{x}" if rel else x, "mode": "100644", "type": "blob", "size": st.st_size, "sha": self.sha_of(full, st)})
        return out

    @staticmethod
    def _size(top):
        n = 0
        for d, _, files in os.walk(top):
            for x in files:
                try:
                    n += os.path.getsize(os.path.join(d, x))
                except OSError:
                    pass
        return n

    def pending_bytes(self, uploader=None):
        """Uploads waiting to be saved: the owner's own (uploader None), or one team member's."""
        if uploader is None:
            q = "SELECT COALESCE(SUM(LENGTH(data)), 0) AS n FROM objects WHERE user_id = ? AND kind = 'blob' AND (uploader IS NULL OR uploader = ?)"
            return db.one(q, (self.uid, self.uid))["n"]
        return db.one("SELECT COALESCE(SUM(LENGTH(data)), 0) AS n FROM objects WHERE user_id = ? AND kind = 'blob' AND uploader = ?", (self.uid, uploader))["n"]

    def used_bytes(self):
        """The account's space in use: both areas' files, and uploads waiting to be saved. (Kept old
        versions have their own allowance: see prune_history.)"""
        return self._size(os.path.join(db.data_dir(), "files", str(self.uid))) + self.pending_bytes()

    def check_room(self, grow):
        if quota_bytes() and grow > 0 and self.used_bytes() + grow > quota_bytes():
            raise StoreError(413, f"This would go over your account's space ({quota_bytes() // (1024 * 1024)} MB). Delete something, or ask your Lectern admin for more.")

    def prune_history(self):
        """Old versions are kept up to the same allowance again; past it, the oldest saves' copies go first."""
        top = os.path.join(db.data_dir(), "history", str(self.uid))
        if not quota_bytes() or self._size(top) <= quota_bytes():
            return
        olds = db.all_("SELECT sha, repo FROM commits WHERE user_id = ? ORDER BY at", (self.uid,))
        total = self._size(top)
        for r in olds:
            d = os.path.join(top, r["repo"], r["sha"])
            if os.path.isdir(d):
                total -= self._size(d)
                shutil.rmtree(d, ignore_errors=True)
            if total <= quota_bytes() * 0.9:
                break

    # ── A save's pieces ──
    def put_object(self, kind, data, sha=None, uploader=None):
        """A save's piece. Uploads (blobs) take space: the owner's count against the account's space; a team
        member's against an allowance of their own (MEMBER_PENDING), so they can't fill the owner's.
        A save's tree and commit are tiny (file contents are always blobs), and a delete must always work."""
        db.run("DELETE FROM objects WHERE user_id = ? AND created < ?", (self.uid, time.time() - OBJECT_TTL))
        member = uploader is not None and uploader != self.uid
        if kind == "blob":
            if member:
                if self.pending_bytes(uploader) + len(data) > MEMBER_PENDING:
                    raise StoreError(413, "Too much waiting to be saved. Save (or wait a day), then try again.")
            else:
                self.check_room(len(data))
        elif len(data) > 2 * 1024 * 1024:
            raise StoreError(413, "That save is too big.")
        sha = sha or hashlib.sha1(kind.encode() + b"\0" + data + secrets.token_bytes(8)).hexdigest()
        db.run("INSERT OR REPLACE INTO objects (user_id, repo, sha, kind, data, created, uploader) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (self.uid, self.name, sha, kind, data, time.time(), uploader if member else None))
        return sha

    def get_object(self, kind, sha):
        r = db.one("SELECT data FROM objects WHERE user_id = ? AND repo = ? AND sha = ? AND kind = ?", (self.uid, self.name, str(sha), kind))
        return bytes(r["data"]) if r else None

    # ── Saving ──
    def commit(self, changes, message, parent, author="", force=False, check=None):
        """Write changes ({path: bytes, or None to delete}) as one save on top of `parent`.
        Returns the new head, or raises StoreError(422) if something else was saved since `parent`."""
        changes = {clean_path(p): v for p, v in changes.items()}
        with db.transaction() as c:
            head = self.head()
            if parent != head and not force:
                raise StoreError(422, "Update is not a fast forward")
            if check:   # check(path, current bytes or None, new bytes or None) → what to write; raises to refuse
                changes = {p: check(p, self.read(p), v) for p, v in changes.items()}
            # Only growth is checked (a save that frees space always works); its uploads already counted.
            grow = sum((len(v) if v is not None else 0) - (self.stat(p).st_size if self.stat(p) else 0) for p, v in changes.items())
            if quota_bytes() and grow > 0 and self.used_bytes() - self.pending_bytes() + grow > quota_bytes():
                raise StoreError(413, f"This would go over your account's space ({quota_bytes() // (1024 * 1024)} MB). Delete something, or ask your Lectern admin for more.")
            new = secrets.token_hex(20)
            for p, v in changes.items():
                full = self._abs(p)
                if os.path.isfile(full):          # keep the version being replaced or deleted
                    keep = os.path.join(self.hist, new, *p.split("/"))
                    os.makedirs(os.path.dirname(keep), exist_ok=True)
                    shutil.copy2(full, keep)
                if v is None:
                    if os.path.isfile(full):
                        os.remove(full)
                        self._prune(os.path.dirname(full))
                    continue
                if os.path.isdir(full):
                    raise StoreError(422, f"{p} is a folder.")
                os.makedirs(os.path.dirname(full), exist_ok=True)
                tmp = full + ".lectern-tmp"
                with open(tmp, "wb") as f:
                    f.write(v)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, full)
            c.execute("UPDATE repos SET head = ? WHERE user_id = ? AND repo = ?", (new, self.uid, self.name))
            c.execute("INSERT INTO commits (sha, user_id, repo, parent, message, author, at, paths) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (new, self.uid, self.name, head, str(message or "")[:500], author, time.time(), json.dumps(sorted(changes))))
            c.execute("DELETE FROM objects WHERE user_id = ? AND repo = ? AND created < ?", (self.uid, self.name, time.time() - OBJECT_TTL))
        self.prune_history()
        return new

    def _prune(self, d):
        root = os.path.normpath(self.root)
        while os.path.normpath(d).startswith(root + os.sep):
            try:
                os.rmdir(d)
            except OSError:
                return
            d = os.path.dirname(d)

    # For the server's own use (accommodation requests): read a text file, and write it if it hasn't changed.
    def read_text(self, path):
        b = self.read(path)
        return (b.decode("utf-8"), blob_sha(b)) if b is not None else (None, None)

    def write_text(self, path, text, sha, message, author=""):
        """True, or False when the file changed since `sha` was read (or appeared, when sha is None)."""
        try:
            with db.transaction():
                cur = self.read(path)
                if (blob_sha(cur) if cur is not None else None) != sha:
                    return False
                self.commit({path: text.encode("utf-8")}, message, self.head(), author)
            return True
        except StoreError as e:
            if e.status == 422:
                return False
            raise


# ── The builders' GitHub calls ───────────────────────────────────────
def _gh(status, message):
    return jsonify(message=message), status


def _info(name, head):
    return {"full_name": f"lectern/{name}", "name": name, "private": name == "priv", "default_branch": BRANCH,
            "owner": {"login": "lectern"}, "permissions": {"push": True}, "head": head}


def open_area(name):
    """The store's address names an area: "pub"/"priv" (your own), or "<handle>.pub"/"<handle>.priv"
    (someone else's, for the offerings you're on the teaching team of). → (Repo, Access)"""
    from .teams import Access
    handle, _, area = name.rpartition(".")
    if area not in REPOS:
        raise StoreError(404, "Not Found")
    if handle:
        u = db.one("SELECT id, disabled FROM users WHERE handle = ?", (handle.lower(),))
        if not u or u["disabled"]:
            raise StoreError(404, "Not Found")
        owner = u["id"]
    else:
        owner = g.user["id"]
    acc = Access(g.user["id"], owner, area)
    if not acc.any():
        raise StoreError(404, "Not Found")
    return Repo(owner, area), acc


@store_bp.route("/api/store/<name>", defaults={"rest": ""}, methods=["GET"])
@store_bp.route("/api/store/<name>/<path:rest>", methods=["GET", "POST", "PATCH"])
@signed_in
def api(name, rest):
    from .auth import Refusal
    try:
        repo, acc = open_area(name)
        return _dispatch(repo, acc, request.method, rest.strip("/"))
    except StoreError as e:
        return _gh(e.status, str(e))
    except Refusal as e:
        return _gh(e.status, str(e))


def _member_rate():
    from .auth import limiter
    if not limiter.ok(f"member-save:{g.user['id']}", 600, 3600):
        raise StoreError(429, "Too many saves at once. Wait a while, then try again.")


def _body():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        raise StoreError(400, "Problems parsing JSON")
    return d


def _dispatch(repo, acc, m, rest):
    head = repo.head()
    if rest == "" and m == "GET":
        return jsonify(_info(repo.name, head))
    if m == "GET" and rest.startswith("branches/"):
        if rest[len("branches/"):] != BRANCH:
            raise StoreError(404, "Branch not found")
        return jsonify(name=BRANCH, commit={"sha": head})
    if m == "GET" and (rest.startswith("git/ref/heads/") or rest.startswith("git/refs/heads/")):
        if rest.rsplit("/", 1)[1] != BRANCH:
            raise StoreError(404, "Not Found")
        return jsonify(ref=f"refs/heads/{BRANCH}", object={"sha": head, "type": "commit"})
    if m == "GET" and rest.startswith("git/commits/"):
        sha = rest.split("/", 2)[2]
        return jsonify(sha=sha, tree={"sha": sha}, parents=[])
    if m == "GET" and rest.startswith("git/trees/"):
        tree = [e for e in repo.walk() if (acc.can_read(e["path"]) if e["type"] == "blob" else acc.can_see_folder(e["path"]))]
        return jsonify(sha=head, tree=tree, truncated=False)
    if m == "GET" and rest.startswith("contents/"):
        path = clean_path(rest[len("contents/"):])
        data = repo.read(path) if acc.can_read(path) else None
        if data is None:
            raise StoreError(404, "Not Found")
        return jsonify(type="file", path=path, name=path.rsplit("/", 1)[-1], size=len(data), sha=blob_sha(data),
                       encoding="base64", content=base64.b64encode(data).decode())
    if m == "GET" and rest == "commits":
        p = request.args.get("path", "")
        st = repo.stat(p) if p and acc.can_read(p) else None
        if p and not st:
            return jsonify([])
        r = db.one("SELECT * FROM commits WHERE user_id = ? AND repo = ? ORDER BY at DESC LIMIT 1", (repo.uid, repo.name)) if acc.own else None
        at = st.st_mtime if st else (r["at"] if r else time.time())
        return jsonify([{"sha": head, "commit": {"message": (r["message"] if r else ""), "committer": {"date": _iso(at)}, "author": {"date": _iso(at)}}}])
    if m == "POST" and rest == "git/blobs":
        d = _body()
        content = d.get("content")
        if not isinstance(content, str):
            raise StoreError(422, "Invalid request")
        if d.get("encoding") == "base64":
            try:
                data = base64.b64decode(content, validate=False)
            except Exception:
                raise StoreError(422, "Bad base64")
        else:
            data = content.encode("utf-8")
        if not acc.own:   # a teaching team member: uploads only where their role can write
            acc.may_upload(len(data))
            _member_rate()
        sha = blob_sha(data)
        repo.put_object("blob", data, sha, uploader=g.user["id"])
        return jsonify(sha=sha, url=""), 201
    if m == "POST" and rest == "git/trees":
        entries = _body().get("tree")
        if not isinstance(entries, list) or len(entries) > 5000:
            raise StoreError(422, "Invalid tree")
        if not acc.own:
            _member_rate()
        clean = []
        for e in entries:
            if not isinstance(e, dict):
                raise StoreError(422, "Invalid tree")
            path, sha, content = clean_path(e.get("path")), e.get("sha"), e.get("content")
            if not acc.own:
                acc.may_change(path, deleting=sha is None and content is None)
            if content is not None:   # a file's text given inline: an upload like any other (same limits)
                data = str(content).encode("utf-8")
                if not acc.own:
                    acc.may_upload(len(data))
                sha = blob_sha(data)
                repo.put_object("blob", data, sha, uploader=g.user["id"])
            clean.append({"path": path, "sha": sha})
        return jsonify(sha=repo.put_object("tree", json.dumps(clean).encode(), uploader=g.user["id"])), 201
    if m == "POST" and rest == "git/commits":
        if not acc.own:
            _member_rate()
        d = _body()
        parents = d.get("parents") or []
        if not isinstance(parents, list) or len(parents) != 1:
            raise StoreError(422, "A save has one parent")
        if repo.get_object("tree", d.get("tree")) is None:
            raise StoreError(422, "Tree not found")
        c = {"tree": d.get("tree"), "parent": str(parents[0]), "message": str(d.get("message") or "")}
        return jsonify(sha=repo.put_object("commit", json.dumps(c).encode()), html_url=""), 201
    if m == "PATCH" and rest.startswith("git/refs/heads/"):
        if rest.rsplit("/", 1)[1] != BRANCH:
            raise StoreError(404, "Not Found")
        d = _body()
        raw = repo.get_object("commit", d.get("sha"))
        if raw is None:
            raise StoreError(422, "Commit not found")
        c = json.loads(raw)
        tree = json.loads(repo.get_object("tree", c["tree"]) or b"[]")
        current = {e["sha"]: e["path"] for e in repo.walk() if e["type"] == "blob" and acc.can_read(e["path"])}
        changes = {}
        for e in tree:
            if e.get("content") is not None:
                changes[e["path"]] = str(e["content"]).encode("utf-8")
            elif e.get("sha") is None:
                changes[e["path"]] = None
            else:
                data = repo.get_object("blob", e["sha"])
                if data is None and e["sha"] in current:      # an existing file, by its sha (a copy)
                    data = repo.read(current[e["sha"]])
                if data is None:
                    raise StoreError(422, f"Blob not found for {e['path']}")
                changes[e["path"]] = data
        # A teaching team member: only what their role allows (teams.py), checked inside the save's lock.
        check = None if acc.own else acc.check_write
        new = repo.commit(changes, c["message"], c["parent"], g.user["email"], bool(d.get("force")) and acc.own, check=check)
        used = [d.get("sha"), c["tree"]] + [e["sha"] for e in tree if e.get("sha")]   # the save's pieces: done with
        for k in range(0, len(used), 400):
            part = used[k:k + 400]
            db.run(f"DELETE FROM objects WHERE user_id = ? AND repo = ? AND sha IN ({','.join('?' * len(part))})", (repo.uid, repo.name, *part))
        return jsonify(ref=f"refs/heads/{BRANCH}", object={"sha": new, "type": "commit"})
    raise StoreError(404, f"Not available: {m} {rest}")


# ── Published course pages ───────────────────────────────────────────
# A page is the account's own HTML, served from Lectern's address. So it can't act as Lectern (use a
# signed-in teacher's cookie, read Lectern's pages), it's served in a sandbox: its scripts run, but in an
# origin of their own, with no cookies or storage of Lectern's. (Or serve them from a different
# address altogether: LECTERN_PAGES_URL.)
PAGE_CSP = "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms allow-downloads allow-modals"


@store_bp.get("/p/<handle>/", defaults={"sub": ""})
@store_bp.get("/p/<handle>/<path:sub>")
def published(handle, sub):
    u = db.one("SELECT id, disabled FROM users WHERE handle = ?", (str(handle).lower(),))
    if not u or u["disabled"]:
        abort(404)
    if sub == "" or sub.endswith("/"):
        sub += "index.html"
    try:
        path = clean_path(sub)
    except StoreError:
        abort(404)
    data = Repo(u["id"], "pub").read(path)
    if data is None:
        abort(404)
    mt = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if mt.startswith("text/") or mt in ("application/javascript", "application/json", "image/svg+xml"):
        mt += "; charset=utf-8"
    resp = Response(data, headers={"Content-Type": mt})
    resp.headers["Content-Security-Policy"] = PAGE_CSP
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    resp.set_etag(blob_sha(data))
    return resp.make_conditional(request)
