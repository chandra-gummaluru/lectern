"""python app.py setup and python app.py admin: answers in; .env and the admin panel's admin out."""
import os

import pytest

from server import cli, db, security, wizard

SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
PW = "correct horse battery staple"


@pytest.fixture(autouse=True)
def fixed_secret(monkeypatch):
    monkeypatch.setattr(security, "new_totp_secret", lambda: SECRET)


def code():
    db.run("UPDATE admins SET totp_step = 0")
    return security.totp_now(SECRET)


def run(monkeypatch, tmp_path, answers, secrets):
    monkeypatch.setattr(wizard, "BASE_PATH", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda q="": (lambda a: a() if callable(a) else a)(answers.pop(0)))
    monkeypatch.setattr(wizard.getpass, "getpass", lambda q="": secrets.pop(0))
    monkeypatch.setattr(wizard, "check", lambda env, path: True)
    wizard.main([])
    return wizard.read_env(str(tmp_path / ".env"))


def test_setup_behind_a_tunnel(monkeypatch, tmp_path):
    env = run(monkeypatch, tmp_path, ["lectern.changapp.net", "", "", "", "utoronto.ca", "n", "chandra@cs.toronto.edu", "Chandra", code], [PW, PW])
    assert env["LECTERN_APP_URL"] == "https://lectern.changapp.net/" and env["LECTERN_BEHIND_PROXY"] == "1" and env["LECTERN_PORT"] == "5003"
    assert env["LECTERN_TEAM_DOMAINS"] == "utoronto.ca"
    assert oct(os.stat(tmp_path / ".env").st_mode & 0o777) == "0o600"
    a = db.one("SELECT * FROM admins")
    assert a["email"] == "chandra@cs.toronto.edu" and a["pw_hash"].startswith("$argon2id$") and SECRET not in a["totp_secret"]
    assert db.one("SELECT COUNT(*) AS n FROM users")["n"] == 0          # an admin isn't a Lectern account


def test_setup_again_keeps_settings_and_other_keys(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("LECTERN_APP_URL=https://a.example/\nLECTERN_BEHIND_PROXY=1\nLECTERN_TIMEZONE=America/Vancouver\n")
    env = run(monkeypatch, tmp_path, ["", "", "", "", "", "n", "a@x.ca", "A B", code], [PW, PW])
    assert env["LECTERN_APP_URL"] == "https://a.example/" and env["LECTERN_TIMEZONE"] == "America/Vancouver"
    assert (tmp_path / ".env.bak").exists()


def test_plain_http_is_refused_away_from_localhost(monkeypatch, tmp_path):
    env = run(monkeypatch, tmp_path, ["http://lectern.example.org", "https://lectern.example.org", "", "", "", "", "n", "a@x.ca", "A", code], [PW, PW])
    assert env["LECTERN_APP_URL"] == "https://lectern.example.org/"


def test_admin_command_needs_a_working_code(monkeypatch):
    answers = ["Ad Min"] + ["000000"] * 5
    monkeypatch.setattr("builtins.input", lambda q="": answers.pop(0))
    monkeypatch.setattr(cli.getpass, "getpass", lambda q="": PW)
    with pytest.raises(SystemExit):
        cli.main(["admin", "ad@x.ca"])
    assert not db.one("SELECT 1 FROM admins")


def test_admin_command_replaces_a_lost_phone(monkeypatch):
    for name in ("Ad Min", "Ad Min"):
        answers = ([] if name and not db.one("SELECT 1 FROM admins") else ["y"]) + [name, code]
        monkeypatch.setattr("builtins.input", lambda q="": (lambda a: a() if callable(a) else a)(answers.pop(0)))
        monkeypatch.setattr(cli.getpass, "getpass", lambda q="": PW)
        cli.main(["admin", "ad@x.ca"])
    assert db.one("SELECT COUNT(*) AS n FROM admins")["n"] == 1


def test_no_other_commands(capsys):
    with pytest.raises(SystemExit):
        cli.main(["invite", "x@x.ca"])
