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
a part in this offering: its owner and teaching team now; students once they can sign in.

Staff can add ?as=public to see the hub as a signed-out visitor does.
"""
import json
import re
from datetime import date

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
    ("overview", "Overview"),
    ("week", "This week"),
    ("lectures", "Lectures"),
    ("evaluations", "Evaluations"),
    ("announcements", "Announcements"),
    ("policies", "Policies"),
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


def has_hub(owner_id, course, term):
    return Repo(owner_id, "pub").stat(f"{course}/{term}/{PAGE_DATA}") is not None


def visibility(page):
    vis = dict(DEFAULT_VIS)
    for k, v in (page.get("tabs") or {}).items() if isinstance(page.get("tabs"), dict) else []:
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
    cards = [{"label": _s(c.get("label"), 200), "title": _s(c.get("title"), 500), "description": _s(c.get("description"), 4000),
              "date": _s(c.get("date"), 60), "hours": c.get("hours") if isinstance(c.get("hours"), int) else 1,
              "files": _files(c.get("files"))}
             for c in _list(w.get("cards")) if isinstance(c, dict)]
    if w.get("isBreak"):
        return {"isBreak": True, "label": _s(w.get("text"), 200) or _s(w.get("label"), 200), "cards": [], "deadlines": []}
    return {"label": _s(w.get("label"), 200), "dates": _s(w.get("dates"), 100), "start": _s(w.get("start"), 10),
            "end": _s(w.get("end"), 10), "topic": _s(w.get("topic"), 1000), "isBreak": False,
            "deadlines": [_s(d, 200) for d in _list(w.get("deadlines")) if _s(d).strip()],
            "noClass": len(_list(w.get("off"))), "cards": cards}


def buckets(page, year=None):
    """Everything the page says, sorted into its tabs (all of them: the caller leaves out what a viewer can't see)."""
    secs = [s for s in _list(page.get("sections")) if isinstance(s, dict) and not s.get("hidden")]
    scheme = page.get("scheme") if isinstance(page.get("scheme"), dict) else {}
    weeks, anns = [], []
    for s in secs:
        if s.get("type") != "schedule":
            continue
        for w in _list(s.get("weeks")):
            if not isinstance(w, dict):
                continue
            wk = _week(w)
            if not wk["isBreak"]:
                wk["start"], wk["end"] = week_range(w, year)
            wk["i"] = len(weeks)
            weeks.append(wk)
            for a in _list(w.get("announcements")):
                if isinstance(a, dict) and (_s(a.get("title")).strip() or _s(a.get("body")).strip()):
                    anns.append({"title": _s(a.get("title"), 500), "body": _s(a.get("body")), "date": _s(a.get("date"), 60),
                                 "at": a.get("at") if isinstance(a.get("at"), (int, float)) else 0,
                                 "week": _s(w.get("label"), 200), "wi": wk["i"]})
    rules = []
    pol = [s for s in secs if s.get("type") == "policies"]
    for s in pol:
        show = s.get("show") if isinstance(s.get("show"), dict) else {}
        for x in _list(scheme.get("policies")):
            if isinstance(x, dict) and (bool(show[x["id"]]) if x.get("id") in show else bool(x.get("show"))):
                rules.append({"title": _s(x.get("title"), 200), "text": _s(x.get("text"), 2000)})
    ef = page.get("evalFiles") if isinstance(page.get("evalFiles"), dict) else {}
    return {
        "overview": {
            "description": _s(page.get("description")),
            "sections": [x for x in (_section(s) for s in secs if s.get("type") in ("table", "sessions", "text", "meetings"))
                         if x["type"] != "meetings" or x["items"] or x["blocks"]],
        },
        "lectures": {"weeks": weeks},
        "announcements": {"items": anns},
        "evaluations": {
            "units": _list(scheme.get("units")),
            "evals": _list(scheme.get("evals")),
            "files": {k: _files(v) for k, v in ef.items() if isinstance(k, str)},
        },
        "policies": {
            "sections": [{"title": _s(s.get("title"), 300), "caption": _s(s.get("caption"), 500), "blocks": _blocks(s.get("blocks"))} for s in pol],
            "rules": rules,
        },
        # This week: the term's calendar (each week's name and dates). The browser fills each week in
        # from the tabs above that this viewer can see.
        "week": {"weeks": [{k: wk.get(k, "") for k in ("i", "label", "dates", "start", "end", "isBreak")} for wk in weeks]},
        "accommodations": {},
    }


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
    preview = role in STAFF and request.args.get("as") == "public"
    signed = bool(role) and not preview
    vis = visibility(page)
    year = year_of(page, term)
    all_b = buckets(page, year)
    tabs, data = [], {}
    for tid, title in TABS:
        open_ = vis[tid] == "public" or signed
        tabs.append({"id": tid, "title": title, "visibility": vis[tid], "open": open_})
        if open_:
            data[tid] = all_b[tid]
    return jsonify(
        course={"title": _s(page.get("title"), 300), "code": _s(page.get("code"), 60), "term": _s(page.get("term"), 100),
                "school": _s(page.get("school"), 200), "offering": offering, "year": year},
        viewer={"signedIn": signed, "role": None if preview else role, "name": u["name"] if u and signed else "",
                "staff": role in STAFF, "preview": preview},
        tabs=tabs, data=data,
        lectern=app_url(),
        pages=f"{pages_base()}{o['handle']}/{offering}/",
    )
