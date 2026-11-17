"""Marking scanned exams (server/autograde), end to end, on made-up scans.

An exam with every kind of answer the grader marks is written with the Exam Builder's own LaTeX code (taken out of
tools/exam-builder.html and run with node), compiled with pdflatex in two versions, and "printed": each page is
drawn at 200 dpi, a student's answers are put on it (filled bubbles, ticks, held-out handwritten digits from
tests/heldout-digits.npz, which the digit reader never trained on), and it's "scanned": turned a little,
scaled, shifted, blurred, speckled, some pages upside down and out of order. Then the grader must find each
student, and mark what it can exactly as a person would. (Skipped without pdflatex, node, or the scan packages.)
"""
import json
import math
import os
import re
import shutil
import subprocess

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("pypdfium2")
if not shutil.which("pdflatex") or not shutil.which("node"):
    pytest.skip("needs pdflatex and node", allow_module_level=True)

from server.autograde import grade, layout, report  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(ROOT, "tools", "exam-builder.html")
NAMES = ["LET", "num", "fmtNum", "TOKEN", "isQ", "nodePoints", "variantFor", "numbering", "handout", "texEsc", "ptsTex", "cm",
         "examSlug", "pts", "scanning", "scanId", "scanCode", "spaceTex", "solutionTex", "markingTex", "itemize", "widestRow",
         "boxSizeTex", "studentInfoTex", "compTex", "bodyTex", "choicesTex", "nodeTex", "genTex"]


def builder_js():
    """The builder's LaTeX functions, as a script: reads {exam, version} on stdin, prints that version's .tex."""
    lines = open(BUILDER, encoding="utf-8").read().split("\n")
    out = []
    for n in NAMES:
        start = next((i for i, l in enumerate(lines) if re.match(rf"^(const {n} = |function {n}\()", l)), None)
        assert start is not None, f"{n} isn't in the exam builder any more: update this test"
        end = start + 1
        while end < len(lines) and not re.match(r"^(const|let|function|async function|//|[A-Za-z_$][\w$]*\.)", lines[end]):
            end += 1
        out.append("\n".join(lines[start:end]))
    return 'let model; const gh = { path: "csc258/f26/midterm/exam.json" };\n' + "\n".join(out) + """
let inp = ""; process.stdin.on("data", d => inp += d).on("end", () => {
  const { exam, version } = JSON.parse(inp); model = exam; process.stdout.write(genTex(version));
});"""


def opt(i, correct=False, text=None):
    return {"id": f"o{i}", "text": text or f"Option {i}", "correct": correct}


def node(nid, typ="written", **kw):
    n = {"id": nid, "type": typ, "body": "", "points": 1, "solution": "", "rubric": [], "space": {"mode": "none", "h": "4cm"},
         "options": [], "layout": "stack", "answer": "true", "comps": {}, "parts": []}
    n.update(kw)
    return n


def question(qid, *variants):
    return {"kind": "question", "id": qid, "marking": "full", "newPage": False, "tags": [], "notes": "", "variants": list(variants)}


def make_exam():
    return {
        "format": "exam-builder/2",
        "settings": {"title": "Midterm", "courseCode": "CSC258", "courseName": "", "term": "Fall 2026", "instructors": "", "date": "",
                     "duration": "", "university": "University of Toronto", "department": "", "target": 0, "versions": 2,
                     "topSpace": 0, "pageNumbers": True, "macros": "", "preamble": "", "layout": "exam", "instructions": "",
                     "link": "", "scan": True},
        "cover": {"on": True, "pointsTable": True, "scoreRow": True, "instructionsOn": False, "goodLuck": False, "aids": "", "instructions": "",
                  "fields": [{"id": "f1", "label": "Last Name", "type": "boxes", "count": 16, "beside": False},
                             {"id": "f2", "label": "First Name", "type": "boxes", "count": 16, "beside": False},
                             {"id": "f3", "label": "UTORId", "type": "boxes", "count": 8, "beside": False},
                             {"id": "f4", "label": "Student #", "type": "boxes", "count": 10, "beside": True}]},
        "items": [
            question("q1", node("mcA", "mc", points=2, body="Which is a universal gate?", options=[opt(1), opt(2, True), opt(3), opt(4)]),
                     node("mcB", "mc", points=2, body="Which is not a universal gate?", options=[opt(1), opt(2), opt(3, True), opt(4)])),
            question("q2", node("tf", "tf", answer="false", body="A latch is edge-triggered.")),
            question("q3", node("ms", "ms", points=2, body="Which are sequential?", layout="row", options=[opt(1, True), opt(2), opt(3, True)])),
            question("q4", node("n4", body="Six times seven is [[c1]].", points=2, comps={"c1": {"kind": "num", "w": "3cm", "ans": "42"}})),
            question("q5", node("n5", points=4, body="Eleven in binary: [[c2]]. Three quarters: $[[c3]]$",
                                comps={"c2": {"kind": "cells", "n": 4, "cell": "9mm", "ans": "1,0,1,1"},
                                       "c3": {"kind": "frac", "w": "1.8cm", "num": "3", "den": "4"}})),
            question("q6", node("n6", points=3, body="Explain why.", space={"mode": "height", "h": "3cm"})),
            {"kind": "break", "id": "br", "title": "", "body": ""},
            question("q7", node("n7", body="Two parts.", parts=[
                node("p7a", "mc", body="Pick C.", layout="cols3", options=[opt(1), opt(2), opt(3, True)]),
                node("p7b", points=2, body="The answer is [[c4]].", space={"mode": "height", "h": "2.5cm"},
                     comps={"c4": {"kind": "num", "w": "3.5cm", "ans": "-3.5"}})])),
        ],
        "total": 0,
    }


ROSTER = [{"num": n, "first": f, "last": l} for n, f, l in [
    ("1008789130", "Iris", "Bauer"), ("1008155252", "Arjun", "Castillo"), ("1009342761", "Maya", "Okafor"),
    ("1007621984", "Liam", "Nguyen"), ("1006213409", "Sofia", "Rossi"), ("1009977143", "Ben", "Adeyemi")]]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("exam")
    shutil.copy(os.path.join(ROOT, "tools", "course.cls"), d / "course.cls")
    exam = make_exam()
    js = builder_js()
    pdfs = []
    for v, name in ((0, "midterm-A"), (1, "midterm-B")):
        p = subprocess.run(["node", "-e", js], input=json.dumps({"exam": exam, "version": v}), capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        (d / f"{name}.tex").write_text(p.stdout, encoding="utf-8")
        for _ in range(2):
            r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{name}.tex"], cwd=d, capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stdout[-3000:]
        pdfs.append(str(d / f"{name}.pdf"))
    return exam, pdfs, d


def test_builder_carries_the_class():
    """The class the builder writes into each exam folder is tools/course.cls."""
    src = open(BUILDER, encoding="utf-8").read()
    m = re.search(r"^const COURSE_CLS = (\".*\");$", src, re.M)
    assert json.loads(m.group(1)) == open(os.path.join(ROOT, "tools", "course.cls"), encoding="utf-8").read()


def test_without_scanning_nothing_changes():
    exam = make_exam()
    exam["settings"]["scan"] = False
    p = subprocess.run(["node", "-e", builder_js()], input=json.dumps({"exam": exam, "version": 0}), capture_output=True, text=True, timeout=60)
    assert "\\ScanID" not in p.stdout and "\\ScanCode" not in p.stdout


def test_layout_has_every_piece(built):
    exam, pdfs, _ = built
    ta, tb = (layout.load_template(p) for p in pdfs)
    assert ta.code == "csc258-fall-2026-midterm-a" and tb.code == "csc258-fall-2026-midterm-b"
    assert len(ta.pages) == 3
    ids = set().union(*(p.regions for p in ta.pages))
    want = {"mcA.o1", "mcA.o4", "tf:T", "tf:F", "ms.o3", "n4.c1", "n5.c2:c0", "n5.c2:c3", "n5.c3:n", "n5.c3:d", "n6.space",
            "p7a.o3", "p7b.c4", "p7b.space", "cover:f3:c9", "cover:f0:c15"}
    assert want <= ids, want - ids
    assert "mcB.o1" in set().union(*(p.regions for p in tb.pages)) and "mcB.o1" not in ids
    assert "p7a.o1" in ta.pages[2].regions                      # after the page break


# ── Making scans ───────────────────────────────────────────────────────

DIGITS = np.load(os.path.join(ROOT, "tests", "heldout-digits.npz"))


class Pen:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.used = {}

    def digit(self, d):
        """A held-out handwritten digit (white on black, 20x20), a different one each time."""
        idx = np.where(DIGITS["labels"] == d)[0]
        k = self.used.get(d, int(self.rng.integers(0, len(idx))))
        self.used[d] = k + 1
        return DIGITS["images"][idx[k % len(idx)]]


def write_digit(img, pen, d, x, y, h):
    g = pen.digit(d)
    g = cv2.resize(g, (int(h), int(h)), interpolation=cv2.INTER_CUBIC)
    ink = (255 - (g > 100) * (255 - int(pen.rng.integers(20, 70)))).astype(np.uint8)
    H, W = img.shape
    y, x = int(y), int(x)
    part = img[y:y + ink.shape[0], x:x + ink.shape[1]]
    np.minimum(part, ink[:part.shape[0], :part.shape[1]], out=part)


def write_text(img, pen, text, rect):
    """Handwriting in a box: digits, a minus sign, a decimal point."""
    x, y, w, h = rect
    ch = 0.62 * h
    cx, base = x + 0.12 * h, y + 0.18 * h
    for c in text:
        if c.isdigit():
            write_digit(img, pen, int(c), cx, base, ch)
            cx += 0.62 * ch
        elif c == "-":
            cv2.line(img, (int(cx + 2), int(base + ch / 2)), (int(cx + 0.5 * ch), int(base + ch / 2)), 40, 3)
            cx += 0.6 * ch
        elif c == ".":
            cv2.circle(img, (int(cx + 0.38 * ch), int(base + 0.82 * ch)), 3, 40, -1)
            cx += 0.62 * ch


def fill_bubble(img, rect, pen):
    x, y, w, h = rect
    cv2.circle(img, (int(x + w / 2 + pen.rng.normal(0, 1)), int(y + h / 2 + pen.rng.normal(0, 1))), int(0.42 * w), int(pen.rng.integers(30, 90)), -1)


def tick(img, rect):
    x, y, w, h = rect
    pts = np.array([[x + 0.2 * w, y + 0.55 * h], [x + 0.42 * w, y + 0.8 * h], [x + 0.85 * w, y + 0.15 * h]], np.int32)
    cv2.polylines(img, [pts], False, 35, 3)


def scanned(img, rng, upside_down=False):
    """Print and scan: a small turn, scale and shift, blur, speckles, a grey background."""
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), float(rng.uniform(-2, 2)) + (180 if upside_down else 0), float(rng.uniform(0.96, 1.02)))
    M[:, 2] += rng.uniform(-25, 25, 2)
    out = cv2.warpAffine(img, M, (w, h), borderValue=255)
    out = cv2.GaussianBlur(out, (3, 3), 0.8).astype(np.float32)
    out = out * 0.92 + 8 + rng.normal(0, 6, out.shape)
    out[rng.random(out.shape) < 0.0005] = 0
    return np.clip(out, 0, 255).astype(np.uint8)


def booklet(t, student, answers, pen, rng):
    """One student's pages, written on: answers maps a piece's id to what they wrote."""
    pages = []
    for tp in t.pages:
        img = tp.image.copy()
        if tp.number == 1 and student:
            for i, d in enumerate(student["num"]):
                x, y, w, h = tp.regions[f"cover:f3:c{i}"]
                write_digit(img, pen, int(d), x + 0.15 * w, y + 0.15 * h, 0.7 * h)
        for rid, what in answers.items():
            r = tp.regions.get(rid)
            if r is None:
                continue
            if what == "fill":
                fill_bubble(img, r, pen)
            elif what == "tick":
                tick(img, r)
            else:
                write_text(img, pen, what, r)
        pages.append(img)
    return pages


def cells(rid, s):
    return {f"{rid}:c{i}": c for i, c in enumerate(s) if c != "_"}


HANDWRITTEN = {"4", "5", "7(b)"}


def test_marks_scans(built, tmp_path):
    """Every student is found; every bubble is marked as a person would; every handwritten answer is either marked
    right or sent to a person (never marked wrong without a flag)."""
    exam, pdfs, _ = built
    ta, tb = (layout.load_template(p) for p in pdfs)
    rng = np.random.default_rng(7)
    S = {s["num"]: s for s in ROSTER}
    # (student, template, answers, expected score per question, expected status per question)
    perfect = {"mcA.o2": "fill", "tf:F": "fill", "ms.o1": "tick", "ms.o3": "tick", "n4.c1": "42", **cells("n5.c2", "1011"),
               "n5.c3:n": "3", "n5.c3:d": "4", "p7a.o3": "fill", "p7b.c4": "-3.5"}
    cases = [
        (S["1008789130"], ta, perfect,
         {"1": 2, "2": 1, "3": 2, "4": 2, "5": 4, "6": None, "7(a)": 1, "7(b)": 2}),
        (S["1009342761"], tb, {"mcB.o1": "fill", "tf:T": "fill", "ms.o1": "tick", "n4.c1": "24", **cells("n5.c2", "1011"),
                               "n5.c3:n": "6", "n5.c3:d": "8", "p7a.o2": "fill", "p7b.c4": "35"},
         {"1": 0, "2": 0, "3": 0, "4": 0, "5": 4, "6": None, "7(a)": 0, "7(b)": 0}),
        (S["1007621984"], ta, {"mcA.o2": "fill", "mcA.o3": "fill", "ms.o1": "tick", "ms.o3": "tick", "n4.c1": "42", **cells("n5.c2", "1001"),
                               "n5.c3:n": "3", "n5.c3:d": "4", "p7a.o3": "fill", "p7b.c4": "-3.5"},
         {"1": "check", "2": 0, "3": 2, "4": 2, "5": 2, "6": None, "7(a)": 1, "7(b)": 2}),
        (S["1009977143"], tb, {"mcB.o3": "fill", "tf:F": "fill", "ms.o1": "tick", "ms.o3": "tick", "n4.c1": "42", **cells("n5.c2", "1011"),
                               "n5.c3:n": "3", "n5.c3:d": "4", "p7a.o3": "fill", "p7b.c4": "-3.5"},
         {"1": 2, "2": 1, "3": 2, "4": 2, "5": 4, "6": None, "7(a)": 1, "7(b)": 2}),
    ]
    from PIL import Image
    scans = []
    for k, (st, t, ans, _) in enumerate(cases):
        pages = booklet(t, st, ans, Pen(k), rng)
        order = [0, 2, 1] if k == 1 else [0, 1, 2]            # booklet 2: pages out of order, one upside down
        scans += [scanned(pages[i], rng, upside_down=(k == 1 and i == 2)) for i in order]
    path = tmp_path / "scans.pdf"
    ims = [Image.fromarray(s) for s in scans]
    ims[0].save(path, save_all=True, append_images=ims[1:], resolution=200)

    res = grade.run(exam, pdfs, [str(path)], ROSTER)
    unsure = []
    assert res["unread"] == []
    assert len(res["booklets"]) == len(cases)
    for b, (st, t, _, want) in zip(res["booklets"], cases):
        assert b["student"]["num"] == st["num"], b["student"]
        assert b["student"]["status"] == "auto", b["student"]
        got = {q["label"]: q for q in b["questions"]}
        assert set(got) == set(want)
        for label, score in want.items():
            q = got[label]
            if score is None:
                assert q["status"] == "manual", (label, q)
                continue
            if score == "check":
                assert q["status"] == "check", (label, q)
                continue
            if q["status"] == "check" and label in HANDWRITTEN:     # an unsure read goes to a person: fine, if rare
                unsure.append((b["student"]["name"], label, q["read"]))
                continue
            assert q["score"] == score, (b["student"]["name"], label, {k: v for k, v in q.items() if k != "picture"})
    assert len(unsure) <= 3, unsure                            # of 16 handwritten answers
    b3 = {q["label"]: q for q in res["booklets"][2]["questions"]}
    assert b3["2"]["status"] == "auto" and b3["2"]["read"] == "none"   # left blank
    b2 = {q["label"]: q for q in res["booklets"][1]["questions"]}
    assert b2["7(b)"]["status"] == "check"                     # wrong (or unsure), with room for working: a person looks
    report.write(res, str(tmp_path / "out"))
    assert (tmp_path / "out" / "review.html").exists() and (tmp_path / "out" / "marks.csv").read_text().count("\n") == len(cases) + 1


def test_unknown_pages_are_reported(built, tmp_path):
    exam, pdfs, _ = built
    from PIL import Image
    blank = np.full((2200, 1700), 250, np.uint8)
    p = tmp_path / "blank.png"
    Image.fromarray(blank).save(p)
    res = grade.run(exam, pdfs[:1], [str(p)], ROSTER)
    assert res["booklets"] == [] and len(res["unread"]) == 1


def test_numbers():
    assert grade.number("3/4") == 0.75 and grade.number("-3.5") == -3.5 and grade.number(".5") == 0.5
    assert grade.number("") is None and grade.number("1/0") is None and grade.number("4-") is None
    assert grade.same(grade.number("6/8"), 0.75)
    assert not grade.same(0.749, 0.75) and grade.same(0.749, 0.75, "0.01")
