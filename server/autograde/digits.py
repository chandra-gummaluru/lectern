"""Reading one handwritten digit: a small neural network (numpy only) and the preprocessing it was trained with.

The weights are in digits.npz beside this file, made by train_digits.py from OpenCV's handwritten-digit sample
(samples/data/digits.png: 5,000 digits from MNIST). Every character goes through prepare() before the network,
training samples and scanned boxes alike, so they look the same to it: cropped to its ink, scaled so its longer
side is 16 pixels, centred by its centre of mass in 20x20, and straightened (deskewed).

read(mask) gives the ten probabilities. The network has seen MNIST-style digits only: anything else (a letter, a
crossed-out digit) still gets a digit, usually with a low probability, which is why the grader sends uncertain
reads to a person.
"""
import os

import cv2
import numpy as np

SIZE = 20
_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digits.npz")
_net = None


def prepare(mask):
    """A character's ink (2-D array, nonzero = ink) as the network's 20x20 image (float32, 0..1), or None if empty."""
    m = (np.asarray(mask) > 0).astype(np.uint8)
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return None
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    h, w = m.shape
    k = 16.0 / max(h, w)
    nh, nw = max(1, int(round(h * k))), max(1, int(round(w * k)))
    m = cv2.resize(m, (nw, nh), interpolation=cv2.INTER_AREA)
    out = np.zeros((SIZE, SIZE), np.float32)
    mo = cv2.moments(m)
    cy, cx = (mo["m01"] / mo["m00"], mo["m10"] / mo["m00"]) if mo["m00"] > 0 else (nh / 2, nw / 2)
    oy, ox = int(round(SIZE / 2 - cy)), int(round(SIZE / 2 - cx))
    oy, ox = min(max(oy, 0), SIZE - nh), min(max(ox, 0), SIZE - nw)
    out[oy:oy + nh, ox:ox + nw] = m
    return _deskew(np.clip(out, 0, 1))


def _deskew(img):
    mo = cv2.moments(img)
    if abs(mo["mu02"]) < 1e-2:
        return img
    skew = mo["mu11"] / mo["mu02"]
    M = np.float32([[1, skew, -0.5 * SIZE * skew], [0, 1, 0]])
    return cv2.warpAffine(img, M, (SIZE, SIZE), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)


def features(img):
    """The network's input: the 20x20 pixels and a histogram of stroke directions (4 quadrants x 16 bins)."""
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1)
    mag, ang = cv2.cartToPolar(gx, gy)
    bins = np.int32(16 * ang / (2 * np.pi)) % 16
    h = SIZE // 2
    hist = [np.bincount(b.ravel(), m.ravel(), 16) for b, m in
            ((bins[:h, :h], mag[:h, :h]), (bins[h:, :h], mag[h:, :h]), (bins[:h, h:], mag[:h, h:]), (bins[h:, h:], mag[h:, h:]))]
    hist = np.hstack(hist).astype(np.float32)
    hist = np.sqrt(hist / (hist.sum() + 1e-6))
    return np.hstack([img.ravel(), hist]).astype(np.float32)


def forward(params, X):
    """Probabilities for each row of X (features)."""
    h = np.maximum(0, X @ params["W1"] + params["b1"])
    z = h @ params["W2"] + params["b2"]
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _load():
    global _net
    if _net is None:
        with np.load(_WEIGHTS) as f:
            _net = {k: f[k].astype(np.float32) for k in ("W1", "b1", "W2", "b2", "mu", "sd")}
    return _net


def read(mask):
    """The ten probabilities for a character's ink, or None if there's no ink."""
    img = prepare(mask)
    if img is None:
        return None
    net = _load()
    x = (features(img)[None, :] - net["mu"]) / net["sd"]
    return forward(net, x)[0]
