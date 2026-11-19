"""Numbered copies of a student copy: every booklet its own number, in each page's QR code.

The student copy (course.cls, Marking from scans on) has LECTERN|<code>|<page> in each page's QR code, the same in
every copy, so a scan's pages are put together by where they are in the pile. A numbered copy's QR code holds
LECTERN|<code>|<page>|<booklet> (and "Booklet 7" is printed beside it): each page knows its booklet, so pages can be
scanned in any order, in any upload, and a booklet's missing pages uploaded later still join it.

The copies are the student copy's own pages (vector, as LaTeX made them) with the QR code drawn over, as squares:
no LaTeX run per copy (its qrcode package takes a fifth of a second a code).
"""
import ctypes

import cv2
import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as c

MM = 72 / 25.4
QR_LEFT, QR_TOP, QR_SIZE = 19 * MM, 8 * MM, 15 * MM      # where course.cls prints its QR code (from the top left)
TEXT_LEFT = 36 * MM


def qr_modules(text):
    """The QR code for text, as a square array of booleans (True: dark), without its quiet zone."""
    img = cv2.QRCodeEncoder.create().encode(text)
    dark = img < 128
    ys, xs = np.where(dark)
    return dark[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _rect(page, x, y, w, h, grey):
    o = c.FPDFPageObj_CreateNewRect(x, y, w, h)
    c.FPDFPageObj_SetFillColor(o, grey, grey, grey, 255)
    c.FPDFPath_SetDrawMode(o, c.FPDF_FILLMODE_WINDING, False)
    c.FPDFPage_InsertObject(page, o)


def _text(doc, page, font, size, x, y, s):
    o = c.FPDFPageObj_NewTextObj(doc, font, size)
    raw = (s + "\0").encode("utf-16-le")
    arr = (ctypes.c_ushort * (len(raw) // 2)).from_buffer_copy(raw)
    c.FPDFText_SetText(o, arr)
    c.FPDFPageObj_Transform(o, 1, 0, 0, 1, x, y)
    c.FPDFPage_InsertObject(page, o)


def _stamp(doc, page, font, height, text, label):
    m = qr_modules(text)
    n = m.shape[0]
    cell = QR_SIZE / n
    top = height - QR_TOP
    _rect(page, QR_LEFT - 1, top - QR_SIZE - 1, QR_SIZE + 2, QR_SIZE + 2, 255)   # over the copy's own code
    for r in range(n):                       # each row's runs of dark modules, one rectangle a run
        k = 0
        while k < n:
            if m[r, k]:
                e = k
                while e < n and m[r, e]:
                    e += 1
                _rect(page, QR_LEFT + k * cell, top - (r + 1) * cell, (e - k) * cell + 0.01, cell + 0.01, 0)
                k = e
            else:
                k += 1
    _text(doc, page, font, 9, TEXT_LEFT, top - 14 * MM / 2 - 4, label)


def numbered(src, code, first, count):
    """count copies of the student copy src (a path or bytes), numbered first, first + 1, …: the PDF's bytes."""
    base = pdfium.PdfDocument(src)
    pages = len(base)
    out = pdfium.PdfDocument.new()
    font = b"Helvetica-Bold"
    for b in range(first, first + count):
        at = len(out)
        out.import_pages(base)
        for p in range(pages):
            page = out[at + p]
            h = page.get_height()
            _stamp(out.raw, page.raw, font, h, f"LECTERN|{code}|{p + 1}|{b}", f"Booklet {b}")
            c.FPDFPage_GenerateContent(page.raw)
    import io
    buf = io.BytesIO()
    out.save(buf)
    base.close()
    out.close()
    return buf.getvalue()
