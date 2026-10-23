"""The admin panel, at /admin: its own accounts, its own sign-in, its own session.

Admins aren't Lectern accounts. They're added only from the terminal, on the server
(`python app.py admin you@example.com`, which also sets up their two-factor code), and they sign in
only here, with email, password and a code from their authenticator app, all three every time.
A Lectern account can't open the panel, and an admin can't open courses.

From the panel an admin:
  - invites people to make Lectern accounts (Lectern is otherwise closed),
  - looks after accounts: signs them out everywhere, lets them try again after wrong passwords,
    turns off their two-factor sign-in (a lost phone), turns an account off or back on,
  - turns other admins off or back on (not themselves).

The admin session: a separate cookie (__Host-lectern_admin, HttpOnly, Secure, SameSite=Strict),
ending after LECTERN_ADMIN_IDLE_MINUTES unused (default 30) and 12 hours at most. LECTERN_ADMIN_URL
gives the panel an address of its own (recommended: see _own_address). Changes need the
X-Lectern header like everything else (core.py); turning anything off needs the admin's password again.

  GET  /admin                           the panel
  GET  /api/admin/me                    { signedIn, admin }
  POST /api/admin/login                 { email, password, code }
  POST /api/admin/logout
  GET  /api/admin/overview              accounts, waiting invitations, admins
  POST /api/admin/invites               { email }
  POST /api/admin/invites/revoke        { id }
  POST /api/admin/users/<id>            { action: sign-out | unlock | reset-2fa | disable | enable, password? }
  POST /api/admin/admins/<id>           { action: disable | enable, password }
"""
import functools
import json
import os
import re
import time

from flask import Blueprint, g, jsonify, make_response, render_template, request

from . import db, mailer, security as sec
from .store import _sha_cache
from .auth import (LOCK_AFTER, Refusal, WAIT, body, create_invite, handles, invite_link, ip, limit, limiter,
                   need_https, norm_email, notify, send_invite, site_of, text)

admin_bp = Blueprint("admin", __name__)

ADMIN_MAX = 12 * 3600


def idle_seconds():
    try:
        return float(os.environ.get("LECTERN_ADMIN_IDLE_MINUTES") or 30) * 60
    except ValueError:
        return 1800


def cookie_name():
    return "__Host-lectern_admin" if request.is_secure else "lectern_admin"


def now():
    return time.time()


def log(kind, detail=""):
    who = g.admin["email"] if getattr(g, "admin", None) else ""
    db.run("INSERT INTO events (user_id, kind, ip, at, detail) VALUES (NULL, ?, ?, ?, ?)", (f"admin:{kind}", ip(), now(), f"{who} {detail}".strip()))


# ── Admin accounts (made from the terminal: cli.py) ──────────────────
def save_admin(email, name, password, totp_secret, step=0):
    """Add an admin, or replace an existing one's password and two-factor secret (and sign it out)."""
    email = norm_email(email)
    t = now()
    with db.transaction() as c:
        cur = c.execute("SELECT id FROM admins WHERE email = ?", (email,)).fetchone()
        if cur:
            c.execute("UPDATE admins SET name = ?, pw_hash = ?, totp_secret = ?, totp_step = ?, failed = 0, locked_until = 0, disabled = 0 WHERE id = ?",
                      (name, sec.hash_password(password), sec.encrypt(totp_secret, "admin-totp"), step, cur["id"]))
            c.execute("DELETE FROM admin_sessions WHERE admin_id = ?", (cur["id"],))
        else:
            c.execute("INSERT INTO admins (email, name, pw_hash, totp_secret, totp_step, created) VALUES (?, ?, ?, ?, ?, ?)",
                      (email, name, sec.hash_password(password), sec.encrypt(totp_secret, "admin-totp"), step, t))
        c.execute("INSERT INTO events (user_id, kind, at, detail) VALUES (NULL, 'admin:saved-from-terminal', ?, ?)", (t, email))


# ── Sessions ─────────────────────────────────────────────────────────
def current_admin():
    if hasattr(g, "_admin"):
        return g._admin
    g._admin = (None, None)
    tok = request.cookies.get(cookie_name())
    if not tok or len(tok) > 200:
        return g._admin
    h, t = sec.token_hash(tok), now()
    s = db.one("SELECT * FROM admin_sessions WHERE id_hash = ?", (h,))
    if not s:
        return g._admin
    if s["expires"] < t or s["last_seen"] < t - idle_seconds():
        db.run("DELETE FROM admin_sessions WHERE id_hash = ?", (h,))
        return g._admin
    a = db.one("SELECT * FROM admins WHERE id = ?", (s["admin_id"],))
    if not a or a["disabled"]:
        db.run("DELETE FROM admin_sessions WHERE id_hash = ?", (h,))
        return g._admin
    if t - s["last_seen"] > 30:
        db.run("UPDATE admin_sessions SET last_seen = ? WHERE id_hash = ?", (t, h))
    g._admin = (a, h)
    return g._admin


def admin_required(fn):
    @functools.wraps(fn)
    def run(*a, **k):
        adm, h = current_admin()
        if not adm:
            return jsonify(error="Your admin session has ended. Sign in again.", code="signed-out"), 401
        g.admin, g.admin_session = adm, h
        try:
            return fn(*a, **k)
        except Refusal as e:
            return jsonify(error=str(e), code=e.code), e.status
    return run


def _lock_until(n):
    return now() + min(900, 30 * 2 ** (n - LOCK_AFTER)) if n >= LOCK_AFTER else 0


def _fail(a):
    with db.transaction() as c:
        n = c.execute("SELECT failed FROM admins WHERE id = ?", (a["id"],)).fetchone()["failed"] + 1
        c.execute("UPDATE admins SET failed = ?, locked_until = ? WHERE id = ?", (n, _lock_until(n), a["id"]))
    db.run("INSERT INTO events (user_id, kind, ip, at, detail) VALUES (NULL, 'admin:sign-in-failed', ?, ?, ?)", (ip(), now(), a["email"]))


def _code_ok(a, code):
    with db.transaction() as c:
        row = c.execute("SELECT totp_step FROM admins WHERE id = ?", (a["id"],)).fetchone()
        step = sec.totp_match(sec.decrypt(a["totp_secret"], "admin-totp"), code, row["totp_step"])
        if step is None:
            return False
        c.execute("UPDATE admins SET totp_step = ? WHERE id = ?", (step, a["id"]))
    return True


def check_admin_password(pw):
    """For turning something off: the admin's password, again (counts towards the lock)."""
    need_https()
    a = db.one("SELECT * FROM admins WHERE id = ?", (g.admin["id"],))
    if a["locked_until"] > now():
        raise Refusal(429, WAIT, "rate")
    if not sec.check_password(a["pw_hash"], str(pw or ""))[0]:
        _fail(a)
        raise Refusal(403, "That password isn't right.", "password")


# ── Its own address (optional) ───────────────────────────────────────
# On the same address as Lectern, a script injected into Lectern's pages could use a signed-in admin's
# session. LECTERN_ADMIN_URL (e.g. https://admin.lectern.changapp.net/, pointing at this same server) puts
# the panel on an address of its own: then it's only there, and its session never meets Lectern's pages.
@admin_bp.before_request
def _own_address():
    want = os.environ.get("LECTERN_ADMIN_URL", "")
    if want and (request.path == "/admin" or request.path.startswith(("/admin/", "/api/admin/"))):
        from urllib.parse import urlsplit
        if (urlsplit(want).hostname or "").lower() != request.host.split(":")[0].lower():
            return jsonify(error="Not Found"), 404


# ── Signing in ───────────────────────────────────────────────────────
@admin_bp.get("/admin")
@admin_bp.get("/admin/")
def panel():
    return render_template("admin.html", institution=os.environ.get("LECTERN_INSTITUTION", "University of Toronto"))


@admin_bp.get("/api/admin/me")
def me():
    a, _ = current_admin()
    return jsonify(signedIn=bool(a), admin={"email": a["email"], "name": a["name"]} if a else None)


@admin_bp.post("/api/admin/login")
@handles
def login():
    need_https()
    d = body()
    email, pw, code = norm_email(text(d, "email")), text(d, "password", sec.MAX_PASSWORD), text(d, "code", 20)
    # Limits per address, and per email from each address. (Not per email alone, and no lock on the admin:
    # either would let anyone who knows an admin's email keep them out. Every try needs the password and a
    # current code, so guessing gets nowhere anyway.) The same for an email that isn't an admin's.
    limit("login-ip", f"admin:{ip()}")
    if not limiter.ok(f"admin-login:{email}:{ip()}", 5, 900):
        raise Refusal(429, WAIT, "rate")
    if not email or not pw or not code:
        raise Refusal(400, "Enter your email, password and the code from your authenticator app.")
    a = db.one("SELECT * FROM admins WHERE email = ?", (email,))
    bad = Refusal(401, "That email, password and code don't match an admin.", "bad-login")
    if not a:
        sec.dummy_check(pw)
        raise bad
    if not sec.check_password(a["pw_hash"], pw)[0] or not _code_ok(a, code):
        db.run("INSERT INTO events (user_id, kind, ip, at, detail) VALUES (NULL, 'admin:sign-in-failed', ?, ?, ?)", (ip(), now(), a["email"]))
        raise bad
    if a["disabled"]:
        raise Refusal(403, "This admin account is turned off.", "disabled")
    tok, t = sec.new_token(), now()
    old = request.cookies.get(cookie_name())
    with db.transaction() as c:
        if old:
            c.execute("DELETE FROM admin_sessions WHERE id_hash = ?", (sec.token_hash(old),))
        c.execute("DELETE FROM admin_sessions WHERE expires < ? OR last_seen < ?", (t, t - idle_seconds()))
        c.execute("INSERT INTO admin_sessions (id_hash, admin_id, created, last_seen, expires, ip, agent) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (sec.token_hash(tok), a["id"], t, t, t + ADMIN_MAX, ip(), (request.user_agent.string or "")[:300]))
        c.execute("UPDATE admins SET failed = 0, locked_until = 0, last_login = ? WHERE id = ?", (t, a["id"]))
    g.admin = a
    log("sign-in")
    resp = make_response(jsonify(ok=True, admin={"email": a["email"], "name": a["name"]}))
    resp.set_cookie(cookie_name(), tok, max_age=ADMIN_MAX, path="/", secure=request.is_secure, httponly=True, samesite="Strict")
    return resp


@admin_bp.post("/api/admin/logout")
def logout():
    tok = request.cookies.get(cookie_name())
    if tok:
        db.run("DELETE FROM admin_sessions WHERE id_hash = ?", (sec.token_hash(tok),))
    resp = make_response(jsonify(ok=True))
    resp.delete_cookie(cookie_name(), path="/", secure=request.is_secure, httponly=True, samesite="Strict")
    return resp


# ── The panel's API ──────────────────────────────────────────────────
@admin_bp.get("/api/admin/overview")
@admin_required
def overview():
    t = now()
    users = db.all_("SELECT * FROM users ORDER BY created")
    invites = db.all_("SELECT * FROM invites WHERE used = 0 AND expires > ? ORDER BY created DESC", (t,))
    admins = db.all_("SELECT * FROM admins ORDER BY created")
    teams = {r["user_id"]: r["n"] for r in db.all_("SELECT user_id, COUNT(*) AS n FROM members GROUP BY user_id")}
    return jsonify(
        me=g.admin["id"], email=mailer.configured(),
        users=[{"id": u["id"], "email": u["email"], "name": u["name"], "handle": u["handle"], "site": site_of(u["handle"]),
                "twoFactor": bool(u["totp_secret"]), "disabled": bool(u["disabled"]), "locked": u["locked_until"] > t,
                "lastLogin": u["last_login"], "created": u["created"], "teams": teams.get(u["id"], 0)} for u in users],
        invites=[{"id": i["token_hash"][:16], "email": i["email"], "created": i["created"], "expires": i["expires"]} for i in invites],
        admins=[{"id": a["id"], "email": a["email"], "name": a["name"], "disabled": bool(a["disabled"]), "lastLogin": a["last_login"]} for a in admins],
    )


@admin_bp.post("/api/admin/invites")
@admin_required
def invite():
    email = norm_email(text(body(), "email"))
    if not limiter.ok(f"admin-invite:{g.admin['id']}", 60, 3600):
        raise Refusal(429, "That's a lot of invitations at once. Wait a while, then try again.", "rate")
    tok = create_invite(email)
    link = invite_link(tok)
    emailed = send_invite(email, link, "Your Lectern admin")
    log("invited", email)
    return jsonify(ok=True, email=email, emailed=emailed, **({} if emailed else {"link": link}))


@admin_bp.post("/api/admin/invites/revoke")
@admin_required
def invite_revoke():
    which = text(body(), "id", 40)
    if not re.fullmatch(r"[0-9a-f]{16}", which):
        raise Refusal(400, "Which invitation?")
    db.run("DELETE FROM invites WHERE substr(token_hash, 1, 16) = ? AND used = 0", (which,))
    log("invite-cancelled", which)
    return jsonify(ok=True)


@admin_bp.post("/api/admin/users/<int:uid>")
@admin_required
def user_action(uid):
    d = body()
    action = text(d, "action", 40)
    u = db.one("SELECT * FROM users WHERE id = ?", (uid,))
    if not u:
        raise Refusal(404, "No such account.")
    if action in ("reset-2fa", "disable", "delete"):
        check_admin_password(text(d, "password", sec.MAX_PASSWORD))
    if action == "delete":
        if norm_email(text(d, "confirm")) != u["email"]:
            raise Refusal(400, "Type their email exactly to confirm.", "confirm")
        where = delete_user(u)
        log("delete", f"{u['email']} ({u['handle']}) files kept in {where}")
        return jsonify(ok=True)
    if action == "disable":
        with db.transaction() as c:
            c.execute("UPDATE users SET disabled = 1 WHERE id = ?", (uid,))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
    elif action == "enable":
        db.run("UPDATE users SET disabled = 0, failed = 0, locked_until = 0 WHERE id = ?", (uid,))
    elif action == "unlock":
        db.run("UPDATE users SET failed = 0, locked_until = 0 WHERE id = ?", (uid,))
    elif action == "sign-out":
        db.run("DELETE FROM sessions WHERE user_id = ?", (uid,))
    elif action == "reset-2fa":
        with db.transaction() as c:
            c.execute("UPDATE users SET totp_secret = NULL, totp_pending = NULL, totp_step = 0 WHERE id = ?", (uid,))
            c.execute("DELETE FROM recovery_codes WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
        notify(u, "two-factor sign-in was turned off", ["Your Lectern admin turned off two-factor sign-in for your account (for example, after a lost phone). Sign in and turn it on again."])
    else:
        raise Refusal(400, "Unknown action.")
    log(action, u["email"])
    return jsonify(ok=True)


@admin_bp.post("/api/admin/admins/<int:aid>")
@admin_required
def admin_action(aid):
    d = body()
    action = text(d, "action", 40)
    if aid == g.admin["id"]:
        raise Refusal(400, "You can't turn yourself off.")
    if action not in ("disable", "enable"):
        raise Refusal(400, "Unknown action.")
    check_admin_password(text(d, "password", sec.MAX_PASSWORD))
    a = db.one("SELECT * FROM admins WHERE id = ?", (aid,))
    if not a:
        raise Refusal(404, "No such admin.")
    with db.transaction() as c:
        c.execute("UPDATE admins SET disabled = ? WHERE id = ?", (1 if action == "disable" else 0, aid))
        if action == "disable":
            c.execute("DELETE FROM admin_sessions WHERE admin_id = ?", (aid,))
    log(f"admin-{action}", a["email"])
    return jsonify(ok=True)


# ── Deleting an account ──────────────────────────────────────────────
def delete_user(u):
    """Delete an account: it can't sign in, its course pages go offline, it leaves every teaching team, and the
    teams on its own offerings end. Its files (and their old versions) aren't erased: they're moved to
    data/deleted/<when>-<handle>/, with a note of whose they were, for the server's owner to remove by hand
    when sure. Its page address stays taken (handle_problem), so old links never show someone else's pages.
    Returns the folder the files went to (relative to the data folder)."""
    uid, root = u["id"], db.data_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    rel = os.path.join("deleted", f"{stamp}-{u['handle']}")
    dest = os.path.join(root, rel)
    os.makedirs(dest, exist_ok=False)
    moved = []
    try:
        for part in ("files", "history"):     # first, so that a later account can never find these under its id
            src = os.path.join(root, part, str(uid))
            if os.path.isdir(src):
                os.replace(src, os.path.join(dest, part))
                moved.append(part)
        with open(os.path.join(dest, "account.json"), "w", encoding="utf-8") as fh:
            json.dump({"id": uid, "email": u["email"], "name": u["name"], "handle": u["handle"], "created": u["created"],
                       "deleted": now(), "by": g.admin["email"]}, fh, indent=2)
        with db.transaction() as c:
            c.execute("INSERT OR IGNORE INTO retired_handles (handle, at) VALUES (?, ?)", (u["handle"], now()))
            c.execute("DELETE FROM objects WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM commits WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM invites WHERE email = ? AND used = 0", (u["email"],))
            c.execute("DELETE FROM team_invites WHERE created_by = ? AND used = 0", (uid,))
            c.execute("DELETE FROM users WHERE id = ?", (uid,))   # sessions, codes, teams, repos… go with it
    except Exception:
        for part in moved:                    # put things back as they were
            os.replace(os.path.join(dest, part), os.path.join(root, part, str(uid)))
        raise
    _sha_cache.clear()
    mailer.send_later(u["email"], "Lectern: your account was deleted",
                      f"Hi {u['name'] or u['email']},\n\nYour Lectern admin deleted your Lectern account. You can't sign in any more, and your "
                      f"course pages are no longer published. If this is a mistake, ask your Lectern admin.\n")
    return rel


# ── Email (SMTP) settings ────────────────────────────────────────────
_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


def _email_json():
    s = mailer.settings()
    return {"source": s["source"], "host": s["host"], "port": str(s.get("port") or ""), "security": s.get("security") or "starttls",
            "user": s.get("user") or "", "from": s.get("from") or "", "hasPassword": bool(s.get("password"))}   # never the password itself


@admin_bp.get("/api/admin/email")
@admin_required
def email_get():
    return jsonify(_email_json())


@admin_bp.post("/api/admin/email")
@admin_required
def email_set():
    """Save the SMTP settings (after a test email to the admin goes through), or remove them (back to .env's)."""
    d = body()
    check_admin_password(text(d, "password", sec.MAX_PASSWORD))
    if d.get("action") == "remove":
        db.run("DELETE FROM settings WHERE key = 'smtp'")
        log("email-removed")
        return jsonify(ok=True, **_email_json())
    host = text(d, "host", 253).strip()
    security = text(d, "security", 10).strip().lower() or "starttls"
    port = text(d, "port", 6).strip() or ("465" if security == "ssl" else "587")
    user, frm = text(d, "user", 254).strip(), text(d, "from", 300).strip()
    if not _HOST.match(host):
        raise Refusal(400, "Enter the SMTP server, e.g. smtp.gmail.com.", "host")
    if security not in ("starttls", "ssl", "none"):
        raise Refusal(400, "Security is STARTTLS, SSL or none.", "security")
    if not port.isdigit() or not 0 < int(port) < 65536:
        raise Refusal(400, "The port is a number, e.g. 587.", "port")
    if any(ch in user + frm for ch in "\r\n"):
        raise Refusal(400, "That address can't have line breaks.", "from")
    pw = text(d, "smtpPassword", 500)
    if not pw:   # blank: keep the one it has (the panel never shows it)
        pw = mailer.settings().get("password") or ""
    cfg = {"host": host, "port": port, "security": security, "user": user, "from": frm, "password": pw}
    err = mailer.deliver(g.admin["email"], "Lectern: email works",
                         f"Hi {g.admin['name'] or g.admin['email']},\n\nThis is the test email from Lectern's admin panel: "
                         f"Lectern can send email through {host}.\n", cfg=cfg)
    if err:
        raise Refusal(400, f"The test email didn't go through, so nothing was saved: {err}", "smtp")
    stored = {k: cfg[k] for k in ("host", "port", "security", "user", "from")}
    if pw:
        stored["password_enc"] = sec.encrypt(pw, "smtp")
    db.run("INSERT INTO settings (key, value) VALUES ('smtp', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (json.dumps(stored),))
    log("email-set", host)
    return jsonify(ok=True, **_email_json())
