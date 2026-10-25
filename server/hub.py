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
import os
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
    ("lectures", "Activities"),   # the weeks and their lectures, tutorials, labs and the rest (the id stays: addresses keep working)
    ("evaluations", "Evaluations"),
    ("about", "About"),
    ("accommodations", "My accommodations"),
]
ALWAYS_SIGNED_IN = {"accommodations"}
DEFAULT_VIS = {t: "public" for t, _ in TABS}
DEFAULT_VIS.update({t: "signed-in" for t in ALWAYS_SIGNED_IN})
STAFF = {"owner", "coordinator", "instructor", "ta", "staff"}


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
    """The offering's title and description (Lectern → the offering: the title is asked for when it's made,
    and the description is under its code): <course>/<term>/about.json, or None."""
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
    # The activity groups (groups.js): who runs each lecture, tutorial and lab. With them, a person's times are
    # what they run (by group) and their own office hours; without them (older offerings), team.json's times.
    graw = Repo(owner_id, "priv").read(f"{off}/groups.json")
    try:
        gd = json.loads(graw.decode("utf-8")) if graw else None
    except (ValueError, UnicodeDecodeError):
        gd = None
    groups = [g for g in _list(gd.get("groups"))] if isinstance(gd, dict) else None
    o = db.one("SELECT id, name, email FROM users WHERE id = ?", (owner_id,))
    rows = [(o, "owner")] + [(r, r["role"]) for r in db.all_(
        "SELECT u.id, u.name, u.email, m.role FROM members m JOIN users u ON u.id = m.user_id WHERE m.owner_id = ? AND m.offering = ? ORDER BY m.role, u.name",
        (owner_id, off))]
    out = []
    for u, role in rows:
        me = info.get(str(u["id"])) if isinstance(info.get(str(u["id"])), dict) else {}
        if me.get("show") is False:
            continue
        times = []
        mine = [x for x in _list(me.get("times")) if isinstance(x, dict) and (groups is None or x.get("kind") == "office")]
        runs = []
        if groups is not None:
            from .teams import runs_section
            for g in groups:
                if not runs_section(g, u["id"]):
                    continue
                runs.append(_s(g.get("id"), 40))
                for x in _list(g.get("items")):
                    if isinstance(x, dict):
                        mine.append({**x, "kind": _kind_of(g, x), "section": g.get("name"), "sid": _s(g.get("id"), 40)})
        for x in mine:
            if not isinstance(x, dict):
                continue
            day = x.get("day")
            day = int(day) if isinstance(day, (int, str)) and str(day).isdigit() and 1 <= int(day) <= 7 else 0
            times.append({"kind": x.get("kind") if x.get("kind") in TEAM_KINDS else "other", "section": _s(x.get("section"), 60), "day": day,
                          "start": _s(x.get("start"), 5), "end": _s(x.get("end"), 5), "where": _s(x.get("where"), 200), **_map(x),
                          **({"sid": x["sid"]} if x.get("sid") else {})})
        out.append({"name": _s(u["name"], 200), "role": role if role in ("coordinator", "ta", "staff") else "instructor", "email": _s(me.get("email"), 200) or _s(u["email"], 200),
                    "office": _s(me.get("office"), 200), "times": times, "sections": runs, "lead": role in ("owner", "coordinator")})
    return out


SECTION_KINDS = ("lecture", "tutorial", "lab")


def section_kind(g):
    """A section's type: its own, or (an older file) from its name (LEC…, TUT…, PRA… or LAB…) or its times."""
    k = g.get("kind") if isinstance(g, dict) else None
    if k in SECTION_KINDS:
        return k
    n = _s(g.get("name"), 100).strip().upper() if isinstance(g, dict) else ""
    for pre, kind in (("LEC", "lecture"), ("TUT", "tutorial"), ("PRA", "lab"), ("LAB", "lab")):
        if n.startswith(pre):
            return kind
    ks = [x.get("kind") for x in _list(g.get("items")) if isinstance(x, dict)] if isinstance(g, dict) else []
    k = max(set(ks), key=ks.count) if ks else None
    return k if k in SECTION_KINDS else "lecture"


def _map(x):
    """A meeting's place on the map (picked in Lectern: static/js/place.js), as an OpenStreetMap link."""
    p = x.get("place") if isinstance(x, dict) else None
    try:
        lat, lon = float(p["lat"]), float(p["lon"])
    except (TypeError, ValueError, KeyError):
        return {}
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {}
    return {"map": f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}",
            "address": _s(p.get("address"), 300)}


def _kind_of(g, x):
    """A meeting time's kind, for the team's times: its section's."""
    k = section_kind(g)
    return k


def groups_of(owner_id, course, term):
    """The sections (groups.json) as the course page shows them: each section (LEC0101…) with its type, its
    weekly meeting times and who runs it (by name). None for an offering without them (its team's times say)."""
    off = f"{course}/{term}"
    raw = Repo(owner_id, "priv").read(f"{off}/groups.json")
    try:
        d = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        d = None
    if not isinstance(d, dict):
        return None
    names = {}
    o = db.one("SELECT id, name, email FROM users WHERE id = ?", (owner_id,))
    for u in [o] + db.all_("SELECT u.id, u.name, u.email FROM members m JOIN users u ON u.id = m.user_id WHERE m.owner_id = ? AND m.offering = ?", (owner_id, off)):
        if u:
            names[str(u["id"])] = _s(u["name"], 200) or _s(u["email"], 200)
    out = []
    for g in _list(d.get("groups")):
        if not isinstance(g, dict):
            continue
        from .teams import runs_section
        items = []
        for x in _list(g.get("items")):
            if not isinstance(x, dict):
                continue
            day = x.get("day")
            day = int(day) if isinstance(day, (int, str)) and str(day).isdigit() and 1 <= int(day) <= 7 else 0
            items.append({"kind": _kind_of(g, x), "day": day, "start": _s(x.get("start"), 5),
                          "end": _s(x.get("end"), 5), "where": _s(x.get("where"), 200), **_map(x)})
        who = [names[p] for p in names if runs_section(g, p)]
        out.append({"id": _s(g.get("id"), 40), "name": _s(g.get("name"), 100), "kind": section_kind(g), "items": items,
                    "who": who})
    return out


def term_name(term):
    """f26 → Fall 2026 (as Lectern names terms)."""
    m = re.match(r"^([wsf])(\d\d)$", term or "", re.I)
    return f"{dict(w='Winter', s='Summer', f='Fall')[m.group(1).lower()]} 20{m.group(2)}" if m else term


def institution():
    return os.environ.get("LECTERN_INSTITUTION", "University of Toronto")


PARTS = ("about.json", "lectures.json", "announcements.json", "grades.json", "team.json")


def page_or_blank(owner_id, course, term):
    """course.json's page; or, for an offering made in Lectern's parts that has none, an empty page (every tab
    public), so its course page is there from the start. None: no such offering."""
    page = page_data(owner_id, course, term)
    if page is not None:
        return page
    if not (SLUG.match(course or "") and SLUG.match(term or "")):
        return None
    priv = Repo(owner_id, "priv")
    return {"sections": []} if any(priv.stat(f"{course}/{term}/{f}") is not None for f in PARTS) else None


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


def _groups(x):
    """An activity's or announcement's activity groups (only their students see it; none: everyone).
    Older ones had one, "group"."""
    gs = x.get("groups") if isinstance(x.get("groups"), list) else ([x.get("group")] if x.get("group") else [])
    return [_s(g, 40) for g in gs[:50] if isinstance(g, (str, int)) and str(g)]


def _week(w):
    cards = [{"kind": _s(c.get("kind"), 20), "label": _s(c.get("label"), 200), "title": _s(c.get("title"), 500), "description": _s(c.get("description"), 4000),
              "date": _s(c.get("date"), 60), "dates": [_s(d, 60) for d in _list(c.get("dates"))[:20] if isinstance(d, str) and d.strip()], "hours": c.get("hours") if isinstance(c.get("hours"), int) else 1,
              "files": _files(c.get("files")), "id": _s(c.get("id"), 40), "groups": _groups(c)}
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
            on = _s(a.get("on"), 60)
            act = next((c for x in weeks for c in x["cards"] if on.startswith("act:") and c["id"] and c["id"] == on[4:]), None)
            import hashlib
            aid = _s(a.get("id"), 80) or "h-" + hashlib.sha1(f'{_s(a.get("title"))}|{_s(a.get("date"))}'.encode()).hexdigest()[:12]
            anns.append({"id": aid, "title": _s(a.get("title"), 500), "body": _s(a.get("body")), "date": _s(a.get("date"), 60), "on": on,
                         # about an activity: for whoever the activity is for
                         "groups": act["groups"] if act else ([] if on.startswith("act:") else _groups(a)),
                         "at": a.get("at") if isinstance(a.get("at"), (int, float)) else 0,
                         "week": wk["label"] if wk else _s(w.get("label"), 200), "wi": wk["i"] if wk else -1})
    # The gradebook's course rules (its Settings choose which the course page shows).
    rules = [{"title": _s(x.get("title"), 200), "text": _s(x.get("text"), 2000)} for x in _list(scheme.get("policies")) if isinstance(x, dict) and x.get("show")]
    ef = page.get("evalFiles") if isinstance(page.get("evalFiles"), dict) else {}
    desc = about.get("description") if isinstance(about, dict) and isinstance(about.get("description"), str) else page.get("description")
    about_b = {"description": _s(desc), "team": team or [], "sections": [], "policies": [], "rules": rules}
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
    page = page_or_blank(o["id"], course, term)
    return (o, page) if page is not None else (o, None)


@hub_bp.get("/c/<handle>/<course>/<term>/")
def hub_page(handle, course, term):
    o, page = _offering_or_404(handle, course, term)
    if not page:
        abort(404)
    a = about_of(o["id"], course, term) or {}
    name = _s(a.get("title"), 300) or _s(page.get("title"), 300)
    return render_template("hub.html", title=f"{course.upper()}: {name}" if name else f"{course.upper()} {term}",
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
    all_b["about"]["groups"] = groups_of(o["id"], course, term)
    # An activity or announcement for one activity group is only for its students (and the teaching team).
    if not (role in STAFF and not preview):
        mine = set()
        if student:
            from .students import roster
            mine = set((roster(o["id"], offering).get(student) or {}).get("groups") or [])
        ok = lambda x: not x.get("groups") or bool(set(x["groups"]) & mine)
        # A student in sections sees only theirs on About: their sections, and the people who run them (with
        # those sections' times and their office hours), the coordinators and staff.
        sections = all_b["about"].get("groups")
        if student and mine and sections:
            all_b["about"]["groups"] = [g for g in sections if g.get("id") in mine]
            team = []
            for p in all_b["about"].get("team") or []:
                theirs = set(p.get("sections") or []) & mine
                if not (theirs or p.get("lead") or p.get("role") == "staff"):
                    continue
                team.append({**p, "times": [x for x in p.get("times") or [] if not x.get("sid") or x["sid"] in mine]})
            all_b["about"]["team"] = team
        for w in all_b["lectures"]["weeks"]:
            w["cards"] = [c for c in w["cards"] if ok(c)]
        all_b["announcements"]["items"] = [a for a in all_b["announcements"]["items"] if ok(a)]
        # An evaluation with its own dates for some sections: a student's is their section's (else its own).
        def own_date(e):
            if not isinstance(e, dict):
                return
            for d in _list(e.get("dates")):
                if isinstance(d, dict) and set(map(str, _list(d.get("groups")))) & mine and d.get("date"):
                    e["date"], e["time"] = _s(d.get("date"), 10), _s(d.get("time"), 5)
                    if d.get("release"):
                        e["release"], e["releaseTime"] = _s(d.get("release"), 10), _s(d.get("releaseTime"), 5)
                    break
            e.pop("dates", None)
        ev = all_b.get("evaluations") or {}
        for u in _list(ev.get("units")):
            own_date(u)
            for m in _list(u.get("members") if isinstance(u, dict) else None):
                own_date(m)
        for e in _list(ev.get("evals")):
            own_date(e)
    head = about or {}
    tabs, data = [], {}
    for tid, title in TABS:
        open_ = vis[tid] == "public" or signed
        tabs.append({"id": tid, "title": title, "visibility": vis[tid], "open": open_})
        if open_:
            data[tid] = all_b[tid]
    if "evaluations" in data:   # where an evaluation's Request Accommodation button goes (accommodations.py's form)
        data["evaluations"]["request"] = {"url": f"{app_url()}request", "r": o["handle"], "o": offering}
    return jsonify(
        # The code, term and school are the offering's (its folder, and this Lectern's institution); the title is the one it was given.
        course={"title": _s(head.get("title"), 300) or _s(page.get("title"), 300), "code": course.upper(),
                "term": term_name(term), "school": institution(),
                "offering": offering, "year": year},
        viewer={"signedIn": signed, "role": None if preview else role, "name": student or (u["name"] if u and signed else ""),
                "staff": role in STAFF, "preview": preview,
                # a student: the announcements they've seen (the others are New for them)
                **({"seen": [r["ann_id"] for r in db.all_("SELECT ann_id FROM announcements_seen WHERE owner_id = ? AND offering = ? AND email = ?", (o["id"], offering, student))]} if student else {})},
        tabs=tabs, data=data,
        lectern=app_url(), signIn=f"/c/{o['handle']}/{offering}/sign-in",
        pages=f"{pages_base()}{o['handle']}/{offering}/",
    )
