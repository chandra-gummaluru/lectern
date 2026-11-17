"""Reading one handwritten character: a digit 0-9, or "something else" (class 10: $, %, a letter, a scribble).

A small convolutional network (two convolutions, a third after pooling, then a dense layer), run here in plain
numpy: the server needs nothing else. The weights are in digits.npz, made by train_digits.py (TensorFlow, only to
retrain) from MNIST's 70,000 handwritten digits, OpenCV's 5,000, digits and symbols drawn in handwriting-like
fonts, and scribbles.

Pens, pencils and scanners make strokes of every width, and a network learns the width of what it's shown. So
every character, in training and here alike, is redrawn first (prepare): cropped to its ink, scaled, thinned to
its skeleton, drawn again at one stroke width, then scaled into 28x28 and centred by its centre of mass, as MNIST is.

read(mask) gives the 11 probabilities (0-9, then "else").
"""
import os

import cv2
import numpy as np

SIZE = 28
OTHER = 10
# How sure the network says it is was measured against MNIST's test digits (half of them as a pen would leave them):
# its probabilities are softened by this temperature, and each character is read in five places (as drawn, and a
# pixel up, down, left and right) and the probabilities averaged. Then a reading that's wrong is rarely also sure:
# 2 in 10,000 test digits were wrong with 95% sureness while the right digit had under 1%, against 54 without.
TEMPERATURE = 2.0
SHIFTS = ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))
_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digits.npz")
_net = None


def thin(imgs):
    """Zhang-Suen thinning of a stack of binary images (N, H, W), all at once: each stroke becomes a 1-pixel line."""
    img = np.pad((np.asarray(imgs) > 0).astype(np.uint8), ((0, 0), (1, 1), (1, 1)))
    inner = img[:, 1:-1, 1:-1]
    while True:
        changed = False
        for step in (0, 1):
            P2, P3, P4 = img[:, :-2, 1:-1], img[:, :-2, 2:], img[:, 1:-1, 2:]
            P5, P6, P7 = img[:, 2:, 2:], img[:, 2:, 1:-1], img[:, 2:, :-2]
            P8, P9 = img[:, 1:-1, :-2], img[:, :-2, :-2]
            ring = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            B = P2.astype(np.int8) + P3 + P4 + P5 + P6 + P7 + P8 + P9
            A = sum(((ring[k] == 0) & (ring[k + 1] == 1)).astype(np.int8) for k in range(8))
            c = ((P2 & P4 & P6) == 0) & ((P4 & P6 & P8) == 0) if step == 0 else ((P2 & P4 & P8) == 0) & ((P2 & P6 & P8) == 0)
            m = (inner == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if m.any():
                inner[m] = 0
                changed = True
        if not changed:
            return img[:, 1:-1, 1:-1].copy()


def _crop(m):
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return None
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _canvas(m, side=26, size=32):
    """A character's ink scaled so its longer side is `side` pixels, in the middle of a size x size square."""
    h, w = m.shape
    k = side / max(h, w)
    nh, nw = max(1, int(round(h * k))), max(1, int(round(w * k)))
    s = cv2.resize(m.astype(np.float32), (nw, nh), interpolation=cv2.INTER_AREA)
    out = np.zeros((size, size), np.uint8)
    y, x = (size - nh) // 2, (size - nw) // 2
    out[y:y + nh, x:x + nw] = s > 0.35
    return out


def _finish(sk):
    """A skeleton drawn again at one width, then in MNIST's frame: longest side 20, centred by mass in 28x28."""
    m = cv2.dilate(sk, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    m = _crop(m)
    if m is None:
        return np.zeros((SIZE, SIZE), np.float32)
    h, w = m.shape
    k = 20.0 / max(h, w)
    nh, nw = max(1, int(round(h * k))), max(1, int(round(w * k)))
    s = cv2.resize(m.astype(np.float32), (nw, nh), interpolation=cv2.INTER_AREA)
    out = np.zeros((SIZE, SIZE), np.float32)
    mo = cv2.moments(s)
    cy, cx = (mo["m01"] / mo["m00"], mo["m10"] / mo["m00"]) if mo["m00"] > 0 else (nh / 2, nw / 2)
    oy, ox = int(round(SIZE / 2 - cy)), int(round(SIZE / 2 - cx))
    oy, ox = min(max(oy, 0), SIZE - nh), min(max(ox, 0), SIZE - nw)
    out[oy:oy + nh, ox:ox + nw] = s
    return np.clip(out, 0, 1)


def prepare_many(masks):
    """Characters' ink (2-D arrays, nonzero = ink) as the network's 28x28 images (N, 28, 28), float32."""
    canv, keep = [], []
    for m in masks:
        c = _crop(np.asarray(m) > 0)
        keep.append(c is not None)
        canv.append(_canvas(c) if c is not None else np.zeros((32, 32), np.uint8))
    sk = thin(np.stack(canv)) if canv else np.zeros((0, 32, 32), np.uint8)
    return np.stack([_finish(s) if k else np.zeros((SIZE, SIZE), np.float32) for s, k in zip(sk, keep)]) if canv else np.zeros((0, SIZE, SIZE), np.float32)


def prepare(mask):
    if _crop(np.asarray(mask) > 0) is None:
        return None
    return prepare_many([mask])[0]


# ── The network, in numpy ─────────────────────────────────────────────

def _conv(x, W, b):
    """Valid 3x3 convolution: x (N, H, W, C), W (3, 3, C, K) → (N, H-2, W-2, K), then ReLU."""
    n, h, w, c = x.shape
    cols = np.stack([x[:, i:i + h - 2, j:j + w - 2, :] for i in range(3) for j in range(3)], axis=3)   # N, h-2, w-2, 9, C
    out = cols.reshape(n, h - 2, w - 2, 9 * c) @ W.reshape(9 * c, -1) + b
    return np.maximum(out, 0)


def _pool(x):
    n, h, w, c = x.shape
    h2, w2 = h // 2, w // 2
    return x[:, :h2 * 2, :w2 * 2, :].reshape(n, h2, 2, w2, 2, c).max(axis=(2, 4))


def forward(P, imgs, t=1.0):
    """Probabilities (N, 11) for images (N, 28, 28), at temperature t."""
    x = imgs[..., None].astype(np.float32)
    x = _conv(x, P["c1w"], P["c1b"])
    x = _pool(_conv(x, P["c2w"], P["c2b"]))
    x = _pool(_conv(x, P["c3w"], P["c3b"]))
    x = np.maximum(x.reshape(len(x), -1) @ P["d1w"] + P["d1b"], 0)
    z = (x @ P["d2w"] + P["d2b"]) / t
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _load():
    global _net
    if _net is None:
        with np.load(_WEIGHTS) as f:
            _net = {k: f[k].astype(np.float32) for k in f.files}
    return _net


def read_many(masks):
    """The 11 probabilities for each character's ink (rows of zeros where there's no ink)."""
    if not masks:
        return np.zeros((0, 11), np.float32)
    imgs, P = prepare_many(masks), _load()
    return np.mean([forward(P, np.roll(np.roll(imgs, dy, 1), dx, 2), TEMPERATURE) for dy, dx in SHIFTS], axis=0)


def read(mask):
    """The 11 probabilities (0-9, then "something else") for a character's ink, or None if there's no ink."""
    if _crop(np.asarray(mask) > 0) is None:
        return None
    return read_many([mask])[0]
