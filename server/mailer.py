"""Email over SMTP: invitations, password resets, security notices, and students' accommodation requests.

Settings (environment variables, or .env beside app.py):
  LECTERN_SMTP_HOST       e.g. smtp.gmail.com
  LECTERN_SMTP_PORT       587 (STARTTLS, the default) or 465 (SSL)
  LECTERN_SMTP_USER       the login
  LECTERN_SMTP_PASSWORD   its password (for Gmail, an app password)
  LECTERN_SMTP_FROM       the From address, e.g. "Lectern <lectern@changapp.net>" (default: the login)
  LECTERN_SMTP_SECURITY   starttls (default), ssl or none

Without a host, nothing is sent and send() returns False so the caller can say so. Only the address
and subject go to the server's log: emails carry sign-in links, so their text is printed only when
LECTERN_PRINT_EMAILS=1 (for trying Lectern on your own computer).
"""
import os
import smtplib
import ssl
import sys
import threading
from email.message import EmailMessage
from email.utils import make_msgid

sent = []      # with keep on (tests): the last few messages, newest last. Off in a real server: they hold sign-in links.
keep = False


def configured():
    return bool(os.environ.get("LECTERN_SMTP_HOST"))


def send(to, subject, body, reply_to=None):
    """Send one plain-text email. Returns True if it went out."""
    env = os.environ.get
    sender = env("LECTERN_SMTP_FROM") or env("LECTERN_SMTP_USER") or "lectern@localhost"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg["Message-ID"] = make_msgid(domain="lectern")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    if keep:
        sent.append({"to": to, "subject": subject, "body": body})
        del sent[:-20]
    if not configured():
        text = f"\n{body}\n" if env("LECTERN_PRINT_EMAILS") == "1" else ""
        print(f"[lectern] email not sent (no LECTERN_SMTP_HOST) → {to}: {subject}{text}", file=sys.stderr)
        return False
    host, sec = env("LECTERN_SMTP_HOST"), (env("LECTERN_SMTP_SECURITY") or "starttls").lower()
    port = int(env("LECTERN_SMTP_PORT") or (465 if sec == "ssl" else 587))
    try:
        if sec == "ssl":
            s = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(host, port, timeout=20)
            if sec == "starttls":
                s.starttls(context=ssl.create_default_context())
        with s:
            if env("LECTERN_SMTP_USER"):
                s.login(env("LECTERN_SMTP_USER"), env("LECTERN_SMTP_PASSWORD", ""))
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[lectern] email to {to} failed: {e}", file=sys.stderr)
        return False


def send_later(to, subject, body):
    """Send in the background, so the reply doesn't wait for (or reveal anything by) the SMTP server's speed."""
    if keep:   # tests: right away, so they can read it
        return send(to, subject, body)
    threading.Thread(target=send, args=(to, subject, body), daemon=True).start()
    return configured()
