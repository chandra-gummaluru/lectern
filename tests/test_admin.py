"""The admin panel: its own accounts and sign-in (email, password and code), separate from Lectern's."""
import json
import os
import time

import pytest

from conftest import H, PASSWORD, make_user
from server import admin, app, auth, db, mailer, security, store

SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


@pytest.fixture(autouse=True)
def clean_limits():
    auth.limiter.reset()


def code():
    db.run("UPDATE admins SET totp_step = 0")   # each code works once: let the same one be used again
    return security.totp_now(SECRET)


@pytest.fixture()
def adm():
    admin.save_admin("root@x.ca", "Root", PASSWORD, SECRET)
    c = app.test_client()
    r = c.post("/api/admin/login", json={"email": "root@x.ca", "password": PASSWORD, "code": code()}, headers=H)
    assert r.status_code == 200, r.get_json()
    return c


def test_the_panel_page(client):
    r = client.get("/admin")
    assert r.status_code == 200 and b'id="lxa-form"' in r.data and r.headers["X-Frame-Options"] == "DENY"


def test_sign_in_needs_password_and_code(client):
    admin.save_admin("root@x.ca", "Root", PASSWORD, SECRET)
    assert client.post("/api/admin/login", json={"email": "root@x.ca", "password": PASSWORD, "code": "000000"}, headers=H).status_code == 401
    assert client.post("/api/admin/login", json={"email": "root@x.ca", "password": "wrong password!", "code": code()}, headers=H).status_code == 401
    assert client.post("/api/admin/login", json={"email": "root@x.ca", "password": PASSWORD}, headers=H).status_code == 400
    assert client.get("/api/admin/me").get_json()["signedIn"] is False
    r = client.post("/api/admin/login", json={"email": "root@x.ca", "password": PASSWORD, "code": code()}, headers=H)
    assert r.status_code == 200 and client.get("/api/admin/me").get_json()["admin"]["email"] == "root@x.ca"
    c = client.get_cookie("lectern_admin")
    assert c and c.http_only and c.same_site == "Strict"


def test_admins_and_accounts_are_separate(client, adm):
    make_user(client)                                    # a Lectern account, signed in on client
    assert client.get("/api/admin/overview").status_code == 401
    assert adm.get("/api/auth/me").get_json()["signedIn"] is False
    assert adm.get("/api/store/priv/git/trees/main").status_code == 401
    # an admin's email and password don't sign in to Lectern, and an account's don't sign in here
    assert adm.post("/api/auth/login", json={"email": "root@x.ca", "password": PASSWORD}, headers=H).status_code == 401
    assert client.post("/api/admin/login", json={"email": "chandra@utoronto.ca", "password": PASSWORD, "code": code()}, headers=H).status_code == 401


def test_wrong_tries_wait_the_same_with_or_without_an_admin(client):
    admin.save_admin("root@x.ca", "Root", PASSWORD, SECRET)
    a, b = app.test_client(), app.test_client()
    real = [a.post("/api/admin/login", json={"email": "root@x.ca", "password": "nope nope nope", "code": "1"}, headers=H).status_code for _ in range(6)]
    fake = [b.post("/api/admin/login", json={"email": "no@x.ca", "password": "nope nope nope", "code": "1"}, headers=H).status_code for _ in range(6)]
    assert real == fake == [401] * 5 + [429]


def test_sessions_end_after_half_an_hour_idle(adm):
    db.run("UPDATE admin_sessions SET last_seen = ?", (time.time() - 31 * 60,))
    assert adm.get("/api/admin/overview").status_code == 401


def test_invite_and_look_after_accounts(client, adm):
    r = adm.post("/api/admin/invites", json={"email": "ta@x.ca"}, headers=H).get_json()
    assert "#invite=" in r["link"]
    ov = adm.get("/api/admin/overview").get_json()
    assert [i["email"] for i in ov["invites"]] == ["ta@x.ca"] and ov["admins"][0]["email"] == "root@x.ca"
    u = make_user(client)
    assert adm.post(f"/api/admin/users/{u['id']}", json={"action": "sign-out"}, headers=H).status_code == 200
    assert client.get("/api/auth/me").get_json()["signedIn"] is False
    assert adm.post(f"/api/admin/users/{u['id']}", json={"action": "disable"}, headers=H).status_code == 403     # needs the password
    assert adm.post(f"/api/admin/users/{u['id']}", json={"action": "disable", "password": PASSWORD}, headers=H).status_code == 200
    assert client.post("/api/auth/login", json={"email": "chandra@utoronto.ca", "password": PASSWORD}, headers=H).status_code == 403


def test_admins_cant_turn_themselves_off(adm):
    me = adm.get("/api/admin/overview").get_json()["me"]
    assert adm.post(f"/api/admin/admins/{me}", json={"action": "disable", "password": PASSWORD}, headers=H).status_code == 400


def test_turning_another_admin_off_signs_them_out(adm):
    admin.save_admin("two@x.ca", "Two", PASSWORD, SECRET)
    two = app.test_client()
    assert two.post("/api/admin/login", json={"email": "two@x.ca", "password": PASSWORD, "code": code()}, headers=H).status_code == 200
    tid = db.one("SELECT id FROM admins WHERE email = 'two@x.ca'")["id"]
    assert adm.post(f"/api/admin/admins/{tid}", json={"action": "disable", "password": PASSWORD}, headers=H).status_code == 200
    assert two.get("/api/admin/overview").status_code == 401


def test_the_panel_needs_lecterns_header(adm):
    assert adm.post("/api/admin/invites", json={"email": "x@x.ca"}).status_code == 403


def test_knowing_an_admins_email_cant_keep_them_out(client):
    admin.save_admin("root@x.ca", "Root", PASSWORD, SECRET)
    for k in range(12):   # someone else, from elsewhere
        app.test_client().post("/api/admin/login", json={"email": "root@x.ca", "password": "nope nope nope", "code": "1"},
                               headers=H, environ_base={"REMOTE_ADDR": f"10.0.0.{k}"})
    r = client.post("/api/admin/login", json={"email": "root@x.ca", "password": PASSWORD, "code": code()}, headers=H, environ_base={"REMOTE_ADDR": "10.9.9.9"})
    assert r.status_code == 200


def test_the_panel_can_have_its_own_address(adm, monkeypatch):
    monkeypatch.setenv("LECTERN_ADMIN_URL", "https://admin.example.org/")
    assert adm.get("/admin").status_code == 404 and adm.get("/api/admin/overview").status_code == 404
    assert adm.get("/admin", base_url="https://admin.example.org").status_code == 200


# ── Deleting an account ──────────────────────────────────────────────
def test_delete_an_account(client, adm, tmp_path):
    from test_store import save
    u = make_user(client)
    save(client, "pub", {"csc258/f26/info.html": "<h1>258</h1>"})
    save(client, "priv", {"csc258/f26/grades.json": "{}"})
    ta = app.test_client(); t = make_user(ta, email="ta@x.ca", name="T A", handle="ta")
    db.run("INSERT INTO members (owner_id, offering, user_id, role, added) VALUES (?, 'csc258/f26', ?, 'ta', 0)", (u["id"], t["id"]))
    go = lambda **k: adm.post(f"/api/admin/users/{u['id']}", json={"action": "delete", **k}, headers=H)
    assert go(password=PASSWORD, confirm="wrong@x.ca").status_code == 400            # their email, typed
    assert go(password="not it at all", confirm=u["email"]).status_code == 403        # the admin's password
    assert db.one("SELECT 1 FROM users WHERE id = ?", (u["id"],))
    assert go(password=PASSWORD, confirm=u["email"].upper()).status_code == 200
    assert not db.one("SELECT 1 FROM users WHERE id = ?", (u["id"],))
    assert not db.one("SELECT 1 FROM members WHERE owner_id = ?", (u["id"],))
    assert client.get("/api/auth/me").get_json().get("user") is None                   # signed out
    assert client.get("/p/chandra/csc258/f26/info.html").status_code == 404           # pages offline
    assert not os.path.exists(tmp_path / "data" / "files" / str(u["id"]))
    kept = list((tmp_path / "data" / "deleted").glob("*-chandra"))
    assert kept and (kept[0] / "files" / "priv" / "csc258" / "f26" / "grades.json").read_text() == "{}"
    assert json.loads((kept[0] / "account.json").read_text())["email"] == u["email"]
    assert any("deleted" in m["subject"] for m in mailer.sent)
    assert "taken" in auth.handle_problem("chandra") and auth.suggest_handle("chandra@x.ca") != "chandra"   # the address stays theirs
    nu = make_user(app.test_client(), email="new@x.ca", name="N", handle="newbie")    # a new account sees none of it
    assert store.Repo(nu["id"], "priv").read_text("csc258/f26/grades.json") is None or nu["id"] != u["id"]


# ── Email (SMTP) settings ────────────────────────────────────────────
def test_email_settings_from_the_panel(adm, monkeypatch):
    tried = []
    def fake(to, subject, body, reply_to=None, cfg=None):
        tried.append((to, cfg))
        return "" if cfg and cfg.get("password") == "app-password" else "535 Authentication failed"
    monkeypatch.setattr(mailer, "deliver", fake)
    assert adm.get("/api/admin/email").get_json()["source"] == ""
    new = {"host": "smtp.gmail.com", "port": "587", "security": "starttls", "user": "lectern@x.ca", "from": "Lectern <lectern@x.ca>"}
    r = adm.post("/api/admin/email", json={**new, "smtpPassword": "wrong", "password": PASSWORD}, headers=H)
    assert r.status_code == 400 and "535" in r.get_json()["error"] and not mailer.configured()   # a failing test saves nothing
    assert adm.post("/api/admin/email", json={**new, "smtpPassword": "app-password", "password": "nope"}, headers=H).status_code == 403
    r = adm.post("/api/admin/email", json={**new, "smtpPassword": "app-password", "password": PASSWORD}, headers=H)
    assert r.status_code == 200 and tried[-1][0] == "root@x.ca"
    j = adm.get("/api/admin/email").get_json()
    assert j["source"] == "panel" and j["hasPassword"] and "app-password" not in json.dumps(j)
    assert "app-password" not in db.one("SELECT value FROM settings WHERE key = 'smtp'")["value"]   # encrypted
    assert mailer.settings()["password"] == "app-password" and mailer.configured()
    # Blank password: keeps the saved one.
    assert adm.post("/api/admin/email", json={**new, "from": "Other <o@x.ca>", "password": PASSWORD}, headers=H).status_code == 200
    assert mailer.settings()["from"] == "Other <o@x.ca>" and mailer.settings()["password"] == "app-password"
    assert adm.post("/api/admin/email", json={**new, "host": "bad host\r\n", "password": PASSWORD}, headers=H).status_code == 400
    assert adm.post("/api/admin/email", json={"action": "remove", "password": PASSWORD}, headers=H).status_code == 200
    assert not mailer.configured()


def test_email_settings_need_an_admin(client, user):
    assert client.get("/api/admin/email").status_code == 401
    assert client.post("/api/admin/email", json={"action": "remove"}, headers=H).status_code == 401
