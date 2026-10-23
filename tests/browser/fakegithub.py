"""A small in-memory GitHub API, for the builders on their own (/tools/<name>.html still talk to GitHub). Playwright: page.route."""
import base64, hashlib, json, re, time
from urllib.parse import urlparse, parse_qs, unquote


def sha(s):
    return hashlib.sha1((s if isinstance(s, bytes) else s.encode()) + str(time.time_ns()).encode()).hexdigest()


class Repo:
    def __init__(self, full, private, files=None):
        self.full, self.private = full, private
        self.files = dict(files or {})
        self.blobs = {}
        self.trees = {}
        self.commits = {}
        self.head = self._commit(dict(self.files), "init")
        self.log = []

    def _commit(self, files, msg):
        t = sha("t"); self.trees[t] = dict(files)
        c = sha("c"); self.commits[c] = {"tree": t, "files": dict(files), "msg": msg}
        return c

    def info(self):
        return {"full_name": self.full, "name": self.full.split("/")[1], "private": self.private, "default_branch": "main",
                "owner": {"login": self.full.split("/")[0]}}


class FakeGitHub:
    def __init__(self):
        self.repos = {}
        self.calls = []
        self.hidden = set()   # repositories that exist on "GitHub" but Lectern hasn't been given

    def add(self, repo):
        self.repos[repo.full] = repo

    def handle(self, route):
        req = route.request
        u = urlparse(req.url)
        path, q = u.path, parse_qs(u.query)
        m = req.method
        body = None
        if req.post_data:
            try: body = json.loads(req.post_data)
            except Exception: body = None
        self.calls.append((m, path))
        status, data = self.dispatch(m, path, q, body)
        route.fulfill(status=status, content_type="application/json",
                      headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*"},
                      body=json.dumps(data) if data is not None else "")

    def dispatch(self, m, path, q, body):
        if m == "OPTIONS":
            return 204, None
        if path == "/user":
            return 200, {"login": "chandra-gummaluru", "avatar_url": ""}
        if path == "/user/installations":
            return 200, {"installations": [{"id": 1}]}
        if path == "/user/installations/1/repositories":
            return 200, {"repositories": [r.info() for r in self.repos.values()]}
        if path == "/user/repos" and m == "POST":
            if f"chandra-gummaluru/{body['name']}" in self.hidden:
                return 422, {"message": "Repository creation failed.", "errors": [{"message": "name already exists on this account"}]}
            r = Repo(f"chandra-gummaluru/{body['name']}", bool(body.get("private")), {"README.md": "# x"})
            self.add(r); return 201, r.info()
        mm = re.match(r"^/repos/([^/]+/[^/]+)(/.*)?$", path)
        if not mm:
            return 404, {"message": "Not Found"}
        full, rest = mm.group(1), mm.group(2) or ""
        r = self.repos.get(full)
        if not r:
            return 404, {"message": "Not Found"}
        if rest == "":
            return 200, r.info()
        if rest == "/pages" and m == "POST":
            return 201, {}
        if rest.startswith("/git/trees/") and m == "GET":
            files = r.commits[r.head]["files"]
            dirs = set()
            for p in files:
                parts = p.split("/")
                for k in range(1, len(parts)):
                    dirs.add("/".join(parts[:k]))
            tree = [{"path": d, "type": "tree"} for d in sorted(dirs)] + [{"path": p, "type": "blob", "size": len(c)} for p, c in files.items()]
            return 200, {"tree": tree}
        if rest.startswith("/contents/") and m == "GET":
            p = unquote(rest[len("/contents/"):])
            files = r.commits[r.head]["files"]
            if p not in files:
                return 404, {"message": "Not Found"}
            c = files[p]
            raw = c if isinstance(c, bytes) else c.encode()
            return 200, {"content": base64.b64encode(raw).decode(), "sha": hashlib.sha1(raw).hexdigest(), "path": p}
        if rest == "/commits" and m == "GET":
            return 200, [{"commit": {"committer": {"date": "2026-10-17T12:00:00Z"}}}]
        if rest.startswith("/git/ref/heads/") or rest.startswith("/git/refs/heads/"):
            if m == "GET":
                return 200, {"object": {"sha": r.head}}
            if m == "PATCH":
                r.head = body["sha"]; return 200, {"object": {"sha": r.head}}
        if rest.startswith("/git/commits/") and m == "GET":
            c = r.commits.get(rest.split("/")[-1])
            return (200, {"sha": rest.split("/")[-1], "tree": {"sha": c["tree"]}}) if c else (404, {"message": "Not Found"})
        if rest == "/git/blobs" and m == "POST":
            s = sha("b"); content = body["content"]
            r.blobs[s] = base64.b64decode(content) if body.get("encoding") == "base64" else content
            return 201, {"sha": s}
        if rest == "/git/trees" and m == "POST":
            base = dict(r.trees.get(body.get("base_tree"), {}))
            for e in body["tree"]:
                if e.get("sha") is None and "content" not in e:
                    base.pop(e["path"], None)
                elif "content" in e:
                    base[e["path"]] = e["content"]
                else:
                    b = r.blobs.get(e["sha"])
                    base[e["path"]] = b.decode() if isinstance(b, bytes) else b
            t = sha("t"); r.trees[t] = base
            return 201, {"sha": t}
        if rest == "/git/commits" and m == "POST":
            c = sha("c"); r.commits[c] = {"tree": body["tree"], "files": r.trees[body["tree"]], "msg": body.get("message")}
            r.log.append(body.get("message"))
            return 201, {"sha": c, "html_url": f"https://github.com/{full}/commit/{c}"}
        return 404, {"message": f"fake: {m} {rest} not handled"}
