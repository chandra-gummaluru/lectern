"""Lectern's database: accounts, sign-ins and the version of each account's files (SQLite).

Everything lives under LECTERN_DATA_DIR (default: data/ beside app.py, which is in .gitignore):

  lectern.db        this database
  secret.key        the server's own key (made on first run unless LECTERN_SECRET_KEY is set)
  files/<user id>/  each account's files (see store.py)

One connection per thread (Flask serves each request on one thread). WAL mode lets readers carry on
while a save writes; writes that must not interleave (a save, a sign-in's counters) use
`transaction()`, which takes SQLite's write lock up front (BEGIN IMMEDIATE), across processes too.
"""
import contextlib
import os
import sqlite3
import threading

from .paths import BASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,          -- lower case
  handle        TEXT NOT NULL UNIQUE,          -- in the public address of course pages: /p/<handle>/
  name          TEXT NOT NULL DEFAULT '',
  pw_hash       TEXT NOT NULL,                 -- argon2id
  pw_changed    REAL NOT NULL,
  totp_secret   TEXT,                          -- encrypted (AES-GCM with the server key); NULL: no 2FA
  totp_pending  TEXT,                          -- encrypted: a secret being set up, not yet confirmed
  totp_step     INTEGER NOT NULL DEFAULT 0,    -- the last time step used (a code works once)
  is_admin      INTEGER NOT NULL DEFAULT 0,
  disabled      INTEGER NOT NULL DEFAULT 0,
  failed        INTEGER NOT NULL DEFAULT 0,    -- wrong passwords / codes in a row
  locked_until  REAL NOT NULL DEFAULT 0,
  created       REAL NOT NULL,
  last_login    REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  id_hash   TEXT PRIMARY KEY,                  -- sha256 of the cookie's value; the value itself is never stored
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created   REAL NOT NULL,
  last_seen REAL NOT NULL,
  expires   REAL NOT NULL,                     -- absolute end, however active
  ip        TEXT NOT NULL DEFAULT '',
  agent     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS challenges (       -- a password was right; waiting for the 2FA code
  id_hash  TEXT PRIMARY KEY,
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires  REAL NOT NULL,
  tries    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS recovery_codes (
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash TEXT NOT NULL,                     -- HMAC-SHA256 with the server key
  used      REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS recovery_user ON recovery_codes(user_id);
CREATE TABLE IF NOT EXISTS invites (
  token_hash TEXT PRIMARY KEY,
  email      TEXT NOT NULL,
  is_admin   INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER,
  created    REAL NOT NULL,
  expires    REAL NOT NULL,
  used       REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS resets (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created    REAL NOT NULL,
  expires    REAL NOT NULL,
  used       REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (           -- a record of security events (sign-ins, changes)
  id      INTEGER PRIMARY KEY,
  user_id INTEGER,
  kind    TEXT NOT NULL,
  ip      TEXT NOT NULL DEFAULT '',
  at      REAL NOT NULL,
  detail  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS repos (            -- each account's two file areas: pub (course pages), priv (grades, exams)
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  repo    TEXT NOT NULL,
  head    TEXT NOT NULL,
  PRIMARY KEY (user_id, repo)
);
CREATE TABLE IF NOT EXISTS commits (
  sha     TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  repo    TEXT NOT NULL,
  parent  TEXT NOT NULL DEFAULT '',
  message TEXT NOT NULL DEFAULT '',
  author  TEXT NOT NULL DEFAULT '',
  at      REAL NOT NULL,
  paths   TEXT NOT NULL DEFAULT '[]'             -- JSON: the files it changed
);
CREATE INDEX IF NOT EXISTS commits_repo ON commits(user_id, repo, at);
CREATE TABLE IF NOT EXISTS objects (          -- blobs, trees and commits made for a save that hasn't landed yet
  user_id INTEGER NOT NULL,
  repo    TEXT NOT NULL,
  sha     TEXT NOT NULL,
  kind    TEXT NOT NULL,
  data    BLOB NOT NULL,
  created REAL NOT NULL,
  PRIMARY KEY (user_id, repo, sha)
);
"""


def data_dir():
    d = os.environ.get("LECTERN_DATA_DIR") or os.path.join(BASE_PATH, "data")
    os.makedirs(d, exist_ok=True)
    return d


_local = threading.local()
_init_lock = threading.Lock()
_ready = set()


def _connect(path):
    c = sqlite3.connect(path, timeout=30, isolation_level=None)   # autocommit; transaction() opens its own
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 30000")
    return c


def conn():
    """This thread's connection to the database (made, and the schema set up, on first use)."""
    path = os.path.join(data_dir(), "lectern.db")
    c = getattr(_local, "conns", {}).get(path)
    if c is None:
        with _init_lock:
            if path not in _ready:
                first = _connect(path)
                first.execute("PRAGMA journal_mode = WAL")
                first.executescript(SCHEMA)
                first.close()
                _ready.add(path)
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
        c = _connect(path)
        if not hasattr(_local, "conns"):
            _local.conns = {}
        _local.conns[path] = c
    return c


@contextlib.contextmanager
def transaction():
    """BEGIN IMMEDIATE … COMMIT (or ROLLBACK on an error). Yields the connection."""
    c = conn()
    if c.in_transaction:            # already inside one: just join it
        yield c
        return
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
    except BaseException:
        c.execute("ROLLBACK")
        raise
    else:
        c.execute("COMMIT")


def one(sql, args=()):
    return conn().execute(sql, args).fetchone()


def all_(sql, args=()):
    return conn().execute(sql, args).fetchall()


def run(sql, args=()):
    return conn().execute(sql, args)


def reset_for_tests():
    """Forget every connection (tests point LECTERN_DATA_DIR somewhere new each time)."""
    for c in getattr(_local, "conns", {}).values():
        try:
            c.close()
        except Exception:
            pass
    _local.conns = {}
    _ready.clear()
