"""Where everything is on the exam: read from the student copy's PDF, the one that was printed.

With "Marking from scans" on, course.cls (v2.6) prints a QR code holding LECTERN|<code>|<page> on every page and
puts an invisible tag, LT:<id>:<width>:<height>, at the lower left of every answer piece the Exam Builder named
with \\ScanID. Here each page of the PDF becomes a TemplatePage: its picture at DPI (to line scans up against
and to tell printed ink from students' ink), its corner squares, and its pieces' rectangles in pixels.

Ids: <node>.<option> for a bubble or check box, <node>:T and <node>:F for true/false, <node>.<comp> for a blank,
box or number box, <node>.<comp>:n and :d for a fraction's boxes, <node>.<comp>:c<i> for a row's cells,
<node>.space for an answer space, cover:f<k>:c<i> for the cover's student boxes.
"""
import ctypes
import re

import cv2
import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from . import scan

DPI = 200
TAG = re.compile(r"LT:(\S+):([\d.]+):([\d.]+)")
TEX_PT = 72 / 72.27          # a TeX point in PDF points


class TemplatePage:
    def __init__(self, number, image, regions, corners):
        self.number = number      # 1, 2, ...
        self.image = image        # grey, uint8, at DPI
        self.regions = regions    # id -> (x, y, w, h) in pixels, from the top left
        self.corners = corners    # the corner squares' centres: top left, top right, bottom right, bottom left
        self.ink = cv2.dilate((image < 160).astype(np.uint8), np.ones((9, 9), np.uint8))   # printed ink, widened


class Template:
    """One version's student copy."""
    def __init__(self, code, pages, path=""):
        self.code, self.pages, self.path = code, pages, path

    def page(self, n):
        return self.pages[n - 1] if 1 <= n <= len(self.pages) else None

    def find(self, rid):
        """(page, rectangle) for an id, or (None, None)."""
        for p in self.pages:
            if rid in p.regions:
                return p, p.regions[rid]
        return None, None


def _tags(page):
    """The page's tags: (id, x, y, w, h) in PDF points from the top left."""
    W, H = page.get_size()
    tp = page.get_textpage()
    text = tp.get_text_range()
    out = []
    for m in TAG.finditer(text):
        i = m.start()
        x, y = ctypes.c_double(), ctypes.c_double()
        if chr(pdfium_c.FPDFText_GetUnicode(tp.raw, i)) != "L" or not pdfium_c.FPDFText_GetCharOrigin(tp.raw, i, x, y):
            continue
        w, h = float(m.group(2)) * TEX_PT, float(m.group(3)) * TEX_PT
        out.append((m.group(1), x.value, H - y.value - h, w, h))
    tp.close()
    return out


def render(page, dpi=DPI):
    return np.array(page.render(scale=dpi / 72, grayscale=True).to_pil().convert("L"))


def load_template(path):
    """A student copy's PDF as a Template. Raises ValueError if it wasn't made with Marking from scans on."""
    doc = pdfium.PdfDocument(path)
    k = DPI / 72
    pages, code = [], None
    for i in range(len(doc)):
        page = doc[i]
        img = render(page)
        regions = {rid: (x * k, y * k, w * k, h * k) for rid, x, y, w, h in _tags(page)}
        qr = scan.find_qr(img)
        corners = scan.find_corners(img)
        if not qr or corners is None:
            raise ValueError(f"{path}: page {i + 1} has no QR code or corner squares. Turn on Marking from scans "
                             "in the Exam Builder's settings, save, and compile the student copy again.")
        c, n = qr[0]
        if int(n) != i + 1:
            raise ValueError(f"{path}: page {i + 1}'s QR code says page {n}")
        code = code or c
        pages.append(TemplatePage(i + 1, img, regions, scan.order_corners(corners, qr[1])))
    doc.close()
    if not pages:
        raise ValueError(f"{path}: no pages")
    return Template(code, pages, path)
