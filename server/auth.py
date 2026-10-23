"""Lectern accounts: sign-in with an email and password, optional two-factor codes, invitations,
password resets, and the account page's API.

Accounts are invite-only: an admin invites an email from the admin panel (/admin, admin.py), and the
link in that email creates the account. (Or an instructor invites someone to a teaching team: teams.py.)
Admins aren't accounts here: they have their own, separate sign-in, added only from the terminal.

Sessions
  A random 256-bit value in an HttpOnly, Secure, SameSite=Lax cookie (__Host-lectern on HTTPS);
  the server keeps only its SHA-256. A session ends after LECTERN_SESSION_IDLE_HOURS without use
  (default 12) and LECTERN_SESSION_DAYS at most (default 7), at sign-out, and when the password
  changes (every other session) or is reset (all of them). Signing in always makes a new session.

Signing in
  POST /api/auth/login        { email, password } → { ok, user } or { twoFactor: true }
  POST /api/auth/login/2fa    { code } or { recovery } (the password step's short-lived cookie)
  Wrong answers count against the account: after 5 in a row it waits 30 s, then 1, 2, 4… minutes
  (at most 15) before taking another try. Each address and each email is also rate-limited. A wrong
  email and a wrong password look the same, in words, in time and in when the waiting starts.
  So someone guessing can't lock the owner out, a browser the account has signed in from before
  (a signed "device" cookie, ended by a password change) isn't held up by the email's limit or the lock.

Every endpoint that changes something also needs the X-Lectern header (core.py).
"""
import functools
import json
import os
import re
import threading
import time

from flask import Blueprint, g, jsonify, make_response, request

from . import db, mailer, security as sec
from .core import app_url, link_base, secure_enough

auth_bp = Blueprint("auth", __name__)

INVITE_DAYS = 7
RESET_MINUTES = 60
CHALLENGE_SECONDS = 300
LOCK_AFTER = 5
_HANDLE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
RESERVED = {"admin", "api", "static", "tools", "p", "request", "lectern", "www", "root", "help", "support", "account", "login", "signin"}
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,63}$")

limiter = sec.Limiter()
LIMITS = {
    "login-ip": (30, 600), "login-email": (10, 600), "2fa": (10, 600), "forgot-ip": (5, 3600), "forgot-email": (3, 3600),
    "token": (30, 600), "change": (10, 600),
}


class Refusal(Exception):
    def __init__(self, status, message, code=""):
        super().__init__(message)
        self.status, self.code = status, code


def _err(e):
    return jsonify(error=str(e), code=e.code), e.status


def handles(fn):
    @functools.wraps(fn)
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except Refusal as e:
            return _err(e)
    return run


# ── Settings ─────────────────────────────────────────────────────────
def _hours(name, default):
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def idle_seconds():
    return _hours("LECTERN_SESSION_IDLE_HOURS", 12) * 3600


def max_seconds():
    return _hours("LECTERN_SESSION_DAYS", 7) * 86400


def cookie_name():
    # __Host-: the browser only accepts it over HTTPS, for this exact host, with Path=/ (no subdomain can set it).
    return "__Host-lectern" if request.is_secure else "lectern_session"


def mfa_cookie():
    """The password step's cookie, waiting for the code: (name, path)."""
    return ("__Host-lectern_mfa", "/") if request.is_secure else ("lectern_mfa", "/api/auth/")


def device_cookie():
    return "__Host-lectern_dev" if request.is_secure else "lectern_dev"


DEVICE_DAYS = 180


def _device_value(u, nonce):
    signed = f"{u['id']}.{nonce}.{u['pw_changed']}"   # a new password ends every device's trust
    return f"{u['id']}.{nonce}.{sec.mac(signed, 'device')}"


def trusted_device(u):
    """Has this browser signed in to u before (since its password last changed)?"""
    v = request.cookies.get(device_cookie(), "")
    parts = v.split(".")
    if len(parts) != 3 or parts[0] != str(u["id"]) or len(v) > 200:
        return False
    return sec.same(v, _device_value(u, parts[1]))


def pages_base():
    """Where published course pages live: LECTERN_PAGES_URL, or /p/ on this server."""
    u = os.environ.get("LECTERN_PAGES_URL") or app_url() + "p/"
    return u if u.endswith("/") else u + "/"


def site_of(handle):
    return f"{pages_base()}{handle}/"


# ── Helpers ──────────────────────────────────────────────────────────
def now():
    return time.time()


def ip():
    return request.remote_addr or "?"


def body():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        raise Refusal(400, "Something went wrong with the form. Reload the page and try again.")
    return d


def text(d, k, maxlen=320):
    v = d.get(k)
    v = "" if v is None else str(v)
    if len(v) > maxlen:
        raise Refusal(400, "That's too long.")
    return v


def norm_email(e):
    return str(e or "").strip().lower()


def limit(kind, key=""):
    n, w = LIMITS[kind]
    if not limiter.ok(f"{kind}:{key or ip()}", n, w):
        raise Refusal(429, "Too many tries. Wait a few minutes, then try again.", "rate")


def need_https():
    if not secure_enough():
        raise Refusal(403, "Lectern only accepts passwords over HTTPS.")


def log(user_id, kind, detail=""):
    db.run("INSERT INTO events (user_id, kind, ip, at, detail) VALUES (?, ?, ?, ?, ?)", (user_id, kind, ip(), now(), detail))


def user_json(u):
    left = db.one("SELECT COUNT(*) AS n FROM recovery_codes WHERE user_id = ? AND used = 0", (u["id"],))["n"]
    return {
        "id": u["id"], "email": u["email"], "name": u["name"], "handle": u["handle"],
        "twoFactor": bool(u["totp_secret"]), "recoveryLeft": left, "site": site_of(u["handle"]),
        "created": u["created"], "passwordChanged": u["pw_changed"],
    }


def notify(u, subject, lines):
    """A security notice to the account's own email (password changed, two-factor off…)."""
    where = link_base()
    body_ = f"Hi {u['name'] or u['email']},\n\n" + "\n".join(lines) + \
        f"\n\nIf this wasn't you, reset your password now{f' ({where})' if where else ''} and tell your Lectern admin.\n"
    mailer.send_later(u["email"], f"Lectern: {subject}", body_)


def _mask(email):
    local, _, dom = email.partition("@")
    return (local[:2] + "…" if len(local) > 2 else local) + "@" + dom


# ── Sessions ─────────────────────────────────────────────────────────
def _set_cookie(resp, name, value, max_age, path="/", samesite="Lax"):
    resp.set_cookie(name, value, max_age=max_age, path=path, secure=request.is_secure, httponly=True, samesite=samesite)


def start_session(resp, u):
    """A new session for u (a new value every time: nothing from before the sign-in carries over)."""
    old = request.cookies.get(cookie_name())
    tok, t = sec.new_token(), now()
    with db.transaction() as c:
        if old:
            c.execute("DELETE FROM sessions WHERE id_hash = ?", (sec.token_hash(old),))
        c.execute("DELETE FROM sessions WHERE expires < ? OR last_seen < ?", (t, t - idle_seconds()))
        c.execute("INSERT INTO sessions (id_hash, user_id, created, last_seen, expires, ip, agent) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (sec.token_hash(tok), u["id"], t, t, t + max_seconds(), ip(), (request.user_agent.string or "")[:300]))
        c.execute("UPDATE users SET last_login = ?, failed = 0, locked_until = 0 WHERE id = ?", (t, u["id"]))
    _set_cookie(resp, cookie_name(), tok, int(max_seconds()))
    name, path = mfa_cookie()
    resp.delete_cookie(name, path=path)
    _set_cookie(resp, device_cookie(), _device_value(u, sec.new_token()[:16]), DEVICE_DAYS * 86400)
    log(u["id"], "sign-in")
    return resp


def current():
    """(user row, session hash) for this request's cookie, or (None, None)."""
    if hasattr(g, "_who"):
        return g._who
    g._who = (None, None)
    tok = request.cookies.get(cookie_name())
    if not tok or len(tok) > 200:
        return g._who
    h, t = sec.token_hash(tok), now()
    s = db.one("SELECT * FROM sessions WHERE id_hash = ?", (h,))
    if not s:
        return g._who
    if s["expires"] < t or s["last_seen"] < t - idle_seconds():
        db.run("DELETE FROM sessions WHERE id_hash = ?", (h,))
        return g._who
    u = db.one("SELECT * FROM users WHERE id = ?", (s["user_id"],))
    if not u or u["disabled"]:
        db.run("DELETE FROM sessions WHERE id_hash = ?", (h,))
        return g._who
    if t - s["last_seen"] > 60:
        db.run("UPDATE sessions SET last_seen = ? WHERE id_hash = ?", (t, h))
    g._who = (u, h)
    return g._who


def signed_in(fn):
    @functools.wraps(fn)
    def run(*a, **k):
        u, h = current()
        if not u:
            return jsonify(error="Your session has ended. Please sign in again.", code="signed-out"), 401
        g.user, g.session = u, h
        try:
            return fn(*a, **k)
        except Refusal as e:
            return _err(e)
    return run


def fresh_user():
    return db.one("SELECT * FROM users WHERE id = ?", (g.user["id"],))


def check_own_password(u, pw):
    """For a change to the account: its password, again. Counts towards the lock like a sign-in."""
    need_https()
    limit("change", f"u{u['id']}")
    if _locked(u):
        raise Refusal(429, "Too many tries. Wait a few minutes, then try again.", "rate")
    ok, new = sec.check_password(u["pw_hash"], str(pw or ""))
    if not ok:
        _fail(u)
        raise Refusal(403, "That password isn't right.", "password")
    if new:
        db.run("UPDATE users SET pw_hash = ? WHERE id = ?", (new, u["id"]))


def second_factor_ok(u, d):
    """A two-factor code ({code}) or a recovery code ({recovery}) for u. Uses it up."""
    if d.get("recovery"):
        r = sec.recovery_norm(d.get("recovery"))
        if len(r) != 10:
            return False
        # Used up in one statement: two requests at once can't both use it.
        cur = db.run("UPDATE recovery_codes SET used = ? WHERE user_id = ? AND code_hash = ? AND used = 0",
                     (now(), u["id"], sec.mac(r, "recovery")))
        if cur.rowcount != 1:
            return False
        log(u["id"], "recovery-code-used")
        return True
    if not u["totp_secret"]:
        return False
    with db.transaction() as c:   # read and move the last step together, so a code can't be used twice at once
        row = c.execute("SELECT totp_step FROM users WHERE id = ?", (u["id"],)).fetchone()
        step = sec.totp_match(sec.decrypt(u["totp_secret"]), d.get("code"), row["totp_step"])
        if step is None:
            return False
        c.execute("UPDATE users SET totp_step = ? WHERE id = ?", (step, u["id"]))
    return True


def _fail(u):
    """One more wrong answer for u: after LOCK_AFTER in a row, a growing wait."""
    with db.transaction() as c:
        n = c.execute("SELECT failed FROM users WHERE id = ?", (u["id"],)).fetchone()["failed"] + 1
        until = _lock_until(n)
        c.execute("UPDATE users SET failed = ?, locked_until = ? WHERE id = ?", (n, until, u["id"]))
    log(u["id"], "sign-in-failed")


def _locked(u):
    return u["locked_until"] and u["locked_until"] > now()


BAD_LOGIN = "That email and password don't match an account."
WAIT = "Too many tries. Wait a few minutes, then try again."

# An email with no account gets the same wait, after the same number of wrong tries and for just as
# long, so the wait doesn't reveal which emails have accounts. (Kept in memory, like the rate limits.)
class _Ghosts:
    def __init__(self):
        self.d, self.lock = {}, threading.Lock()

    def fail(self, email):
        with self.lock:
            if len(self.d) > 50000:
                self.d = {k: v for k, v in self.d.items() if v[1] > now()}
            n = self.d.get(email, (0, 0))[0] + 1
            self.d[email] = (n, _lock_until(n))

    def locked(self, email):
        with self.lock:
            return self.d.get(email, (0, 0))[1] > now()

    def reset(self):
        with self.lock:
            self.d.clear()


ghosts = _Ghosts()


def _lock_until(n):
    """After n wrong answers in a row: wait until when (0: no wait)."""
    return now() + min(900, 30 * 2 ** (n - LOCK_AFTER)) if n >= LOCK_AFTER else 0


# ── Signing in and out ───────────────────────────────────────────────
@auth_bp.get("/api/auth/me")
def me():
    u, _ = current()
    if not u:
        return jsonify(signedIn=False, email=mailer.configured())
    return jsonify(signedIn=True, user=user_json(u), email=mailer.configured())


@auth_bp.post("/api/auth/login")
@handles
def login():
    need_https()
    d = body()
    email, pw = norm_email(text(d, "email")), text(d, "password", sec.MAX_PASSWORD)
    limit("login-ip")
    if not email or not pw:
        raise Refusal(400, "Enter your email and password.")
    u = db.one("SELECT * FROM users WHERE email = ?", (email,))
    known = bool(u) and trusted_device(u)     # a browser this account signed in from before
    if known:
        limit("login-email", f"{email}:{ip()}")
    else:
        limit("login-email", email)
    if not u:
        sec.dummy_check(pw)
        if ghosts.locked(email):
            raise Refusal(429, WAIT, "rate")
        ghosts.fail(email)
        raise Refusal(401, BAD_LOGIN, "bad-login")
    if _locked(u) and not known:
        sec.dummy_check(pw)
        raise Refusal(429, WAIT, "rate")
    ok, new = sec.check_password(u["pw_hash"], pw)
    if not ok:
        _fail(u)
        raise Refusal(401, BAD_LOGIN, "bad-login")
    if new:
        db.run("UPDATE users SET pw_hash = ? WHERE id = ?", (new, u["id"]))
    if u["disabled"]:
        raise Refusal(403, "This account is turned off. Ask your Lectern admin.", "disabled")
    if u["totp_secret"]:
        tok = sec.new_token()
        with db.transaction() as c:
            c.execute("DELETE FROM challenges WHERE user_id = ? OR expires < ?", (u["id"], now()))
            c.execute("INSERT INTO challenges (id_hash, user_id, expires) VALUES (?, ?, ?)", (sec.token_hash(tok), u["id"], now() + CHALLENGE_SECONDS))
        resp = make_response(jsonify(twoFactor=True))
        name, path = mfa_cookie()
        _set_cookie(resp, name, tok, CHALLENGE_SECONDS, path=path, samesite="Strict")
        return resp
    return start_session(make_response(jsonify(ok=True, user=user_json(u))), u)


@auth_bp.post("/api/auth/login/2fa")
@handles
def login_2fa():
    need_https()
    d = body()
    tok = request.cookies.get(mfa_cookie()[0], "")
    ch = db.one("SELECT * FROM challenges WHERE id_hash = ?", (sec.token_hash(tok),)) if tok else None
    if not ch or ch["expires"] < now():
        raise Refusal(401, "That took too long. Enter your email and password again.", "expired")
    limit("2fa", f"u{ch['user_id']}")
    u = db.one("SELECT * FROM users WHERE id = ?", (ch["user_id"],))
    if not u or u["disabled"] or (_locked(u) and not trusted_device(u)):
        raise Refusal(429, WAIT, "rate")
    if not second_factor_ok(u, d):
        _fail(u)
        db.run("UPDATE challenges SET tries = tries + 1 WHERE id_hash = ?", (ch["id_hash"],))
        if ch["tries"] + 1 >= 5:
            db.run("DELETE FROM challenges WHERE id_hash = ?", (ch["id_hash"],))
            raise Refusal(401, "Too many wrong codes. Enter your email and password again.", "expired")
        raise Refusal(401, "That code isn't right." + (" Check your authenticator app's time is set automatically." if d.get("code") else ""), "bad-code")
    if db.run("DELETE FROM challenges WHERE id_hash = ?", (ch["id_hash"],)).rowcount != 1:   # used once, even by two requests at once
        raise Refusal(401, "That took too long. Enter your email and password again.", "expired")
    u = db.one("SELECT * FROM users WHERE id = ?", (u["id"],))
    return start_session(make_response(jsonify(ok=True, user=user_json(u))), u)


@auth_bp.post("/api/auth/logout")
def logout():
    tok = request.cookies.get(cookie_name())
    if tok:
        db.run("DELETE FROM sessions WHERE id_hash = ?", (sec.token_hash(tok),))
    resp = make_response(jsonify(ok=True))
    resp.delete_cookie(cookie_name(), path="/", secure=request.is_secure, httponly=True, samesite="Lax")
    resp.headers["Clear-Site-Data"] = '"cache", "storage"'
    return resp


# ── Forgotten passwords ──────────────────────────────────────────────
FORGOT_SAID = "If that email has a Lectern account, we've sent it a link to choose a new password. It works for an hour."


@auth_bp.post("/api/auth/forgot")
@handles
def forgot():
    d = body()
    email = norm_email(text(d, "email"))
    limit("forgot-ip")
    if not _EMAIL.match(email):
        raise Refusal(400, "Enter your email address.")
    if not limiter.ok(f"forgot-email:{email}", *LIMITS["forgot-email"]):
        return jsonify(ok=True, message=FORGOT_SAID)   # say the same thing: don't reveal anything
    u = db.one("SELECT * FROM users WHERE email = ?", (email,))
    base = link_base()
    if u and not u["disabled"] and not base:
        print("[lectern] a password reset wasn't sent: set LECTERN_APP_URL (links in emails use only that address)", flush=True)
    elif u and not u["disabled"]:
        tok = sec.new_token()
        with db.transaction() as c:
            c.execute("DELETE FROM resets WHERE user_id = ? OR expires < ?", (u["id"], now()))
            c.execute("INSERT INTO resets (token_hash, user_id, created, expires) VALUES (?, ?, ?, ?)",
                      (sec.token_hash(tok), u["id"], now(), now() + RESET_MINUTES * 60))
        log(u["id"], "reset-requested")
        # In the background: the reply takes the same time whether or not there's an account.
        mailer.send_later(u["email"], "Lectern: choose a new password", f"""Hi {u['name'] or u['email']},

Someone (hopefully you) asked to reset your Lectern password. To choose a new one, open this link within an hour:

{base}#reset={tok}

If you didn't ask, ignore this email: your password stays the same.
""")
    return jsonify(ok=True, message=FORGOT_SAID)


def _reset_row(tok):
    limit("token")
    r = db.one("SELECT * FROM resets WHERE token_hash = ?", (sec.token_hash(tok),)) if tok and len(tok) < 200 else None
    if not r or r["used"] or r["expires"] < now():
        raise Refusal(410, "That link has expired or was already used. Ask for a new one.", "expired")
    u = db.one("SELECT * FROM users WHERE id = ?", (r["user_id"],))
    if not u or u["disabled"]:
        raise Refusal(410, "That link has expired or was already used. Ask for a new one.", "expired")
    return r, u


@auth_bp.post("/api/auth/reset/check")
@handles
def reset_check():
    _, u = _reset_row(text(body(), "token"))
    return jsonify(ok=True, email=u["email"], twoFactor=bool(u["totp_secret"]))


@auth_bp.post("/api/auth/reset")
@handles
def reset():
    need_https()
    d = body()
    r, u = _reset_row(text(d, "token"))
    pw = text(d, "password", sec.MAX_PASSWORD)
    bad = sec.password_problem(pw, u["email"], u["name"])
    if bad:
        raise Refusal(400, bad, "weak")
    if u["totp_secret"] and _locked(u):
        raise Refusal(429, WAIT, "rate")
    new = sec.hash_password(pw)
    try:
        with db.transaction() as c:
            # All or nothing: the link is claimed (once, even for two requests at once), the code checked and
            # used up, and the password changed together. A wrong code undoes it all, so the link still works.
            if c.execute("UPDATE resets SET used = ? WHERE token_hash = ? AND used = 0", (now(), r["token_hash"])).rowcount != 1:
                raise Refusal(410, "That link has expired or was already used. Ask for a new one.", "expired")
            if u["totp_secret"] and not second_factor_ok(u, d):
                raise Refusal(401, "That code isn't right. Use the code from your authenticator app, or a recovery code.", "bad-code")
            c.execute("UPDATE users SET pw_hash = ?, pw_changed = ?, failed = 0, locked_until = 0 WHERE id = ?", (new, now(), u["id"]))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))
            c.execute("DELETE FROM challenges WHERE user_id = ?", (u["id"],))
            c.execute("DELETE FROM resets WHERE user_id = ? AND used = 0", (u["id"],))
    except Refusal as e:
        if e.code == "bad-code":
            _fail(u)
        raise
    log(u["id"], "password-reset")
    notify(u, "your password was reset", ["Your Lectern password was just reset, and every device was signed out."])
    return jsonify(ok=True)


# ── Invitations ──────────────────────────────────────────────────────
def create_invite(email, by=None):
    """A new invitation for email → its link. (Any earlier one for that email stops working.)"""
    email = norm_email(email)
    if not _EMAIL.match(email):
        raise Refusal(400, "Enter an email address.")
    if db.one("SELECT 1 FROM users WHERE email = ?", (email,)):
        raise Refusal(409, f"{email} already has an account.", "exists")
    tok = sec.new_token()
    with db.transaction() as c:
        c.execute("DELETE FROM invites WHERE email = ? AND used = 0", (email,))
        c.execute("INSERT INTO invites (token_hash, email, created_by, created, expires) VALUES (?, ?, ?, ?, ?)",
                  (sec.token_hash(tok), email, by, now(), now() + INVITE_DAYS * 86400))
    return tok


def invite_link(tok, base=None):
    base = base or link_base()
    if not base:
        raise Refusal(503, "Set LECTERN_APP_URL on the server first: links in emails use only that address.")
    return f"{base}#invite={tok}"


def send_invite(email, link, by_name=""):
    return mailer.send_later(email, "You're invited to Lectern", f"""Hello,

{by_name or 'Your Lectern admin'} has invited you to Lectern, for your course pages, grades and exams.

To create your account, open this link within {INVITE_DAYS} days:

{link}
""")


def _invite_row(tok):
    limit("token")
    r = db.one("SELECT * FROM invites WHERE token_hash = ?", (sec.token_hash(tok),)) if tok and len(tok) < 200 else None
    if not r or r["used"] or r["expires"] < now():
        raise Refusal(410, "That invitation has expired or was already used. Ask for a new one.", "expired")
    return r


def suggest_handle(email):
    base = re.sub(r"[^a-z0-9]+", "-", email.split("@")[0].lower()).strip("-")[:32] or "me"
    if base in RESERVED or len(base) < 2:
        base = f"{base}-1".strip("-")
    h, k = base, 2
    while db.one("SELECT 1 FROM users WHERE handle = ?", (h,)) or db.one("SELECT 1 FROM retired_handles WHERE handle = ?", (h,)):
        h, k = f"{base}-{k}", k + 1
    return h


def handle_problem(h):
    if not _HANDLE.match(h) or len(h) < 2:
        return "Use 2 to 32 lower-case letters, numbers and dashes (not at the start or end)."
    if h in RESERVED:
        return "That name is reserved. Choose another."
    if db.one("SELECT 1 FROM users WHERE handle = ?", (h,)) or db.one("SELECT 1 FROM retired_handles WHERE handle = ?", (h,)):
        return "That name is taken. Choose another."
    return ""


@auth_bp.post("/api/auth/invite/check")
@handles
def invite_check():
    r = _invite_row(text(body(), "token"))
    return jsonify(ok=True, email=r["email"], handle=suggest_handle(r["email"]), pages=pages_base())


@auth_bp.post("/api/auth/invite/accept")
@handles
def invite_accept():
    need_https()
    d = body()
    r = _invite_row(text(d, "token"))
    name, handle = text(d, "name", 120).strip(), text(d, "handle", 64).strip().lower()
    pw = text(d, "password", sec.MAX_PASSWORD)
    if not name:
        raise Refusal(400, "Enter your name.", "name")
    bad = handle_problem(handle)
    if bad:
        raise Refusal(400, bad, "handle")
    bad = sec.password_problem(pw, r["email"], name)
    if bad:
        raise Refusal(400, bad, "weak")
    t = now()
    try:
        with db.transaction() as c:
            again = c.execute("SELECT used FROM invites WHERE token_hash = ?", (r["token_hash"],)).fetchone()
            if not again or again["used"]:
                raise Refusal(410, "That invitation was already used.", "expired")
            c.execute("UPDATE invites SET used = ? WHERE token_hash = ?", (t, r["token_hash"]))
            cur = c.execute("INSERT INTO users (email, handle, name, pw_hash, pw_changed, created) VALUES (?, ?, ?, ?, ?, ?)",
                            (r["email"], handle, name, sec.hash_password(pw), t, t))
            uid = cur.lastrowid
    except db.sqlite3.IntegrityError:
        raise Refusal(409, "That email or name already has an account.", "exists")
    log(uid, "account-created")
    u = db.one("SELECT * FROM users WHERE id = ?", (uid,))
    return start_session(make_response(jsonify(ok=True, user=user_json(u))), u)


# ── Your account ─────────────────────────────────────────────────────
@auth_bp.post("/api/auth/profile")
@signed_in
def profile():
    d = body()
    name = text(d, "name", 120).strip()
    if not name:
        raise Refusal(400, "Enter your name.")
    db.run("UPDATE users SET name = ? WHERE id = ?", (name, g.user["id"]))
    return jsonify(ok=True, user=user_json(fresh_user()))


@auth_bp.post("/api/auth/password")
@signed_in
def change_password():
    d = body()
    u = fresh_user()
    check_own_password(u, text(d, "current", sec.MAX_PASSWORD))
    pw = text(d, "password", sec.MAX_PASSWORD)
    bad = sec.password_problem(pw, u["email"], u["name"])
    if bad:
        raise Refusal(400, bad, "weak")
    if sec.check_password(u["pw_hash"], pw)[0]:
        raise Refusal(400, "That's your current password. Choose a new one.", "weak")
    with db.transaction() as c:
        c.execute("UPDATE users SET pw_hash = ?, pw_changed = ? WHERE id = ?", (sec.hash_password(pw), now(), u["id"]))
        c.execute("DELETE FROM sessions WHERE user_id = ? AND id_hash != ?", (u["id"], g.session))
        c.execute("DELETE FROM challenges WHERE user_id = ?", (u["id"],))
        c.execute("DELETE FROM resets WHERE user_id = ?", (u["id"],))
    log(u["id"], "password-changed")
    notify(u, "your password was changed", ["Your Lectern password was just changed. Every other device was signed out."])
    return jsonify(ok=True, user=user_json(fresh_user()))


@auth_bp.post("/api/auth/2fa/setup")
@signed_in
def totp_setup():
    """Step 1: a new secret (not on yet), as a QR code and as text."""
    u, d = fresh_user(), body()
    check_own_password(u, text(d, "password", sec.MAX_PASSWORD))
    if u["totp_secret"] and not second_factor_ok(u, d):   # already on: replacing it needs the current app (or a recovery code)
        raise Refusal(400, "Two-factor sign-in is already on. To set up a new app, turn it off first (that needs a code).", "bad-code")
    s = sec.new_totp_secret()
    db.run("UPDATE users SET totp_pending = ? WHERE id = ?", (sec.encrypt(s), u["id"]))
    uri = sec.totp_uri(s, u["email"])
    return jsonify(ok=True, secret=" ".join(s[i:i + 4] for i in range(0, len(s), 4)), uri=uri, qr=sec.qr_svg(uri))


@auth_bp.post("/api/auth/2fa/enable")
@signed_in
def totp_enable():
    """Step 2: a code from the app proves it's set up; then it's on, with fresh recovery codes."""
    u = fresh_user()
    limit("change", f"u{u['id']}")
    if not u["totp_pending"]:
        raise Refusal(400, "Start again: set up two-factor from the beginning.")
    s = sec.decrypt(u["totp_pending"])
    step = sec.totp_match(s, body().get("code"))
    if step is None:
        raise Refusal(400, "That code isn't right. Check the app shows Lectern, and that your phone's time is set automatically.", "bad-code")
    codes = sec.new_recovery_codes()
    with db.transaction() as c:
        c.execute("UPDATE users SET totp_secret = ?, totp_pending = NULL, totp_step = ? WHERE id = ?", (u["totp_pending"], step, u["id"]))
        c.execute("DELETE FROM recovery_codes WHERE user_id = ?", (u["id"],))
        c.executemany("INSERT INTO recovery_codes (user_id, code_hash) VALUES (?, ?)", [(u["id"], sec.mac(sec.recovery_norm(x), "recovery")) for x in codes])
        c.execute("DELETE FROM sessions WHERE user_id = ? AND id_hash != ?", (u["id"], g.session))
    log(u["id"], "2fa-on")
    notify(u, "two-factor sign-in is on", ["Two-factor sign-in was just turned on for your Lectern account."])
    return jsonify(ok=True, codes=codes, user=user_json(fresh_user()))


@auth_bp.post("/api/auth/2fa/disable")
@signed_in
def totp_disable():
    d = body()
    u = fresh_user()
    check_own_password(u, text(d, "password", sec.MAX_PASSWORD))
    if u["totp_secret"] and not second_factor_ok(u, d):
        raise Refusal(400, "That code isn't right.", "bad-code")
    with db.transaction() as c:
        c.execute("UPDATE users SET totp_secret = NULL, totp_pending = NULL, totp_step = 0 WHERE id = ?", (u["id"],))
        c.execute("DELETE FROM recovery_codes WHERE user_id = ?", (u["id"],))
    log(u["id"], "2fa-off")
    notify(u, "two-factor sign-in is off", ["Two-factor sign-in was just turned off for your Lectern account."])
    return jsonify(ok=True, user=user_json(fresh_user()))


@auth_bp.post("/api/auth/recovery")
@signed_in
def new_recovery():
    u, d = fresh_user(), body()
    check_own_password(u, text(d, "password", sec.MAX_PASSWORD))
    if not u["totp_secret"]:
        raise Refusal(400, "Turn on two-factor sign-in first.")
    if not second_factor_ok(u, d):
        raise Refusal(400, "That code isn't right.", "bad-code")
    codes = sec.new_recovery_codes()
    with db.transaction() as c:
        c.execute("DELETE FROM recovery_codes WHERE user_id = ?", (u["id"],))
        c.executemany("INSERT INTO recovery_codes (user_id, code_hash) VALUES (?, ?)", [(u["id"], sec.mac(sec.recovery_norm(x), "recovery")) for x in codes])
    log(u["id"], "recovery-codes-new")
    return jsonify(ok=True, codes=codes, user=user_json(fresh_user()))


@auth_bp.get("/api/auth/sessions")
@signed_in
def sessions():
    rows = db.all_("SELECT * FROM sessions WHERE user_id = ? AND expires > ? AND last_seen > ? ORDER BY last_seen DESC",
                   (g.user["id"], now(), now() - idle_seconds()))
    return jsonify(sessions=[{"id": r["id_hash"][:16], "created": r["created"], "lastSeen": r["last_seen"], "ip": r["ip"],
                              "agent": r["agent"], "current": r["id_hash"] == g.session} for r in rows])


@auth_bp.post("/api/auth/sessions/revoke")
@signed_in
def revoke():
    which = text(body(), "id", 40)
    if which == "others":
        db.run("DELETE FROM sessions WHERE user_id = ? AND id_hash != ?", (g.user["id"], g.session))
    elif re.fullmatch(r"[0-9a-f]{16}", which):
        db.run("DELETE FROM sessions WHERE user_id = ? AND substr(id_hash, 1, 16) = ? AND id_hash != ?", (g.user["id"], which, g.session))
    else:
        raise Refusal(400, "Which session?")
    log(g.user["id"], "sessions-revoked", which)
    return jsonify(ok=True)
