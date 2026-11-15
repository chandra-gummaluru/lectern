"""The grade so far (server/grading.py) agrees with the gradebook's own (the Grade Builder's studentResult).

The builder's JavaScript is taken out of tools/grade-builder.html and run with node on the same gradebooks:
the sample ones, then the same with random statuses, accommodations, makeups and reweights. Every student's
grade, and every evaluation's weight, score and status, must match. (Skipped where node isn't installed.)
"""
import copy
import json
import os
import random
import re
import shutil
import subprocess

import pytest

from server import grading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(os.path.join(ROOT, "sample-data/demo-courses-private")) for f in fs if f == "grades.json")
NAMES = ["num", "fmtNum", "totalSet", "ratio", "evalById", "makeupsOf", "counted", "groupOf", "units", "groupShort", "markOf", "overrideOf",
         "STATUSES", "statusOf", "groupOverride", "weightSum", "shortName", "shareParts", "policyFor", "studentResult"]


def builder_js():
    """The builder's grade functions, as a script that reads {book, students} on stdin and prints the results."""
    src = open(os.path.join(ROOT, "tools/grade-builder.html"), encoding="utf-8").read()
    out = []
    for n in NAMES:
        m = re.search(rf"^(const {n} = .*|function {n}\(.*)$", src, re.M)
        assert m, f"{n} isn't in the grade builder any more: update server/grading.py and this test"
        if m.group(1).startswith("const"):
            out.append(m.group(1))
            continue
        i, depth = src.index("{", m.start()), 0
        for j in range(i, len(src)):
            depth += {"{": 1, "}": -1}.get(src[j], 0)
            if depth == 0:
                out.append(src[m.start():j + 1])
                break
    return "let model;\n" + "\n".join(out) + """
let inp = ""; process.stdin.on("data", d => inp += d).on("end", () => {
  const { book, students } = JSON.parse(inp); model = book;
  const res = {}; students.forEach(s => { const r = studentResult(s), rows = {};
    Object.entries(r.rows).forEach(([k, x]) => { rows[k] = { w: x.w, score: x.score, status: x.status, note: x.note }; });
    res[s] = { current: r.current, final: r.final, earned: r.earned, pending: r.pending, rows }; });
  process.stdout.write(JSON.stringify(res));
});"""


def js_results(book):
    node = shutil.which("node")
    p = subprocess.run([node, "-e", builder_js()], input=json.dumps({"book": book, "students": [s["num"] for s in book["students"]]}),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def close(a, b):
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)


def same(book):
    js = js_results(book)
    for s in book["students"]:
        py, want = grading.student_result(book, s["num"]), js[s["num"]]
        for k in ("current", "final", "earned"):
            assert close(py[k], want[k]), (s["num"], k, py[k], want[k])
        assert py["pending"] == want["pending"]
        for eid, w in want["rows"].items():
            r = py["rows"][eid]
            assert r["status"] == w["status"] and close(r["w"], w["w"]) and close(r["score"], w["score"]) and r["note"] == w["note"], (s["num"], eid, r, w)


def shake(book, seed):
    """The same gradebook with random statuses, accommodations, makeups and reweights."""
    rnd, b = random.Random(seed), copy.deepcopy(book)
    ids = [e["id"] for e in b["evals"]]
    alone = [e for e in b["evals"] if not e.get("makeupFor") and not any(e["id"] in g["members"] for g in b["groups"])]
    for e in alone:   # some are reweighted when missed, to others (and back: chains and loops)
        if rnd.random() < 0.5:
            others = [x["id"] for x in alone if x is not e]
            e["missed"] = {"mode": "reweight", "split": "custom", "makeups": e["missed"].get("makeups", []),
                           "to": [{"id": i, "share": rnd.choice([25, 50, 60, 100])} for i in rnd.sample(others, min(len(others), rnd.randint(1, 2)))]}
    for s in b["students"]:
        m = b["marks"].setdefault(s["num"], {})
        for i in ids:
            x = rnd.random()
            if x < 0.05:
                m[i] = {"status": rnd.choice(["aiv", "excused", "deferred"])}
            elif x < 0.12:
                m[i] = {"missed": True}
            elif x < 0.17:
                m.pop(i, None)
        if rnd.random() < 0.3 and alone:
            e = rnd.choice(alone)
            b["overrides"].setdefault(s["num"], {})[e["id"]] = {"weight": rnd.choice([0, 5, 12.5, 30])}
        if rnd.random() < 0.3 and b["groups"]:
            g = b["groups"][0]
            b["overrides"].setdefault(s["num"], {})["g:" + g["id"]] = {"keep": rnd.randint(1, 4), "excused": rnd.sample(g["members"], 1), **({"weight": 7} if rnd.random() < 0.5 else {})}
    return b


needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node isn't installed")


@needs_node
@pytest.mark.parametrize("path", BOOKS, ids=lambda p: "/".join(p.split(os.sep)[-3:-1]))
def test_the_same_as_the_gradebook_on_the_samples(path):
    same(json.load(open(path, encoding="utf-8")))


@needs_node
@pytest.mark.parametrize("seed", range(6))
def test_the_same_as_the_gradebook_with_accommodations_and_reweights(seed):
    for path in BOOKS[::2]:
        same(shake(json.load(open(path, encoding="utf-8")), seed * 31 + len(path)))


def test_a_small_gradebook_by_hand():
    book = {"evals": [{"id": "a", "name": "Assn 1", "total": 10, "weight": 40, "missed": {"mode": "zero"}},
                      {"id": "t", "name": "Test 1", "total": 50, "weight": 60, "missed": {"mode": "reweight", "split": "custom", "to": [{"id": "a", "share": 100}], "makeups": []}}],
            "groups": [], "marks": {"1": {"a": {"pts": 8}}, "2": {"a": {"pts": 5}, "t": {"missed": True}}}, "overrides": {}}
    one = grading.student_result(book, "1")
    assert one["current"] == pytest.approx(80) and one["pending"] == 1 and one["final"] is None
    two = grading.student_result(book, "2")   # the test's weight moved to the assignment: 50% of everything
    assert two["final"] == pytest.approx(50) and two["rows"]["a"]["w"] == pytest.approx(100)
    assert two["rows"]["t"]["note"] == "Not submitted: 60% moved to Assn 1"
    assert grading.fmt_num(12.345) == "12.35" and grading.fmt_num(3) == "3" and grading.num("12abc") == 12
