"""One student's course grade so far, worked out the way the gradebook does it.

This is the Grade Builder's studentResult (tools/grade-builder.html), in Python, so the course page can show
a student their grade so far (My Marks) without sending them the gradebook. It follows the builder step by
step and must keep doing so: tests/test_grading.py runs the builder's own JavaScript (with node, when it's
installed) on the sample gradebooks and checks that both give the same answer for every student.

Only the marks a student may see go in: hub.py keeps the evaluations whose marks aren't released out of it,
so an unreleased mark counts as not marked yet. The course's final rules (ranges, rounding, automatic fail)
aren't applied: they're for the final grade, and the page says so.
"""
import math
import re

STATUSES = {"missed": "Not submitted", "aiv": "Academic integrity violation", "excused": "Excused", "deferred": "Deferred"}
_FLOAT = re.compile(r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")


def num(v):
    """JavaScript's parseFloat, or 0 (the builder's num)."""
    if isinstance(v, bool) or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else 0.0
    m = _FLOAT.match(str(v))
    if not m:
        return 0.0
    x = float(m.group(1))
    return x if math.isfinite(x) else 0.0


def _js_round(x):
    """Math.round: halves go up."""
    return math.floor(x + 0.5)


def fmt_num(n):
    """The builder's fmtNum: at most two decimals, written as JavaScript writes a number."""
    v = _js_round(num(n) * 100) / 100
    return str(int(v)) if v == int(v) else repr(v)


def _truthy(x):
    """JavaScript's truthiness (an empty object or list is true there)."""
    if isinstance(x, (dict, list)):
        return True
    if isinstance(x, float) and math.isnan(x):
        return False
    return bool(x)


def _dict(x):
    return x if isinstance(x, dict) else {}


def _list(x):
    return x if isinstance(x, list) else []


class Book:
    """A gradebook (grades.json), with the builder's small helpers."""

    def __init__(self, book):
        b = _dict(book)
        self.evals = [e for e in _list(b.get("evals")) if isinstance(e, dict)]
        self.groups = [g for g in _list(b.get("groups")) if isinstance(g, dict)]
        self.marks = _dict(b.get("marks"))
        self.overrides = _dict(b.get("overrides"))

    def eval_by_id(self, i):
        return next((e for e in self.evals if e.get("id") == i), None)

    def counted(self):
        return [e for e in self.evals if not _truthy(e.get("makeupFor"))]

    def group_of(self, e):
        return next((g for g in self.groups if e.get("id") in _list(g.get("members"))), None)

    def mark_of(self, s, e):
        m = _dict(self.marks.get(s)).get(e)
        return m if _truthy(m) and isinstance(m, dict) else {}

    def override_of(self, s, e):
        o = _dict(self.overrides.get(s)).get(e)
        return o if _truthy(o) else None

    def group_override(self, s, g):
        return self.override_of(s, "g:" + str(g.get("id")))

    def units(self):
        out, done = [], set()
        for e in self.counted():
            g = self.group_of(e)
            if not g:
                out.append({"e": e, "w": num(e.get("weight"))})
            elif g.get("id") not in done:
                done.add(g.get("id"))
                out.append({"g": g, "w": num(g.get("weight"))})
        for g in self.groups:
            if g.get("id") not in done:
                out.append({"g": g, "w": num(g.get("weight"))})
        return out

    def weight_sum(self):
        return sum(u["w"] for u in self.units())


def status_of(m):
    if _truthy(m.get("missed")):
        return "missed"
    st = m.get("status")
    return st if isinstance(st, str) and st in STATUSES else ""


def total_set(e):
    return bool(e) and e.get("total") is not None and e.get("total") != "" and num(e.get("total")) > 0


def ratio(pts, e):
    return num(pts) / num(e.get("total")) if total_set(e) else None


def _name(e):
    return str((e or {}).get("name") or "")


def share_parts(b, pol, e):
    """A not-submitted policy's parts, as fractions of the weight: its makeups and where its weight moves."""
    pol = _dict(pol)

    def ok(i):
        x = b.eval_by_id(i)
        return bool(x) and x.get("id") != e.get("id") and not b.group_of(x)

    mk = [{"id": t.get("id"), "f": max(0.0, num(t.get("share"))) / 100} for t in _list(pol.get("makeups")) if isinstance(t, dict) and ok(t.get("id"))]
    to = [{"id": t.get("id"), "f": max(0.0, num(t.get("share"))) / 100}
          for t in (_list(pol.get("to")) if pol.get("mode") == "reweight" else [])
          if isinstance(t, dict) and ok(t.get("id")) and not _truthy(b.eval_by_id(t.get("id")).get("makeupFor")) and not any(x["id"] == t.get("id") for x in mk)]
    if pol.get("mode") != "reweight":
        mk = []
    total = sum(x["f"] for x in mk + to)
    if total > 1:
        for x in mk + to:
            x["f"] /= total
    return {"mk": mk, "to": to, "total": total}


def policy_for(b, s, e):
    o, g = b.override_of(s, e.get("id")) or {}, b.group_of(e)
    if g:
        return {"weight": 0.0, "missed": {"mode": "zero", "to": []}, "group": g}
    return {"weight": num(o.get("weight")) if o.get("weight") is not None else num(e.get("weight")),
            "missed": o.get("missed") if _truthy(o.get("missed")) else e.get("missed")}


def student_result(book, s):
    """The builder's studentResult(s): each evaluation's weight, score (0..1), status and note, and the grade
    so far (current: the average of what's settled, as a percentage) or final (once everything's settled)."""
    b = book if isinstance(book, Book) else Book(book)
    s = str(s)
    rows, evs = {}, b.counted()
    # 1. each evaluation on its own
    for e in evs:
        p, m = policy_for(b, s, e), b.mark_of(s, e.get("id"))
        r = rows[e.get("id")] = {"w": p["weight"], "score": None, "status": "pending", "note": ""}
        st = status_of(m)
        if st == "missed":
            r["missed"] = p["missed"]
        elif st == "aiv":
            r.update(score=0.0, status="aiv", note="Academic integrity violation: zero")
        elif st == "excused":
            r.update(w=0.0, status="excused", note="Excused: doesn't count")
        elif st == "deferred":
            r["note"] = "Deferred: still to come"
        elif m.get("pts") is not None and total_set(e):
            r.update(score=ratio(m["pts"], e), status="graded")
        elif m.get("pts") is not None:
            r["note"] = "Marked, but it's out of ? points: set its total and the mark counts"
    # 2. work not submitted: its makeups (each worth its share) and the weight it moves; the rest is zero
    for e in evs:
        r = rows[e.get("id")]
        if not _truthy(r.get("missed")):
            continue
        pol = _dict(r["missed"])
        parts = share_parts(b, pol, e)
        if pol.get("mode") != "reweight" or (not parts["mk"] and not any(t["id"] in rows for t in parts["to"])):
            r.update(score=0.0, status="missed", note="Not submitted: counts as zero")
            continue
        if parts["mk"]:
            sc, exc, pend = 0.0, 0.0, []
            for x in parts["mk"]:
                me, m = b.eval_by_id(x["id"]), b.mark_of(s, x["id"])
                st = status_of(m)
                if st == "excused":
                    exc += x["f"]
                elif m.get("pts") is not None and not st and total_set(me):
                    sc += x["f"] * ratio(m["pts"], me)
                elif st not in ("missed", "aiv"):
                    pend.append(me)
            if pend:
                r.update(status="pending", note=f"Not submitted: the makeup ({', '.join(_name(x) for x in pend)}) is still to come")
                del r["missed"]
                continue
            r["mk"] = {"sc": sc, "exc": exc}
        r["w0"] = r["w"]
        r["status"] = "reweight"
    # 3. move the weight of reweighted work; a target that was itself reweighted passes on what it gets
    for e in evs:
        r = rows[e.get("id")]
        if r["status"] == "reweight":
            r["inbox"] = r["w"]
    for _ in range(12):
        moved = False
        for e in evs:
            r = rows[e.get("id")]
            if r["status"] != "reweight" or not (r.get("inbox", 0) > 1e-12):
                continue
            to = [t for t in share_parts(b, r["missed"], e)["to"] if t["id"] in rows]
            fr = [t["f"] for t in to]
            amt = r["inbox"]
            r["inbox"] = 0
            for t, f in zip(to, fr):
                gain, tr = amt * f, rows[t["id"]]
                tr["w"] += gain
                if tr["status"] == "reweight":
                    tr["inbox"] = tr.get("inbox", 0) + gain
            r["w"] -= amt * sum(fr)
            kept = r["w"] > 1e-9
            r["note"] = f"Not submitted: {'part of ' if kept else ''}its weight moved to {', '.join(_name(b.eval_by_id(t['id'])) for t in to)}{'; the rest counts as zero' if kept else ''}"
            moved = True
        if not moved:
            break
    for e in evs:   # what stays is the makeups' part (their marks) and the rest (zero)
        r = rows[e.get("id")]
        if r["status"] != "reweight":
            continue
        parts, W = share_parts(b, r["missed"], e), r["w0"]
        r2 = lambda x: fmt_num(_js_round(x * 100) / 100)
        mv = [t for t in parts["to"] if t["id"] in rows]
        fmk, fto = sum(x["f"] for x in parts["mk"]), sum(x["f"] for x in mv)
        rest = max(0.0, 1 - fmk - fto)
        bits = []
        if parts["mk"]:
            many = len(parts["mk"]) > 1
            bits.append(f"the makeup{'s' if many else ''} ({', '.join(_name(b.eval_by_id(x['id'])) for x in parts['mk'])}) count{'' if many else 's'} for {r2(W * fmk)}%")
        if mv:
            bits.append(f"{r2(W * fto)}% moved to {', '.join(_name(b.eval_by_id(t['id'])) for t in mv)}")
        if rest > 1e-9:
            bits.append(f"{r2(W * rest)}% counts as zero")
        r["note"] = f"Not submitted: {'; '.join(bits)}"
        if r.get("mk"):
            r["w"] -= W * r["mk"]["exc"]
        if r["w"] > 1e-9:
            r["score"] = min(1.5, W * r["mk"]["sc"] / r["w"]) if r.get("mk") else 0.0
            if r.get("mk"):
                r["status"] = "madeup"
        else:
            r["w"], r["score"] = 0.0, None
    # 4. groups: the best `keep` members that are in share the group's weight; the rest aren't counted
    for g in b.groups:
        go = b.group_override(s, g) or {}
        members = _list(g.get("members"))
        ex = set(_list(go.get("excused"))) | {i for i in members if status_of(b.mark_of(s, i)) == "excused"}
        mem = [x for x in (b.eval_by_id(i) for i in members) if x]
        live = [x for x in mem if x.get("id") not in ex]
        for x in mem:
            if x.get("id") in ex and x.get("id") in rows:
                rows[x["id"]].update(w=0.0, score=None, status="excused", note="Excused (accommodation)", group=g.get("id"))
        gw = num(go.get("weight")) if go.get("weight") is not None else num(g.get("weight"))
        keep = max(1.0, min(num(go.get("keep")) if go.get("keep") is not None else num(g.get("keep")), float(len(live) or 1)))
        done = [x for x in live if x.get("id") in rows and rows[x["id"]]["score"] is not None]
        best = sorted(done, key=lambda x: -rows[x["id"]]["score"])[:int(keep)]
        kept = {x["id"] for x in best}
        for x in live:
            r = rows.get(x.get("id"))
            if not r:
                continue
            r["group"] = g.get("id")
            if x["id"] in kept:
                r["w"] = gw / keep
                r["note"] = f"{r['note'] + ' · ' if r['note'] else ''}One of the best {fmt_num(keep)} in {g.get('name')}"
            elif r["score"] is not None:
                r.update(w=0.0, status="notcounted", note=f"Not counted: not among the best {fmt_num(keep)} in {g.get('name')}")

    # A weight changed for this student: the others scale so the total stays the course's (usually 100%).
    def g_weight(g):
        go = b.group_override(s, g) or {}
        live = any(b.eval_by_id(i) and i not in _list(go.get("excused")) and status_of(b.mark_of(s, i)) != "excused" for i in _list(g.get("members")))
        return (num(go.get("weight")) if go.get("weight") is not None else num(g.get("weight"))) if live else 0.0

    base = b.weight_sum()
    eff = sum(g_weight(u["g"]) if "g" in u else 0.0 if status_of(b.mark_of(s, u["e"].get("id"))) == "excused" else policy_for(b, s, u["e"])["weight"] for u in b.units())
    if eff > 0 and abs(base - eff) > 1e-9:
        for e in evs:
            rows[e.get("id")]["w"] *= base / eff
    settled = [e for e in evs if rows[e.get("id")]["status"] != "pending"]
    w_done = sum(rows[e.get("id")]["w"] for e in settled)
    earned = sum(rows[e.get("id")]["w"] * (rows[e.get("id")]["score"] or 0) for e in settled)
    pending = len(evs) - len(settled)
    for r in rows.values():
        for k in ("missed", "mk", "w0", "inbox"):
            r.pop(k, None)
    return {"rows": rows, "current": earned / w_done * 100 if w_done > 0 else None,
            "final": earned if pending == 0 and evs else None, "earned": earned, "done": w_done, "pending": pending}
