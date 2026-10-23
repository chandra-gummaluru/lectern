"""python app.py setup: answers in, .env and the admin account out."""
import os

from server import db, wizard


def run(monkeypatch, tmp_path, answers, secrets):
    monkeypatch.setattr(wizard, "BASE_PATH", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda q="": answers.pop(0))
    monkeypatch.setattr(wizard.getpass, "getpass", lambda q="": secrets.pop(0))
    monkeypatch.setattr(wizard, "check", lambda env, path: True)
    wizard.main([])
    return wizard.read_env(str(tmp_path / ".env"))


def test_setup_behind_a_tunnel(monkeypatch, tmp_path):
    pw = "correct horse battery staple"
    env = run(monkeypatch, tmp_path,
              ["lectern.changapp.net", "", "", "", "n", "chandra@cs.toronto.edu", "Chandra Gummaluru", "chandra", "n"], [pw, pw])
    assert env["LECTERN_APP_URL"] == "https://lectern.changapp.net/" and env["LECTERN_BEHIND_PROXY"] == "1" and env["LECTERN_PORT"] == "5003"
    assert oct(os.stat(tmp_path / ".env").st_mode & 0o777) == "0o600"
    u = db.one("SELECT * FROM users")
    assert u["email"] == "chandra@cs.toronto.edu" and u["is_admin"] == 1 and u["handle"] == "chandra" and u["pw_hash"].startswith("$argon2id$")


def test_setup_again_keeps_settings_and_other_keys(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("LECTERN_APP_URL=https://a.example/\nLECTERN_BEHIND_PROXY=1\nLECTERN_TIMEZONE=America/Vancouver\n")
    env = run(monkeypatch, tmp_path, ["", "", "", "", "n", "a@x.ca", "A B", "", "n"], ["correct horse battery staple"] * 2)
    assert env["LECTERN_APP_URL"] == "https://a.example/" and env["LECTERN_TIMEZONE"] == "America/Vancouver"
    assert (tmp_path / ".env.bak").exists()


def test_plain_http_is_refused_away_from_localhost(monkeypatch, tmp_path):
    env = run(monkeypatch, tmp_path, ["http://lectern.example.org", "https://lectern.example.org", "", "", "", "n", "a@x.ca", "A B", "", "n"],
              ["correct horse battery staple"] * 2)
    assert env["LECTERN_APP_URL"] == "https://lectern.example.org/"
