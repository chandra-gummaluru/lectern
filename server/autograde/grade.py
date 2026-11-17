"""Marking a pile of scanned exams against the exam's answers (exam.json).

The scans are read page by page and grouped into booklets: one student's pages, together, in any order (a new
booklet starts at another exam or version, or at a page this booklet already has, so a booklet missing a page
runs into the next one's first pages: scan whole booklets). Each booklet
is lined up, marked and let go before the next, so a whole class's scans never sit in memory at once.

Each question (or sub-question) gets one of:
- auto:    marked by the grader (multiple choice, true or false, multiple answers, numbers in boxes, cells);
- check:   marked, but a person should look (an unclear bubble, an unsure read, a wrong answer to a question that
           also has room for working, where part marks may be due); the score is a suggestion;
- manual:  for a person to mark (written answers, blanks and boxes with words in them); no score;
- missing: its page wasn't in the scans.

Multiple answers is all or nothing. Answer pieces in one question share its marks equally (to the half mark).
The student is found from the cover's student-number boxes, matched against the class list.
"""
import math
import re

from . import layout, read, scan

LET = "ABCDEF"
TOKEN = re.compile(r"\[\[(\w+)\]\]")
_FLOAT = re.compile(r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
# Handwriting. A misread almost never turns into exactly the right answer, so a reading that matches the answer is
# trusted from RIGHT sure. One that doesn't is marked wrong without a person only when it's WRONG sure and the right
# answer is an unlikely reading of the same ink (below ALT); otherwise it goes to a person.
RIGHT, WRONG, ALT = 0.6, 0.95, 0.01


def num(v):
    if isinstance(v, bool) or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else 0.0
    m = _FLOAT.match(str(v))
    return float(m.group(1)) if m else 0.0


def number(s):
    """A written answer as a number: 42, -3.5, .5, 3/4, 1e3; None if it isn't one."""
    s = str(s or "").strip().replace(" ", "").replace("−", "-")
    if not s:
        return None
    if "/" in s:
        a, _, b = s.partition("/")
        x, y = number(a), number(b)
        return None if x is None or not y else x / y
    try:
        return float(s)
    except ValueError:
        return None


def same(a, b, tol=None):
    if a is None or b is None:
        return False
    t = num(tol) if tol not in (None, "") else 1e-9 * max(1.0, abs(b))
    return abs(a - b) <= t + 1e-12


def variant_for(q, vi):
    vs = q.get("variants") or []
    return vs[0] if len(vs) == 1 else (vs[vi] if vi < len(vs) else None)


def node_points(n):
    return sum(node_points(p) for p in n.get("parts") or []) if n.get("parts") else num(n.get("points"))


def _roman(k):
    return ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"][k] if k < 10 else str(k + 1)


def leaves(exam, vi):
    """(label, node) for every question and sub-question that has no sub-questions, in order."""
    out, qn = [], 0

    def walk(n, label, depth):
        parts = n.get("parts") or []
        if not parts:
            out.append((label, n))
        for j, p in enumerate(parts):
            walk(p, label + (f"({chr(97 + j)})" if depth == 0 else f"({_roman(j)})"), depth + 1)

    for it in exam.get("items") or []:
        if it.get("kind") != "question":
            continue
        qn += 1
        v = variant_for(it, vi)
        if v:
            walk(v, str(qn), 0)
    return out


def version_of(code, exam):
    """The version index a template's code stands for (its last part is the version letter when there are several)."""
    if int(num(exam.get("settings", {}).get("versions")) or 1) <= 1:
        return 0
    last = code.rsplit("-", 1)[-1].upper()
    return LET.index(last) if len(last) == 1 and last in LET else 0


# ── Choosing among bubbles ─────────────────────────────────────────────

def choose_one(fills):
    """(index or None, status, note) for bubbles of which one should be filled."""
    cand = [i for i, f in enumerate(fills) if f >= read.TRACE]
    if not cand:
        return None, "auto", "left blank"
    if len(cand) == 1:
        return cand[0], "auto", ""
    best = max(cand, key=lambda i: fills[i])
    if fills[best] >= read.FILLED and all(fills[i] < 2 * read.TRACE for i in cand if i != best):
        return best, "auto", "a stray mark elsewhere was ignored"
    return best, "check", "more than one bubble has ink"


class Booklet:
    def __init__(self, template, version):
        self.template, self.version = template, version
        self.pages = {}        # page number -> (label, lined-up scan, student ink)

    @property
    def code(self):
        return self.template.code

    def get(self, rid):
        tp, r = self.template.find(rid)
        if tp is None or tp.number not in self.pages:
            return None
        _, img, ink = self.pages[tp.number]
        return r, img, ink

    def picture(self, rids, right=0, pad=14):
        """A picture of the scan around some pieces (all on one page)."""
        got = [(rid, self.get(rid)) for rid in rids]
        got = [g for _, g in got if g]
        if not got:
            return None
        img = got[0][1]
        x0 = min(g[0][0] for g in got); y0 = min(g[0][1] for g in got)
        x1 = max(g[0][0] + g[0][2] for g in got); y1 = max(g[0][1] + g[0][3] for g in got)
        return read.picture(img, (x0, y0, x1 - x0, y1 - y0), pad=pad, right=right)


# ── Marking one question ───────────────────────────────────────────────

def mark_choice(b, n):
    t = n.get("type")
    if t == "tf":
        ids = [f"{n['id']}:T", f"{n['id']}:F"]
        vals = ["true", "false"]
    else:
        ids = [f"{n['id']}.{o['id']}" for o in n.get("options") or []]
        vals = [o["id"] for o in n.get("options") or []]
    got = [b.get(r) for r in ids]
    if not ids or any(g is None for g in got):
        return {"status": "missing"}
    pts = num(n.get("points"))
    if t == "ms":
        fills = [read.fill(g[2], g[0], round_=False) for g in got]
        marked = [f >= read.TICK for f in fills]
        unsure = any(read.TICK / 2 <= f < read.TICK for f in fills)
        right = [bool(o.get("correct")) for o in n["options"]]
        ok = marked == right
        return {"status": "check" if unsure else "auto", "score": pts if ok else 0.0,
                "read": ", ".join(LET[i] for i, m in enumerate(marked) if m) or "none",
                "answer": ", ".join(LET[i] for i, r in enumerate(right) if r),
                "note": "a box is faintly marked" if unsure else "", "fills": [round(f, 3) for f in fills],
                "picture": b.picture(ids, right=260)}
    fills = [read.fill(g[2], g[0]) for g in got]
    i, status, note = choose_one(fills)
    if t == "tf":
        answer = n.get("answer") or "true"
        chosen = vals[i] if i is not None else None
        name = {"true": "True", "false": "False"}
        return {"status": status, "score": pts if chosen == answer else 0.0, "read": name.get(chosen, "none"),
                "answer": name[answer], "note": note, "fills": [round(f, 3) for f in fills], "picture": b.picture(ids, right=180)}
    right = [k for k, o in enumerate(n["options"]) if o.get("correct")]
    return {"status": status, "score": pts if i is not None and i in right else 0.0,
            "read": LET[i] if i is not None else "none", "answer": " or ".join(LET[k] for k in right),
            "note": note, "fills": [round(f, 3) for f in fills], "picture": b.picture(ids, right=260)}


def _trusted(correct, sure, alt):
    """Whether a reading's verdict can stand without a person (see RIGHT, WRONG, ALT)."""
    return sure >= RIGHT if correct else (sure >= WRONG and alt < ALT)


def mark_comp(b, nid, cid, c):
    """(correct?, trusted?, what was read, the answer, ids) for one answer piece; correct is None when a person
    must read it."""
    rid = f"{nid}.{cid}"
    k = c.get("kind")
    if k == "num":
        g = b.get(rid)
        if not g:
            return None
        r = read.read_box(g[2], g[0])
        key = str(c.get("ans", "")).strip()
        if not r.chars:
            return False, True, "blank", key, [rid]
        ok = same(number(r.text), number(key), c.get("tol"))
        return ok, _trusted(ok, r.sure, r.chance(key)), r.text, key, [rid]
    if k == "frac":
        gn, gd = b.get(rid + ":n"), b.get(rid + ":d")
        if not gn or not gd:
            return None
        rn, rd = read.read_box(gn[2], gn[0]), read.read_box(gd[2], gd[0])
        kn, kd = str(c.get("num", "")).strip(), str(c.get("den", "")).strip()
        a, d = number(kn), number(kd)
        if not rn.chars and not rd.chars:
            return False, True, "blank", f"{kn}/{kd}", [rid + ":n", rid + ":d"]
        got = number(f"{rn.text}/{rd.text}") if rn.text and rd.text else None
        ok = same(got, a / d) if a is not None and d else False
        return ok, _trusted(ok, min(rn.sure, rd.sure), rn.chance(kn) * rd.chance(kd)), f"{rn.text or '?'}/{rd.text or '?'}", f"{kn}/{kd}", [rid + ":n", rid + ":d"]
    if k == "cells":
        cnt = max(1, int(round(num(c.get("n")))) or 1)
        want = ([x.strip() for x in str(c.get("ans") or "").split(",")] + [""] * cnt)[:cnt]
        ids = [f"{rid}:c{i}" for i in range(cnt)]
        gs = [b.get(r) for r in ids]
        if any(g is None for g in gs):
            return None
        if any(w and not w.isdigit() for w in want):
            return None, False, "", ",".join(want), ids          # letters: a person reads them
        seen, sure, alt, ok = [], 1.0, 1.0, True
        for g, w in zip(gs, want):
            p = read.digit_probs(g[2], g[0])
            ch = "" if p is None else str(int(p.argmax()))
            if p is not None:
                sure = min(sure, float(p.max()))
            alt *= (float(p[int(w)]) if w else 0.0) if p is not None else float(not w)
            seen.append(ch or "_")
            ok = ok and ch == w
        return ok, _trusted(ok, sure, alt), " ".join(seen), " ".join(w or "_" for w in want), ids
    return None, False, "", str(c.get("ans", "")), [rid]                # blank line, box: a person reads it


def mark_written(b, n):
    comps = [(m.group(1), (n.get("comps") or {})[m.group(1)]) for m in TOKEN.finditer(n.get("body") or "") if m.group(1) in (n.get("comps") or {})]
    space = n.get("space") or {}
    has_space = space.get("mode") not in (None, "none")
    pts = num(n.get("points"))
    if not comps:
        pic = b.picture([f"{n['id']}.space"]) if has_space else None
        sp = b.template.find(f"{n['id']}.space")[0]
        if has_space and sp is not None and sp.number not in b.pages:
            return {"status": "missing"}
        return {"status": "manual", "note": "written answer", "picture": pic}
    results = [mark_comp(b, n["id"], cid, c) for cid, c in comps]
    if any(r is None for r in results):
        return {"status": "missing"}
    ids = [i for r in results for i in r[4]]
    reads = "; ".join(r[2] for r in results)
    answers = "; ".join(r[3] for r in results)
    if any(r[0] is None for r in results):
        return {"status": "manual", "note": "an answer to read", "read": reads, "answer": answers, "picture": b.picture(ids, right=40)}
    right = sum(1 for r in results if r[0])
    score = round(pts * right / len(results) * 2) / 2
    status, note = "auto", ""
    if not all(r[1] for r in results):
        status, note = "check", "not sure of the handwriting: is this what it says?"
    elif has_space and right < len(results):
        status, note = "check", "wrong answer: look at the working for part marks"
    pic = b.picture(ids, right=40)
    return {"status": status, "score": score, "read": reads, "answer": answers, "note": note, "picture": pic}


def mark_node(b, n):
    if n.get("type") in ("mc", "ms", "tf"):
        return mark_choice(b, n)
    return mark_written(b, n)


# ── Whose exam ─────────────────────────────────────────────────────────

def student_field(exam, roster):
    """The cover field that holds the student number: by its label, else the one as long as the class's numbers."""
    fields = (exam.get("cover") or {}).get("fields") or []
    for k, f in enumerate(fields):
        if re.search(r"student\s*(#|no\b|num)", f.get("label") or "", re.I):
            return k, int(num(f.get("count")))
    lens = {len(str(s.get("num", ""))) for s in roster or []}
    for k, f in enumerate(fields):
        if int(num(f.get("count"))) in lens:
            return k, int(num(f.get("count")))
    return None, 0


def identify_student(b, exam, roster):
    k, count = student_field(exam, roster)
    fields = (exam.get("cover") or {}).get("fields") or []
    every = [f"cover:f{j}:c{i}" for j, f in enumerate(fields) for i in range(int(num(f.get("count"))))]
    pic = b.picture(every, pad=30)
    if k is None:
        return {"status": "check", "note": "the cover has no student-number boxes", "picture": pic}
    gs = [b.get(f"cover:f{k}:c{i}") for i in range(count)]
    if any(g is None for g in gs):
        return {"status": "missing", "note": "the cover page isn't in the scans", "picture": pic}
    probs = [read.digit_probs(g[2], g[0]) for g in gs]
    seen = "".join("_" if p is None else str(int(p.argmax())) for p in probs).rstrip("_")
    out = {"read": seen, "picture": pic}
    people = [s for s in roster or [] if str(s.get("num", "")).isdigit()]
    if not people:
        out.update(status="check" if not seen or "_" in seen else "auto", num=seen)
        return out
    scored = []
    for s in people:
        digits_ = str(s["num"])
        t = 0.0
        for i, p in enumerate(probs):
            if i < len(digits_):
                t += math.log(p[int(digits_[i])] + 1e-4) if p is not None else math.log(0.02)
            elif p is not None:
                t += math.log(0.05)
        scored.append((t / max(1, len(digits_)), t, s))
    scored.sort(key=lambda x: -x[1])
    best = scored[0]
    gap = best[1] - (scored[1][1] if len(scored) > 1 else -1e9)
    sure = math.exp(best[0]) > 0.35 and gap > 3.0
    s = best[2]
    out.update(status="auto" if sure else "check", num=str(s["num"]), name=f"{s.get('first', '')} {s.get('last', '')}".strip(),
               note="" if sure else "not sure who this is: check the cover",
               candidates=[{"num": str(x[2]["num"]), "name": f"{x[2].get('first', '')} {x[2].get('last', '')}".strip()} for x in scored[:3]])
    return out


# ── The whole pile ─────────────────────────────────────────────────────

def booklets(scan_paths, templates, exam, unread):
    """Booklets, one at a time, from the scans in order. Pages that can't be placed go into unread."""
    by_code = {t.code: t for t in templates}
    cur = None
    for path in scan_paths:
        for label, img in scan.load_pages(path):
            ident = scan.identify(img)
            if not ident:
                unread.append({"page": label, "why": "no QR code or corner squares found"})
                continue
            t = by_code.get(ident["code"])
            tp = t.page(ident["page"]) if t else None
            if tp is None:
                unread.append({"page": label, "why": f"from another exam ({ident['code']} p.{ident['page']})"})
                continue
            if cur is None or cur.template is not t or ident["page"] in cur.pages:
                if cur is not None:
                    yield cur
                cur = Booklet(t, version_of(t.code, exam))
            lined = scan.align(img, ident, tp)
            cur.pages[ident["page"]] = (label, lined, read.student_ink(lined, tp))
    if cur is not None:
        yield cur


def mark_booklet(b, exam, roster):
    qs = []
    for label, n in leaves(exam, b.version):
        r = mark_node(b, n)
        r.update(label=label, id=n["id"], points=num(n.get("points")))
        r.setdefault("score", None)
        qs.append(r)
    out_of = sum(q["points"] for q in qs)
    return {
        "pages": [b.pages[k][0] for k in sorted(b.pages)],
        "code": b.code,
        "version": LET[b.version] if int(num(exam.get("settings", {}).get("versions")) or 1) > 1 else "",
        "student": identify_student(b, exam, roster),
        "questions": qs,
        "marked": sum(q["score"] or 0 for q in qs if q["status"] in ("auto", "check")),
        "out_of": out_of,
        "to_check": sum(1 for q in qs if q["status"] != "auto"),
    }


def run(exam, template_paths, scan_paths, roster=None, progress=None):
    """Mark the scans. Returns {"booklets": [...], "unread": [...]}; pictures are JPEG bytes in each result."""
    templates = [layout.load_template(p) for p in template_paths]
    unread, done = [], []
    for b in booklets(scan_paths, templates, exam, unread):
        done.append(mark_booklet(b, exam, roster))
        if progress:
            progress(len(done))
    seen = {}
    for r in done:                                       # one student, two booklets: both need a look
        k = r["student"].get("num")
        if k and r["student"].get("status") != "missing":
            seen.setdefault(k, []).append(r)
    for k, rs in seen.items():
        if len(rs) > 1:
            for r in rs:
                r["student"]["status"] = "check"
                r["student"]["note"] = f"{len(rs)} booklets matched this student"
    return {"booklets": done, "unread": unread}
