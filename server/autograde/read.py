"""Reading what a student wrote in each answer piece of a lined-up scan.

Only ink the student added counts: a pixel is the student's when it's dark on the scan and not near printed ink
on the template (bubble outlines, box edges and option labels are taken away). From that:

- bubble / check box: the share of its inside that's inked (fill);
- number box, fraction box, cell: the characters in it, read with the digit reader (digits.py), with how sure.
"""
import cv2
import numpy as np

from . import digits

# A bubble counts as filled from this share of its inside inked; a check box (ticked, crossed or filled) from TICK.
FILLED, TRACE, TICK = 0.25, 0.06, 0.06


def student_ink(scan, tpage):
    """1 where the student wrote: dark on the scan and away from printed ink."""
    bg = float(np.percentile(scan, 95))
    dark = (scan < 0.8 * bg).astype(np.uint8)
    return dark & (1 - tpage.ink)


def _crop(mask, r, inset=0):
    x, y, w, h = r
    x0, y0 = int(round(x + inset)), int(round(y + inset))
    x1, y1 = int(round(x + w - inset)), int(round(y + h - inset))
    H, W = mask.shape
    return mask[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]


def fill(mask, r, round_=True):
    """The share of a bubble's (round) or box's inside that is the student's ink."""
    x, y, w, h = r
    if round_:
        cx, cy, rad = x + w / 2, y + h / 2, 0.8 * min(w, h) / 2
        x0, y0 = max(0, int(cx - rad)), max(0, int(cy - rad))
        part = mask[y0:y0 + int(2 * rad) + 1, x0:x0 + int(2 * rad) + 1]
        yy, xx = np.mgrid[0:part.shape[0], 0:part.shape[1]]
        disc = (xx + x0 - cx) ** 2 + (yy + y0 - cy) ** 2 <= rad ** 2
        return float(part[disc].mean()) if disc.any() else 0.0
    part = _crop(mask, r, inset=0.15 * min(w, h))
    return float(part.mean()) if part.size else 0.0


def _components(part):
    """The characters in a box, left to right: lists of (x, y, w, h, mask) after joining broken strokes."""
    if part.size == 0 or part.sum() == 0:
        return []
    joined = cv2.morphologyEx(part, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
    H = part.shape[0]
    comps = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 10 or max(w, h) < 4:
            continue                                        # specks (a decimal point is bigger)
        comps.append([x, y, w, h, (lab == i).astype(np.uint8)])
    comps.sort(key=lambda c: c[0])
    merged = []
    for c in comps:                                         # pieces of one character overlap a lot across
        if merged:
            p = merged[-1]
            ov = min(p[0] + p[2], c[0] + c[2]) - max(p[0], c[0])
            if ov > 0.5 * min(p[2], c[2]):
                x0, y0 = min(p[0], c[0]), min(p[1], c[1])
                x1, y1 = max(p[0] + p[2], c[0] + c[2]), max(p[1] + p[3], c[1] + c[3])
                merged[-1] = [x0, y0, x1 - x0, y1 - y0, p[4] | c[4]]
                continue
        merged.append(c)
    out = []
    for c in merged:
        out.extend(_split(c))
    return out


def _split(c, depth=0):
    """Digits written touching each other: a blob much wider than tall is cut at a narrow neck in its middle part,
    where both sides are big enough to be digits, and each side again, up to a few digits. Pieces of a cut blob
    are marked (a sixth item, True), since the cut may be wrong."""
    x, y, w, h, m = c[:5]
    if depth > 3 or w <= 1.3 * h or h < 8:
        return [c]
    cols = m[y:y + h, x:x + w].sum(axis=0).astype(float)
    lo, hi = int(0.2 * w), int(0.8 * w)

    def side(a, b):
        part = np.zeros_like(m)
        part[:, x + a:x + b] = m[:, x + a:x + b]
        ys, xs = np.nonzero(part)
        if len(xs) == 0:
            return None
        return [xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1, part]

    for cut in sorted(range(lo, hi), key=lambda k: cols[k]):
        if cols[cut] > 0.4 * cols.max():                    # no narrow neck: one wide character
            break
        l, r = side(0, cut), side(cut, w)
        if l and r and all(p[2] >= 0.4 * h and p[3] >= 0.5 * h for p in (l, r)):
            return [p[:5] + [True] for p in _split(l, depth + 1) + _split(r, depth + 1)]
    return [c]


class Reading:
    """What's written in a box: its characters, each with the digit reader's probabilities (None for a minus sign
    or a decimal point), and whether there was a mark it couldn't explain."""
    def __init__(self, chars, odd=False, cut=False):
        self.chars, self.odd, self.cut = chars, odd, cut   # cut: touching characters were cut apart

    @property
    def text(self):
        return "".join(c for c, _ in self.chars)

    @property
    def sure(self):
        """How sure of the whole reading: its least sure digit (0.5 at most with an unexplained mark)."""
        s = min([float(p.max()) for _, p in self.chars if p is not None] + [1.0])
        return min(s, 0.5) if self.odd else s

    def chance(self, text):
        """How likely the same ink says text instead (the digit reader's probabilities, character by character)."""
        text = str(text or "").strip()
        if len(text) != len(self.chars):
            return 1.0 if self.cut else 0.0                 # cut wrongly, it could say anything
        out = 1.0
        for want, (c, p) in zip(text, self.chars):
            out *= float(p[int(want)]) if p is not None and want.isdigit() else float(want == c)
        return out


def read_chars(part):
    """A Reading of a box's handwriting: digits, a minus sign and a decimal point."""
    comps = _components(part)
    if not comps:
        return Reading([])
    tall = max(c[3] for c in comps)
    bottom = max(c[1] + c[3] for c in comps)
    chars, odd = [], False
    for x, y, w, h, m, *_ in comps:
        if h < 0.3 * tall and w < 0.35 * tall:              # a small mark: a decimal point if it's low down
            if y + h > bottom - 0.35 * tall:
                chars.append((".", None))
            else:
                odd = True                                  # high up: not sure what it is
            continue
        if w > 1.6 * h and h < 0.45 * tall:
            chars.append(("-", None))
            continue
        p = digits.read(m[y:y + h, x:x + w])
        chars.append((str(int(np.argmax(p))), p))
    return Reading(chars, odd, any(len(c) > 5 for c in comps))


def read_box(mask, r, inset=4):
    return read_chars(_crop(mask, r, inset))


def digit_probs(mask, r, inset=3):
    """For one cell: None if it's empty, else the ten probabilities of its digit."""
    part = _crop(mask, r, inset)
    comps = _components(part)
    if not comps:
        return None
    x0 = min(c[0] for c in comps); y0 = min(c[1] for c in comps)
    x1 = max(c[0] + c[2] for c in comps); y1 = max(c[1] + c[3] for c in comps)
    m = np.zeros_like(part)
    for c in comps:
        m |= c[4]
    return digits.read(m[y0:y1, x0:x1])


def picture(scan, rect, pad=12, right=0):
    """A piece of the lined-up scan for people to look at (JPEG bytes)."""
    x, y, w, h = rect
    H, W = scan.shape
    x0, y0 = max(0, int(x - pad)), max(0, int(y - pad))
    x1, y1 = min(W, int(x + w + pad + right)), min(H, int(y + h + pad))
    ok, buf = cv2.imencode(".jpg", scan[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes() if ok else b""
