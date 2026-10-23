"""Lectern for the browser walkthroughs: the real server, in this process, on a free port, with an empty
data folder of its own, plus helpers to make an account, put files in it, sign a page in, and read
what was saved.

    from harness import Server
    with Server() as srv:
        user = srv.account()                       # chandra@utoronto.ca, handle "chandra", an admin
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(book)})
        srv.sign_in(page)                          # a Playwright page, signed in
        srv.text("priv", "csc258/f26/grades.json")  # what's there now
"""
import os
import shutil
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

OUT = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(OUT, exist_ok=True)
PASSWORD = "correct horse battery staple"


class Server:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="lectern-")
        os.environ["LECTERN_DATA_DIR"] = self.dir
        os.environ.pop("LECTERN_SMTP_HOST", None)
        from server import mailer; mailer.keep = True
        from werkzeug.serving import make_server
        from server import app, db
        db.reset_for_tests()
        self.app = app
        import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
        self.httpd = make_server("127.0.0.1", 0, app, threaded=True)
        self.base = f"http://localhost:{self.httpd.server_port}/"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        shutil.rmtree(self.dir, ignore_errors=True)

    def account(self, email="chandra@utoronto.ca", name="Chandra Gummaluru", handle="chandra", admin=True):
        from server import auth, db, security
        import time
        t = time.time()
        db.run("INSERT INTO users (email, handle, name, pw_hash, pw_changed, is_admin, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (email, handle, name, security.hash_password(PASSWORD), t, 1 if admin else 0, t))
        self.user = db.one("SELECT * FROM users WHERE email = ?", (email,))
        return self.user

    def repo(self, name, user=None):
        from server.store import Repo
        return Repo((user or self.user)["id"], name)

    def put(self, name, files, user=None):
        r = self.repo(name, user)
        r.commit({p: (v.encode() if isinstance(v, str) else v) for p, v in files.items()}, "seed", r.head())

    def text(self, name, path, user=None):
        return self.repo(name, user).read_text(path)[0]

    def files(self, name, user=None):
        return {e["path"]: self.repo(name, user).read_text(e["path"])[0] for e in self.repo(name, user).walk() if e["type"] == "blob"}

    def sign_in(self, page, email="chandra@utoronto.ca", password=PASSWORD, hash="#/"):
        page.goto(self.base)
        page.wait_for_selector("#sp-email", state="visible")
        page.fill("#sp-email", email)
        page.fill("#sp-pw", password)
        page.click("#sp-go")
        page.wait_for_selector("#app:not([hidden])")
        if hash != "#/":
            page.evaluate(f"location.hash = {hash!r}")
        page.wait_for_timeout(600)


def block_cdns(ctx):
    ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
    ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
    ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
