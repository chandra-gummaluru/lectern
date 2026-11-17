"""Train the digit reader (digits.npz beside this file). Run it only to remake the weights:

    python -m server.autograde.train_digits [path/to/digits.png]

Without a path it downloads OpenCV's handwritten-digit sample, samples/data/digits.png (5,000 digits, 500 of
each, from MNIST: Yann LeCun and Corinna Cortes, CC BY-SA 3.0), from GitHub. The last 50 of each digit are held
back to test on; 20 of each of those also go to tests/heldout-digits.npz, which the scan tests write into
answer boxes as "handwriting". Training uses each digit several times, shifted, turned, scaled and with thinner
or thicker strokes, at the size a scanned box has, so the network copes with pens and scanners.
"""
import io
import os
import sys
import urllib.request

import cv2
import numpy as np

from . import digits as D

URL = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/digits.png"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def load(path=None):
    if path:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    else:
        data = urllib.request.urlopen(URL, timeout=60).read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    cells = [np.hsplit(r, 100) for r in np.vsplit(img, 50)]
    cells = np.array(cells).reshape(-1, 20, 20)      # 500 of each digit, in order 0..9
    labels = np.repeat(np.arange(10), 500)
    return cells, labels


def scanned(cell, rng):
    """A 20x20 sample as a scanned box would show it: about 60 pixels high, a little turned, shifted and scaled,
    with its strokes made thinner or thicker."""
    big = cv2.resize(cell, (60, 60), interpolation=cv2.INTER_CUBIC)
    a, s = rng.uniform(-12, 12), rng.uniform(0.85, 1.12)
    M = cv2.getRotationMatrix2D((30, 30), a, s)
    M[:, 2] += rng.uniform(-3, 3, 2)
    big = cv2.warpAffine(big, M, (60, 60))
    mask = (big > 110).astype(np.uint8)
    k = rng.integers(0, 5)
    if k == 1:
        mask = cv2.erode(mask, np.ones((2, 2), np.uint8))
    elif k == 2:
        mask = cv2.dilate(mask, np.ones((2, 2), np.uint8))
    elif k == 3:
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    return mask


def as_mask(cell):
    big = cv2.resize(cell, (60, 60), interpolation=cv2.INTER_CUBIC)
    return (big > 110).astype(np.uint8)


def featurize(masks):
    X = []
    for m in masks:
        img = D.prepare(m)
        X.append(D.features(img if img is not None else np.zeros((20, 20), np.float32)))
    return np.array(X, np.float32)


def train(X, y, epochs=40, hidden=160, seed=0):
    rng = np.random.default_rng(seed)
    mu, sd = X.mean(0), X.std(0) + 1e-3
    Xn = (X - mu) / sd
    d = X.shape[1]
    P = {"W1": rng.normal(0, np.sqrt(2 / d), (d, hidden)).astype(np.float32), "b1": np.zeros(hidden, np.float32),
         "W2": rng.normal(0, np.sqrt(2 / hidden), (hidden, 10)).astype(np.float32), "b2": np.zeros(10, np.float32)}
    m = {k: np.zeros_like(v) for k, v in P.items()}
    v = {k: np.zeros_like(x) for k, x in P.items()}
    Y = np.eye(10, dtype=np.float32)[y]
    t, lr, wd = 0, 1e-3, 1e-4
    for ep in range(epochs):
        idx = rng.permutation(len(Xn))
        for i in range(0, len(idx), 128):
            b = idx[i:i + 128]
            xb, yb = Xn[b], Y[b]
            h = np.maximum(0, xb @ P["W1"] + P["b1"])
            z = h @ P["W2"] + P["b2"]
            z -= z.max(1, keepdims=True)
            p = np.exp(z)
            p /= p.sum(1, keepdims=True)
            g = (p - yb) / len(b)
            G = {"W2": h.T @ g + wd * P["W2"], "b2": g.sum(0)}
            gh = (g @ P["W2"].T) * (h > 0)
            G["W1"] = xb.T @ gh + wd * P["W1"]
            G["b1"] = gh.sum(0)
            t += 1
            for k in P:
                m[k] = 0.9 * m[k] + 0.1 * G[k]
                v[k] = 0.999 * v[k] + 0.001 * G[k] ** 2
                P[k] -= lr * (m[k] / (1 - 0.9 ** t)) / (np.sqrt(v[k] / (1 - 0.999 ** t)) + 1e-8)
        if ep == int(epochs * 0.7):
            lr /= 5
    P["mu"], P["sd"] = mu.astype(np.float32), sd.astype(np.float32)
    return P


def main(argv):
    cells, labels = load(argv[0] if argv else None)
    keep = np.array([i % 500 < 450 for i in range(5000)])
    rng = np.random.default_rng(1)
    tr_cells, tr_y = cells[keep], labels[keep]
    masks, ys = [], []
    for c, yv in zip(tr_cells, tr_y):
        masks.append(as_mask(c)); ys.append(yv)
        for _ in range(5):
            masks.append(scanned(c, rng)); ys.append(yv)
    X, y = featurize(masks), np.array(ys)
    print(f"training on {len(X)} samples")
    P = train(X, y)
    te_cells, te_y = cells[~keep], labels[~keep]
    Xt = (featurize([scanned(c, rng) for c in te_cells]) - P["mu"]) / P["sd"]
    acc = (D.forward(P, Xt).argmax(1) == te_y).mean()
    print(f"held-out accuracy (scanned look): {acc:.4f}")
    np.savez_compressed(os.path.join(HERE, "digits.npz"), **{k: v.astype(np.float16 if k.startswith("W") else np.float32) for k, v in P.items()})
    # 20 held-out samples of each digit for the tests
    sel = np.concatenate([np.where(~keep & (labels == d))[0][:20] for d in range(10)])
    np.savez_compressed(os.path.join(ROOT, "tests", "heldout-digits.npz"), images=cells[sel], labels=labels[sel])
    print("wrote digits.npz and tests/heldout-digits.npz")


if __name__ == "__main__":
    main(sys.argv[1:])
