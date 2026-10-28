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


# Which automatic emails go to students (each on unless turned off), where replies go, and a sign-off.
SEND_KINDS = ("grades", "accomReceipts", "accomDecisions", "remarkReceipts", "remarkDecisions", "announcements")


def prefs_for(owner_id, off):
    r = db.one("SELECT prefs FROM offering_mail_prefs WHERE owner_id = ? AND offering = ?", (owner_id, off))
    try:
        d = json.loads(r["prefs"]) if r else {}
    except ValueError:
        d = {}
    send = d.get("send") if isinstance(d.get("send"), dict) else {}
    return {"replyTo": str(d.get("replyTo") or ""), "signature": str(d.get("signature") or ""),
            "send": {k: send.get(k) is not False for k in SEND_KINDS}}


def student_mail(owner_id, off, to, subject, text_, kind, reply_to=None):
    """One email to a student from the offering, if that kind is on: its reply-to and signature added.
    True if it went out."""
    p = prefs_for(owner_id, off)
    if kind and not p["send"].get(kind, True):
        return False
    return mailer.send(to, subject, signed(p, text_), reply_to=p["replyTo"] or reply_to, cfg=settings_for(owner_id, off))


def signed(p, text_):
    """The email with the offering's signature at the end. The signature is rich text (the Markdown of
    richtext.js: **bold**, *italic*, [text](url), "- " and "1. " lists): the plain-text email gets it as
    readable text, and an HTML part (mailer.Mail.html) gets it drawn."""
    sig = (p.get("signature") or "").strip()
    if not sig:
        return text_
    return mailer.Mail(f"{text_.rstrip()}\n\n{md_plain(sig)}\n",
                       html=f"{text_html(text_)}<br>{md_html(sig)}")


_LINK = re.compile(r"\[([^\]]*)\]\(((?:https?://|mailto:)[^)\s]+)\)")


def md_plain(md):
    md = _LINK.sub(lambda m: m.group(1) if m.group(1) == m.group(2) else f"{m.group(1)} ({m.group(2)})", md)
    return re.sub(r"\*\*(.+?)\*\*|\*(.+?)\*", lambda m: m.group(1) or m.group(2), md)


def _esc(x):
    return x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _inline(x):
    out, at = [], 0
    for m in _LINK.finditer(x):
        out.append(_esc(x[at:m.start()]))
        out.append(f'<a href="{_esc(m.group(2))}">{_esc(m.group(1))}</a>')
        at = m.end()
    out.append(_esc(x[at:]))
    h = "".join(out)
    h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
    return re.sub(r"\*(.+?)\*", r"<i>\1</i>", h).replace("\n", "<br>")


def md_html(md):
    parts = []
    for blk in re.split(r"\n\s*\n", md.strip()):
        lines = blk.split("\n")
        if all(re.match(r"\s*[-*] ", l) for l in lines):
            parts.append("<ul>" + "".join("<li>" + _inline(re.sub(r"^\s*[-*] ", "", l)) + "</li>" for l in lines) + "</ul>")
        elif all(re.match(r"\s*\d+[.)] ", l) for l in lines):
            parts.append("<ol>" + "".join("<li>" + _inline(re.sub(r"^\s*\d+[.)] ", "", l)) + "</li>" for l in lines) + "</ol>")
        else:
            parts.append(f"<p style=\"margin:0 0 10px\">{_inline(blk)}</p>")
    return "".join(parts)


def text_html(t):
    return "".join('<p style="margin:0 0 10px">' + _esc(b).replace("\n", "<br>") + "</p>" for b in re.split(r"\n\s*\n", t.strip()))


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
                   sends=_sends(o["id"], off), you=g.user["email"], prefs=prefs_for(o["id"], off))


@mail_bp.get("/api/mail/<owner>/<course>/<term>/prefs")
@signed_in
def get_prefs(owner, course, term):   # anyone on the teaching team (e.g. whether an announcement is emailed by default)
    o, off, role = _where(owner, course, term)
    return jsonify(prefs=prefs_for(o["id"], off))


@mail_bp.post("/api/mail/<owner>/<course>/<term>/prefs")
@signed_in
def set_prefs(owner, course, term):
    o, off, role = _where(owner, course, term)
    _instructor(role)
    d = body()
    reply = text(d, "replyTo", 254).strip()
    if reply and not _ADDR.match(reply.lower()):
        raise Refusal(400, "Replies go to an email address, e.g. csc258@utoronto.ca.", "replyTo")
    sig = text(d, "signature", 2000).replace("\r\n", "\n").strip()
    send = d.get("send") if isinstance(d.get("send"), dict) else {}
    prefs = {"replyTo": reply, "signature": sig, "send": {k: bool(send.get(k, True)) for k in SEND_KINDS}}
    db.run("""INSERT INTO offering_mail_prefs (owner_id, offering, prefs, updated) VALUES (?, ?, ?, ?)
              ON CONFLICT(owner_id, offering) DO UPDATE SET prefs = excluded.prefs, updated = excluded.updated""",
           (o["id"], off, json.dumps(prefs), time.time()))
    log(g.user["id"], "class-mail-prefs", off)
    return jsonify(ok=True, prefs=prefs_for(o["id"], off))


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
    pf = prefs_for(o["id"], off)
    reply, msg = pf["replyTo"] or g.user["email"], signed(pf, msg)

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


# ── An announcement, emailed when it's saved ─────────────────────────
#   POST /api/mail/<owner>/<course>/<term>/announcement   { title, body, groups: [section ids] }
# To the students it's for: everyone (no sections), or the students in those sections. The coordinators
# email anyone; instructors and TAs, the students of sections they run. Without email set up, nothing
# is sent (and it says so): the announcement is saved either way.
@mail_bp.post("/api/mail/<owner>/<course>/<term>/announcement")
@signed_in
def announce(owner, course, term):
    from .students import roster as class_list, hub_url
    from .teams import LEAD, my_groups
    o, off, role = _where(owner, course, term)
    d = body()
    title = text(d, "title", MAX_SUBJECT + 50).strip() or "Announcement"
    msg = text(d, "body", MAX_BODY + 1000).replace("\r\n", "\n").strip()
    groups = [str(x)[:64] for x in (d.get("groups") if isinstance(d.get("groups"), list) else []) if str(x).strip()][:50]
    if role not in LEAD:
        mine = my_groups(g.user["id"], o["id"], off) if role in ("instructor", "ta") else set()
        if not groups or not set(groups) <= mine:
            raise Refusal(403, "You can email the students of the sections you run.")
    if len(title) > MAX_SUBJECT or len(msg) > MAX_BODY:
        raise Refusal(400, f"That's too long to email: a title up to {MAX_SUBJECT} characters, a message up to {MAX_BODY}.")
    cfg = settings_for(o["id"], off)
    if not cfg.get("host"):
        return jsonify(ok=True, emailed=False, total=0, why="Email isn't set up for this offering, so it wasn't emailed.")
    by_email = class_list(o["id"], off)   # each student's sections
    people = [x["email"] for x in roster(_book(o["id"], off))["students"]
              if not groups or set((by_email.get(x["email"]) or {}).get("groups") or []) & set(groups)]
    if not people:
        return jsonify(ok=True, emailed=False, total=0, why="Nobody to email: no student it's for has an email yet.")
    if len(people) > MAX_RECIPIENTS:
        raise Refusal(413, f"That's more than {MAX_RECIPIENTS} people.")
    if not limiter.ok(f"class-mail:{o['id']}:{off}", SENDS_PER_HOUR, 3600):
        raise Refusal(429, f"That's {SENDS_PER_HOUR} emails to the class this hour. It's saved; email it later.", "rate")
    subject = f"{course.upper()}: {title}"[:MAX_SUBJECT + 20]
    text_ = f"{msg}\n\n—\nOn the course page: {hub_url(o, off)}#announcements\n"
    label = "Everyone" if not groups else f"{len(groups)} section{'s' if len(groups) > 1 else ''}"
    with db.transaction() as c:
        sid = c.execute("""INSERT INTO mail_sends (owner_id, offering, by_user, by_name, at, subject, to_label, total)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (o["id"], off, g.user["id"], g.user["name"] or g.user["email"], time.time(), subject, label, len(people))).lastrowid
    log(g.user["id"], "announcement-mail", f"{off} {label} {len(people)}")
    pf = prefs_for(o["id"], off)
    reply, text_ = pf["replyTo"] or g.user["email"], signed(pf, text_)

    def run():
        counts = {"sent": 0, "failed": 0}

        def done(addr, err):
            counts["failed" if err else "sent"] += 1
        failed = mailer.deliver_many(people, subject, text_, reply_to=reply, cfg=cfg, done=done)
        db.run("UPDATE mail_sends SET sent = ?, failed = ?, done = 1, errors = ? WHERE id = ?",
               (counts["sent"], counts["failed"], json.dumps(dict(list(failed.items())[:50])), sid))

    if mailer.keep:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True, emailed=True, total=len(people), to=label)


# ── Marks: released to students, and emailed when they're out or changed ────────────────
# An evaluation's marks show on the course page only once the gradebook says so (its "released"). Saving
# the gradebook emails the students whose mark is out and who haven't been told; a mark changed after
# they were told waits for an instructor's Email Them (so editing cell by cell doesn't send a stream).
#   GET  /api/mail/<owner>/<course>/<term>/grades            { evals: { id: { released, told, waiting, changed } } }
#   POST /api/mail/<owner>/<course>/<term>/grades            {} (what's newly out) or { e, changes: true }
def _mark(m):
    """A mark as it's compared (and kept): its points or what happened; None if there isn't one."""
    if not isinstance(m, dict):
        return None
    st = m.get("status") or ("missed" if m.get("missed") else "")
    if st:
        return json.dumps({"status": st})
    return json.dumps({"pts": m["pts"]}) if isinstance(m.get("pts"), (int, float)) else None


def _grade_state(owner_id, off, book):
    told = {}
    for r in db.all_("SELECT eval_id, num, mark FROM grade_notices WHERE owner_id = ? AND offering = ?", (owner_id, off)):
        told[(r["eval_id"], r["num"])] = r["mark"]
    marks = book.get("marks") if isinstance(book.get("marks"), dict) else {}
    people = roster(book)["students"]
    out = {}
    for e in book.get("evals") or []:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        eid, w, c, n = e["id"], [], [], 0
        for p in people:
            m = _mark((marks.get(p["num"]) or {}).get(eid))
            was = told.get((eid, p["num"]))
            n += was is not None
            if m is None:
                continue
            if was is None:
                w.append((p, m))
            elif was != m:
                c.append((p, m))
        out[eid] = {"e": e, "released": e.get("released") is True, "told": n, "waiting": w, "changed": c}
    return out


@mail_bp.get("/api/mail/<owner>/<course>/<term>/grades")
@signed_in
def grade_notices(owner, course, term):
    o, off, role = _where(owner, course, term)
    book = _book(o["id"], off) or {}
    st = _grade_state(o["id"], off, book)
    return jsonify(evals={k: {"released": v["released"], "told": v["told"], "waiting": len(v["waiting"]), "changed": len(v["changed"])} for k, v in st.items()},
                   on=prefs_for(o["id"], off)["send"]["grades"])


@mail_bp.post("/api/mail/<owner>/<course>/<term>/grades")
@signed_in
def notify_grades(owner, course, term):
    from .students import hub_url
    o, off, role = _where(owner, course, term)
    _instructor(role)
    d = body()
    book = _book(o["id"], off) or {}
    st = _grade_state(o["id"], off, book)
    one = text(d, "e", 64).strip()
    if one and (one not in st or not st[one]["released"]):
        raise Refusal(400, "Its marks aren't visible to students yet: tick that, and save the gradebook.")
    pf, cfg = prefs_for(o["id"], off), settings_for(o["id"], off)
    code = str((book.get("course") or {}).get("code") or course.upper())
    jobs, t = [], time.time()
    for eid, v in st.items():
        if not v["released"] or (one and eid != one):
            continue
        name = str(v["e"].get("name") or v["e"].get("title") or eid)
        link = f"{hub_url(o, off)}#evaluation/{eid}"
        for kind, who in (("released", v["waiting"]), ("updated", v["changed"] if one and d.get("changes") else [])):
            if not who:
                continue
            subject = f"{code}: your mark for {name} is out" if kind == "released" else f"{code}: your mark for {name} has changed"
            msg = (f"Your mark for {name} is now on the course page." if kind == "released"
                   else f"Your mark for {name} has been updated.") + f"\n\nSee it here: {link}\n"
            jobs.append(([p["email"] for p, _ in who], subject, signed(pf, msg)))
            with db.transaction() as c:
                for p, m in who:
                    c.execute("""INSERT INTO grade_notices (owner_id, offering, eval_id, num, mark, at) VALUES (?, ?, ?, ?, ?, ?)
                                 ON CONFLICT(owner_id, offering, eval_id, num) DO UPDATE SET mark = excluded.mark, at = excluded.at""",
                              (o["id"], off, eid, p["num"], m, t))
    total = sum(len(j[0]) for j in jobs)
    if not total:
        return jsonify(ok=True, emailed=0)
    if not pf["send"]["grades"] or not cfg.get("host"):   # kept as told, so turning it on later doesn't send old news
        return jsonify(ok=True, emailed=0, why="Emails about marks are off." if not pf["send"]["grades"] else "Email isn't set up for this offering.")
    log(g.user["id"], "grade-mail", f"{off} {total}")
    reply = pf["replyTo"] or g.user["email"]

    def run():
        for addrs, subject, msg in jobs:
            mailer.deliver_many(addrs, subject, msg, reply_to=reply, cfg=cfg)

    if mailer.keep:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True, emailed=total)
