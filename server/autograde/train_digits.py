"""Train the character reader (digits.npz beside this file). Only to remake the weights; it needs TensorFlow:

    pip install tensorflow-cpu
    python -m server.autograde.train_digits <folder with MNIST's four .gz files>

What it learns from:
  digits        MNIST's 60,000 training digits (Yann LeCun, Corinna Cortes and Chris Burges; CC BY-SA 3.0),
                each also turned, slanted and stretched; and digits drawn in OpenCV's handwriting-like (Hershey) fonts.
  else (10)     what students also write in an answer box: $, %, letters, signs, and scribbles, drawn in the
                same fonts and by hand-like random strokes; and "$" drawn the usual ways (an S with a line through).
Every one goes through digits.prepare_many first, as reading does: the network sees one stroke width.

It's tested on MNIST's 10,000 test digits (never trained on), as they come and as a pen and scanner would make
them; 20 of each digit from those go to tests/heldout-digits.npz for the scan tests.
"""
import gzip
import os
import sys
import time

import cv2
import numpy as np

from . import digits as D

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FONTS = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_COMPLEX, cv2.FONT_HERSHEY_TRIPLEX,
         cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, cv2.FONT_HERSHEY_SCRIPT_COMPLEX, cv2.FONT_HERSHEY_PLAIN, cv2.FONT_HERSHEY_COMPLEX_SMALL]
# Not digits, and not easily taken for one (no l, I, O, S, Z, B, G, b, g, q, /, ( or )).
OTHERS = "$$$$%&@#+=<>?!*xXacdehkmnprtuvwyACDEFHKMNPRUVWY"


def idx(path):
    with gzip.open(path, "rb") as f:
        data = f.read()
    if int.from_bytes(data[2:3], "big") != 8:
        raise ValueError(path)
    dims = data[3]
    shape = [int.from_bytes(data[4 + 4 * i:8 + 4 * i], "big") for i in range(dims)]
    return np.frombuffer(data, np.uint8, offset=4 + 4 * dims).reshape(shape)


def warp(m, rng, strong=1.0):
    """Turned, slanted, stretched and shifted a little (a binary image, any size)."""
    h, w = m.shape
    big = cv2.copyMakeBorder(m, h // 2, h // 2, w // 2, w // 2, cv2.BORDER_CONSTANT, value=0)
    H, W = big.shape
    a = np.deg2rad(rng.uniform(-14, 14) * strong)
    sh = rng.uniform(-0.3, 0.3) * strong
    sx, sy = np.exp(rng.uniform(-0.15, 0.15) * strong), np.exp(rng.uniform(-0.15, 0.15) * strong)
    R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]) @ np.array([[1, sh], [0, 1]]) @ np.diag([sx, sy])
    c = np.array([W / 2, H / 2])
    M = np.hstack([R, (c - R @ c)[:, None]])
    return (cv2.warpAffine(big.astype(np.float32), M, (W, H)) > 0.5).astype(np.uint8)


def font_char(ch, rng):
    font = FONTS[rng.integers(len(FONTS))] | (cv2.FONT_ITALIC if rng.random() < 0.3 else 0)
    img = np.zeros((96, 96), np.uint8)
    cv2.putText(img, ch, (18, 70), font, rng.uniform(1.4, 2.0), 255, int(rng.integers(1, 5)), cv2.LINE_AA)
    return warp((img > 100).astype(np.uint8), rng)


def dollar(rng):
    """$ by hand: an S (from a font) with a line through it, or across it top and bottom."""
    s = font_char("S", rng)
    ys, xs = np.nonzero(s)
    if len(xs) == 0:
        return s
    cx = int(np.median(xs) + rng.normal(0, 2))
    top, bot = ys.min() - int(rng.uniform(2, 10)), ys.max() + int(rng.uniform(2, 10))
    cv2.line(s, (cx + int(rng.normal(0, 2)), max(0, top)), (cx + int(rng.normal(0, 2)), min(s.shape[0] - 1, bot)), 1, int(rng.integers(1, 4)))
    return s


def scribble(rng):
    img = np.zeros((64, 64), np.uint8)
    pts = rng.uniform(8, 56, (int(rng.integers(3, 8)), 2)).astype(np.int32)
    cv2.polylines(img, [pts], False, 1, int(rng.integers(1, 4)))
    return img


def augment_mnist(img, rng):
    m = cv2.resize(img, (56, 56), interpolation=cv2.INTER_CUBIC) > 110
    return warp(m.astype(np.uint8), rng)


def pen(img, rng):
    """A digit as a pen would leave it in a scanned box: bigger, thinner or thicker, a little broken."""
    m = cv2.resize(img, (64, 64), interpolation=cv2.INTER_CUBIC)
    m = (m > rng.uniform(80, 200)).astype(np.uint8)
    k = rng.integers(0, 3)
    if k == 1:
        m = cv2.erode(m, np.ones((3, 3), np.uint8))
    elif k == 2:
        m = cv2.dilate(m, np.ones((3, 3), np.uint8))
    return m


def build(Xtr, ytr, rng):
    masks, labels = [], []
    for img, y in zip(Xtr, ytr):
        masks.append((img > 100).astype(np.uint8)); labels.append(y)
        masks.append(augment_mnist(img, rng)); labels.append(y)
    for _ in range(12000):
        d = int(rng.integers(10))
        masks.append(font_char(str(d), rng)); labels.append(d)
    for _ in range(9000):
        masks.append(font_char(OTHERS[rng.integers(len(OTHERS))], rng)); labels.append(D.OTHER)
    for _ in range(5000):
        masks.append(dollar(rng)); labels.append(D.OTHER)
    for _ in range(4000):
        masks.append(scribble(rng)); labels.append(D.OTHER)
    return masks, np.array(labels)


def prepare(masks, chunk=4000):
    out = []
    for i in range(0, len(masks), chunk):
        out.append(D.prepare_many(masks[i:i + chunk]))
        print(f"\r  prepared {min(i + chunk, len(masks))} of {len(masks)}", end="", flush=True)
    print()
    return np.concatenate(out)


def model():
    import tensorflow as tf
    L = tf.keras.layers
    m = tf.keras.Sequential([
        tf.keras.Input((28, 28, 1)),
        L.RandomTranslation(0.08, 0.08), L.RandomRotation(0.03),
        L.Conv2D(32, 3, activation="relu", name="c1"), L.Conv2D(32, 3, activation="relu", name="c2"), L.MaxPooling2D(),
        L.Conv2D(64, 3, activation="relu", name="c3"), L.MaxPooling2D(),
        L.Flatten(), L.Dropout(0.25), L.Dense(128, activation="relu", name="d1"), L.Dropout(0.3), L.Dense(11, activation="softmax", name="d2")])
    m.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return m


def main(argv):
    src = argv[0]
    rng = np.random.default_rng(0)
    Xtr, ytr = idx(os.path.join(src, "train-images-idx3-ubyte.gz")), idx(os.path.join(src, "train-labels-idx1-ubyte.gz"))
    Xte, yte = idx(os.path.join(src, "t10k-images-idx3-ubyte.gz")), idx(os.path.join(src, "t10k-labels-idx1-ubyte.gz"))
    t = time.time()
    masks, y = build(Xtr, ytr, rng)
    X = prepare(masks)
    print(f"{len(X)} training samples ({time.time() - t:.0f}s)")
    import tensorflow as tf
    tf.random.set_seed(0)
    m = model()
    perm = rng.permutation(len(X))
    X, y = X[perm], y[perm]
    m.fit(X[..., None], y, batch_size=128, epochs=int(os.environ.get("EPOCHS", 8)), validation_split=0.04, verbose=2,
          callbacks=[tf.keras.callbacks.ReduceLROnPlateau(patience=1, factor=0.3)])
    P = {}
    for name in ("c1", "c2", "c3", "d1", "d2"):
        w, b = m.get_layer(name).get_weights()
        P[name[:2] + "w"], P[name[:2] + "b"] = w.astype(np.float16), b.astype(np.float32)
    np.savez_compressed(os.path.join(HERE, "digits.npz"), **P)
    # Tests, with the numpy network (as the server reads).
    D._net = None
    plain = D.forward(D._load(), prepare([(x > 100).astype(np.uint8) for x in Xte]))
    print(f"MNIST test digits: {(plain.argmax(1) == yte).mean():.4f} right; {(plain.argmax(1) == D.OTHER).mean():.4f} called something else")
    penned = D.forward(D._load(), prepare([pen(x, rng) for x in Xte]))
    print(f"  as a pen and scanner would make them: {(penned.argmax(1) == yte).mean():.4f}")
    oth = D.forward(D._load(), prepare([font_char(c, rng) for c in "$%&@#+=?xX" * 20] + [dollar(rng) for _ in range(200)]))
    print(f"symbols called something else: {(oth.argmax(1) == D.OTHER).mean():.4f}")
    sel = np.concatenate([np.where(yte == d)[0][:20] for d in range(10)])
    np.savez_compressed(os.path.join(ROOT, "tests", "heldout-digits.npz"), images=Xte[sel], labels=yte[sel])
    print("wrote digits.npz and tests/heldout-digits.npz")


if __name__ == "__main__":
    main(sys.argv[1:])
