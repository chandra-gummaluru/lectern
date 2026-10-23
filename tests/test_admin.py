"""The admin panel: its own accounts and sign-in (email, password and code), separate from Lectern's."""
import io
import json
import time
import zipfile

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


def test_import_a_github_zip(client, adm):
    u = make_user(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("courses-utor-main/csc258/f26/info.html", "<h1>258</h1>")
        z.writestr("courses-utor-main/.github/workflows/x.yml", "x")
        z.writestr("courses-utor-main/../../evil.txt", "x")
    r = adm.post("/api/admin/import", data={"user": str(u["id"]), "area": "pub", "zip": (io.BytesIO(buf.getvalue()), "courses-utor-main.zip")},
                 headers=H, content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["files"] == 1
    assert store.Repo(u["id"], "pub").read_text("csc258/f26/info.html")[0] == "<h1>258</h1>"


def test_knowing_an_admins_email_cant_keep_them_out(client):
    admin.save_admin("root@x.ca", "Root", PASSWORD, SECRET)
    for k in range(12):   # someone else, from elsewhere
        app.test_client().post("/api/admin/login", json={"email": "root@x.ca", "password": "nope nope nope", "code": "1"},
                               headers=H, environ_base={"REMOTE_ADDR": f"10.0.0.{k}"})
    r = client.post("/api/admin/login", json={"email": "root@x.ca", "password": PASSWORD, "code": code()}, headers=H, environ_base={"REMOTE_ADDR": "10.9.9.9"})
    assert r.status_code == 200


def test_import_never_replaces_an_accounts_files(client, adm):
    u = make_user(client)
    store.Repo(u["id"], "priv").commit({"csc258/f26/grades.json": b'{"marks": {"1": 90}}'}, "x", store.Repo(u["id"], "priv").head())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("r-main/csc258/f26/grades.json", '{"marks": {"1": 0}}')
        z.writestr("r-main/csc108/w26/grades.json", "{}")
    r = adm.post("/api/admin/import", data={"user": str(u["id"]), "area": "priv", "zip": (io.BytesIO(buf.getvalue()), "r.zip")},
                 headers=H, content_type="multipart/form-data").get_json()
    assert r["files"] == 1 and r["already"] == 1
    assert store.Repo(u["id"], "priv").read_text("csc258/f26/grades.json")[0] == '{"marks": {"1": 90}}'
    assert any("imported" in m["subject"] for m in mailer.sent)


def test_the_panel_can_have_its_own_address(adm, monkeypatch):
    monkeypatch.setenv("LECTERN_ADMIN_URL", "https://admin.example.org/")
    assert adm.get("/admin").status_code == 404 and adm.get("/api/admin/overview").status_code == 404
    assert adm.get("/admin", base_url="https://admin.example.org").status_code == 200
