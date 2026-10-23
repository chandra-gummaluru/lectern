"""Lectern's command line, for whoever runs the server:

  python app.py setup                            set up this Lectern (or change its settings): a few questions

  python app.py invite you@utoronto.ca --admin   an invitation link (emailed too, when SMTP is set up);
                                                 the way to make the first admin account
  python app.py users                            every account
  python app.py reset-2fa you@utoronto.ca        turn off someone's two-factor sign-in (a lost phone)
  python app.py disable you@utoronto.ca          turn an account off (and sign it out); enable turns it back on
  python app.py import you@utoronto.ca courses-utor courses-utor-private
                                                 copy your git clones of the two GitHub repositories
                                                 (course pages, then grades and exams) into an account
"""
import argparse
import os
import sys
import time

from . import db
from .auth import Refusal, create_invite, invite_link, send_invite

COMMANDS = ("setup", "invite", "users", "reset-2fa", "disable", "enable", "import")


def _base():
    u = os.environ.get("LECTERN_APP_URL") or "http://localhost:5003/"
    return u if u.endswith("/") else u + "/"


def _user(email):
    u = db.one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    if not u:
        sys.exit(f"No account for {email}.")
    return u


def main(argv):
    if argv and argv[0] == "setup":
        from .wizard import main as setup
        return setup(argv[1:])
    p = argparse.ArgumentParser(prog="python app.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("invite", help="invite someone to make an account")
    i.add_argument("email")
    i.add_argument("--admin", action="store_true", help="the account can invite others and manage accounts")
    sub.add_parser("users", help="list accounts")
    for name in ("reset-2fa", "disable", "enable"):
        sub.add_parser(name).add_argument("email")
    im = sub.add_parser("import", help="copy two folders (git clones) into an account's files")
    im.add_argument("email")
    im.add_argument("public", help="the public repository's folder (course pages), e.g. courses-utor")
    im.add_argument("private", help="the private one (grades, exams), e.g. courses-utor-private")
    a = p.parse_args(argv)

    if a.cmd == "invite":
        try:
            tok = create_invite(a.email, a.admin)
        except Refusal as e:
            sys.exit(str(e))
        link = invite_link(tok, _base())
        sent = send_invite(a.email.strip().lower(), link)
        print(f"Invitation for {a.email}{' (admin)' if a.admin else ''}, valid 7 days{' (emailed)' if sent else ''}:\n\n  {link}\n")
        print("Anyone with this link can make the account: send it only to that person.")
    elif a.cmd == "users":
        for u in db.all_("SELECT * FROM users ORDER BY created"):
            flags = [x for x, on in (("admin", u["is_admin"]), ("2FA", u["totp_secret"]), ("OFF", u["disabled"])) if on]
            last = time.strftime("%Y-%m-%d %H:%M", time.localtime(u["last_login"])) if u["last_login"] else "never"
            print(f"{u['email']:<40} {u['handle']:<20} {' '.join(flags):<14} last sign-in {last}")
    elif a.cmd == "reset-2fa":
        u = _user(a.email)
        with db.transaction() as c:
            c.execute("UPDATE users SET totp_secret = NULL, totp_pending = NULL, totp_step = 0 WHERE id = ?", (u["id"],))
            c.execute("DELETE FROM recovery_codes WHERE user_id = ?", (u["id"],))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))
        print(f"Two-factor sign-in is off for {u['email']}, and it's signed out everywhere.")
    elif a.cmd in ("disable", "enable"):
        u = _user(a.email)
        with db.transaction() as c:
            c.execute("UPDATE users SET disabled = ?, failed = 0, locked_until = 0 WHERE id = ?", (1 if a.cmd == "disable" else 0, u["id"]))
            if a.cmd == "disable":
                c.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))
        print(f"{u['email']} is {'off' if a.cmd == 'disable' else 'on'}.")

    elif a.cmd == "import":
        _import(_user(a.email), a.public, a.private)


def _import(u, public, private):
    from .store import Repo, StoreError, clean_path
    for name, folder in (("pub", public), ("priv", private)):
        if not os.path.isdir(folder):
            sys.exit(f"No folder {folder}.")
        files = {}
        for d, dirs, names in os.walk(folder):
            dirs[:] = [x for x in dirs if not x.startswith(".")]     # not .git
            for n in names:
                full = os.path.join(d, n)
                rel = os.path.relpath(full, folder).replace(os.sep, "/")
                try:
                    clean_path(rel)
                except StoreError:
                    print(f"  skipped {rel}")
                    continue
                with open(full, "rb") as f:
                    files[rel] = f.read()
        repo = Repo(u["id"], name)
        repo.commit(files, f"Import from {os.path.basename(os.path.abspath(folder))}", repo.head(), "import")
        print(f"{'Course pages' if name == 'pub' else 'Grades and exams'}: {len(files)} files from {folder}")
    print(f"Done. {u['email']}'s course pages are at /p/{u['handle']}/. Open each course page in Lectern and save it once, "
          "so its Request Accommodation buttons point at the new address.")
