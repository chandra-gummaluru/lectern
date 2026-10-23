"""python app.py setup: set up a Lectern instance (or change one) by answering a few questions.

  1. Where it lives: its public address, and whether HTTPS is handled in front of it (Cloudflare
     Tunnel, nginx); its port; the institution under the wordmark.
  2. Email (optional): an SMTP login, and a test email.
  3. Writes .env beside app.py (readable only by you; the old one is kept as .env.bak).
  4. The first admin account (asked here, so there's no link to open), if there isn't one yet.
  5. Import (optional): course pages, grades and exams from git clones of the old GitHub repositories.
  6. Checks that Lectern answers the way visitors will reach it (through the tunnel or proxy).

Run it again any time: it starts from the current settings, and Enter keeps each one.
new-lectern.sh does the rest of a new install (gets the code, makes a Python environment) and then runs this.
"""
import getpass
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

from .paths import BASE_PATH

LOCAL = {"localhost", "127.0.0.1", "::1"}

# What setup writes into .env, in this order, with a comment above each group. Other keys already in
# .env are kept, after these.
LAYOUT = [
    ("Where Lectern lives (links in emails use only this address)", ["LECTERN_APP_URL"]),
    ("HTTPS is handled in front of Lectern (Cloudflare Tunnel, nginx): trust its X-Forwarded-Proto/-For.\n"
     "# Lectern must then listen only on 127.0.0.1 (the default), so nothing else can reach it.", ["LECTERN_BEHIND_PROXY"]),
    ("The port Lectern listens on (python app.py)", ["LECTERN_PORT"]),
    ("Under the wordmark", ["LECTERN_INSTITUTION"]),
    ("Teaching team invitations may make new accounts only for these email domains (unset: any)", ["LECTERN_TEAM_DOMAINS"]),
    ("Email: invitations, password resets, security notices, students' receipts", [
        "LECTERN_SMTP_HOST", "LECTERN_SMTP_PORT", "LECTERN_SMTP_SECURITY", "LECTERN_SMTP_USER", "LECTERN_SMTP_PASSWORD", "LECTERN_SMTP_FROM"]),
]


class Quit(Exception):
    pass


# ── Asking ───────────────────────────────────────────────────────────
def ask(question, default=""):
    shown = f" [{default}]" if default else ""
    try:
        a = input(f"{question}{shown}: ").strip()
    except EOFError:
        raise Quit()
    return a or default


def yes(question, default=True):
    while True:
        a = ask(f"{question} ({'Y/n' if default else 'y/N'})").lower()
        if not a:
            return default
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False


def secret(question, keep=False):
    try:
        v = getpass.getpass(f"{question}{' [Enter keeps the current one]' if keep else ''}: ")
    except EOFError:
        raise Quit()
    return v


def say(text=""):
    print(text, flush=True)


def heading(text):
    say(f"\n── {text} " + "─" * max(0, 60 - len(text)))


# ── .env ─────────────────────────────────────────────────────────────
def read_env(path):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


def write_env(path, values):
    """Write .env: setup's own keys (grouped, commented), then any others it already had."""
    if os.path.exists(path):
        with open(path, "rb") as f:
            old = f.read()
        fd = os.open(path + ".bak", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(old)
    lines = [f"# Lectern's settings, written by `python app.py setup` on {time.strftime('%Y-%m-%d %H:%M')}.",
             "# Run it again to change them. Never commit this file (it's in .gitignore).", ""]
    done = set()
    for comment, keys in LAYOUT:
        have = [k for k in keys if values.get(k)]
        if not have:
            continue
        lines.append(f"# {comment}")
        lines += [f"{k}={values[k]}" for k in have]
        lines.append("")
        done.update(keys)
    rest = [k for k in values if k not in done and values[k] != ""]
    if rest:
        lines.append("# Other settings")
        lines += [f"{k}={values[k]}" for k in rest]
        lines.append("")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def norm_url(u):
    u = u.strip()
    if not re.match(r"^https?://", u):
        u = ("http://" if (u.split("/")[0].split(":")[0] in LOCAL) else "https://") + u
    return u if u.endswith("/") else u + "/"


# ── The steps ────────────────────────────────────────────────────────
def where(env):
    heading("1. Where Lectern lives")
    say("Its public address, as people type it: e.g. https://lectern.changapp.net/ (or http://localhost:5003/\nto use it only on this computer).")
    while True:
        url = norm_url(ask("Address", env.get("LECTERN_APP_URL") or "http://localhost:5003/"))
        p = urlsplit(url)
        if not p.hostname:
            say("  That isn't an address. Try again.")
            continue
        local = p.hostname in LOCAL
        if not local and p.scheme != "https":
            say("  Away from this computer, Lectern needs https:// (it won't take passwords without it).")
            continue
        break
    env["LECTERN_APP_URL"] = url
    if local:
        env.pop("LECTERN_BEHIND_PROXY", None)
    else:
        say("\nIs HTTPS handled in front of Lectern, by a Cloudflare Tunnel, nginx or similar, which passes\nvisitors on to Lectern on this machine? (Almost always yes.)")
        if yes("Behind a tunnel or proxy", env.get("LECTERN_BEHIND_PROXY", "1") == "1"):
            env["LECTERN_BEHIND_PROXY"] = "1"
        else:
            env.pop("LECTERN_BEHIND_PROXY", None)
            say("  Then Lectern itself must be served over HTTPS (e.g. by gunicorn with a certificate). The README has more.")
    port = str(p.port) if local and p.port else env.get("LECTERN_PORT") or "5003"
    while True:
        port = ask("Port for Lectern on this machine", port)
        if port.isdigit() and 0 < int(port) < 65536:
            break
        say("  A number, e.g. 5003.")
    env["LECTERN_PORT"] = port
    env["LECTERN_INSTITUTION"] = ask("Institution (shown under the wordmark)", env.get("LECTERN_INSTITUTION") or "University of Toronto")
    say("\nInstructors can invite people to their teaching teams, and someone new makes an account that way.\n"
        "To allow that only for some email domains, list them (e.g. utoronto.ca, which includes mail.utoronto.ca).")
    doms = ask("Domains for new accounts from teaching teams (Enter: any; '-' to clear)", env.get("LECTERN_TEAM_DOMAINS", ""))
    if doms.strip() == "-":
        env.pop("LECTERN_TEAM_DOMAINS", None)
    elif doms.strip():
        env["LECTERN_TEAM_DOMAINS"] = ",".join(d.strip().lstrip("@").lower() for d in doms.split(",") if d.strip())


def email(env):
    heading("2. Email")
    say("Lectern emails invitations, password-reset links, security notices and students' receipts.\nAny SMTP login works (for Gmail: smtp.gmail.com, and an app password).")
    if not yes("Set up email now", bool(env.get("LECTERN_SMTP_HOST"))):
        if env.get("LECTERN_SMTP_HOST") and yes("Turn email off (remove the SMTP settings)", False):
            for k in next(keys for _, keys in LAYOUT if "LECTERN_SMTP_HOST" in keys):
                env.pop(k, None)
        return
    env["LECTERN_SMTP_HOST"] = ask("SMTP server", env.get("LECTERN_SMTP_HOST") or "smtp.gmail.com")
    sec = ask("Security: starttls or ssl", env.get("LECTERN_SMTP_SECURITY") or "starttls").lower()
    env["LECTERN_SMTP_SECURITY"] = sec if sec in ("starttls", "ssl", "none") else "starttls"
    env["LECTERN_SMTP_PORT"] = ask("Port", env.get("LECTERN_SMTP_PORT") or ("465" if env["LECTERN_SMTP_SECURITY"] == "ssl" else "587"))
    env["LECTERN_SMTP_USER"] = ask("Login (usually the email address)", env.get("LECTERN_SMTP_USER", ""))
    pw = secret("Password (for Gmail, an app password)", keep=bool(env.get("LECTERN_SMTP_PASSWORD")))
    if pw:
        env["LECTERN_SMTP_PASSWORD"] = pw
    env["LECTERN_SMTP_FROM"] = ask("From (e.g. Lectern <lectern@changapp.net>)", env.get("LECTERN_SMTP_FROM") or env.get("LECTERN_SMTP_USER", ""))


def test_email(env):
    if not env.get("LECTERN_SMTP_HOST"):
        return
    to = ask("\nSend a test email to (Enter to skip)", "")
    if not to:
        return
    from . import mailer
    ok = mailer.send(to, "Lectern: test email", f"This is a test from Lectern at {env['LECTERN_APP_URL']}.\n\nEmail is set up.\n")
    say("  Sent. Check that it arrived (and isn't in spam)." if ok else "  It didn't send: see the error above. Run setup again to fix the settings.")


def admin(env):
    from . import db, security as sec
    from .auth import RESERVED, _HANDLE, suggest_handle
    heading("4. Your admin account")
    users = db.all_("SELECT email, is_admin FROM users")
    if users:
        admins = [u["email"] for u in users if u["is_admin"]]
        say(f"There {'is' if len(users) == 1 else 'are'} already {len(users)} account{'s' if len(users) != 1 else ''}; admin{'s' if len(admins) != 1 else ''}: {', '.join(admins) or 'none'}.")
        if not yes("Make another admin account", not admins):
            return admins[0] if admins else None
    while True:
        em = ask("Your email").lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", em):
            say("  An email address, please.")
            continue
        if db.one("SELECT 1 FROM users WHERE email = ?", (em,)):
            say("  That email already has an account.")
            continue
        break
    name = ""
    while not name:
        name = ask("Your name")
    handle = suggest_handle(em)
    say(f"Your course pages will be at {env['LECTERN_APP_URL']}p/<name>/…, e.g. {env['LECTERN_APP_URL']}p/{handle}/csc258/f26/info.html")
    while True:
        h = ask("Name for that address (lower case, dashes)", handle).lower()
        if not _HANDLE.match(h) or len(h) < 2 or h in RESERVED:
            say("  2 to 32 lower-case letters, numbers and dashes; not a reserved word.")
        elif db.one("SELECT 1 FROM users WHERE handle = ?", (h,)):
            say("  That's taken.")
        else:
            break
    while True:
        pw = secret(f"Password ({sec.MIN_PASSWORD}+ characters; a few words together is good)")
        bad = sec.password_problem(pw, em, name)
        if bad:
            say(f"  {bad}")
            continue
        if secret("Password, again") != pw:
            say("  The two aren't the same.")
            continue
        break
    t = time.time()
    db.run("INSERT INTO users (email, handle, name, pw_hash, pw_changed, is_admin, created) VALUES (?, ?, ?, ?, ?, 1, ?)",
           (em, h, name, sec.hash_password(pw), t, t))
    db.run("INSERT INTO events (user_id, kind, at, detail) VALUES ((SELECT id FROM users WHERE email = ?), 'account-created', ?, 'setup')", (em, t))
    say(f"  Made {em} (an admin). After you sign in, turn on two-factor sign-in under Your account.")
    return em


def import_courses(email_):
    heading("5. Courses from GitHub (optional)")
    say("If your course pages, grades and exams are in the old pair of GitHub repositories, Lectern can copy\nthem in from git clones on this machine (e.g. courses-utor and courses-utor-private).")
    if not email_ or not yes("Import now", False):
        return
    from . import db
    from .cli import _import
    u = db.one("SELECT * FROM users WHERE email = ?", (email_,))
    while True:
        pub = os.path.expanduser(ask("Folder of the public repository (course pages)"))
        priv = os.path.expanduser(ask("Folder of the private repository (grades, exams)"))
        if os.path.isdir(pub) and os.path.isdir(priv):
            break
        say(f"  Not found: {pub if not os.path.isdir(pub) else priv}")
        if not yes("Try again", True):
            return
    _import(u, pub, priv)
    say("  Delete the clones when you've checked everything is there: they hold grades.")


CHECK = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
import app as entry
from server import app
url = os.environ["LECTERN_APP_URL"]
from urllib.parse import urlsplit
p = urlsplit(url)
base = f"http://{p.netloc}/"
headers = {"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.7"} if os.environ.get("LECTERN_BEHIND_PROXY") else {}
c = app.test_client()
r = c.get("/", base_url=base if headers else url, headers=headers)
cfg = c.get("/api/config", base_url=base if headers else url, headers=headers)
print(json.dumps({"page": r.status_code, "location": r.headers.get("Location", ""), "config": cfg.get_json() if cfg.status_code == 200 else None}))
"""


def check(env, env_path):
    heading("6. Checking")
    full = {**os.environ, **{k: v for k, v in env.items() if v}}
    r = subprocess.run([sys.executable, "-c", CHECK], cwd=BASE_PATH, env=full, capture_output=True, text=True)
    problems = []
    try:
        d = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        say("  Lectern didn't start:\n" + (r.stderr.strip()[-1500:] or r.stdout.strip()))
        say("  If it says No module named …, install the requirements: pip install -r requirements.txt")
        return False
    if d["page"] != 200:
        problems.append(f"the page answered {d['page']}{' → ' + d['location'] if d['location'] else ''}"
                        + (": a redirect loop. Behind a tunnel or proxy? Run setup again and say yes." if d["page"] in (301, 302) else ""))
    elif not d["config"] or d["config"].get("app_url") != env["LECTERN_APP_URL"]:
        problems.append("the address didn't come through as set")
    if problems:
        say("  Problem: " + "; ".join(problems))
        return False
    say(f"  OK: Lectern answers as {env['LECTERN_APP_URL']}" + (" (through the tunnel or proxy)" if env.get("LECTERN_BEHIND_PROXY") else "") + ".")
    say(f"  Email: {'set up' if env.get('LECTERN_SMTP_HOST') else 'off (invitations show a link to send yourself; password resets need email)'}.")
    return True


def finish(env, ok):
    heading("Done" if ok else "Almost done")
    p = urlsplit(env["LECTERN_APP_URL"])
    port = env.get("LECTERN_PORT", "5003")
    say(f"Start Lectern (from {BASE_PATH}, in this Python environment):\n\n    python app.py\n")
    say(f"It listens on 127.0.0.1:{port}. For a server, run it under tmux, systemd or similar so it keeps going.")
    if env.get("LECTERN_BEHIND_PROXY"):
        say(f"""
Point your tunnel or proxy at it. For a Cloudflare Tunnel, in cloudflared's config.yml, under ingress:

    - hostname: {p.hostname}
      service: http://localhost:{port}

(and a DNS route: cloudflared tunnel route dns <tunnel name> {p.hostname}). For nginx:
proxy_pass http://127.0.0.1:{port}; with proxy_set_header X-Forwarded-Proto $scheme;
and proxy_set_header X-Forwarded-For $remote_addr;""")
    say(f"\nThen sign in at {env['LECTERN_APP_URL']} and turn on two-factor sign-in (Your account).")
    say(f"Invite others from the account menu, or: python app.py invite them@example.com\n"
        f"Back up {os.environ.get('LECTERN_DATA_DIR') or os.path.join(BASE_PATH, 'data')} (secret.key included).")


def main(argv=()):
    env_path = os.path.join(BASE_PATH, ".env")
    say("Setting up Lectern. Enter keeps the value in [brackets]; Ctrl+C stops without changing anything.")
    env = read_env(env_path)
    try:
        where(env)
        email(env)
        heading("3. Saving the settings")
        write_env(env_path, env)
        for k in list(os.environ):
            if k.startswith("LECTERN_SMTP_") or k == "LECTERN_BEHIND_PROXY":
                del os.environ[k]
        os.environ.update({k: v for k, v in env.items() if v})
        say(f"  Wrote {env_path} (only you can read it){'; the old one is .env.bak' if os.path.exists(env_path + '.bak') else ''}.")
        test_email(env)
        who = admin(env)
        import_courses(who)
        ok = check(env, env_path)
        finish(env, ok)
    except (Quit, KeyboardInterrupt):
        say("\nStopped. (Anything already saved stays saved.)")
        sys.exit(1)
