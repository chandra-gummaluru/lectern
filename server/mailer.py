"""Email over SMTP: invitations, password resets, security notices, and students' accommodation requests.

Settings (environment variables, or .env beside app.py):
  LECTERN_SMTP_HOST       e.g. smtp.gmail.com
  LECTERN_SMTP_PORT       587 (STARTTLS, the default) or 465 (SSL)
  LECTERN_SMTP_USER       the login
  LECTERN_SMTP_PASSWORD   its password (for Gmail, an app password)
  LECTERN_SMTP_FROM       the From address, e.g. "Lectern <lectern@changapp.net>" (default: the login)
  LECTERN_SMTP_SECURITY   starttls (default), ssl or none

The admin panel can set these too (Email): they're kept in the database (the password encrypted with the
server's key) and used instead of the environment's. Removing them there goes back to the environment's.

Without a host, nothing is sent and send() returns False so the caller can say so. Only the address
and subject go to the server's log: emails carry sign-in links, so their text is printed only when
LECTERN_PRINT_EMAILS=1 (for trying Lectern on your own computer).
"""
import json
import os
import smtplib
import ssl
import sys
import threading
from email.message import EmailMessage
from email.utils import make_msgid

sent = []      # with keep on (tests): the last few messages, newest last. Off in a real server: they hold sign-in links.
keep = False


KEYS = ("host", "port", "security", "user", "password", "from")


def settings():
    """The SMTP settings in use: the admin panel's if it has some, else the environment's. Includes the password."""
    from . import db, security
    row = None
    try:
        row = db.one("SELECT value FROM settings WHERE key = 'smtp'")
    except Exception:
        pass
    if row:
        d = json.loads(row["value"])
        d["password"] = security.decrypt(d.pop("password_enc"), "smtp") if d.get("password_enc") else ""
        d["source"] = "panel"
        return d
    env = os.environ.get
    d = {k: env(f"LECTERN_SMTP_{k.upper()}") or "" for k in KEYS}
    d["source"] = "env" if d["host"] else ""
    return d


def configured():
    return bool(settings()["host"])


def deliver(to, subject, body, reply_to=None, cfg=None):
    """Send one plain-text email. Returns "" if it went out, else what went wrong."""
    cfg = cfg or settings()
    sender = cfg.get("from") or cfg.get("user") or "lectern@localhost"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg["Message-ID"] = make_msgid(domain="lectern")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    if keep:
        sent.append({"to": to, "subject": subject, "body": body})
        del sent[:-20]
    if not cfg.get("host"):
        text = f"\n{body}\n" if os.environ.get("LECTERN_PRINT_EMAILS") == "1" else ""
        print(f"[lectern] email not sent (no SMTP settings) → {to}: {subject}{text}", file=sys.stderr)
        return "Email isn't set up."
    host, sec = cfg["host"], (cfg.get("security") or "starttls").lower()
    port = int(cfg.get("port") or (465 if sec == "ssl" else 587))
    try:
        if sec == "ssl":
            s = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(host, port, timeout=20)
            if sec == "starttls":
                s.starttls(context=ssl.create_default_context())
        with s:
            if cfg.get("user"):
                s.login(cfg["user"], cfg.get("password") or "")
            s.send_message(msg)
        return ""
    except Exception as e:
        print(f"[lectern] email to {to} failed: {e}", file=sys.stderr)
        return str(e) or type(e).__name__


def send(to, subject, body, reply_to=None):
    """Send one plain-text email. Returns True if it went out."""
    return deliver(to, subject, body, reply_to) == ""


def send_later(to, subject, body):
    """Send in the background, so the reply doesn't wait for (or reveal anything by) the SMTP server's speed."""
    if keep:   # tests: right away, so they can read it
        return send(to, subject, body)
    threading.Thread(target=send, args=(to, subject, body), daemon=True).start()
    return configured()
