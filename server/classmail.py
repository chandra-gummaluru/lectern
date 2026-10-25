"""Emailing a course offering's class, and each offering's own email (SMTP) settings.

Every student in a gradebook has an email (the grade builder asks for one, at the domain set in its
Settings). An instructor writes a message in Lectern and it goes to the class, or one section: one
email to each student (so nobody sees the others' addresses), from the offering's sender, with replies
going to the instructor who wrote it. Sending happens in the background; the offering's page shows how
it went.

An offering can have its own SMTP settings (its own From, e.g. "CSC258 <csc258@…>"). They're kept here
on the server, not in the gradebook (TAs can read that), with the password encrypted with the server's
key and never sent back to the browser. Without them, the admin panel's (or .env's) are used. They're
also used for the offering's accommodation emails.

  GET  /api/mail/<owner>/<course>/<term>            who'd get it, the settings in use, recent sends   instructors
  POST /api/mail/<owner>/<course>/<term>/settings   { host, port, security, user, smtpPassword, from } (or { action: "remove" })
                                                    saved only after a test email to you goes through
  POST /api/mail/<owner>/<course>/<term>/send       { to: "all" | "section:<name>", subject, body }
"""
import json
import re
import threading
import time

from flask import Blueprint, g, jsonify

from . import db, mailer, security as sec
from .auth import Refusal, body, limiter, log, signed_in, text
from .teams import _where

mail_bp = Blueprint("classmail", __name__)

MAX_SUBJECT = 200
MAX_BODY = 20000
MAX_RECIPIENTS = 3000
SENDS_PER_HOUR = 10
_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
_ADDR = re.compile(r"^[^\s@]+@[a-z0-9-]+(\.[a-z0-9-]+)+$")


# ── Settings ─────────────────────────────────────────────────────────
def _row(owner_id, off):
    return db.one("SELECT * FROM offering_mail WHERE owner_id = ? AND offering = ?", (owner_id, off))


def settings_for(owner_id, off):
    """The SMTP settings an offering's email goes out with: its own, else the server's. Includes the password."""
    r = _row(owner_id, off)
    if r:
        d = json.loads(r["smtp"])
        d["password"] = sec.decrypt(d.pop("password_enc"), "smtp") if d.get("password_enc") else ""
        d["source"] = "offering"
        return d
    return mailer.settings()


def _settings_json(owner_id, off):
    s = settings_for(owner_id, off)
    return {"source": s.get("source") or "", "host": s.get("host") or "", "port": str(s.get("port") or ""),
            "security": s.get("security") or "starttls", "user": s.get("user") or "", "from": s.get("from") or "",
            "hasPassword": bool(s.get("password"))}   # never the password itself


def _instructor(role):
    if role not in ("owner", "coordinator"):
        raise Refusal(403, "Only the offering's instructors can email the class.")


# ── Who's in the class ───────────────────────────────────────────────
def _book(owner_id, off):
    from .store import Repo
    t = Repo(owner_id, "priv").read_text(f"{off}/grades.json")
    if not t or not t[0]:
        return None
    try:
        return json.loads(t[0])
    except ValueError:
        return None


def _section_field(book):
    for f in ((book.get("fields") or {}).get("custom") or []):
        if re.match(r"^\s*sections?\s*$", str(f.get("label") or ""), re.I):
            return f.get("id")
    return None


def roster(book):
    """The enrolled students, each with an email and section, and the ones without a usable email."""
    if not book:
        return {"domain": "", "students": [], "missing": [], "sections": []}
    domain = str((book.get("fields") or {}).get("emailDomain") or "").strip().lower()
    sf = _section_field(book)
    ok, missing = [], []
    for s in book.get("students") or []:
        if s.get("dropped"):
            continue
        f = s.get("f") or {}
        email = str(f.get("email") or s.get("email") or "").strip().lower()
        who = {"num": str(s.get("num") or ""), "name": ", ".join(x for x in (s.get("last"), s.get("first")) if x) or str(s.get("num") or ""),
               "email": email, "section": str(f.get(sf) or "").strip() if sf else ""}
        if _ADDR.match(email) and (not domain or email.endswith("@" + domain)):
            ok.append(who)
        else:
            missing.append(who)
    sections = sorted({x["section"] for x in ok if x["section"]})   # the ones with someone to email
    return {"domain": domain, "students": ok, "missing": missing, "sections": sections}


def _recipients(r, to):
    if to == "all":
        return r["students"]
    if to.startswith("section:"):
        sec_ = to[len("section:"):]
        if sec_ not in r["sections"]:
            raise Refusal(400, "There's no such section.")
        return [x for x in r["students"] if x["section"] == sec_]
    raise Refusal(400, "Send it to whom?")


# ── The API ──────────────────────────────────────────────────────────
def _sends(owner_id, off):
    return [{"id": x["id"], "at": x["at"], "by": x["by_name"], "subject": x["subject"], "to": x["to_label"],
             "total": x["total"], "sent": x["sent"], "failed": x["failed"], "done": bool(x["done"]),
             "errors": json.loads(x["errors"] or "{}")}
            for x in db.all_("SELECT * FROM mail_sends WHERE owner_id = ? AND offering = ? ORDER BY at DESC LIMIT 10", (owner_id, off))]


@mail_bp.get("/api/mail/<owner>/<course>/<term>")
@signed_in
def overview(owner, course, term):
    o, off, role = _where(owner, course, term)
    _instructor(role)
    r = roster(_book(o["id"], off))
    counts = {s: sum(1 for x in r["students"] if x["section"] == s) for s in r["sections"]}
    return jsonify(settings=_settings_json(o["id"], off), domain=r["domain"], total=len(r["students"]),
                   missing=[{"num": x["num"], "name": x["name"], "email": x["email"]} for x in r["missing"]][:200],
                   missingCount=len(r["missing"]), sections=[{"name": s, "count": counts[s]} for s in r["sections"]],
                   sends=_sends(o["id"], off), you=g.user["email"])


@mail_bp.post("/api/mail/<owner>/<course>/<term>/settings")
@signed_in
def set_settings(owner, course, term):
    o, off, role = _where(owner, course, term)
    _instructor(role)
    d = body()
    if d.get("action") == "remove":
        db.run("DELETE FROM offering_mail WHERE owner_id = ? AND offering = ?", (o["id"], off))
        log(g.user["id"], "class-mail-settings-removed", off)
        return jsonify(ok=True, settings=_settings_json(o["id"], off))
    if not limiter.ok(f"mail-settings:{g.user['id']}", 20, 3600):
        raise Refusal(429, "That's a lot of tries. Wait a while and try again.", "rate")
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
    if not pw:   # blank: keep the one it has (never shown)
        r = _row(o["id"], off)
        pw = settings_for(o["id"], off).get("password", "") if r else ""
    cfg = {"host": host, "port": port, "security": security, "user": user, "from": frm, "password": pw}
    err = mailer.deliver(g.user["email"], f"Lectern: email for {off} works",
                         f"Hi {g.user['name'] or g.user['email']},\n\nThis is the test email for {off}'s email settings in Lectern: "
                         f"it can send through {host}.\n", cfg=cfg)
    if err:
        raise Refusal(400, f"The test email didn't go through, so nothing was saved: {err}", "smtp")
    stored = {k: cfg[k] for k in ("host", "port", "security", "user", "from")}
    if pw:
        stored["password_enc"] = sec.encrypt(pw, "smtp")
    db.run("""INSERT INTO offering_mail (owner_id, offering, smtp, updated, updated_by) VALUES (?, ?, ?, ?, ?)
              ON CONFLICT(owner_id, offering) DO UPDATE SET smtp = excluded.smtp, updated = excluded.updated, updated_by = excluded.updated_by""",
           (o["id"], off, json.dumps(stored), time.time(), g.user["id"]))
    log(g.user["id"], "class-mail-settings", f"{off} {host}")
    return jsonify(ok=True, settings=_settings_json(o["id"], off))


@mail_bp.post("/api/mail/<owner>/<course>/<term>/send")
@signed_in
def send(owner, course, term):
    o, off, role = _where(owner, course, term)
    _instructor(role)
    d = body()
    subject = text(d, "subject", MAX_SUBJECT + 50).strip()
    msg = text(d, "body", MAX_BODY + 1000).replace("\r\n", "\n").strip()
    to = text(d, "to", 200).strip() or "all"
    if not subject or not msg:
        raise Refusal(400, "Write a subject and a message.")
    if len(subject) > MAX_SUBJECT or len(msg) > MAX_BODY:
        raise Refusal(400, f"That's too long: a subject up to {MAX_SUBJECT} characters, a message up to {MAX_BODY}.")
    if "\n" in subject or "\r" in subject:
        raise Refusal(400, "The subject is one line.")
    cfg = settings_for(o["id"], off)
    if not cfg.get("host"):
        raise Refusal(400, "Email isn't set up: set it up for this offering (or ask your Lectern admin to).", "no-smtp")
    people = _recipients(roster(_book(o["id"], off)), to)
    if not people:
        raise Refusal(400, "Nobody to send it to: no student there has an email yet.")
    if len(people) > MAX_RECIPIENTS:
        raise Refusal(413, f"That's more than {MAX_RECIPIENTS} people.")
    if not limiter.ok(f"class-mail:{o['id']}:{off}", SENDS_PER_HOUR, 3600):
        raise Refusal(429, f"That's {SENDS_PER_HOUR} emails to the class this hour. Wait a while and send again.", "rate")
    label = "Everyone" if to == "all" else f"Section {to[len('section:'):]}"
    with db.transaction() as c:
        cur = c.execute("""INSERT INTO mail_sends (owner_id, offering, by_user, by_name, at, subject, to_label, total)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (o["id"], off, g.user["id"], g.user["name"] or g.user["email"], time.time(), subject, label, len(people)))
        sid = cur.lastrowid
    log(g.user["id"], "class-mail", f"{off} {label} {len(people)}")
    addrs = [p["email"] for p in people]
    reply = g.user["email"]

    def run():
        counts = {"sent": 0, "failed": 0}

        def done(addr, err):
            counts["failed" if err else "sent"] += 1
            if (counts["sent"] + counts["failed"]) % 20 == 0:
                db.run("UPDATE mail_sends SET sent = ?, failed = ? WHERE id = ?", (counts["sent"], counts["failed"], sid))
        failed = mailer.deliver_many(addrs, subject, msg, reply_to=reply, cfg=cfg, done=done)
        db.run("UPDATE mail_sends SET sent = ?, failed = ?, done = 1, errors = ? WHERE id = ?",
               (counts["sent"], counts["failed"], json.dumps(dict(list(failed.items())[:50])), sid))

    if mailer.keep:   # tests: right away
        run()
    else:
        threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True, id=sid, total=len(people), to=label)
