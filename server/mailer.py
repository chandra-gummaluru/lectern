"""Email to students (accommodation requests), over SMTP.

Settings (environment variables, or .env beside app.py):
  LECTERN_SMTP_HOST       e.g. smtp.gmail.com
  LECTERN_SMTP_PORT       587 (STARTTLS, the default) or 465 (SSL)
  LECTERN_SMTP_USER       the login
  LECTERN_SMTP_PASSWORD   its password (for Gmail, an app password)
  LECTERN_SMTP_FROM       the From address, e.g. "Lectern <lectern@changapp.net>" (default: the login)
  LECTERN_SMTP_SECURITY   starttls (default), ssl or none

Without a host, nothing is sent: the message is printed to the server's log instead (handy
while developing), and send() returns False so the caller can say so.
"""
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import make_msgid

sent = []   # tests read this; the last few messages, newest last


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
    sent.append({"to": to, "subject": subject, "body": body})
    del sent[:-20]
    if not configured():
        print(f"[lectern] email not sent (no LECTERN_SMTP_HOST) → {to}: {subject}\n{body}\n", file=sys.stderr)
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
