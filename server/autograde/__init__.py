"""Marking scanned exams automatically (the Exam Builder's "Marking from scans").

    python app.py autograde exam.json --pdf midterm.pdf --scans scans.pdf [--class grades.json] [--out results]

How it fits together:
  layout.py   where every answer piece is, read from the student copy's PDF (the tags course.cls v2.6 puts there)
  scan.py     a scanned page's QR code and corner squares, and lining it up with its printed page
  read.py     the student's ink in each piece: how filled a bubble is, the characters in a box
  digits.py   reading one handwritten digit (a small network; weights in digits.npz, made by train_digits.py)
  grade.py    booklets, marking each question, finding the student on the class list
  report.py   results.json, marks.csv, review.html and its pictures

It needs numpy, opencv-python-headless and pypdfium2 (requirements-scan.txt); the rest of Lectern doesn't.
"""
import argparse
import json
import os
import sys


def main(argv):
    p = argparse.ArgumentParser(prog="python app.py autograde", description="Mark scanned exams against exam.json.")
    p.add_argument("exam", help="the exam's exam.json (from the Exam Builder, with Marking from scans on)")
    p.add_argument("--pdf", action="append", required=True, metavar="PDF",
                   help="the student copy that was printed (compiled from <exam>.tex); one --pdf per version")
    p.add_argument("--scans", action="append", required=True, metavar="FILE",
                   help="scanned PDFs or images, in the order scanned (repeat for more files)")
    p.add_argument("--class", dest="roster", metavar="grades.json",
                   help="the offering's gradebook, for its class list (student numbers and names)")
    p.add_argument("--out", default="autograde-results", help="folder for the results (default: autograde-results)")
    a = p.parse_args(argv)
    try:
        from . import grade, report
    except ImportError as err:
        sys.exit(f"Marking from scans needs a few more Python packages: pip install -r requirements-scan.txt ({err})")
    with open(a.exam, encoding="utf-8") as f:
        exam = json.load(f)
    roster = None
    if a.roster:
        with open(a.roster, encoding="utf-8") as f:
            roster = [s for s in json.load(f).get("students") or [] if not s.get("dropped")]
    res = grade.run(exam, a.pdf, a.scans, roster, progress=lambda n: print(f"\r{n} booklets marked", end="", flush=True))
    print()
    os.makedirs(a.out, exist_ok=True)
    title = " ".join(x for x in (exam.get("settings", {}).get("courseCode"), exam.get("settings", {}).get("title")) if x) or "Scanned exams"
    report.write(res, a.out, title)
    bs = res["booklets"]
    print(f"{len(bs)} booklets; {sum(b['to_check'] for b in bs)} answers to look at; "
          f"{sum(1 for b in bs if b['student'].get('status') != 'auto')} students to confirm; "
          f"{len(res['unread'])} pages not placed.")
    print(f"Open {os.path.join(a.out, 'review.html')} to look through them; marks.csv has the marks.")
