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
  is_admin      INTEGER NOT NULL DEFAULT 0,    -- no longer used: admins have their own accounts (admins table)
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
CREATE TABLE IF NOT EXISTS members (          -- teaching teams: who else works on an offering, and as what
  owner_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,   -- whose files the offering is in
  offering  TEXT NOT NULL,                                             -- <course>/<term>, e.g. csc258/f26
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role      TEXT NOT NULL,                                             -- coordinator | instructor | ta | staff
  added_by  INTEGER,
  added     REAL NOT NULL,
  PRIMARY KEY (owner_id, offering, user_id)
);
CREATE INDEX IF NOT EXISTS members_user ON members(user_id);
CREATE TABLE IF NOT EXISTS admins (           -- the admin panel's own accounts: added only from the terminal
  id           INTEGER PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  name         TEXT NOT NULL DEFAULT '',
  pw_hash      TEXT NOT NULL,
  totp_secret  TEXT NOT NULL,                  -- encrypted; two-factor is required for admins
  totp_step    INTEGER NOT NULL DEFAULT 0,
  disabled     INTEGER NOT NULL DEFAULT 0,
  failed       INTEGER NOT NULL DEFAULT 0,
  locked_until REAL NOT NULL DEFAULT 0,
  created      REAL NOT NULL,
  last_login   REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS admin_sessions (
  id_hash   TEXT PRIMARY KEY,
  admin_id  INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
  created   REAL NOT NULL,
  last_seen REAL NOT NULL,
  expires   REAL NOT NULL,
  ip        TEXT NOT NULL DEFAULT '',
  agent     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS team_invites (     -- someone asked to join a team: they accept (and make an account if need be)
  token_hash TEXT PRIMARY KEY,
  owner_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering   TEXT NOT NULL,
  email      TEXT NOT NULL,
  role       TEXT NOT NULL,
  created_by INTEGER NOT NULL,
  created    REAL NOT NULL,
  expires    REAL NOT NULL,
  used       REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS team_invites_offering ON team_invites(owner_id, offering);
CREATE TABLE IF NOT EXISTS settings (         -- set in the admin panel (email): over the .env's
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offering_mail (     -- an offering's own email (SMTP) settings: classmail.py
  owner_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering   TEXT NOT NULL,
  smtp       TEXT NOT NULL,                     -- JSON; the password encrypted (password_enc)
  updated    REAL NOT NULL,
  updated_by INTEGER,
  PRIMARY KEY (owner_id, offering)
);
CREATE TABLE IF NOT EXISTS offering_mail_prefs ( -- an offering's email to students: reply-to, signature, which go out
  owner_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering   TEXT NOT NULL,
  prefs      TEXT NOT NULL,                     -- JSON { replyTo, signature, send: { kind: bool } }
  updated    REAL NOT NULL,
  PRIMARY KEY (owner_id, offering)
);
CREATE TABLE IF NOT EXISTS grade_notices (      -- what each student was last emailed about an evaluation's mark
  owner_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering   TEXT NOT NULL,
  eval_id    TEXT NOT NULL,
  num        TEXT NOT NULL,                     -- the student's identifier in the gradebook
  mark       TEXT NOT NULL,                     -- the mark as it was then (JSON)
  at         REAL NOT NULL,
  PRIMARY KEY (owner_id, offering, eval_id, num)
);
CREATE TABLE IF NOT EXISTS mail_sends (        -- emails to a class: who sent what, to how many, how it went
  id        INTEGER PRIMARY KEY,
  owner_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering  TEXT NOT NULL,
  by_user   INTEGER,
  by_name   TEXT NOT NULL DEFAULT '',
  at        REAL NOT NULL,
  subject   TEXT NOT NULL,
  to_label  TEXT NOT NULL DEFAULT '',
  total     INTEGER NOT NULL DEFAULT 0,
  sent      INTEGER NOT NULL DEFAULT 0,
  failed    INTEGER NOT NULL DEFAULT 0,
  done      INTEGER NOT NULL DEFAULT 0,
  errors    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS mail_sends_offering ON mail_sends(owner_id, offering, at);
CREATE TABLE IF NOT EXISTS retired_handles (  -- page addresses of deleted accounts: never given to anyone else
  handle TEXT PRIMARY KEY,
  at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS resets (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created    REAL NOT NULL,
  expires    REAL NOT NULL,
  used       REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS announcements_seen (  -- the announcements each student has seen on the course page (the rest are New for them)
  owner_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering  TEXT NOT NULL,
  email     TEXT NOT NULL,
  ann_id    TEXT NOT NULL,
  at        REAL NOT NULL,
  PRIMARY KEY (owner_id, offering, email, ann_id)
);
CREATE TABLE IF NOT EXISTS discussion_posts (  -- a course page's discussions (discuss.py): posts on an evaluation, an activity or an announcement, and their comments
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering    TEXT NOT NULL,
  target      TEXT NOT NULL,              -- "eval:<id>", "act:<id>", "ann:<id>"
  parent_id   INTEGER,                    -- a comment: the post or comment it answers
  author_kind TEXT NOT NULL,              -- "student" (by the email they signed in with) or "staff" (a Lectern account)
  author      TEXT NOT NULL,
  anon        INTEGER NOT NULL DEFAULT 0, -- a student's, anonymous to classmates (the teaching team sees who)
  title       TEXT NOT NULL DEFAULT '',
  body        TEXT NOT NULL DEFAULT '',
  created     REAL NOT NULL,
  pinned      INTEGER NOT NULL DEFAULT 0,
  endorsed_by TEXT NOT NULL DEFAULT '',
  removed_by  TEXT NOT NULL DEFAULT '',
  deleted     INTEGER NOT NULL DEFAULT 0  -- by its author
);
CREATE INDEX IF NOT EXISTS discussion_posts_target ON discussion_posts (owner_id, offering, target);
CREATE TABLE IF NOT EXISTS discussion_votes (
  post_id INTEGER NOT NULL REFERENCES discussion_posts(id) ON DELETE CASCADE,
  voter   TEXT NOT NULL,                  -- "s:<email>" or "u:<user id>"
  PRIMARY KEY (post_id, voter)
);
CREATE TABLE IF NOT EXISTS discussion_aliases (  -- each student's anonymous name in a course ("Anonymous Heron"), the same in all its discussions
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering TEXT NOT NULL,
  email    TEXT NOT NULL,
  alias    TEXT NOT NULL,
  PRIMARY KEY (owner_id, offering, email),
  UNIQUE (owner_id, offering, alias)
);
CREATE TABLE IF NOT EXISTS course_students (  -- when each student was sent the course page's link and last signed in (students.py; the class list is the gradebook's)
  owner_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering  TEXT NOT NULL,
  email     TEXT NOT NULL,
  added     REAL NOT NULL,
  added_by  INTEGER,
  invited   REAL NOT NULL DEFAULT 0,
  last_in   REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (owner_id, offering, email)
);
CREATE TABLE IF NOT EXISTS student_codes (    -- a one-time code emailed to a student signing in (kept as a keyed hash)
  owner_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering  TEXT NOT NULL,
  email     TEXT NOT NULL,
  code_mac  TEXT NOT NULL,
  expires   REAL NOT NULL,
  tries     INTEGER NOT NULL DEFAULT 0,
  created   REAL NOT NULL,
  PRIMARY KEY (owner_id, offering, email)
);
CREATE TABLE IF NOT EXISTS student_sessions ( -- a student signed in to one course page
  id_hash   TEXT PRIMARY KEY,
  owner_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  offering  TEXT NOT NULL,
  email     TEXT NOT NULL,
  created   REAL NOT NULL,
  last_seen REAL NOT NULL,
  expires   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS student_sessions_who ON student_sessions(owner_id, offering, email);
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


# Columns added after a database was first made: (table, column, definition).
MIGRATIONS = [
    ("objects", "uploader", "INTEGER"),   # who uploaded a save's piece (a teaching team member's count separately)
]


def _migrate(c):
    for table, col, kind in MIGRATIONS:
        if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
    # Activity groups (teams.py): an "instructor" could do everything with an offering; that's a coordinator now.
    if not c.execute("SELECT 1 FROM settings WHERE key = 'roles-v2'").fetchone():
        c.execute("UPDATE members SET role = 'coordinator' WHERE role = 'instructor'")
        c.execute("UPDATE team_invites SET role = 'coordinator' WHERE role = 'instructor'")
        c.execute("INSERT INTO settings (key, value) VALUES ('roles-v2', '1')")


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
                _migrate(first)
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
