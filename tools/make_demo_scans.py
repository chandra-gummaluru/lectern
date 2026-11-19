"""Makes the demo course's scanned midterm booklets (sample-data/demo-course/scans/midterm/): the printed student
copy, and ten students' booklets written on and "scanned", as tests/test_autograde.py makes them (held-out
handwritten digits; a tidier scanner than the tests', so the file stays small). Loading the demo copies them in and reads them, as an upload.

Run it again after changing the demo midterm (its printed copy must be the one the booklets were written on):

    python tools/make_demo_scans.py

Needs pdflatex and the scan packages (requirements-scan.txt).
"""
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import test_autograde as T  # noqa: E402
from server.autograde import grade, layout  # noqa: E402

DEMO = os.path.join(ROOT, "sample-data", "demo-course")
OUT = os.path.join(DEMO, "scans", "midterm")
STUDENTS = 10


def compile_student_copy():
    with tempfile.TemporaryDirectory() as tmp:
        for f in ("midterm.tex", "course.cls"):
            shutil.copy(os.path.join(DEMO, "priv", "midterm", f), tmp)
        from server.scanning import build_pdf
        return build_pdf(tmp, "midterm.tex")


def answers_for(exam, rng):
    """One student's answers: each question right about three times in four, else wrong (now and then blank).
    Words (a blank's, a written answer's) aren't written: those are marked by hand in the demo."""
    out = {}
    for label, n in grade.leaves(exam, 0):
        opts, t = n.get("options") or [], n.get("type")
        def good():
            return rng.random() < 0.78
        if rng.random() < 0.04:
            continue                                         # left blank
        if t == "ms":
            right = [o["id"] for o in opts if o["correct"]]
            pick = right if good() else [o["id"] for o in opts if rng.random() < 0.5] or [opts[0]["id"]]
            out.update({f"{n['id']}.{i}": "tick" for i in pick})
        elif t == "mc":
            right = next(o["id"] for o in opts if o["correct"])
            other = [o["id"] for o in opts if o["id"] != right]
            out[f"{n['id']}.{right if good() else other[int(rng.integers(len(other)))]}"] = "fill"
        elif t == "tf":
            truth = "T" if str(n.get("answer")).lower() == "true" else "F"
            out[f"{n['id']}:{truth if good() else ('F' if truth == 'T' else 'T')}"] = "fill"
        for cid, c in (n.get("comps") or {}).items():
            rid = f"{n['id']}.{cid}"
            if c["kind"] == "num":
                out[rid] = c["ans"] if good() else str(int(rng.integers(1, 99)))
            elif c["kind"] == "cells":
                v = c["ans"].replace(",", "")
                if not good():
                    k = int(rng.integers(len(v)))
                    v = v[:k] + ("0" if v[k] == "1" else "1") + v[k + 1:]
                out.update(T.cells(rid, v))
            elif c["kind"] == "frac":
                ok = good()
                out[f"{rid}:n"] = c["num"] if ok else str(int(rng.integers(5, 9)))
                out[f"{rid}:d"] = c["den"] if ok else "8"
    return out


def scanned(img, rng):
    """A tidy scanner's page (the tests' scanner is rougher, and its noise would make the demo's file big): a small
    turn and shift, a little blur, a white background."""
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), float(rng.uniform(-1.2, 1.2)), float(rng.uniform(0.98, 1.01)))
    M[:, 2] += rng.uniform(-15, 15, 2)
    out = cv2.warpAffine(img, M, (w, h), borderValue=255)
    out = cv2.GaussianBlur(out, (3, 3), 0.7).astype(np.float32) * 0.95 + 6 + rng.normal(0, 1.5, out.shape)
    out = np.clip(out, 0, 255).astype(np.uint8)
    out[out > 232] = 255
    return out


def main():
    exam = json.load(open(os.path.join(DEMO, "priv", "midterm", "exam.json"), encoding="utf-8"))
    book = json.load(open(os.path.join(DEMO, "priv", "grades.json"), encoding="utf-8"))
    people = [s for s in book["students"] if not s.get("dropped")][:STUDENTS]
    printed = compile_student_copy()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "midterm.pdf"), "wb") as f:
        f.write(printed)
    t = layout.load_template(os.path.join(OUT, "midterm.pdf"))
    rng = np.random.default_rng(258)
    pages = []
    for k, who in enumerate(people):
        pages += [scanned(img, rng) for img in T.booklet(t, who, answers_for(exam, rng), T.Pen(300 + k), rng)]
    # As a scanner's own PDF: each page a JPEG, put together without re-encoding.
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument.new()
    for x in pages:
        ok, jpg = cv2.imencode(".jpg", x, [cv2.IMWRITE_JPEG_QUALITY, 60])
        img = pdfium.PdfImage.new(doc)
        img.load_jpeg(io.BytesIO(jpg.tobytes()), inline=True)
        h, w = x.shape
        pw, ph = w * 72 / 200, h * 72 / 200
        img.set_matrix(pdfium.PdfMatrix().scale(pw, ph))
        page = doc.new_page(pw, ph)
        page.insert_obj(img)
        page.gen_content()
    buf = io.BytesIO()
    doc.save(buf)
    with open(os.path.join(OUT, "booklets.pdf"), "wb") as f:
        f.write(buf.getvalue())
    with open(os.path.join(OUT, "students.json"), "w", encoding="utf-8") as f:
        json.dump([s["num"] for s in people], f)
    print(f"{len(people)} booklets, {len(pages)} pages, {len(buf.getvalue()) // 1024} KB")


if __name__ == "__main__":
    main()
