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

Multiple answers is all or nothing. Answer pieces (blanks) in one question are each worth their own marks when the exam
gives them ("pts"), and otherwise share what's left of the question's marks equally (to the half mark). A question with
two or more blanks lists each one in "blanks" (its reading, answer, marks and status), so a person can mark just the
ones the grader couldn't.
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
RIGHT, WRONG, ALT = 0.35, 0.92, 0.01
# A student is matched without a person only when the next likeliest student on the class list is e^ID_GAP (about 400)
# times less likely: marks going to the wrong student is worse than a click to confirm.
ID_GAP = 6.0


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
        return None, "auto", "Left blank."
    if len(cand) == 1:
        return cand[0], "auto", ""
    best = max(cand, key=lambda i: fills[i])
    if fills[best] >= read.FILLED and all(fills[i] < 2 * read.TRACE for i in cand if i != best):
        return best, "auto", "A stray mark elsewhere was left out."
    return best, "check", "More than one bubble has ink. Which is their answer?"


class Booklet:
    def __init__(self, template, version, number=None):
        self.template, self.version, self.number = template, version, number   # number: a numbered copy's
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

    def paper(self, rids, right=0, pad=14):
        """The same piece of the printed copy as picture(rids, right, pad), clean: for the page's typed copy of what
        was read, drawn on the exam itself. With its size, so the page can size what it writes on it."""
        found = [self.template.find(rid) for rid in rids]
        if not found or any(tp is None for tp, _ in found):
            return None
        img = found[0][0].image
        x0 = min(r[0] for _, r in found); y0 = min(r[1] for _, r in found)
        x1 = max(r[0] + r[2] for _, r in found); y1 = max(r[1] + r[3] for _, r in found)
        return read.picture(img, (x0, y0, x1 - x0, y1 - y0), pad=pad, right=right)

    def paper_size(self, rids, right=0, pad=14):
        """[width, height] in pixels of paper(rids, right, pad)."""
        found = [self.template.find(rid) for rid in rids]
        if not found or any(tp is None for tp, _ in found):
            return None
        H, W = found[0][0].image.shape
        x0 = min(r[0] for _, r in found); y0 = min(r[1] for _, r in found)
        x1 = max(r[0] + r[2] for _, r in found); y1 = max(r[1] + r[3] for _, r in found)
        return [min(W, int(x1 + pad + right)) - max(0, int(x0 - pad)), min(H, int(y1 + pad)) - max(0, int(y0 - pad))]

    def on_paper(self, ids, groups, right=0, pad=14):
        """A typed copy's paper and where its pieces are: {"paper", "size", "fields": [[rect, …] per piece]}."""
        sp = self.spots(ids, right=right, pad=pad)
        if not sp:
            return {}
        at = dict(zip(ids, sp))
        return {"paper": self.paper(ids, right=right, pad=pad), "size": self.paper_size(ids, right=right, pad=pad),
                "fields": [[at[i] for i in g] for g in groups]}

    def spots(self, rids, right=0, pad=14):
        """Where each piece is in picture(rids, right, pad), as fractions of it: [[left, top, width, height]], so the
        page can ring the right answers on it."""
        got = [self.get(rid) for rid in rids]
        if not got or any(g is None for g in got):
            return None
        H, W = got[0][1].shape
        x0 = min(g[0][0] for g in got); y0 = min(g[0][1] for g in got)
        x1 = max(g[0][0] + g[0][2] for g in got); y1 = max(g[0][1] + g[0][3] for g in got)
        L, T = max(0, int(x0 - pad)), max(0, int(y0 - pad))
        R, B = min(W, int(x1 + pad + right)), min(H, int(y1 + pad))
        return [[round((g[0][0] - L) / (R - L), 4), round((g[0][1] - T) / (B - T), 4), round(g[0][2] / (R - L), 4), round(g[0][3] / (B - T), 4)] for g in got]


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
        return {"status": "check" if unsure else "auto", "score": ms_score(n, marked, right),
                "read": ", ".join(LET[i] for i, m in enumerate(marked) if m) or "none",
                "answer": ", ".join(LET[i] for i, r in enumerate(right) if r),
                "note": "A box is only faintly marked. Which are their answers?" if unsure else "", "ask": "choice" if unsure else "",
                "options": [LET[k] for k in range(len(ids))], "multi": True, "fills": [round(f, 3) for f in fills],
                "picture": b.picture(ids, right=260), "spots": b.spots(ids, right=260), "right": [k for k, r in enumerate(right) if r],
                **b.on_paper(ids, [[i] for i in ids], right=260)}
    fills = [read.fill(g[2], g[0]) for g in got]
    i, status, note = choose_one(fills)
    if t == "tf":
        answer = n.get("answer") or "true"
        chosen = vals[i] if i is not None else None
        name = {"true": "True", "false": "False"}
        return {"status": status, "score": pts if chosen == answer else 0.0, "read": name.get(chosen, "none"),
                "answer": name[answer], "note": note, "ask": "choice" if status == "check" else "", "options": ["True", "False"],
                "fills": [round(f, 3) for f in fills], "picture": b.picture(ids, right=180), "spots": b.spots(ids, right=180),
                "right": [vals.index(answer)], **b.on_paper(ids, [[i] for i in ids], right=180)}
    right = [k for k, o in enumerate(n["options"]) if o.get("correct")]
    return {"status": status, "score": pts if i is not None and i in right else 0.0,
            "read": LET[i] if i is not None else "none", "answer": " or ".join(LET[k] for k in right),
            "note": note, "ask": "choice" if status == "check" else "", "options": [LET[k] for k in range(len(ids))],
            "fills": [round(f, 3) for f in fills], "picture": b.picture(ids, right=260), "spots": b.spots(ids, right=260), "right": right,
            **b.on_paper(ids, [[i] for i in ids], right=260)}


def ms_score(n, ticked, right):
    """Multiple answers: all or nothing, or, with a penalty, that many marks off for each box that's wrong (ticked
    and shouldn't be, or not ticked and should be), never below 0."""
    pts, pen = num(n.get("points")), _own({"pts": n.get("penalty")})
    wrong = sum(1 for t, r in zip(ticked, right) if bool(t) != bool(r))
    if not wrong:
        return pts
    return 0.0 if pen is None else max(0.0, round(pts - pen * wrong, 2))


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
        ok = same(number(r.core), number(key), c.get("tol"))
        # A mark that surely isn't a digit at either end ($30, 30 cm) is left out; anywhere else, a person reads it.
        trusted = _trusted(ok, r.sure, r.chance(key)) and ("?" not in r.text or (ok and r.core is not None and r.strays_sure))
        return ok, trusted, r.text, key, [rid]
    if k == "frac":
        gn, gd = b.get(rid + ":n"), b.get(rid + ":d")
        if not gn or not gd:
            return None
        rn, rd = read.read_box(gn[2], gn[0]), read.read_box(gd[2], gd[0])
        kn, kd = str(c.get("num", "")).strip(), str(c.get("den", "")).strip()
        a, d = number(kn), number(kd)
        if not rn.chars and not rd.chars:
            return False, True, "blank", f"{kn}/{kd}", [rid + ":n", rid + ":d"]
        got = number(f"{rn.core}/{rd.core}") if rn.core and rd.core else None
        ok = same(got, a / d) if a is not None and d else False
        trusted = _trusted(ok, min(rn.sure, rd.sure), rn.chance(kn) * rd.chance(kd)) and "?" not in rn.text + rd.text
        return ok, trusted, f"{rn.text or '?'}/{rd.text or '?'}", f"{kn}/{kd}", [rid + ":n", rid + ":d"]
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
            k = None if p is None else int(p.argmax())
            ch = "" if p is None else "?" if k == 10 else str(k)
            if p is not None:
                sure = min(sure, float(p.max()))
            alt *= (float(p[int(w)]) if w else 0.0) if p is not None else float(not w)
            seen.append(ch or "_")
            ok = ok and ch == w
        return ok, _trusted(ok, sure, alt), " ".join(seen), " ".join(w or "_" for w in want), ids
    return None, False, "", str(c.get("ans", "")), [rid]                # blank line, box: a person reads it


def comps_of(n):
    """(id, piece) for each answer piece in a question's text, in order."""
    cs = n.get("comps") or {}
    return [(m.group(1), cs[m.group(1)]) for m in TOKEN.finditer(n.get("body") or "") if m.group(1) in cs]


def _own(c):
    v = c.get("pts")
    return None if v is None or str(v).strip() == "" else max(0.0, num(v))


def blank_points(n, comps):
    """What each answer piece is worth: its own marks, or an even share of what the others leave of the question's."""
    pts, own = num(n.get("points")), [_own(c) for c in comps]
    rest = [x for x in own if x is None]
    share = max(0.0, pts - sum(x for x in own if x is not None)) / len(rest) if rest else 0.0
    return [x if x is not None else share for x in own]


def blank_total(n, comps, scores):
    """A question's score from its pieces' scores: to the half mark when they share it evenly, as the grader always has."""
    t = sum(x or 0 for x in scores)
    return round(t * 2) / 2 if all(_own(c) is None for c in comps) else round(t, 2)


def mark_written(b, n):
    comps = comps_of(n)
    space = n.get("space") or {}
    has_space = space.get("mode") not in (None, "none")
    pts = num(n.get("points"))
    if not comps:
        pic = b.picture([f"{n['id']}.space"]) if has_space else None
        sp = b.template.find(f"{n['id']}.space")[0]
        if has_space and sp is not None and sp.number not in b.pages:
            return {"status": "missing"}
        return {"status": "manual", "picture": pic}
    results = [mark_comp(b, n["id"], cid, c) for cid, c in comps]
    if any(r is None for r in results):
        return {"status": "missing"}
    ids = [i for r in results for i in r[4]]
    reads = "; ".join(r[2] for r in results)
    answers = "; ".join(r[3] for r in results)
    if len(comps) > 1:
        return _mark_blanks(b, n, comps, results, ids, has_space)
    paper = b.on_paper(ids, [r[4] for r in results], right=40)
    if any(r[0] is None for r in results):
        return {"status": "manual", "ask": "type", "read": "", "answer": answers, "picture": b.picture(ids, right=40), **paper}
    right = sum(1 for r in results if r[0])
    score = round(pts * right / len(results) * 2) / 2
    status, note, ask = "auto", "", ""
    if not all(r[1] for r in results):
        status, ask = "check", "read"
        note = ("There's a mark that isn't a digit. Is this what it says?" if any("?" in r[2] for r in results if not r[1])
                else "Not sure of the handwriting. Is this what it says?")
    elif has_space and right < len(results):
        status, note, ask = "check", "The answer is wrong. Is there working worth part marks?", "working"
    pic = b.picture(ids, right=40)
    return {"status": status, "score": score, "read": reads, "answer": answers, "note": note, "ask": ask, "picture": pic, **paper}


def _blank_note(r):
    return "There's a mark that isn't a digit. Is this what it says?" if "?" in r[2] else "Not sure of the handwriting. Is this what it says?"


def _mark_blanks(b, n, comps, results, ids, has_space):
    """A question with several blanks: each marked on its own (worth its own marks), then the question from them."""
    ws, blanks = blank_points(n, [c for _, c in comps]), []
    for (cid, c), r, w in zip(comps, results, ws):
        if r[0] is None:                                  # words: a person reads them
            st, sc, note = "manual", None, ""
        else:
            st, sc, note = ("auto" if r[1] else "check"), (w if r[0] else 0.0), ("" if r[1] else _blank_note(r))
        blanks.append({"id": cid, "kind": c.get("kind"), "points": round(w, 4), "status": st, "score": sc, "read": r[2] if r[0] is not None else "",
                       "answer": r[3], "note": note, "picture": b.picture(r[4], right=40), **b.on_paper(r[4], [r[4]], right=40)})
    out = {"read": "; ".join(x["read"] for x in blanks), "answer": "; ".join(x["answer"] for x in blanks), "blanks": blanks,
           "picture": b.picture(ids, right=40), "note": "", "ask": "", "space": has_space,
           "even": all(_own(c) is None for _, c in comps)}
    if any(x["status"] == "manual" for x in blanks):
        out.update(status="manual", score=None)
    else:
        out["score"] = blank_total(n, [c for _, c in comps], [x["score"] for x in blanks])
        if any(x["status"] == "check" for x in blanks):
            out["status"] = "check"
        elif has_space and any(not x["score"] for x in blanks):
            out.update(status="check", note="An answer is wrong. Is there working worth part marks?", ask="working")
        else:
            out["status"] = "auto"
    return out


def mark_node(b, n):
    if n.get("type") in ("mc", "ms", "tf"):
        return mark_choice(b, n)
    return mark_written(b, n)


# ── What a person says the answer is ───────────────────────────────────

def find_node(exam, nid):
    """The question or sub-question with this id, in any version."""
    def walk(n):
        if n.get("id") == nid:
            return n
        for p in n.get("parts") or []:
            f = walk(p)
            if f:
                return f
        return None
    for it in exam.get("items") or []:
        for v in it.get("variants") or []:
            f = walk(v)
            if f:
                return f
    return None


def _clean_number(t):
    """A typed number without what's around it: "$30" → "30", "30 dollars" → "30", "1,250" → "1250"."""
    t = str(t or "").strip().replace(",", "").replace(" ", "").replace("\u2212", "-")
    return re.sub(r"^[^\d.+-]+|[^\d.]+$", "", t)


def _words(t):
    return re.sub(r"[^\w]+", " ", str(t or "")).strip().lower()


def score_typed(n, typed):
    """(score, the reading as it's kept) for an answer as a person says it reads: a letter (or letters) for multiple
    choice, True or False, or the written answer (pieces separated by ";", cells by spaces)."""
    pts = num(n.get("points"))
    t = str(typed or "").strip()
    if n.get("type") == "tf":                           # True, False, both (two bubbles filled) or neither
        words = [w for w in re.split(r"[\s,;/]+", t.lower()) if w]
        T, F = any(w[0] == "t" for w in words), any(w[0] == "f" for w in words)
        got = "true" if T and not F else "false" if F and not T else None
        return (pts if got == (n.get("answer") or "true") else 0.0), "True, False" if T and F else {"true": "True", "false": "False"}.get(got, "none")
    if n.get("type") in ("mc", "ms"):
        opts = n.get("options") or []
        picked = sorted({LET.index(c) for c in t.upper() if c in LET[:len(opts)]})
        right = [k for k, o in enumerate(opts) if o.get("correct")]
        if n.get("type") == "ms":
            return ms_score(n, [k in picked for k in range(len(opts))], [bool(o.get("correct")) for o in opts]), ", ".join(LET[k] for k in picked) or "none"
        ok = len(picked) == 1 and picked[0] in right
        return (pts if ok else 0.0), ", ".join(LET[k] for k in picked) or "none"
    comps = [c for _, c in comps_of(n)]
    parts = [x.strip() for x in t.split(";")] if len(comps) > 1 else [t]
    parts += [""] * (len(comps) - len(parts))
    if not comps:
        return 0.0, t
    ws = blank_points(n, comps)
    return blank_total(n, comps, [w if piece_right(c, x) else 0.0 for c, x, w in zip(comps, parts, ws)]), t


def piece_right(c, x):
    """Whether what a person says one answer piece reads (x) is its answer."""
    x = str(x or "").strip()
    k = c.get("kind")
    if k == "num":
        return same(number(_clean_number(x)), number(c.get("ans")), c.get("tol"))
    if k == "frac":
        a, d = number(c.get("num")), number(c.get("den"))
        return bool(a is not None and d) and same(number(_clean_number(x.replace(" ", ""))) if "/" not in x else number("/".join(_clean_number(y) for y in x.split("/", 1))), a / d)
    if k == "cells":
        cnt = max(1, int(round(num(c.get("n")))) or 1)
        want = ([y.strip() for y in str(c.get("ans") or "").split(",")] + [""] * cnt)[:cnt]
        got = (re.split(r"[\s,]+", x) if re.search(r"[\s,]", x) else list(x)) + [""] * cnt
        return [("" if g.strip() in ("_", "?") else g.strip().lower()) for g in got[:cnt]] == [w.lower() for w in want]   # "_": an empty cell
    return bool(x) and _words(x) == _words(c.get("ans"))      # a blank line or box: the words, any case or punctuation


# ── Comments ───────────────────────────────────────────────────────────

def nodes_of(exam):
    """{node id: (node, how its question is marked: "full" or "zero")} for every question and part, in every version."""
    out = {}

    def walk(n, mode):
        out[n.get("id")] = (n, mode)
        for p in n.get("parts") or []:
            walk(p, mode)
    for it in exam.get("items") or []:
        if it.get("kind") == "question":
            for v in it.get("variants") or []:
                walk(v, "zero" if it.get("marking") == "zero" else "full")
    return out


def rubric_score(n, mode, deltas):
    """A score from rubric comments: from full marks (or zero) plus each comment's marks, kept from 0 to full."""
    pts = num(n.get("points"))
    return round(min(pts, max(0.0, (pts if mode != "zero" else 0.0) + sum(num(d) for d in deltas))), 2)


def plain(t):
    """An option's text without its LaTeX, for a comment: "$\\frac{3}{4}$" → "3/4"-ish, "\\$40" → "$40"."""
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", str(t or ""))
    t = re.sub(r"\\[a-zA-Z]+\*?|[{}]|(?<!\\)\$", "", t)
    t = re.sub(r"\\([$%&#_])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def auto_comments(n, q):
    """What the grader says about an answer it marked down: [{"text", "delta", "answer"}] ("answer": the right one,
    shown to the student only if asked for). Nothing for a full score, or for an answer a person marks."""
    pts, sc = num(q.get("points")), q.get("score")
    if sc is None or sc >= pts - 1e-9 or q.get("status") == "missing":
        return []
    lose, t = -round(pts - sc, 2), n.get("type")
    opts = n.get("options") or []
    if t in ("mc", "tf"):
        none, many = q.get("read") in (None, "", "none"), "," in str(q.get("read") or "")
        return [{"text": "No answer selected" if none else "More than one answer selected" if many else "Incorrect answer selected",
                 "delta": lose, "answer": q.get("answer", "")}]
    if t == "ms":
        got = {x.strip() for x in str(q.get("read") or "").split(",")}
        pen = _own({"pts": n.get("penalty")})
        out = []
        for k, o in enumerate(opts):
            L, name = LET[k], plain(o.get("text")) or LET[k]
            if L in got and not o.get("correct"):
                out.append({"text": f"Incorrect answer selected: {name}", "delta": -pen if pen is not None else None})
            elif L not in got and o.get("correct"):
                out.append({"text": "Correct answer not selected", "delta": -pen if pen is not None else None, "answer": name})
        if pen is None and out:                       # all or nothing: the marks go once, by the first thing wrong
            out[0]["delta"] = lose
        elif sum(-x["delta"] for x in out if x["delta"]) > pts - sc + 1e-9:
            out.append({"text": "Not below 0", "delta": None})
        return out
    if q.get("blanks"):
        return [{"text": f"Blank {k + 1}: incorrect" if x.get("read") not in (None, "", "blank") else f"Blank {k + 1}: left empty",
                 "delta": -round((x.get("points") or 0) - (x.get("score") or 0), 2), "answer": x.get("answer", "")}
                for k, x in enumerate(q["blanks"]) if x.get("score") is not None and (x.get("score") or 0) < (x.get("points") or 0) - 1e-9]
    if comps_of(n):
        return [{"text": "Left empty" if q.get("read") in ("", "blank", None) else "Incorrect answer", "delta": lose, "answer": q.get("answer", "")}]
    return []


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
    sure = math.exp(best[0]) > 0.35 and gap > ID_GAP
    s = best[2]
    out.update(status="auto" if sure else "check", num=str(s["num"]), name=f"{s.get('first', '')} {s.get('last', '')}".strip(),
               note="" if sure else "Not sure whose booklet this is. Check the cover.",
               candidates=[{"num": str(x[2]["num"]), "name": f"{x[2].get('first', '')} {x[2].get('last', '')}".strip()} for x in scored[:3]])
    return out


# ── The whole pile ─────────────────────────────────────────────────────

def booklets(scan_paths, templates, exam, unread):
    """Booklets, one at a time, from the scans in order. Pages that can't be placed go into unread.

    A numbered copy's pages (numbered.py: the booklet's number in each QR code) go to their booklet wherever they
    are in the scans, in any upload: they're found on the way through (only where each is, not its picture, is
    kept) and put together after, a booklet at a time, in the order of their numbers. Others go together as they
    come: a new booklet starts at another exam or version, or at a page this one already has."""
    by_code = {t.code: t for t in templates}
    cur, numbered = None, {}
    for path in scan_paths:
        for i, (label, img) in enumerate(scan.load_pages(path)):
            ident = scan.identify(img)
            if not ident:
                unread.append({"page": label, "why": "no QR code or corner squares found"})
                continue
            t = by_code.get(ident["code"])
            tp = t.page(ident["page"]) if t else None
            if tp is None:
                unread.append({"page": label, "why": f"from another exam ({ident['code']} p.{ident['page']})"})
                continue
            if ident.get("booklet") is not None:
                numbered.setdefault((ident["booklet"], t.code), []).append((path, i, label, ident))
                continue
            if cur is None or cur.template is not t or ident["page"] in cur.pages:
                if cur is not None:
                    yield cur
                cur = Booklet(t, version_of(t.code, exam))
            lined = scan.align(img, ident, tp)
            cur.pages[ident["page"]] = (label, lined, read.student_ink(lined, tp))
    if cur is not None:
        yield cur
    for (n, code), found in sorted(numbered.items(), key=lambda x: (x[0][0], x[0][1])):
        t = by_code[code]
        b = Booklet(t, version_of(code, exam), n)
        for path, i, label, ident in found:
            if ident["page"] in b.pages:        # the same page twice: two copies with one number (photocopied?)
                yield b
                b = Booklet(t, version_of(code, exam), n)
            tp = t.page(ident["page"])
            lined = scan.align(scan.load_page(path, i), ident, tp)
            b.pages[ident["page"]] = (label, lined, read.student_ink(lined, tp))
        yield b


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
        "missing": [n for n in range(1, len(b.template.pages) + 1) if n not in b.pages],   # its pages not in the scans
        "booklet": b.number,                                                                 # a numbered copy's number
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
    nums = {}
    for r in done:                                       # one number, two booklets (a copy photocopied?): say so
        if r.get("booklet") is not None:
            nums.setdefault(r["booklet"], []).append(r)
    for rs in nums.values():
        for r in rs:
            r["twins"] = len(rs) if len(rs) > 1 else 0
    seen = {}
    for r in done:                                       # one student, two booklets: both need a look
        k = r["student"].get("num")
        if k and r["student"].get("status") != "missing":
            seen.setdefault(k, []).append(r)
    for k, rs in seen.items():
        if len(rs) > 1:
            for r in rs:
                r["student"]["status"] = "check"
                r["student"]["note"] = f"{len(rs)} booklets matched this student. Check the cover."
    return {"booklets": done, "unread": unread}
