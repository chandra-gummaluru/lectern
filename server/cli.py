"""Lectern's command line, on the server. One job: admins.

  python app.py admin you@example.com    add an admin for the admin panel (/admin), with its password and
                                         two-factor code set up here; for an existing admin, replace both
                                         (a forgotten password or a lost phone)
  python app.py setup                    set this Lectern up (or change its settings), adding the first admin

Everything else (inviting people, looking after accounts, email settings) is in the admin panel.
"""
import getpass
import re
import sys

from . import db, security as sec

COMMANDS = ("setup", "admin")


def ask(q, default=""):
    try:
        a = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        sys.exit(1)
    return a or default


def add_admin(email, out=print):
    """Ask for the admin's name and password, show their two-factor QR code and key, check a code, save."""
    from .admin import save_admin
    email = email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        sys.exit(f"{email} isn't an email address.")
    old = db.one("SELECT * FROM admins WHERE email = ?", (email,))
    if old:
        out(f"{email} is already an admin. Going on replaces their password and two-factor app (and signs them out).")
        if ask("Go on? (y/N)").lower() not in ("y", "yes"):
            sys.exit(1)
    name = ask("Name", old["name"] if old else "")
    while True:
        pw = getpass.getpass(f"Password ({sec.MIN_PASSWORD}+ characters): ")
        bad = sec.password_problem(pw, email, name)
        if bad:
            out(f"  {bad}")
            continue
        if getpass.getpass("Password, again: ") != pw:
            out("  The two aren't the same.")
            continue
        break
    secret = sec.new_totp_secret()
    uri = sec.totp_uri(secret, email, "Lectern Admin")
    out("\nTwo-factor sign-in is required for admins. In your authenticator app, add an account by scanning this:\n")
    try:
        import segno
        segno.make(uri, error="m").terminal(compact=True)
    except Exception:
        pass
    out(f"\nor typing this key: {' '.join(secret[i:i + 4] for i in range(0, len(secret), 4))}\n")
    step = None
    for _ in range(5):
        step = sec.totp_match(secret, ask("Then the 6-digit code it shows"))
        if step is not None:
            break
        out("  That code isn't right. Check the app's account says Lectern Admin, and the phone's time is set automatically.")
    else:
        sys.exit("Not saved.")
    save_admin(email, name, pw, secret, step)   # that code is used up: it won't sign in
    out(f"\n{email} is {'updated' if old else 'an admin'}. Sign in at <your Lectern address>/admin.")


def main(argv):
    if argv and argv[0] == "setup":
        from .wizard import main as setup
        return setup(argv[1:])
    if len(argv) == 2 and argv[0] == "admin":
        return add_admin(argv[1])
    print(__doc__)
    sys.exit(1)
