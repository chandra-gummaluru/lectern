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
import html as _html
import json
import os
import re
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


class Mail(str):
    """A plain-text email body that also has an HTML version (.html), sent as its alternative, and what
    heads it (.head: {"title": "CSC258: Computer Organization", "sub": "Winter 2027 · University of Toronto"};
    without one, Lectern's own)."""
    def __new__(cls, text, html="", head=None):
        o = super().__new__(cls, text)
        o.html = html or getattr(text, "html", "")
        o.head = head or getattr(text, "head", None)
        return o


def _message(cfg, to, subject, body, reply_to=None):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg.get("from") or cfg.get("user") or "lectern@localhost", to, subject
    msg["Message-ID"] = make_msgid(domain="lectern")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(str(body))
    msg.add_alternative(page(subject, getattr(body, "html", "") or to_html(str(body)), getattr(body, "head", None),
                             preview=_preview(str(body))), subtype="html")
    if keep:
        sent.append({"to": to, "subject": subject, "body": str(body), "html": getattr(body, "html", ""), "from": msg["From"], "reply_to": reply_to or ""})
        del sent[:-20]
    return msg


# ── How every email looks ─────────────────────────────────────────────
# How every email reads (docs/ui-patterns.md, "Emails"):
#   Subject   "<who>: <what>", sentence case: Lectern for an account's emails, the course code for a
#             course's ("CSC258: your mark for Test 1 is out"). A code goes first ("12345678 is your
#             code for …") so phones can offer it.
#   Greeting  hi(name): "Hi Maya," or "Hi,". No sign-off: the header says who it's from.
#   Action    one per email: a sentence ending in ":", then the link on a line of its own (a button).
#             How long it works, in that sentence ("within an hour").
#   Unasked   "If you didn't ask for this, you can ignore this email." (or "weren't expecting this").
#   Facts     a reference and the like go last, under "—" (a rule, small and grey).
# One layout for all of Lectern's emails, in the splash's style (splash.css): sage paper, a white card
# with a thin outline, the sender's name in the serif over a short gold rule, and the main link as
# Lectern's button (white, outlined in black). Plain text stays the email's first part; the HTML is
# made from it (to_html), so the emails are written once, as text. Inline styles and tables only:
# email programs ignore style sheets and most of CSS.
INK, INK2, INK3, LINE, PAPER, GOLD, GOLD_BG, GOLD_LINE = "#1c211d", "#4d564f", "#7d857e", "#dcdfd6", "#f3f4ef", "#a67c00", "#fbf3d9", "#ecd58f"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
SERIF = "'EB Garamond',Garamond,Georgia,'Times New Roman',serif"
MONO = "ui-monospace,Menlo,Consolas,'Courier New',monospace"
# A link on a line of its own becomes a button; what it says, by where it goes.
BUTTONS = ((r"^https?://[^/#?]+/?$", "Open Lectern"), (r"#myrequest/", "Open Your Request"), (r"#reset=", "Choose a New Password"), (r"#invite=", "Create Your Account"), (r"#join=", "Join the Teaching Team"),
           (r"#evaluation/", "See Your Mark"), (r"/c/[^#\s]*#announcements", "Open the Course Page"), (r"/c/", "Open the Course Page"))
_URL = re.compile(r"(?<![\w\"'=(])((?:https?://)[^\s<>()]+[^\s<>().,;:!?'\"])")
_MDLINK = re.compile(r"\[([^\]]*)\]\(((?:https?://|mailto:)[^)\s]+)\)")
_A = f"color:{INK};text-decoration:underline;text-decoration-color:{GOLD};text-underline-offset:3px"


def hi(name=""):
    """The greeting: "Hi Maya," (the first name) or, without one, "Hi,"."""
    first = str(name or "").strip().split(" ")[0] if name and "@" not in str(name) else ""
    if first and first == first.lower():
        first = first[:1].upper() + first[1:]
    return f"Hi {first}," if first else "Hi,"


def _inline(x):
    """One paragraph's text as HTML: escaped, with **bold**, *italic*, [text](url) and bare links."""
    out, at = [], 0
    for m in _MDLINK.finditer(x):
        out.append(_bare(x[at:m.start()]))
        out.append(f'<a href="{_html.escape(m.group(2))}" style="{_A}">{_html.escape(m.group(1))}</a>')
        at = m.end()
    out.append(_bare(x[at:]))
    h = "".join(out)
    h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
    h = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", h)
    return h.replace("\n", "<br>")


def _bare(x):
    return _URL.sub(lambda m: f'<a href="{m.group(1)}" style="{_A}">{m.group(1)}</a>', _html.escape(x, quote=False))


def _button(url):
    label = next((l for pat, l in BUTTONS if re.search(pat, url)), "Open the Link")
    u = _html.escape(url)
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 18px"><tr>'
            f'<td style="border:1.5px solid {INK};border-radius:9px;background:#ffffff">'
            f'<a href="{u}" style="display:inline-block;padding:12px 22px;font:600 15px/1 {SANS};color:{INK};text-decoration:none">{_html.escape(label)}</a>'
            f'</td></tr></table>'
            f'<p style="margin:0 0 18px;font:12.5px/1.5 {SANS};color:{INK3};word-break:break-all">Or copy this link: <a href="{u}" style="color:{INK3}">{u}</a></p>')


def to_html(text):
    """A plain-text (or Markdown) email body as HTML: paragraphs, lists, links; a link on its own line
    as a button; a code on its own (indented) line in a box; an indented passage (what someone wrote)
    as a quote; a line of just "—" as a rule."""
    P = f"margin:0 0 14px;font:15px/1.6 {SANS};color:{INK}"
    out = []
    for blk in re.split(r"\n[ \t]*\n", str(text).strip("\n")):
        if not blk.strip():
            continue
        lines = blk.split("\n")
        one = blk.strip()
        if lines[0].strip() == "—" or lines[0].strip() == "--":   # a rule, then (often) a footnote under it
            out.append(f'<hr style="border:0;border-top:1px solid {LINE};margin:22px 0 14px">')
            rest = "\n".join(lines[1:]).strip()
            m = re.fullmatch(r"([^\n:]{1,60}):\s*(https?://\S+)", rest)   # "On the course page: <link>": the words are the link
            if m:
                out.append(f'<p style="margin:0 0 14px;font:13.5px/1.6 {SANS};color:{INK3}"><a href="{_html.escape(m.group(2))}" style="{_A}">{_html.escape(m.group(1))}</a></p>')
            elif rest:
                out.append(f'<p style="margin:0 0 14px;font:13.5px/1.6 {SANS};color:{INK3}">{_inline(rest)}</p>')
            continue
        if len(lines) == 1 and _URL.fullmatch(one):
            out.append(_button(one))
            continue
        if len(lines) == 1 and blk[:1] in " \t" and re.fullmatch(r"[A-Za-z0-9-]{4,16}", one):   # a code
            # Centred, and the whole code selected by one click or tap (email can't run a Copy button).
            out.append(f'<div style="margin:8px 0 6px;text-align:center"><span style="display:inline-block;padding:16px 26px 16px 30px;border:1px solid {GOLD_LINE};'
                       f'border-radius:12px;background:{GOLD_BG};font:600 32px/1 {MONO};letter-spacing:.24em;color:{INK};'
                       f'-webkit-user-select:all;user-select:all;cursor:text">{_html.escape(one)}</span></div>'
                       f'<p style="margin:0 0 20px;text-align:center;font:12.5px/1.5 {SANS};color:{INK3}">Click or tap the code once to select all of it, then copy.</p>')
            continue
        if all(l.startswith(("    ", "\t")) or not l.strip() for l in lines):   # what someone wrote, quoted
            inner = re.sub(r"(?m)^(    |\t)", "", blk)
            out.append(f'<div style="margin:0 0 16px;padding:14px 16px 1px;border-radius:10px;background:{PAPER};font:15px/1.6 {SANS};color:{INK2}">'
                       f'{to_html(inner).replace(f"color:{INK}", f"color:{INK2}")}</div>')
            continue
        if all(re.match(r"\s*[-*] ", l) for l in lines):
            out.append(f'<ul style="margin:0 0 14px;padding-left:22px;font:15px/1.6 {SANS};color:{INK}">'
                       + "".join("<li>" + _inline(re.sub(r"^\s*[-*] ", "", l)) + "</li>" for l in lines) + "</ul>")
            continue
        if all(re.match(r"\s*\d+[.)] ", l) for l in lines):
            out.append(f'<ol style="margin:0 0 14px;padding-left:22px;font:15px/1.6 {SANS};color:{INK}">'
                       + "".join("<li>" + _inline(re.sub(r"^\s*\d+[.)] ", "", l)) + "</li>" for l in lines) + "</ol>")
            continue
        m = re.fullmatch(r"(.*\S):\s*(https?://\S+)", one, re.S)   # "See it here: <link>": the sentence, then the button
        if m and "\n" not in m.group(1) and _URL.fullmatch(m.group(2)):
            out.append(f'<p style="{P}">{_inline(m.group(1))}:</p>{_button(m.group(2))}')
            continue
        out.append(f'<p style="{P}">{_inline(blk.strip())}</p>')
    return "".join(out)


def _preview(text):
    """The line an inbox shows beside the subject: the code, if there's one, else the message's first words."""
    m = re.search(r"(?m)^[ \t]+([A-Za-z0-9-]{4,16})[ \t]*$", text)
    if m and re.search(r"\d", m.group(1)):
        return f"Your code is {m.group(1)}"
    for line in text.splitlines():
        t = line.strip()
        if t and not re.match(r"^(Hi|Hello|Dear)\b.{0,60},$", t):
            return re.sub(r"\*\*|\[([^\]]*)\]\([^)]*\)", lambda x: x.group(1) or "", t)[:140]
    return ""


def page(subject, inner, head=None, preview=""):
    """The whole HTML email, as the course page looks: a white card headed by the course's name in the
    serif and its term and school in small capitals (or Lectern's, for an account's emails), a rule,
    then the subject as the title and the message."""
    school = os.environ.get("LECTERN_INSTITUTION", "University of Toronto")
    head = head or {"title": "Lectern", "sub": school, "school": school}
    name, sub = str(head.get("title") or "Lectern"), str(head.get("sub") or "")
    title = re.sub(r"^Lectern:\s*", "", subject or "")
    code = name.split(":")[0].strip()
    for pre in (name, code):   # the course is already in the header
        if pre and title.lower().startswith(pre.lower() + ":"):
            title = title[len(pre) + 1:].strip()
            break
    title = title[:1].upper() + title[1:]
    if re.match(r"^\d{4,}\b", title):   # "12345678 is your code for …": the code is in the message
        title = "Your code to send your request" if "send your request" in title else "Your sign-in code"
    h1 = f'<h1 style="margin:0 0 18px;font:500 24px/1.25 {SERIF};letter-spacing:-.005em;color:{INK}">{_html.escape(title)}</h1>'
    who = " ".join(x for x in (head.get("code"), head.get("term")) if x)
    at = f" at {_html.escape(head['school'])}" if head.get("school") else ""
    foot = f"Sent with Lectern for {_html.escape(who)}{at}." if who else f"Sent with Lectern{at}."
    subline = f'<div style="margin-top:6px;font:600 11.5px/1.4 {SANS};letter-spacing:.1em;text-transform:uppercase;color:{INK3}">{_html.escape(sub)}</div>' if sub else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><title>{_html.escape(subject or "")}</title></head>
<body style="margin:0;padding:0;background:{PAPER};-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{_html.escape(preview or name)}&#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAPER}"><tr><td align="center" style="padding:36px 14px 40px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;background:#ffffff;border:1px solid {LINE};border-radius:14px;border-collapse:separate">
<tr><td style="padding:28px 34px 22px;border-bottom:1px solid {LINE}">
<div style="font:500 26px/1.15 {SERIF};letter-spacing:-.015em;color:{INK}">{_html.escape(name)}</div>{subline}</td></tr>
<tr><td style="padding:28px 34px 16px;font:15px/1.6 {SANS};color:{INK}">{h1}{inner}</td></tr>
</table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px"><tr>
<td style="padding:16px 6px 0;font:12px/1.6 {SANS};color:{INK3};text-align:center">{foot}</td></tr></table>
</td></tr></table></body></html>"""


def _connect(cfg):
    host, sec = cfg["host"], (cfg.get("security") or "starttls").lower()
    port = int(cfg.get("port") or (465 if sec == "ssl" else 587))
    if sec == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
    else:
        s = smtplib.SMTP(host, port, timeout=20)
        if sec == "starttls":
            s.starttls(context=ssl.create_default_context())
    if cfg.get("user"):
        s.login(cfg["user"], cfg.get("password") or "")
    return s


def deliver(to, subject, body, reply_to=None, cfg=None):
    """Send one plain-text email. Returns "" if it went out, else what went wrong."""
    cfg = cfg or settings()
    msg = _message(cfg, to, subject, body, reply_to)
    if not cfg.get("host"):
        text = f"\n{body}\n" if os.environ.get("LECTERN_PRINT_EMAILS") == "1" else ""
        print(f"[lectern] email not sent (no SMTP settings) → {to}: {subject}{text}", file=sys.stderr)
        return "Email isn't set up."
    try:
        with _connect(cfg) as s:
            s.send_message(msg)
        return ""
    except Exception as e:
        print(f"[lectern] email to {to} failed: {e}", file=sys.stderr)
        return str(e) or type(e).__name__


def deliver_many(to_list, subject, body, reply_to=None, cfg=None, done=None):
    """The same email to each address, one at a time (nobody sees the others), over one connection
    (opened again if it drops). done(address, error) after each. Returns {address: error} for those that failed."""
    cfg = cfg or settings()
    failed, conn = {}, None
    for to in to_list:
        msg = _message(cfg, to, subject, body, reply_to)
        err = ""
        if not cfg.get("host"):
            err = "Email isn't set up."
        else:
            for attempt in (1, 2):
                try:
                    conn = conn or _connect(cfg)
                    conn.send_message(msg)
                    err = ""
                    break
                except smtplib.SMTPRecipientsRefused as e:
                    err = str(e)
                    break
                except Exception as e:
                    err = str(e) or type(e).__name__
                    try:
                        conn and conn.close()
                    except Exception:
                        pass
                    conn = None
        if err:
            failed[to] = err
        if done:
            done(to, err)
    try:
        conn and conn.quit()
    except Exception:
        pass
    return failed


def send(to, subject, body, reply_to=None, cfg=None):
    """Send one plain-text email. Returns True if it went out."""
    return deliver(to, subject, body, reply_to, cfg) == ""


def send_later(to, subject, body):
    """Send in the background, so the reply doesn't wait for (or reveal anything by) the SMTP server's speed."""
    if keep:   # tests: right away, so they can read it
        return send(to, subject, body)
    threading.Thread(target=send, args=(to, subject, body), daemon=True).start()
    return configured()
