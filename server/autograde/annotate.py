"""A marked booklet as a PDF for its student: their own scanned pages, straightened, with the marking drawn on in red,
as a marker's pen would:

- the cover's points table filled in (each question's score, and the total), and the overall percentage top right;
- each question's score in its own "[    ] / 2" box;

- a tick or a cross by each bubble, box and blank the grader marked (and, if asked, a green ring round the right
  bubbles and the right answer by a wrong blank);
- each question's comments (and a note) in the right margin, level with its first answer piece (with its score
  there too, in a box, if its own box wasn't found).

The pages are drawn again from the uploaded scans (the results keep only small pictures), so this needs the scans
and the printed student copy the booklet was marked against.
"""
import io
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import scan
from .grade import LET, leaves, num

RED, GREEN, INK, GREY = (192, 42, 32), (40, 130, 80), (31, 35, 41), (110, 116, 124)
W_IN, MARGIN_IN = 8.5, 1.0


def _font_path(name):
    try:
        p = subprocess.run(["kpsewhich", name], capture_output=True, text=True, timeout=5).stdout.strip()
        return p if p and os.path.isfile(p) else None
    except Exception:
        return None


_FONTS = {}
HAND = os.path.join(os.path.dirname(__file__), "fonts")     # Kalam (SIL Open Font License, fonts/OFL.txt): a marker's hand


def font(kind, size):
    """Latin Modern (the exam's own type, from TeX) when it's there, else Pillow's own; "hand" and "hand-bold": Kalam,
    which comes with Lectern, for comments that look written by the marker."""
    key = (kind, size)
    if key not in _FONTS and kind.startswith("hand"):
        p = os.path.join(HAND, "Kalam-Bold.ttf" if kind == "hand-bold" else "Kalam-Regular.ttf")
        try:
            _FONTS[key] = ImageFont.truetype(p, size)
        except Exception:
            _FONTS[key] = font("serif-italic", size)
    if key not in _FONTS:
        p = _font_path({"serif": "lmroman10-regular.otf", "serif-bold": "lmroman10-bold.otf",
                        "serif-italic": "lmroman10-italic.otf", "sans": "lmsans10-regular.otf", "sans-bold": "lmsans10-bold.otf"}[kind])
        try:
            _FONTS[key] = ImageFont.truetype(p, size) if p else ImageFont.load_default(size=size)
        except Exception:
            _FONTS[key] = ImageFont.load_default(size=size)
    return _FONTS[key]


def wrap(draw, text, f, width):
    """The text in lines no wider than width (a word longer than that gets a line of its own)."""
    out = []
    for para in str(text or "").split("\n"):
        line = ""
        for w in para.split():
            t = f"{line} {w}".strip()
            if draw.textlength(t, font=f) <= width or not line:
                line = t
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


def fmt(x):
    if x is None:
        return "–"
    return str(int(x)) if float(x) == int(x) else f"{x:g}"


def delta(d):
    if d is None:
        return ""
    return f"+{fmt(d)}" if d > 0 else f"−{fmt(-d)}" if d < 0 else "±0"


def comments_of(q, answers):
    """A question's comments as the student sees them: (marks, text) lines, then the note. The right answer isn't
    in them: with answers on, it's drawn by the answer itself."""
    lines = [(delta(c.get("delta")), c.get("text", "")) for c in (q.get("comments") or []) + (q.get("auto") or [])]
    return lines, (q.get("note") or "").strip()


# ── Where each answer piece is ──────────────────────────────────────────

def pieces(n):
    """[(scan id, what it is)] for a question's answer pieces: ("opt", k) for the k-th bubble or box, ("blank", k) for the
    k-th blank (its ids all share k), ("space", 0) for room for working."""
    from .grade import comps_of
    t = n.get("type")
    if t == "tf":
        return [(f"{n['id']}:T", ("opt", 0)), (f"{n['id']}:F", ("opt", 1))]
    if t in ("mc", "ms"):
        return [(f"{n['id']}.{o['id']}", ("opt", k)) for k, o in enumerate(n.get("options") or [])]
    out = []
    for k, (cid, c) in enumerate(comps_of(n)):
        rid = f"{n['id']}.{cid}"
        kind = c.get("kind")
        if kind == "frac":
            out += [(rid + ":n", ("blank", k)), (rid + ":d", ("blank", k))]
        elif kind == "cells":
            out += [(f"{rid}:c{i}", ("blank", k)) for i in range(max(1, int(round(num(c.get("n")))) or 1))]
        else:
            out.append((rid, ("blank", k)))
    if (n.get("space") or {}).get("mode") not in (None, "none"):
        out.append((f"{n['id']}.space", ("space", 0)))
    return out


def chosen(n, q):
    """The option indexes the student picked, from what was read ("A, C", "B", "True")."""
    r = str(q.get("read") or "")
    if n.get("type") == "tf":
        return {0} if r.lower().startswith("t") else {1} if r.lower().startswith("f") else set()
    return {LET.index(x.strip()) for x in r.split(",") if x.strip() in LET}


def right_options(n):
    if n.get("type") == "tf":
        return {0} if (n.get("answer") or "true") == "true" else {1}
    return {k for k, o in enumerate(n.get("options") or []) if o.get("correct")}


# ── The marks table and the questions' score boxes ─────────────────────

_PRINTED = {}


def score_boxes(t, dpi=scan.DPI):
    """Where the printed copy has room for scores, found from its text: {"table": {"cells": {question number or
    "Total": (page, x, y)}}, "boxes": [(page, x, y, points)]}. The cover's points table has a Score row under its
    Question row; each question's "[    ] / 2" box is a "/" with a wide gap before it and its points after."""
    import pypdfium2 as pdfium
    if t.path in _PRINTED:
        return _PRINTED[t.path]
    k = dpi / 72
    out = {"table": {}, "boxes": []}
    try:
        doc = pdfium.PdfDocument(t.path)
    except Exception:
        return out
    for pi in range(len(doc)):
        page = doc[pi]
        H = page.get_size()[1]
        tp = page.get_textpage()
        chars = []
        for i in range(tp.count_chars()):
            c = tp.get_text_range(i, 1)
            if c.strip():
                l, b, r, top = tp.get_charbox(i)
                chars.append((c, l, b, r, top))
        tp.close()
        words, cur = [], None                   # characters into words: on one line, close together
        for c, l, b, r, top in chars:
            if cur and abs(b - cur[2]) < 3 and -1.5 <= l - cur[3] < 2.5:
                cur = [cur[0] + c, cur[1], min(cur[2], b), r, max(cur[4], top)]
            else:
                if cur:
                    words.append(cur)
                cur = [c, l, b, r, top]
        if cur:
            words.append(cur)
        px = lambda x, y: (x * k, (H - y) * k)
        heads = [w for w in words if w[0] == "Question:"]
        scores = [w for w in words if w[0] == "Score:"]
        if heads and scores and not out["table"]:
            h, sc = heads[0], scores[0]
            cols = sorted((w for w in words if abs(w[2] - h[2]) < 3 and w[1] > h[3] and (w[0].isdigit() or w[0] == "Total")), key=lambda w: w[1])
            img = t.page(pi + 1).image if t.page(pi + 1) else None
            for w in cols:
                x, y = px((w[1] + w[3]) / 2, (sc[2] + sc[4]) / 2)
                if img is not None:              # the middle of the cell: between the rules above and below the Score label
                    xi, yi = int(x), int(y)
                    up = next((yy for yy in range(yi, max(0, yi - int(dpi * .6)), -1) if img[yy, xi] < 110), None)
                    dn = next((yy for yy in range(yi, min(img.shape[0] - 1, yi + int(dpi * .6))) if img[yy, xi] < 110), None)
                    if up is not None and dn is not None:
                        y = (up + dn) / 2
                out["table"][w[0]] = (pi + 1, x, y)
        prev = None
        for j, w in enumerate(words):           # "/" after a wide gap, then the points
            if w[0] == "/" and prev and abs(prev[2] - w[2]) < 4 and w[1] - prev[3] > 20 and j + 1 < len(words) and words[j + 1][0].replace(".", "").isdigit():
                n = words[j + 1]                 # the points: their baseline, and how tall they're printed
                x, base = px((prev[3] + w[1]) / 2 + 2, n[2])     # the middle of the box's empty part (the box starts after the label)
                out["boxes"].append((pi + 1, x, base, float(n[0]), (n[4] - n[2]) * k))
            prev = w
    doc.close()
    _PRINTED[t.path] = out
    return out


def box_order(exam, version):
    """[(label, points)] in the order the student copy prints score boxes: a question (its own, or its parts' total),
    then each of its parts, and theirs."""
    from .grade import variant_for, node_points, _roman
    out, qn = [], 0

    def walk(n, label, depth):
        out.append((label, node_points(n)))
        for j, p in enumerate(n.get("parts") or []):
            walk(p, label + (f"({chr(97 + j)})" if depth == 0 else f"({_roman(j)})"), depth + 1)
    for it in exam.get("items") or []:
        if it.get("kind") != "question":
            continue
        qn += 1
        v = variant_for(it, version)
        if v:
            walk(v, str(qn), 0)
    return out


def scores_by_label(shown):
    """A function: a label's score (a question's, a part's, a sub-part's), the sum of its answers' scores; None
    while any of them isn't scored."""
    qs = shown.get("questions") or []

    def get(label):
        mine = [q for q in qs if q["label"] == label or q["label"].startswith(label + "(")]
        if not mine or any(q.get("score") is None for q in mine):
            return None
        return round(sum(q["score"] for q in mine), 2)
    return get


def fill_boxes(t, exam, version, shown, dpi):
    """The scores written into the printed copy's own places for them: the cover's table and each question's box."""
    where, marks = score_boxes(t, dpi), {}
    score = scores_by_label(shown)
    for name, (page, x, y) in where["table"].items():
        v = shown.get("total") if name == "Total" else score(name)
        if v is not None:
            marks.setdefault(page, []).append(("write", (x, y, 0, 0), fmt(v), "mm", dpi * .2))
    tot, out_of = shown.get("total"), shown.get("out_of")
    if out_of:                                  # the overall percentage, top right of the cover, its points under it
        pct = f"{fmt(round((tot or 0) / out_of * 1000) / 10)}%"
        x = dpi * (W_IN - MARGIN_IN)
        marks.setdefault(1, []).append(("big", (x, dpi * .95, 0, 0), pct, "rs"))
        marks[1].append(("write", (x, dpi * 1.2, 0, 0), f"{fmt(tot or 0)} / {fmt(out_of)}", "rs", dpi * .19))
    want, found, i = box_order(exam, version), where["boxes"], 0
    marks["filled"] = {}
    for page, x, y, pts, tall in found:               # in order, matched by their points; a "/ 3" in a question's text is skipped
        j = next((jj for jj in range(i, min(len(want), i + 3)) if abs(want[jj][1] - pts) < 1e-9), None)
        if j is None:
            continue
        v = score(want[j][0])
        if v is not None:
            marks.setdefault(page, []).append(("write", (x, y, 0, 0), fmt(v), "ms", tall / .72 * 1.15))     # on the printed baseline, a little bigger than print
            marks["filled"][want[j][0]] = (page, y - tall)
        i = j + 1
    return marks


# ── Drawing ─────────────────────────────────────────────────────────────

def tick(d, x, y, s, colour=RED, w=5):
    d.line([(x, y + s * .55), (x + s * .38, y + s * .9), (x + s, y + s * .1)], fill=colour, width=w, joint="curve")


def cross(d, x, y, s, colour=RED, w=5):
    d.line([(x, y), (x + s, y + s)], fill=colour, width=w)
    d.line([(x + s, y), (x, y + s)], fill=colour, width=w)


def ring(d, rect, colour=GREEN, pad=8, w=4):
    x, y, ww, hh = rect
    d.ellipse([x - pad, y - pad, x + ww + pad, y + hh + pad], outline=colour, width=w)


def mark_page(img, dpi, marks, notes):
    """marks: [(kind, rect, ...)] to draw on the page; notes: [(y, score text, comment lines, note)] for the margin."""
    page = Image.fromarray(img).convert("RGB")
    d = ImageDraw.Draw(page)
    s = int(dpi * 0.16)
    for m in marks:
        kind, (x, y, w, h) = m[0], m[1]
        cy = y + h / 2 - s / 2
        on = len(m) > 2 and m[2] == "on"          # a blank or box: on its top right corner (text sits on either side)
        if kind == "tick":
            tick(d, *((x + w - s * .4, y - s * .6) if on else (x - s - 10, cy)), s)
        elif kind == "cross":
            cross(d, *((x + w - s * .3, y - s * .5) if on else (x - s - 10, cy)), s * .8)
        elif kind == "ring":
            ring(d, (x, y, w, h))
        elif kind == "big":
            d.text((x, y), m[2], fill=RED, font=font("hand", int(dpi * .42)), anchor=m[3])
        elif kind == "write":                     # a score in the cover's table or a question's "[   ] / 2" box
            d.text((x, y), m[2], fill=RED, font=font("hand", int(m[4]) if len(m) > 4 else int(dpi * .17)), anchor=m[3])
        elif kind == "answer":                    # under the blank, so it covers nothing printed
            d.text((x, y + h + 6), m[2], fill=GREEN, font=font("sans-bold", int(dpi * .1)), anchor="la")
    W = page.width
    left, right = W - int(dpi * (MARGIN_IN - .1)), W - int(dpi * .12)
    width = right - left
    size = int(dpi * .115)                       # comments in a marker's hand
    fd, fc, fi = font("hand-bold", size), font("hand", size), font("hand", size)
    lh, col, floor = int(size * 1.12), int(dpi * .2), 0
    for y, score, lines, note in sorted(notes, key=lambda z: z[0]):
        y = max(y, floor)
        if score:                                # no box of its own was found: the score, boxed, first
            fb = font("hand", int(dpi * .18))
            tw = d.textlength(score, font=fb)
            d.rounded_rectangle([right - tw - 24, y - 6, right, y + int(dpi * .17) + 12], radius=10, outline=RED, width=4)
            d.text((right - 12, y), score, fill=RED, font=fb, anchor="ra")
            y += int(dpi * .17) + 24
        for dl, text in lines:                   # the marks in a column of their own, the words beside them
            if dl:
                d.text((left + col - 8, y), dl, fill=RED, font=fd, anchor="ra")
            for t in wrap(d, text, fc, width - col):
                d.text((left + col, y), t, fill=RED, font=fc, anchor="la")
                y += lh
            y += int(lh * .45)
        if note:
            for t in wrap(d, note, fi, width):
                d.text((left, y), t, fill=RED, font=fi, anchor="la")
                y += lh
        floor = y + int(lh * .8)
    return page


def booklet_pdf(exam, templates, page_image, booklet, shown, answers=False, dpi=scan.DPI):
    """PDF bytes. templates: the printed student copies (layout.Template); page_image(label): the scanned page with
    that label (grey); booklet: as marked (results.json); shown: as the page shows it (with the team's decisions,
    comments and notes); answers: whether to show the right answers."""
    by_code = {t.code: t for t in templates}
    t = by_code.get(booklet.get("code"))
    lined = {}
    for label in booklet.get("pages") or []:
        img = page_image(label)
        ident = scan.identify(img) if img is not None else None
        tp = t.page(ident["page"]) if t and ident and ident["code"] == t.code else None
        if tp is not None:
            lined[tp.number] = scan.align(img, ident, tp)
    version = LET.index(booklet["version"]) if booklet.get("version") in LET else 0
    qs = {q["label"]: q for q in shown.get("questions") or []}
    marks, notes = (fill_boxes(t, exam, version, shown, dpi) if t else {}), {}
    filled = marks.pop("filled", {})
    for label, n in leaves(exam, version):
        q = qs.get(label)
        if not q:
            continue
        lines, note = comments_of(q, answers)
        where = [(rid, what, *(t.find(rid) if t else (None, None))) for rid, what in pieces(n)]
        where = [w for w in where if w[2] is not None and w[2].number in lined]
        if not where:
            continue
        first = min(where, key=lambda w: (w[2].number, w[3][1]))
        badge = "" if label in filled else f"{fmt(q.get('score'))} / {fmt(q.get('points'))}"     # its own box has it already
        page_no, top = filled.get(label) or (first[2].number, first[3][1])       # level with the question's title, else its answer
        if badge or lines or note:
            notes.setdefault(page_no, []).append((int(top), badge, lines, note))
        pm = lambda w, *m: marks.setdefault(w[2].number, []).append(m)
        typ = n.get("type")
        if typ in ("mc", "ms", "tf") and q.get("status") != "missing":
            got, right = chosen(n, q), right_options(n)
            for w in where:
                k = w[1][1]
                if k in got:
                    pm(w, "tick" if k in right else "cross", w[3])
                if answers and k in right and k not in got:
                    pm(w, "ring", w[3])
        elif q.get("blanks") or any(x[1][0] == "blank" for x in where):
            bl = q.get("blanks")
            for k in sorted({x[1][1] for x in where if x[1][0] == "blank"}):
                ws = [x for x in where if x[1] == ("blank", k)]
                if bl and k < len(bl):
                    sc, pts, ans = bl[k].get("score"), bl[k].get("points") or 0, bl[k].get("answer", "")
                else:
                    sc, pts, ans = q.get("score"), q.get("points") or 0, q.get("answer", "")
                if sc is None:
                    continue
                x0 = min(x[3][0] for x in ws)
                y0 = min(x[3][1] for x in ws)
                x1 = max(x[3][0] + x[3][2] for x in ws)
                y1 = max(x[3][1] + x[3][3] for x in ws)
                pm(ws[0], "tick" if sc >= pts - 1e-9 else "cross", (x0, y0, x1 - x0, y1 - y0), "on")
                if answers and sc < pts - 1e-9 and ans:
                    pm(ws[0], "answer", (x0, y0, x1 - x0, y1 - y0), f"the answer: {ans}")
    pages = []
    for k in sorted(lined):
        pages.append(mark_page(lined[k], dpi, marks.get(k, []), notes.get(k, [])))
    if not pages:
        raise ValueError("None of this booklet's pages could be read again from the scans.")
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:], resolution=dpi, quality=70)
    return buf.getvalue()


def page_reader(uploads_dir, dpi=scan.DPI):
    """page_image(label) for a booklet's pages, labels as the grader gave them ("<file> p.<n>", or "<file>" for an image),
    keeping each PDF open while it's read."""
    import pypdfium2 as pdfium
    import cv2
    docs = {}

    def get(label):
        m = re.match(r"^(.*) p\.(\d+)$", label)
        name, n = (m.group(1), int(m.group(2))) if m else (label, 1)
        path = os.path.join(uploads_dir, name)
        if not os.path.isfile(path):
            return None
        if path.lower().endswith(".pdf"):
            doc = docs.get(path) or docs.setdefault(path, pdfium.PdfDocument(path))
            if not 1 <= n <= len(doc):
                return None
            return np.array(doc[n - 1].render(scale=dpi / 72, grayscale=True).to_pil().convert("L"))
        return cv2.imread(path, cv2.IMREAD_GRAYSCALE)

    def close():
        for d in docs.values():
            d.close()
    get.close = close
    return get
