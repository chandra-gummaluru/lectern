"""Moving a course offering in and out of Lectern: Export, Import, and the demo course.

Export (GET /api/offerings/<owner>/<course>/<term>/export) makes a .zip of one offering for its instructors:
its course page and files (pub/), and its gradebook, activities, sections and exams (priv/), each relative to
the offering's folder, with lectern-export.json saying what it is. What belongs to this term's students is
left out, so the file can be shared with a colleague: the class list, marks and accommodations (and finals)
from the gradebook, accommodation and remark requests, announcements, and who on the team runs which section
(team.json, and the people in groups.json, are this server's accounts). Discussions, attendance and sign-ins
are in the database, not in the files, so they never go.

Import (POST /api/offerings/import, with /import/peek first to read a file's manifest) brings an export in as
a new offering of the signed-in account, under any code and term that account doesn't have yet. The same
things are left out again (a file can be made by hand), and with "move the dates" every date moves by whole
weeks from the old term to the new one, so each activity and evaluation keeps its weekday.

The demo (POST /api/offerings/demo) is sample-data/demo-course, a generic made-up course (DEMO101, "A Sample
Course"), loaded as demo101 in the current term: the same date move, with its students (emails at example.com,
which takes no mail) and the marks of the evaluations whose dates have passed, released, so every part of
Lectern has something in it.
"""
import io
import json
import os
import re
import zipfile
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request, send_file

from . import db
from .auth import Refusal, signed_in, text
from .store import Repo, StoreError, clean_path
from .teams import LEAD, _where, clean_offering

transfer_bp = Blueprint("transfer", __name__)

FORMAT = "lectern-export/1"
MANIFEST = "lectern-export.json"
MAX_FILES = 5000
MAX_BYTES = 512 * 1024 * 1024   # unzipped
# The offering's own files that are this term's students' (or this server's accounts'), never exported or imported.
LEFT_OUT = {"accommodations.json", "announcements.json", "team.json"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_TERM = "f26"           # sample-data/demo-course: its dates are Fall 2026's
DEMO_COURSE = "demo101"

_TERM = re.compile(r"^([wsf])(\d\d)$")
_ISO = re.compile(r"^(\d{4})-(\d\d)-(\d\d)$")
_MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# "Sep 7, 2026, 09:00" (an announcement's stamp), the whole string
_STAMP = re.compile(r"^([A-Z][a-z]{2})[a-z]*\.? (\d{1,2}), (\d{4})(.*)$")
# "Wednesday, October 28, 2026" (an exam's date, in exam.json and its .tex files), anywhere
_LONG = re.compile(r"\b(?:(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), )?(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (\d{4})\b")


# ── Terms and dates ──────────────────────────────────────────────────
def term_name(t):
    m = _TERM.match(t or "")
    return f"{dict(w='Winter', s='Summer', f='Fall')[m.group(1)]} 20{m.group(2)}" if m else t


def term_now(today=None):
    """The term today is in (or the next one, between terms): f26, w27, s27."""
    d = today or date.today()
    return f"{'w' if d.month <= 4 else 's' if d.month <= 8 else 'f'}{d.year % 100:02d}"


def term_monday(t):
    """The first Monday of a term's first month (January, May or September): where its weeks are counted from."""
    m = _TERM.match(t or "")
    if not m:
        return None
    d = date(2000 + int(m.group(2)), {"w": 1, "s": 5, "f": 9}[m.group(1)], 1)
    return d + timedelta(days=(7 - d.weekday()) % 7)


def weeks_between(a, b):
    """How many whole weeks term b is after term a (0 if either isn't a term)."""
    x, y = term_monday(a), term_monday(b)
    return round((y - x).days / 7) if x and y else 0


def _shift_iso(s, days):
    m = _ISO.match(s)
    if not m:
        return s
    try:
        return (date(int(m.group(1)), int(m.group(2)), int(m.group(3))) + timedelta(days=days)).isoformat()
    except ValueError:
        return s


def _shift_stamp(s, days):
    m = _STAMP.match(s)
    if not m or m.group(1) not in _MON3:
        return s
    try:
        d = date(int(m.group(3)), _MON3.index(m.group(1)) + 1, int(m.group(2))) + timedelta(days=days)
    except ValueError:
        return s
    return f"{_MON3[d.month - 1]} {d.day}, {d.year}{m.group(4)}"


def shift_text(s, days, old_term="", new_term=""):
    """An exam's text: its long dates ("Wednesday, October 28, 2026") moved, and the term's name changed."""
    def long(m):
        try:
            d = date(int(m.group(4)), _MONTHS.index(m.group(2)) + 1, int(m.group(3))) + timedelta(days=days)
        except ValueError:
            return m.group(0)
        return f"{_DAYS[d.weekday()] + ', ' if m.group(1) else ''}{_MONTHS[d.month - 1]} {d.day}, {d.year}"
    s = _LONG.sub(long, s) if days else s
    if old_term and new_term and old_term != new_term and _TERM.match(old_term) and _TERM.match(new_term):
        s = s.replace(term_name(old_term), term_name(new_term))
    return s


def shift_json(x, days):
    """Every date in a JSON value moved by `days`: ISO dates and announcement stamps (whole strings only, so a
    link that happens to have a date in it is left alone). A week's dates text is redone from its new start."""
    if isinstance(x, dict):
        out = {k: shift_json(v, days) for k, v in x.items()}
        if isinstance(x.get("dates"), str) and _ISO.match(str(out.get("start") or "")):
            from .hub import range_text
            out["dates"] = range_text(out["start"], out.get("end") or out["start"])
        return out
    if isinstance(x, list):
        return [shift_json(v, days) for v in x]
    if isinstance(x, str) and days:
        return _shift_stamp(_shift_iso(x, days), days)
    return x


# ── What's left out ──────────────────────────────────────────────────
def scrub_book(b, course=None, term=None):
    """A gradebook's setup, without this term's students: no class list, marks, accommodations or set grades,
    and nothing released."""
    if not isinstance(b, dict):
        return b
    b = dict(b, students=[], marks={}, overrides={}, finals={})
    b["evals"] = [{k: v for k, v in e.items() if k not in ("released", "booklets")} if isinstance(e, dict) else e for e in (b.get("evals") or [])]
    if course and term:
        b["course"] = dict(b.get("course") if isinstance(b.get("course"), dict) else {}, code=course.upper(), term=term_name(term))
    return b


def scrub_groups(d):
    """The sections, without who runs them (those are this server's accounts)."""
    if not isinstance(d, dict):
        return d
    gs = []
    for gr in d.get("groups") or []:
        if isinstance(gr, dict):
            gr = {k: v for k, v in gr.items() if k != "people"}
            gr["items"] = [{k: v for k, v in x.items() if k != "people"} if isinstance(x, dict) else x for x in (gr.get("items") or [])]
        gs.append(gr)
    return dict(d, groups=gs)


def scrub_page(p, course=None, term=None):
    """A course page (course.json): its own announcements out (an older page keeps them in its weeks)."""
    if not isinstance(p, dict) or not isinstance(p.get("page"), dict):
        return p
    page = dict(p["page"])
    page["sections"] = [dict(s, weeks=[{k: v for k, v in w.items() if k != "announcements"} if isinstance(w, dict) else w for w in s.get("weeks") or []])
                        if isinstance(s, dict) and s.get("type") == "schedule" else s for s in page.get("sections") or []]
    if course and term:
        page.update(code=course.upper(), term=term_name(term))
    return dict(p, page=page)


def _json(b):
    try:
        return json.loads(b.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None


def _dump(x):
    return (json.dumps(x, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def prepare(area, rel, data, course, term, old_term, days, keep_people=False):
    """One file of an offering, as it goes into another (export: course/term None; import; the demo: keep_people).
    None: it's left out."""
    name = rel.split("/")[-1]
    top = "/" not in rel
    if area == "priv" and top and name in LEFT_OUT and not (keep_people and name == "announcements.json"):
        return None
    j = _json(data) if name.endswith(".json") else None
    if area == "priv" and top and name == "grades.json" and isinstance(j, dict):
        j = j if keep_people else scrub_book(j, course, term)
        if keep_people and course and term:
            j = dict(j, course=dict(j.get("course") if isinstance(j.get("course"), dict) else {}, code=course.upper(), term=term_name(term)))
    elif area == "priv" and top and name == "groups.json" and isinstance(j, dict):
        j = scrub_groups(j)
    elif area == "pub" and top and name == "course.json" and isinstance(j, dict):
        j = j if keep_people else scrub_page(j)
        if course and term and isinstance(j.get("page"), dict):
            j = dict(j, page=dict(j["page"], code=course.upper(), term=term_name(term)))
    if j is not None and course:   # only on the way in: the dates move
        j = shift_json(j, days)
        if name == "exam.json":
            j = json.loads(shift_text(json.dumps(j, ensure_ascii=False), days, old_term, term))
        return _dump(j)
    if j is not None:
        return _dump(j)
    if course and name.endswith(".tex"):
        try:
            return shift_text(data.decode("utf-8"), days, old_term, term).encode("utf-8")
        except UnicodeDecodeError:
            return data
    return data


# ── Export ───────────────────────────────────────────────────────────
def offering_files(uid, off):
    """{"pub" | "priv": {path in the offering: bytes}}."""
    out = {}
    for area in ("pub", "priv"):
        r, got = Repo(uid, area), {}
        for x in r.walk():
            if x["type"] == "blob" and x["path"].startswith(off + "/"):
                b = r.read(x["path"])
                if b is not None:
                    got[x["path"][len(off) + 1:]] = b
        out[area] = got
    return out


def about_title(files):
    a = _json(files["priv"].get("about.json") or b"") or {}
    if isinstance(a, dict) and str(a.get("title") or "").strip():
        return str(a["title"]).strip()
    p = _json(files["pub"].get("course.json") or b"") or {}
    return str(((p.get("page") or {}) if isinstance(p, dict) else {}).get("title") or "")


@transfer_bp.get("/api/offerings/<owner>/<course>/<term>/export")
@signed_in
def export(owner, course, term):
    o, off, role = _where(owner, course, term)
    if role not in LEAD:
        raise Refusal(403, "Only the offering's instructors can export it.")
    files = offering_files(o["id"], off)
    if not files["pub"] and not files["priv"]:
        raise Refusal(404, "This course offering has nothing in it to export yet.")
    c, t = off.split("/")
    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for area in ("pub", "priv"):
            for rel, data in sorted(files[area].items()):
                d = prepare(area, rel, data, None, None, None, 0)
                if d is not None:
                    z.writestr(f"{area}/{rel}", d)
                    n += 1
        z.writestr(MANIFEST, _dump({"format": FORMAT, "course": c, "term": t, "title": about_title(files), "files": n,
                                    "exported": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                                    "leftOut": "students, marks, accommodations and requests, announcements, the teaching team"}))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{c}-{t}.lectern.zip")


# ── Import ───────────────────────────────────────────────────────────
def read_export(f):
    """(manifest, {"pub": {...}, "priv": {...}}) from an uploaded export, or a Refusal."""
    if not f:
        raise Refusal(400, "Choose a Lectern export file (.zip).")
    try:
        z = zipfile.ZipFile(f.stream if hasattr(f, "stream") else f)
    except (zipfile.BadZipFile, OSError):
        raise Refusal(400, "That isn't a Lectern export: it's not a .zip file.")
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES:
            raise Refusal(413, f"That export has more than {MAX_FILES} files.")
        if sum(i.file_size for i in infos) > MAX_BYTES:
            raise Refusal(413, "That export is too big to import.")
        try:
            man = json.loads(z.read(MANIFEST).decode("utf-8"))
        except (KeyError, ValueError, UnicodeDecodeError):
            raise Refusal(400, "That isn't a Lectern export: it has no lectern-export.json. Export the offering from Lectern (its Export button) and import that file.")
        if not isinstance(man, dict) or man.get("format") != FORMAT:
            raise Refusal(400, "That export is from a version of Lectern this one can't read.")
        files = {"pub": {}, "priv": {}}
        for i in infos:
            area, _, rel = i.filename.partition("/")
            if area not in files or not rel:
                continue
            try:
                rel = clean_path(rel)
            except StoreError:
                continue   # a hidden or odd name: skipped
            files[area][rel] = z.read(i)
    return man, files


def _peek(man, files):
    c, t = str(man.get("course") or ""), str(man.get("term") or "")
    return {"course": c, "term": t if _TERM.match(t) else "", "termName": term_name(t), "title": str(man.get("title") or "")[:300],
            "files": len(files["pub"]) + len(files["priv"]),
            "exams": sorted({r.split("/")[0] for r in files["priv"] if r.count("/") == 1 and r.endswith("/exam.json")}),
            "hasGrades": "grades.json" in files["priv"], "hasPage": "course.json" in files["pub"]}


def _has(uid, off):
    return any(os.path.isdir(os.path.join(db.data_dir(), "files", str(uid), a, *off.split("/"))) for a in ("pub", "priv"))


def _put(uid, off, files, course, term, old_term, days, message, keep_people=False):
    """Write an offering's files into an account (both areas), each as one save."""
    for area in ("pub", "priv"):
        out = {}
        for rel, data in files[area].items():
            d = prepare(area, rel, data, course, term, old_term, days, keep_people)
            if d is not None:
                out[f"{off}/{rel}"] = d
        if out:
            r = Repo(uid, area)
            try:
                r.commit(out, message, r.head(), g.user["email"])
            except StoreError as e:
                raise Refusal(e.status, str(e))


def _target(course, term):
    c, t = str(course or "").strip().lower(), str(term or "").strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9.-]{0,63}$", c):
        raise Refusal(400, "Enter the course as letters and numbers, e.g. csc258.")
    if not _TERM.match(t):
        raise Refusal(400, "Choose the term, e.g. Fall 2026.")
    return clean_offering(f"{c}/{t}")


@transfer_bp.post("/api/offerings/import/peek")
@signed_in
def import_peek():
    man, files = read_export(request.files.get("file"))
    return jsonify(export=_peek(man, files))


@transfer_bp.post("/api/offerings/import")
@signed_in
def import_offering():
    man, files = read_export(request.files.get("file"))
    off = _target(request.form.get("course"), request.form.get("term"))
    uid = g.user["id"]
    if _has(uid, off):
        raise Refusal(409, f"You already have {off}. Choose another term (or delete that offering first).")
    c, t = off.split("/")
    old = str(man.get("term") or "")
    days = 7 * weeks_between(old, t) if request.form.get("moveDates", "1") != "0" else 0
    _put(uid, off, files, c, t, old, days, f"Import {off} (from {man.get('course')}/{old})")
    title = text(request.form, "title", 300).strip()
    if title or "about.json" not in files["priv"]:   # its title (asked for, as a new offering's is)
        r = Repo(uid, "priv")
        a = _json(r.read(f"{off}/about.json") or b"") or {}
        a = dict(a if isinstance(a, dict) else {}, format="lectern-about/2")
        a["title"] = title or a.get("title") or str(man.get("title") or "")
        a.setdefault("description", "")
        r.commit({f"{off}/about.json": _dump(a)}, f"Import {off}: its title", r.head(), g.user["email"])
    return jsonify(ok=True, course=c, term=t, weeks=days // 7)


# ── The demo course ──────────────────────────────────────────────────
def demo_files():
    out = {"pub": {}, "priv": {}}
    for area in ("pub", "priv"):
        base = os.path.join(ROOT, "sample-data", "demo-course", area)
        for d, _, fs in os.walk(base):
            for x in fs:
                full = os.path.join(d, x)
                with open(full, "rb") as f:
                    out[area][os.path.relpath(full, base).replace(os.sep, "/")] = f.read()
    return out


def demo_book(b, days, today):
    """The demo's gradebook: its students with emails that take no mail, and the marks of what's happened by
    today, released (the rest not marked yet); with the grade so far shown on My Marks."""
    b = json.loads(json.dumps(b))
    past = {e["id"] for e in b.get("evals") or [] if isinstance(e, dict) and e.get("date") and _shift_iso(e["date"], days) < today.isoformat()}
    for e in b.get("evals") or []:
        if isinstance(e, dict) and e.get("id") in past:
            e["released"] = True
    b["marks"] = {s: {k: v for k, v in (m or {}).items() if k in past} for s, m in (b.get("marks") or {}).items()}
    fields = b.get("fields") if isinstance(b.get("fields"), dict) else {}
    custom = [x for x in fields.get("custom") or [] if isinstance(x, dict) and x.get("id") != "email"]
    b["fields"] = dict(fields, custom=[{"id": "email", "label": "Email"}] + custom, emailDomain="example.com")
    for s in b.get("students") or []:
        if isinstance(s, dict):
            who = re.sub(r"[^a-z]+", ".", f"{s.get('first', '')} {s.get('last', '')}".lower()).strip(".") or f"student{s.get('num')}"
            s["f"] = dict(s.get("f") or {}, email=f"{who}@example.com")
    pol = b.get("policies") if isinstance(b.get("policies"), dict) else {}
    b["policies"] = dict(pol, show=dict(pol.get("show") if isinstance(pol.get("show"), dict) else {}, sofar=True))
    return b


@transfer_bp.post("/api/offerings/demo")
@signed_in
def load_demo():
    uid, today = g.user["id"], date.today()
    t = term_now(today)
    off = f"{DEMO_COURSE}/{t}"
    if _has(uid, off):
        raise Refusal(409, f"You already have the demo course ({off}). Delete it from its page to load a fresh one.", "have")
    days = 7 * weeks_between(DEMO_TERM, t)
    files = demo_files()
    files["priv"]["grades.json"] = _dump(demo_book(_json(files["priv"]["grades.json"]), days, today))
    _put(uid, off, files, DEMO_COURSE, t, DEMO_TERM, days, "The demo course", keep_people=True)
    return jsonify(ok=True, course=DEMO_COURSE, term=t)
