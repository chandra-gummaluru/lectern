"""Security building blocks: the server key, password hashing, two-factor codes, tokens, rate limits,
and the checks every request gets (HTTPS, cross-site requests, security headers).

Passwords
  Hashed with argon2id (argon2-cffi's defaults: RFC 9106's second recommended setting, 64 MiB, t=3,
  p=4), salted per password. A password is never stored, logged or sent anywhere: it arrives only
  inside HTTPS (the server refuses passwords over plain HTTP except on localhost while developing),
  is checked, and dropped. Hashes are upgraded on sign-in when the settings change.

Two-factor
  TOTP (RFC 6238: 6 digits, 30 seconds, SHA-1, which every authenticator app supports), with ±1
  step for clock drift. Each code works once (the last step used is kept). Secrets are encrypted
  at rest with AES-256-GCM under a key derived from the server key. Ten single-use recovery codes,
  stored as HMAC-SHA256 under the server key.

Tokens
  Session cookies, invite and reset links are 256-bit random values; only their SHA-256 is stored,
  so a copy of the database can't be used to sign in.

The server key
  LECTERN_SECRET_KEY (any long random string), or else a key made on first run in
  <data dir>/secret.key (readable only by the server's user). Keep it with backups of the
  database: without it, two-factor secrets and recovery codes can't be checked.
"""
import base64
import collections
import hashlib
import hmac
import os
import re
import secrets
import struct
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import db

# ── The server key ───────────────────────────────────────────────────
_key_cache = {}


def _master():
    env = os.environ.get("LECTERN_SECRET_KEY", "")
    if env:
        if len(env) < 32:
            raise RuntimeError("LECTERN_SECRET_KEY must be at least 32 characters (e.g. python -c \"import secrets; print(secrets.token_urlsafe(48))\").")
        return env.encode()
    path = os.path.join(db.data_dir(), "secret.key")
    if path in _key_cache:
        return _key_cache[path]
    try:
        with open(path, "rb") as f:
            k = f.read().strip()
    except FileNotFoundError:
        k = base64.urlsafe_b64encode(secrets.token_bytes(48))
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k)
    _key_cache[path] = k
    return k


def subkey(purpose):
    """A 256-bit key for one purpose, derived from the server key (HKDF-SHA256)."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"lectern", info=purpose.encode()).derive(_master())


def encrypt(text, purpose="totp"):
    nonce = secrets.token_bytes(12)
    ct = AESGCM(subkey(purpose)).encrypt(nonce, text.encode(), purpose.encode())
    return base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt(blob, purpose="totp"):
    raw = base64.urlsafe_b64decode(blob.encode())
    return AESGCM(subkey(purpose)).decrypt(raw[:12], raw[12:], purpose.encode()).decode()


def mac(value, purpose):
    return hmac.new(subkey(purpose), value.encode(), hashlib.sha256).hexdigest()


# ── Random tokens (stored only as their hash) ────────────────────────
def new_token():
    return secrets.token_urlsafe(32)


def token_hash(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


# ── Passwords ────────────────────────────────────────────────────────
_ph = PasswordHasher()
MIN_PASSWORD = 12
MAX_PASSWORD = 1024         # argon2 takes any length; this just stops someone posting megabytes
_DUMMY = None


def hash_password(pw):
    return _ph.hash(pw)


def check_password(stored, pw):
    """(ok, new hash or None). Takes the same time whether or not there's an account (see dummy_check)."""
    try:
        _ph.verify(stored, pw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, None
    return True, (_ph.hash(pw) if _ph.check_needs_rehash(stored) else None)


def dummy_check(pw):
    """Spend as long as checking a real password, so a wrong email can't be told from a wrong password by timing."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = _ph.hash(secrets.token_urlsafe(16))
    check_password(_DUMMY, pw)


# A short list of the most common passwords (all at least 12 characters), refused outright.
COMMON = {
    "123456789012", "1234567890123", "12345678901234", "123456789abc", "1q2w3e4r5t6y", "qwertyuiop12",
    "qwertyuiopasdf", "qwerty123456", "password1234", "password12345", "passwordpassword", "iloveyou1234",
    "aaaaaaaaaaaa", "111111111111", "000000000000", "abcdefghijkl", "abcdef123456", "abc123abc123",
    "letmein12345", "welcome12345", "changeme1234", "administrator", "trustno1trustno1", "football1234",
    "baseball1234", "superman1234", "1qaz2wsx3edc", "zaq12wsxcde3", "asdfghjkl123", "qazwsxedcrfv",
    "lectern12345", "lecternlectern", "universityoftoronto", "uoftuoftuoft", "teaching1234", "professor123",
}


def password_problem(pw, email="", name=""):
    """What's wrong with a new password, in words, or '' if it's fine. (NIST SP 800-63B: length over
    composition rules; no forced mixtures of character types, but no common or account-derived ones.)"""
    if not isinstance(pw, str) or len(pw) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters. A few words together is easy to remember."
    if len(pw) > MAX_PASSWORD:
        return f"That's too long (at most {MAX_PASSWORD} characters)."
    low = pw.lower()
    if low in COMMON or len(set(low)) < 4:
        return "That password is too easy to guess. Try a few words together."
    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in low:
        return "Don't use your email address in your password."
    if name and len(name) >= 4 and name.lower().replace(" ", "") in low.replace(" ", ""):
        return "Don't use your name in your password."
    return ""


# ── Two-factor codes (TOTP, RFC 6238) ────────────────────────────────
STEP = 30


def new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    d = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = d[-1] & 0x0F
    return "%06d" % ((struct.unpack(">I", d[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


def totp_now(secret, at=None):
    return _hotp(secret, int((at if at is not None else time.time()) // STEP))


def totp_match(secret, code, last_step=0, at=None):
    """The time step the code is for (within ±1 step, and after last_step), or None."""
    code = re.sub(r"\s+", "", str(code or ""))
    if not re.fullmatch(r"\d{6}", code):
        return None
    now = int((at if at is not None else time.time()) // STEP)
    for step in (now, now - 1, now + 1):
        if step > last_step and hmac.compare_digest(_hotp(secret, step), code):
            return step
    return None


def totp_uri(secret, email, issuer="Lectern"):
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period={STEP}"


def qr_svg(text):
    import segno
    import io
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, dark="#111", light="#fff", xmldecl=False, svgns=True)
    return buf.getvalue().decode()


RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i


def new_recovery_codes(n=10):
    out = []
    for _ in range(n):
        s = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        out.append(f"{s[:5]}-{s[5:]}")
    return out


def recovery_norm(code):
    return re.sub(r"[^a-z0-9]", "", str(code or "").lower())


# ── Rate limits ──────────────────────────────────────────────────────
class Limiter:
    """At most n events per window (seconds) for each key, in this process. (With several worker
    processes each counts on its own; the per-account lock in the database is shared.)"""
    def __init__(self):
        self.hits = {}               # key → (deque of times, window)
        self.lock = threading.Lock()
        self.calls = 0

    def ok(self, key, n, window):
        now = time.time()
        with self.lock:
            q = self.hits.get(key)
            if q is None:
                q = self.hits[key] = (collections.deque(), window)
            q = q[0]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= n:
                return False
            q.append(now)
            self.calls += 1
            if self.calls % 1000 == 0 or len(self.hits) > 100000:   # forget keys whose last event is out of its window
                for k in [k for k, (d, w) in self.hits.items() if not d or d[-1] < now - w]:
                    del self.hits[k]
            return True

    def reset(self):
        with self.lock:
            self.hits.clear()


def same(a, b):
    return hmac.compare_digest(str(a).encode(), str(b).encode())
