"""Scanned pages: reading them in, their QR code and corner squares, and lining each up with its printed page.

A page is identified by its QR code (LECTERN|<code>|<page>), so pages can come in any order and either way up.
The four corner squares give the scan's geometry: the scan is warped so they land on the printed page's squares,
after which every answer piece is at the same pixels as in the template.
"""
import math
import os

import cv2
import numpy as np
import pypdfium2 as pdfium

DPI = 200
SQUARE_MM = 7.0
LETTER_MM = 215.9
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


def load_pages(path, dpi=DPI):
    """(label, grey image) for each page of a scanned PDF or each image file."""
    if path.lower().endswith(".pdf"):
        doc = pdfium.PdfDocument(path)
        for i in range(len(doc)):
            img = np.array(doc[i].render(scale=dpi / 72, grayscale=True).to_pil().convert("L"))
            yield f"{os.path.basename(path)} p.{i + 1}", img
        doc.close()
    elif path.lower().endswith(IMAGE_TYPES):
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"can't read {path}")
        yield os.path.basename(path), img
    else:
        raise ValueError(f"{path}: not a PDF or an image")


def _decode(img):
    for det in (cv2.QRCodeDetector(), getattr(cv2, "QRCodeDetectorAruco", None)):
        if det is None:
            continue
        if not isinstance(det, cv2.QRCodeDetector):
            det = det()
        try:
            text, pts, _ = det.detectAndDecode(img)
        except cv2.error:
            continue
        if text and text.startswith("LECTERN|") and pts is not None:
            return text, np.asarray(pts, np.float32).reshape(-1, 2)
    return None


def find_qr(img):
    """((code, page), QR centre (x, y)) or None. Tries the whole page, then each corner larger."""
    found = _decode(img)
    if not found:
        h, w = img.shape
        for y0, x0 in ((0, 0), (0, w // 2), (h // 2, 0), (h // 2, w // 2)):
            part = img[y0:y0 + h // 2, x0:x0 + w // 2]
            for s in (1.0, 2.0):
                f = _decode(cv2.resize(part, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC) if s != 1 else part)
                if f:
                    found = (f[0], f[1] / s + [x0, y0])
                    break
            if found:
                break
    if not found:
        return None
    parts = found[0].split("|")
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return (parts[1], int(parts[2])), tuple(found[1].mean(axis=0))


def find_corners(img):
    """The corner squares' centres (4 x 2, one per corner of the image), or None."""
    h, w = img.shape
    side = SQUARE_MM / LETTER_MM * min(w, h)                    # expected side in pixels (letter paper, either way up)
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    _, dark = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(dark, 8)
    best = {}
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if not (0.55 * side <= bw <= 1.7 * side and 0.55 * side <= bh <= 1.7 * side):
            continue
        if not 0.7 <= bw / bh <= 1.4 or area < 0.8 * bw * bh:
            continue
        cx, cy = cents[i]
        q = (int(cx > w / 2), int(cy > h / 2))
        d = math.hypot(cx - (w if q[0] else 0), cy - (h if q[1] else 0))
        if d > 0.25 * math.hypot(w, h):
            continue
        if q not in best or d < best[q][0]:
            best[q] = (d, (cx, cy))
    if len(best) != 4:
        return None
    return np.array([best[q][1] for q in ((0, 0), (1, 0), (1, 1), (0, 1))], np.float32)


def order_corners(corners, qr_centre):
    """The corners as the printed page's top left, top right, bottom right, bottom left: the top left is the one
    nearest the QR code, the rest follow clockwise (so a page scanned upside down or sideways comes out right)."""
    c = corners.mean(axis=0)
    ang = [math.atan2(p[1] - c[1], p[0] - c[0]) for p in corners]
    order = sorted(range(4), key=lambda i: ang[i])                  # clockwise on the image (y down)
    tl = min(range(4), key=lambda i: math.hypot(corners[i][0] - qr_centre[0], corners[i][1] - qr_centre[1]))
    k = order.index(tl)
    return np.array([corners[order[(k + j) % 4]] for j in range(4)], np.float32)


def identify(img):
    """What a scanned page is: {"code", "page", "corners" (ordered as printed)}, or None if its QR code or
    corner squares can't be found."""
    qr = find_qr(img)
    corners = find_corners(img) if qr else None
    if corners is None:
        return None
    return {"code": qr[0][0], "page": qr[0][1], "corners": order_corners(corners, qr[1])}


def align(img, ident, tpage):
    """The scan warped onto its printed page: the same size as the template's image, every piece where it was printed."""
    M = cv2.getPerspectiveTransform(ident["corners"], tpage.corners)
    h, w = tpage.image.shape
    return cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=255)
