"""The course hub: an offering's course page, served by Lectern itself, in tabs.

The Course Page Builder saves the page as data, course.json, in an offering's public area (older pages
are an info.html, which the builder opens and saves as course.json). The hub is built from course.json,
and the builder shows it the same way (static/js/hub-view.js draws both):

  GET /c/<handle>/<course>/<term>/        the hub (a Lectern page, so it can know who's signed in)
  GET /api/hub/<handle>/<course>/<term>   what this viewer may see of it, tab by tab

/p/<handle>/<course>/<term>/ (and …/info.html) send people here once course.json exists, and
course.json itself is never served from /p/: everything in it reaches people through the API
below, which leaves out the tabs a viewer may not see.

Tabs: each is public or for signed-in people only (course.json's "tabs", set in the builder; all
public unless changed). My accommodations is always signed-in only. "Signed in" means someone with
a part in this offering: its owner and teaching team (Lectern accounts), and students on its class list
signed in to this course page (students.py: email and a one-time code).

Staff can add ?as=public to see the hub as a signed-out visitor does.
"""
import json
import re
from datetime import date, timedelta

from flask import Blueprint, abort, jsonify, redirect, render_template, request

from . import db
from .auth import current, Refusal, handles, pages_base
from .core import app_url
from .store import Repo
from .teams import role_of

hub_bp = Blueprint("hub", __name__)

PAGE_DATA = "course.json"
SLUG = re.compile(r"^[\w.-]{1,64}$")

# id, title. Overview and This week first: This week is where the hub opens.
TABS = [
    ("week", "This week"),
    ("announcements", "Announcements"),
    ("lectures", "Lectures"),
    ("evaluations", "Evaluations"),
    ("about", "About"),
    ("accommodations", "My accommodations"),
]
ALWAYS_SIGNED_IN = {"accommodations"}
DEFAULT_VIS = {t: "public" for t, _ in TABS}
DEFAULT_VIS.update({t: "signed-in" for t in ALWAYS_SIGNED_IN})
STAFF = {"owner", "instructor", "ta"}


# ── Reading an offering's page data ───────────────────────────────────
def owner_of(handle):
    u = db.one("SELECT id, handle, name, disabled FROM users WHERE handle = ?", (str(handle or "").lower(),))
    return None if not u or u["disabled"] else u


def page_data(owner_id, course, term):
    """course.json's page, or None (not there, or not something the builder wrote)."""
    if not (SLUG.match(course or "") and SLUG.match(term or "")):
        return None
    raw = Repo(owner_id, "pub").read(f"{course}/{term}/{PAGE_DATA}")
    if raw is None:
        return None
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    page = d.get("page") if isinstance(d, dict) else None
    return page if isinstance(page, dict) and isinstance(page.get("sections"), list) else None


def gradebook_files(owner_id, course, term):
    """{evaluation id: [files]}: the files and links each evaluation has in the gradebook (Evaluations → its page).
    They're public (they go on the course page); nothing else of the gradebook is read."""
    raw = Repo(owner_id, "priv").read(f"{course}/{term}/grades.json")
    try:
        book = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        return {}
    out = {}
    for e in _list(book.get("evals") if isinstance(book, dict) else None):
        if isinstance(e, dict) and isinstance(e.get("id"), str) and _files(e.get("files")):
            out[e["id"]] = _files(e.get("files"))
    return out


def announcements_of(owner_id, course, term):
    """The Announcements part's (announcements.js): <course>/<term>/announcements.json's items, or None."""
    raw = Repo(owner_id, "priv").read(f"{course}/{term}/announcements.json")
    try:
        d = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        return None
    return d["items"] if isinstance(d, dict) and isinstance(d.get("items"), list) else None


def about_of(owner_id, course, term):
    """The About part's (about.js): <course>/<term>/about.json, or None."""
    raw = Repo(owner_id, "priv").read(f"{course}/{term}/about.json")
    try:
        d = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        return None
    return d if isinstance(d, dict) else None


def lectures_of(owner_id, course, term):
    """The Lectures part's weeks (lectures.js): <course>/<term>/lectures.json in the private files, or None."""
    raw = Repo(owner_id, "priv").read(f"{course}/{term}/lectures.json")
    try:
        d = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("weeks"), list) else None


TEAM_KINDS = {"lecture", "tutorial", "lab", "office", "other"}


def team_of(owner_id, course, term):
    """The teaching team as the course page shows it: each person (owner, instructors, TAs) with what
    their page in Lectern says (team.json: email, office, sections and times). Removed members aren't
    here; nor is anyone whose page says not to show them."""
    off = f"{course}/{term}"
    raw = Repo(owner_id, "priv").read(f"{off}/team.json")
    try:
        d = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        d = {}
    info = d.get("people") if isinstance(d, dict) and isinstance(d.get("people"), dict) else {}
    o = db.one("SELECT id, name, email FROM users WHERE id = ?", (owner_id,))
    rows = [(o, "instructor")] + [(r, r["role"]) for r in db.all_(
        "SELECT u.id, u.name, u.email, m.role FROM members m JOIN users u ON u.id = m.user_id WHERE m.owner_id = ? AND m.offering = ? ORDER BY m.role, u.name",
        (owner_id, off))]
    out = []
    for u, role in rows:
        me = info.get(str(u["id"])) if isinstance(info.get(str(u["id"])), dict) else {}
        if me.get("show") is False:
            continue
        times = []
        for x in _list(me.get("times")):
            if not isinstance(x, dict):
                continue
            day = x.get("day")
            day = int(day) if isinstance(day, (int, str)) and str(day).isdigit() and 1 <= int(day) <= 7 else 0
            times.append({"kind": x.get("kind") if x.get("kind") in TEAM_KINDS else "other", "section": _s(x.get("section"), 60), "day": day,
                          "start": _s(x.get("start"), 5), "end": _s(x.get("end"), 5), "where": _s(x.get("where"), 200)})
        out.append({"name": _s(u["name"], 200), "role": "ta" if role == "ta" else "instructor", "email": _s(me.get("email"), 200) or _s(u["email"], 200),
                    "office": _s(me.get("office"), 200), "times": times})
    return out


def has_hub(owner_id, course, term):
    return Repo(owner_id, "pub").stat(f"{course}/{term}/{PAGE_DATA}") is not None


def visibility(page):
    vis = dict(DEFAULT_VIS)
    tabs = dict(page.get("tabs")) if isinstance(page.get("tabs"), dict) else {}
    if "about" not in tabs and "overview" in tabs:   # About was Overview (and Policies)
        tabs["about"] = tabs["overview"]
    for k, v in tabs.items():
        if k in vis and k not in ALWAYS_SIGNED_IN and v in ("public", "signed-in"):
            vis[k] = v
    return vis


# ── What goes in each tab ─────────────────────────────────────────────
def _s(x, n=20000):
    return x[:n] if isinstance(x, str) else ""


def _list(x):
    return x if isinstance(x, list) else []


def _files(fs):
    return [{"label": _s(f.get("label"), 200), "url": _s(f.get("url"), 2000)}
            for f in _list(fs) if isinstance(f, dict) and _s(f.get("url")).strip()]


def _blocks(bs):
    out = []
    for b in _list(bs):
        if not isinstance(b, dict) or b.get("hidden"):   # a policy the instructor keeps off the page
            continue
        if isinstance(b.get("table"), dict):
            t = b["table"]
            out.append({"heading": _s(b.get("heading"), 300), "table": {
                "columns": [_s(c, 300) for c in _list(t.get("columns"))],
                "rows": [[_s(c, 4000) for c in _list(r)] for r in _list(t.get("rows"))],
                "footer": [_s(c, 300) for c in _list(t.get("footer"))] or None}})
        elif _s(b.get("heading")).strip() or _s(b.get("body")).strip():
            out.append({"heading": _s(b.get("heading"), 300), "body": _s(b.get("body"))})
    return out


def _meeting(m):
    day = m.get("day")
    if isinstance(day, str) and day.isdigit():
        day = int(day)
    return {"kind": _s(m.get("kind"), 20) or "other", "label": _s(m.get("label"), 200), "who": _s(m.get("who"), 300),
            "day": day if isinstance(day, int) and 1 <= day <= 7 else 0,
            "start": _s(m.get("start"), 5), "end": _s(m.get("end"), 5), "where": _s(m.get("where"), 300)}


def _section(s):
    """An Overview section, as students see it."""
    base = {"type": s.get("type"), "title": _s(s.get("title"), 300), "caption": _s(s.get("caption"), 500)}
    t = s.get("type")
    if t == "table":
        base.update(columns=[_s(c, 300) for c in _list(s.get("columns"))],
                    rows=[[_s(c, 4000) for c in _list(r)] for r in _list(s.get("rows")) if any(_s(c).strip() for c in _list(r))],
                    footer=[_s(c, 300) for c in _list(s.get("footer"))] or None)
    elif t == "sessions":
        base.update(headers=[_s(h, 300) for h in _list(s.get("headers"))],
                    groups=[{"name": _s(g.get("name"), 300), "extra": _s(g.get("extra"), 2000),
                             "slots": [{"a": _s(x.get("a"), 500), "b": _s(x.get("b"), 500)} for x in _list(g.get("slots")) if isinstance(x, dict)]}
                            for g in _list(s.get("groups")) if isinstance(g, dict)])
    elif t == "meetings":
        base.update(items=[x for x in (_meeting(m) for m in _list(s.get("items")) if isinstance(m, dict)) if x["day"]])
    base["blocks"] = _blocks(s.get("blocks"))
    return base


_MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_RANGE = re.compile(r"([a-z]{3})[a-z]*\.?\s*(\d{1,2})(?:\s*[-\u2013\u2014]\s*(?:([a-z]{3})[a-z]*\.?\s*)?(\d{1,2}))?", re.I)
_ISO = re.compile(r"^\d{4}-\d\d-\d\d$")


def week_range(w, year):
    """A week's first and last day (ISO): its dates, or (older pages) read from text like "Sept 8 – 12"."""
    start, end = _s(w.get("start"), 10), _s(w.get("end"), 10)
    if _ISO.match(start):
        return start, end if _ISO.match(end) and end >= start else start
    m = _RANGE.search(_s(w.get("dates"), 100))
    if not m or not year or m.group(1).lower() not in _MON:
        return "", ""
    sm = _MON[m.group(1).lower()]
    em = _MON.get((m.group(3) or "").lower(), sm)
    try:
        a = date(year, sm, int(m.group(2)))
        b = date(year + (1 if em < sm else 0), em, int(m.group(4) or m.group(2)))
    except ValueError:
        return "", ""
    return a.isoformat(), b.isoformat()


def _week(w):
    cards = [{"kind": _s(c.get("kind"), 20), "label": _s(c.get("label"), 200), "title": _s(c.get("title"), 500), "description": _s(c.get("description"), 4000),
              "date": _s(c.get("date"), 60), "hours": c.get("hours") if isinstance(c.get("hours"), int) else 1,
              "files": _files(c.get("files"))}
             for c in _list(w.get("cards")) if isinstance(c, dict)]
    if w.get("isBreak"):
        return {"isBreak": True, "label": _s(w.get("text"), 200) or _s(w.get("label"), 200), "cards": [], "deadlines": []}
    return {"label": _s(w.get("label"), 200), "dates": _s(w.get("dates"), 100), "start": _s(w.get("start"), 10),
            "end": _s(w.get("end"), 10), "topic": _s(w.get("topic"), 1000), "isBreak": False,
            "deadlines": [_s(d, 200) for d in _list(w.get("deadlines")) if _s(d).strip()],
            "noClass": len(_list(w.get("off"))), "cards": cards}


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"]
_STAMP = re.compile(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})")


def range_text(start, end):
    """"Sept 8 – 12", "Sept 28 – Oct 2" (as the builder writes a week's dates)."""
    try:
        a = date.fromisoformat(start)
        b = date.fromisoformat(end) if end else a
    except ValueError:
        return ""
    A = f"{_MONTHS[a.month - 1]} {a.day}"
    if a == b:
        return A
    return f"{A} – {b.day}" if a.month == b.month else f"{A} – {_MONTHS[b.month - 1]} {b.day}"


def _stamp_day(t):
    """"Oct 18, 2026, 15:42" → the ISO day, or ""."""
    m = _STAMP.search(t or "")
    if not m or m.group(1).lower() not in _MON:
        return ""
    try:
        return date(int(m.group(3)), _MON[m.group(1).lower()], int(m.group(2))).isoformat()
    except ValueError:
        return ""


def _week_of(day, weeks):
    """The week a day is in: Monday of a week's first day to the day before the next week starts."""
    dated = [w for w in weeks if not w["isBreak"] and w.get("start")]
    found = None
    for j, w in enumerate(dated):
        mon = date.fromisoformat(w["start"]) - timedelta(days=date.fromisoformat(w["start"]).weekday())
        if mon.isoformat() <= day:
            found = w
    return found


def buckets(page, year=None, book_files=None, lectures=None, team=None, announcements=None, about=None):
    """Everything the page says, sorted into its tabs (all of them: the caller leaves out what a viewer can't see).
    lectures: the Lectures part's weeks (lectures.json), when there is one; else the course page's own."""
    secs = [s for s in _list(page.get("sections")) if isinstance(s, dict) and not s.get("hidden")]
    scheme = page.get("scheme") if isinstance(page.get("scheme"), dict) else {}
    weeks, anns, own = [], [], []
    for s in secs:
        if s.get("type") == "schedule":
            own += [w for w in _list(s.get("weeks")) if isinstance(w, dict)]
    for w in (_list(lectures.get("weeks")) if isinstance(lectures, dict) else own):
        if not isinstance(w, dict):
            continue
        wk = _week(w)
        if not wk["isBreak"]:
            wk["start"], wk["end"] = week_range(w, year)
            wk["dates"] = wk["dates"] or range_text(wk["start"], wk["end"])
        wk["i"] = len(weeks)
        weeks.append(wk)
    # Announcements: the Announcements part's (announcements.json), else the course page's own; each in the
    # week its date is in (else, for the course page's, the week it was written in).
    written = [({"label": ""}, a) for a in _list(announcements)] if isinstance(announcements, list) else [(w, a) for w in own for a in _list(w.get("announcements"))]
    for w, a in written:
        if isinstance(a, dict) and (_s(a.get("title")).strip() or _s(a.get("body")).strip()):
            day = _stamp_day(_s(a.get("date"), 60))
            wk = _week_of(day, weeks) if day else None
            if not wk:
                wk = next((x for x in weeks if not x["isBreak"] and x["label"] == _s(w.get("label"), 200)), None)
            anns.append({"title": _s(a.get("title"), 500), "body": _s(a.get("body")), "date": _s(a.get("date"), 60),
                         "at": a.get("at") if isinstance(a.get("at"), (int, float)) else 0,
                         "week": wk["label"] if wk else _s(w.get("label"), 200), "wi": wk["i"] if wk else -1})
    rules = []
    pol = [s for s in secs if s.get("type") == "policies"]
    for s in pol:
        show = s.get("show") if isinstance(s.get("show"), dict) else {}
        for x in _list(scheme.get("policies")):
            if isinstance(x, dict) and (bool(show[x["id"]]) if x.get("id") in show else bool(x.get("show"))):
                rules.append({"title": _s(x.get("title"), 200), "text": _s(x.get("text"), 2000)})
    ef = page.get("evalFiles") if isinstance(page.get("evalFiles"), dict) else {}
    if isinstance(about, dict):   # the About part's (about.json): its own sections and policies, and which gradebook rules show
        show = about.get("rules") if isinstance(about.get("rules"), dict) else {}
        rules = [{"title": _s(x.get("title"), 200), "text": _s(x.get("text"), 2000)} for x in _list(scheme.get("policies"))
                 if isinstance(x, dict) and (bool(show[x["id"]]) if x.get("id") in show else bool(x.get("show")))]
        about_b = {"description": _s(about.get("description")), "team": team or [],
                   "sections": [{"type": "text", "title": "", "caption": "", "blocks": _blocks([b])} for b in _list(about.get("sections")) if _blocks([b])],
                   "policies": _blocks(about.get("policies")), "rules": rules}
    else:
        about_b = {"description": _s(page.get("description")), "team": team or [],
                   # Only the page's own text: its contact and meeting-time tables are the teaching team's now.
                   "sections": [x for x in (_section(s) for s in secs if s.get("type") == "text") if x["blocks"]],
                   "policies": [b for s in pol for b in _blocks(s.get("blocks"))], "rules": rules}
    return {
        "about": about_b,
        "lectures": {"weeks": weeks},
        "announcements": {"items": anns},
        "evaluations": {
            "units": _list(scheme.get("units")),
            "evals": _list(scheme.get("evals")),
            # The gradebook's files first (where they're added now), then any the course page itself had.
            "files": _merge_files(book_files or {}, {k: _files(v) for k, v in ef.items() if isinstance(k, str)}),
        },
        # This week: the term's calendar (each week's name and dates). The browser fills each week in
        # from the tabs above that this viewer can see.
        "week": {"weeks": [{k: wk.get(k, "") for k in ("i", "label", "dates", "start", "end", "isBreak")} for wk in weeks]},
        "accommodations": {},
    }


def _merge_files(a, b):
    out = {k: list(v) for k, v in a.items()}
    for k, v in b.items():
        have = {f["url"] for f in out.get(k, [])}
        out[k] = out.get(k, []) + [f for f in v if f["url"] not in have]
    return {k: v for k, v in out.items() if v}


def year_of(page, term):
    m = re.search(r"\b(20\d\d)\b", _s(page.get("term")))
    if m:
        return int(m.group(1))
    m = re.match(r"^[wsf](\d\d)$", term or "", re.I)
    return 2000 + int(m.group(1)) if m else None


# ── Pages and API ─────────────────────────────────────────────────────
def _offering_or_404(handle, course, term):
    o = owner_of(handle)
    if not o:
        return None, None
    page = page_data(o["id"], course, term)
    return (o, page) if page else (o, None)


@hub_bp.get("/c/<handle>/<course>/<term>/")
def hub_page(handle, course, term):
    o, page = _offering_or_404(handle, course, term)
    if not page:
        abort(404)
    return render_template("hub.html", title=_s(page.get("title"), 300) or f"{course.upper()} {term}",
                           api=f"/api/hub/{o['handle']}/{course}/{term}")


@hub_bp.get("/c/<handle>/<course>/<term>")
def hub_slash(handle, course, term):
    return redirect(f"/c/{handle}/{course}/{term}/", code=301)


@hub_bp.get("/api/hub/<handle>/<course>/<term>")
@handles
def hub_api(handle, course, term):
    o, page = _offering_or_404(handle, course, term)
    if not page:
        raise Refusal(404, "There's no course page here.")
    offering = f"{course}/{term}"
    u, _ = current()
    role = role_of(u["id"], o["id"], offering) if u else None
    student = None
    if not role:   # a student signed in to this course page (students.py)
        from .students import student_of
        student = student_of(o["id"], offering)
        role = "student" if student else None
    preview = role in STAFF and request.args.get("as") == "public"
    signed = bool(role) and not preview
    vis = visibility(page)
    year = year_of(page, term)
    about = about_of(o["id"], course, term)
    all_b = buckets(page, year, gradebook_files(o["id"], course, term), lectures_of(o["id"], course, term), team_of(o["id"], course, term),
                    announcements_of(o["id"], course, term), about)
    head = about if about else page
    tabs, data = [], {}
    for tid, title in TABS:
        open_ = vis[tid] == "public" or signed
        tabs.append({"id": tid, "title": title, "visibility": vis[tid], "open": open_})
        if open_:
            data[tid] = all_b[tid]
    if "evaluations" in data:   # where an evaluation's Request Accommodation button goes (accommodations.py's form)
        data["evaluations"]["request"] = {"url": f"{app_url()}request", "r": o["handle"], "o": offering}
    return jsonify(
        course={"title": _s(head.get("title"), 300) or _s(page.get("title"), 300), "code": _s(head.get("code"), 60) or _s(page.get("code"), 60),
                "term": _s(head.get("term"), 100) or _s(page.get("term"), 100), "school": _s(head.get("school"), 200) or _s(page.get("school"), 200),
                "offering": offering, "year": year},
        viewer={"signedIn": signed, "role": None if preview else role, "name": student or (u["name"] if u and signed else ""),
                "staff": role in STAFF, "preview": preview},
        tabs=tabs, data=data,
        lectern=app_url(), signIn=f"/c/{o['handle']}/{offering}/sign-in",
        pages=f"{pages_base()}{o['handle']}/{offering}/",
    )
