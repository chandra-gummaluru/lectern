"""Accounts: invitations, signing in and out, two-factor codes, resets, the account and admin API,
and the checks every request gets (HTTPS, cross-site requests, headers).

Run with:  python -m pytest
"""
import re
import time

import pytest

from conftest import H, PASSWORD, make_user
from server import auth, db, mailer, security


def login(client, email="chandra@utoronto.ca", password=PASSWORD, **kw):
    return client.post("/api/auth/login", json={"email": email, "password": password}, headers=H, **kw)


def secret_of(email="chandra@utoronto.ca"):
    u = db.one("SELECT totp_secret FROM users WHERE email = ?", (email,))
    return security.decrypt(u["totp_secret"])


def turn_on_2fa(client):
    s = client.post("/api/auth/2fa/setup", json={"password": PASSWORD}, headers=H).get_json()
    secret = s["secret"].replace(" ", "")
    r = client.post("/api/auth/2fa/enable", json={"code": security.totp_now(secret)}, headers=H)
    assert r.status_code == 200, r.get_json()
    return secret, r.get_json()["codes"]


def later_code(secret, steps=1):
    return security.totp_now(secret, time.time() + steps * security.STEP)


# ── Passwords are never kept ─────────────────────────────────────────
def test_password_is_hashed_with_argon2id(client, user):
    row = db.one("SELECT pw_hash FROM users WHERE id = ?", (user["id"],))
    assert row["pw_hash"].startswith("$argon2id$") and PASSWORD not in row["pw_hash"]


def test_sessions_store_only_a_hash_of_the_cookie(client, user):
    cookie = client.get_cookie("lectern_session")
    assert cookie and cookie.http_only and cookie.same_site == "Lax"
    rows = db.all_("SELECT id_hash FROM sessions")
    assert rows and all(r["id_hash"] != cookie.value and len(r["id_hash"]) == 64 for r in rows)


@pytest.mark.parametrize("pw,why", [("short", "12"), ("password1234", "guess"), ("aaaaaaaaaaaaaaa", "guess"), ("chandra-rocks-2026", "email")])
def test_weak_passwords_are_refused(client, pw, why):
    tok = auth.create_invite("chandra@utoronto.ca")
    r = client.post("/api/auth/invite/accept", json={"token": tok, "name": "C G", "handle": "chandra", "password": pw}, headers=H)
    assert r.status_code == 400 and why in r.get_json()["error"]


# ── Invitations ──────────────────────────────────────────────────────
def test_invite_makes_an_account_and_signs_in(client, user):
    assert user["email"] == "chandra@utoronto.ca" and user["handle"] == "chandra" and user["admin"]
    me = client.get("/api/auth/me").get_json()
    assert me["signedIn"] and me["user"]["site"] == "http://localhost/p/chandra/"


def test_an_invitation_works_once(client):
    tok = auth.create_invite("a@x.ca")
    ok = {"token": tok, "name": "A B", "handle": "ab", "password": PASSWORD}
    assert client.post("/api/auth/invite/accept", json=ok, headers=H).status_code == 200
    again = client.post("/api/auth/invite/accept", json={**ok, "handle": "ab2"}, headers=H)
    assert again.status_code == 410


def test_invitations_expire(client):
    tok = auth.create_invite("a@x.ca")
    db.run("UPDATE invites SET expires = ?", (time.time() - 1,))
    assert client.post("/api/auth/invite/check", json={"token": tok}, headers=H).status_code == 410


def test_invite_tokens_are_stored_hashed(client):
    tok = auth.create_invite("a@x.ca")
    assert not db.one("SELECT 1 FROM invites WHERE token_hash = ?", (tok,))


def test_handles_must_be_unique_and_tidy(client, user):
    for bad in ("chandra", "API", "-x", "a b", "admin", "x"):
        tok = auth.create_invite(f"n{abs(hash(bad))}@x.ca")
        r = client.post("/api/auth/invite/accept", json={"token": tok, "name": "N", "handle": bad, "password": PASSWORD}, headers=H)
        assert r.status_code == 400, bad


def test_no_public_sign_up(client):
    r = client.post("/api/auth/invite/accept", json={"token": "made-up", "name": "N", "handle": "nn", "password": PASSWORD}, headers=H)
    assert r.status_code == 410


# ── Signing in ───────────────────────────────────────────────────────
def test_sign_in_and_out(client, user):
    client.post("/api/auth/logout", headers=H)
    assert client.get("/api/auth/me").get_json()["signedIn"] is False
    r = login(client, email="  Chandra@UToronto.ca ")
    assert r.status_code == 200 and r.get_json()["user"]["email"] == "chandra@utoronto.ca"
    assert client.get("/api/auth/me").get_json()["signedIn"]


def test_sign_out_ends_the_session_on_the_server(client, user):
    cookie = client.get_cookie("lectern_session").value
    client.post("/api/auth/logout", headers=H)
    client.set_cookie("lectern_session", cookie)          # an old copy of the cookie
    assert client.get("/api/auth/me").get_json()["signedIn"] is False


def test_signing_in_makes_a_new_session(client, user):
    before = client.get_cookie("lectern_session").value
    login(client)
    assert client.get_cookie("lectern_session").value != before
    assert len(db.all_("SELECT 1 FROM sessions")) == 1    # the old one went


def test_wrong_email_and_wrong_password_look_the_same(client, user):
    client.post("/api/auth/logout", headers=H)
    a, b = login(client, password="wrong password!!"), login(client, email="nobody@x.ca")
    assert a.status_code == b.status_code == 401 and a.get_json() == b.get_json()


def test_account_waits_after_five_wrong_passwords(client, user):
    stranger = client.application.test_client()            # a browser that has never signed in here
    for _ in range(5):
        assert login(stranger, password="wrong password!!").status_code == 401
    assert login(stranger).status_code == 429              # even the right password waits now
    # ...but not the owner, on a browser they've signed in from before: guessing can't lock them out
    client.post("/api/auth/logout", headers=H)
    assert login(client).status_code == 200
    assert db.one("SELECT failed FROM users")["failed"] == 0


def test_no_account_waits_the_same(client, user):
    """The wait doesn't reveal which emails have accounts."""
    a, b = client.application.test_client(), client.application.test_client()
    real = [login(a, password="wrong password!!").status_code for _ in range(6)]
    fake = [login(b, email="nobody@x.ca", password="wrong password!!").status_code for _ in range(6)]
    assert real == fake == [401] * 5 + [429]


def test_a_new_password_ends_device_trust(client, user):
    client.post("/api/auth/password", json={"current": PASSWORD, "password": "a whole new passphrase"}, headers=H)
    from server.auth import trusted_device
    with client.application.test_request_context(headers={"Cookie": f"lectern_dev={client.get_cookie('lectern_dev').value}"}):
        assert not trusted_device(db.one("SELECT * FROM users"))


def test_sign_in_is_rate_limited_per_email(client, user):
    client.post("/api/auth/logout", headers=H)
    codes = [login(client, email="someone@x.ca").status_code for _ in range(12)]
    assert codes[-1] == 429


def test_disabled_accounts_cant_sign_in(client, user):
    db.run("UPDATE users SET disabled = 1")
    assert client.get("/api/auth/me").get_json()["signedIn"] is False   # and its sessions end
    assert login(client).status_code == 403


def test_sessions_end_when_idle(client, user, monkeypatch):
    db.run("UPDATE sessions SET last_seen = ?", (time.time() - 13 * 3600,))
    assert client.get("/api/auth/me").get_json()["signedIn"] is False


def test_sessions_have_an_absolute_end(client, user):
    db.run("UPDATE sessions SET expires = ?", (time.time() - 1,))
    assert client.get("/api/auth/me").get_json()["signedIn"] is False


# ── Two-factor codes ─────────────────────────────────────────────────
def test_totp_matches_rfc6238():
    # RFC 6238 appendix B (SHA-1), secret "12345678901234567890", 6 digits.
    import base64
    s = base64.b32encode(b"12345678901234567890").decode()
    assert security.totp_now(s, 59) == "287082" and security.totp_now(s, 1111111109) == "081804"


def test_two_factor_sign_in(client, user):
    secret, codes = turn_on_2fa(client)
    assert len(codes) == 10 and client.get("/api/auth/me").get_json()["user"]["twoFactor"]
    client.post("/api/auth/logout", headers=H)
    r = login(client)
    assert r.get_json() == {"twoFactor": True}
    assert client.get("/api/auth/me").get_json()["signedIn"] is False      # not yet
    assert client.post("/api/auth/login/2fa", json={"code": "000000"}, headers=H).status_code == 401
    r = client.post("/api/auth/login/2fa", json={"code": later_code(secret)}, headers=H)
    assert r.status_code == 200 and client.get("/api/auth/me").get_json()["signedIn"]


def test_a_code_works_only_once(client, user):
    secret, _ = turn_on_2fa(client)
    client.post("/api/auth/logout", headers=H)
    code = later_code(secret)
    login(client)
    assert client.post("/api/auth/login/2fa", json={"code": code}, headers=H).status_code == 200
    client.post("/api/auth/logout", headers=H)
    login(client)
    assert client.post("/api/auth/login/2fa", json={"code": code}, headers=H).status_code == 401


def test_second_step_needs_the_first(client, user):
    secret, _ = turn_on_2fa(client)
    client.post("/api/auth/logout", headers=H)
    r = client.post("/api/auth/login/2fa", json={"code": later_code(secret)}, headers=H)
    assert r.status_code == 401 and r.get_json()["code"] == "expired"


def test_recovery_codes_work_once(client, user):
    _, codes = turn_on_2fa(client)
    client.post("/api/auth/logout", headers=H)
    login(client)
    assert client.post("/api/auth/login/2fa", json={"recovery": codes[0].upper()}, headers=H).status_code == 200
    assert client.get("/api/auth/me").get_json()["user"]["recoveryLeft"] == 9
    client.post("/api/auth/logout", headers=H)
    login(client)
    assert client.post("/api/auth/login/2fa", json={"recovery": codes[0]}, headers=H).status_code == 401


def test_two_factor_secret_is_encrypted_at_rest(client, user):
    secret, codes = turn_on_2fa(client)
    row = db.one("SELECT totp_secret FROM users")
    assert secret not in row["totp_secret"]
    assert not db.one("SELECT 1 FROM recovery_codes WHERE code_hash = ?", (codes[0],))


def test_enabling_needs_a_working_code(client, user):
    client.post("/api/auth/2fa/setup", json={"password": PASSWORD}, headers=H)
    assert client.post("/api/auth/2fa/enable", json={"code": "123456"}, headers=H).status_code == 400
    assert client.get("/api/auth/me").get_json()["user"]["twoFactor"] is False


def test_an_app_cant_be_swapped_without_a_code(client, user):
    turn_on_2fa(client)
    r = client.post("/api/auth/2fa/setup", json={"password": PASSWORD}, headers=H)
    assert r.status_code == 400
    assert client.post("/api/auth/recovery", json={"password": PASSWORD}, headers=H).status_code == 400


def test_wrong_passwords_on_changes_count_too(client, user):
    for _ in range(5):
        client.post("/api/auth/2fa/setup", json={"password": "nope"}, headers=H)
    assert db.one("SELECT failed FROM users")["failed"] == 5
    assert client.post("/api/auth/2fa/setup", json={"password": PASSWORD}, headers=H).status_code == 429


def test_setup_needs_the_password(client, user):
    assert client.post("/api/auth/2fa/setup", json={"password": "nope"}, headers=H).status_code == 403


def test_setup_gives_a_qr_code(client, user):
    s = client.post("/api/auth/2fa/setup", json={"password": PASSWORD}, headers=H).get_json()
    assert s["qr"].lstrip().startswith("<svg") and s["uri"].startswith("otpauth://totp/Lectern:")


def test_turning_off_needs_password_and_code(client, user):
    secret, _ = turn_on_2fa(client)
    assert client.post("/api/auth/2fa/disable", json={"password": PASSWORD, "code": "000000"}, headers=H).status_code == 400
    r = client.post("/api/auth/2fa/disable", json={"password": PASSWORD, "code": later_code(secret)}, headers=H)
    assert r.status_code == 200 and r.get_json()["user"]["twoFactor"] is False
    assert any("two-factor sign-in is off" in m["subject"] for m in mailer.sent)


def test_too_many_wrong_codes_end_the_attempt(client, user):
    turn_on_2fa(client)
    client.post("/api/auth/logout", headers=H)
    login(client)
    for _ in range(4):
        assert client.post("/api/auth/login/2fa", json={"code": "000000"}, headers=H).get_json()["code"] == "bad-code"
    assert client.post("/api/auth/login/2fa", json={"code": "000000"}, headers=H).get_json()["code"] == "expired"


# ── Forgotten passwords ──────────────────────────────────────────────
def reset_token():
    m = re.search(r"#reset=([\w-]+)", mailer.sent[-1]["body"])
    return m.group(1)


def test_forgot_says_the_same_either_way(client, user):
    a = client.post("/api/auth/forgot", json={"email": "chandra@utoronto.ca"}, headers=H).get_json()
    b = client.post("/api/auth/forgot", json={"email": "nobody@x.ca"}, headers=H).get_json()
    assert a == b
    assert len([m for m in mailer.sent if "new password" in m["subject"]]) == 1


def test_reset_password(client, user):
    other = client.application.test_client()
    login(other)
    client.post("/api/auth/forgot", json={"email": "chandra@utoronto.ca"}, headers=H)
    tok = reset_token()
    assert client.post("/api/auth/reset/check", json={"token": tok}, headers=H).get_json()["twoFactor"] is False
    assert client.post("/api/auth/reset", json={"token": tok, "password": "a whole new passphrase"}, headers=H).status_code == 200
    assert client.get("/api/auth/me").get_json()["signedIn"] is False      # every session ended
    assert other.get("/api/auth/me").get_json()["signedIn"] is False
    assert login(client).status_code == 401
    assert login(client, password="a whole new passphrase").status_code == 200
    assert client.post("/api/auth/reset", json={"token": tok, "password": "yet another passphrase"}, headers=H).status_code == 410


def test_reset_with_two_factor_needs_a_code(client, user):
    secret, _ = turn_on_2fa(client)
    client.post("/api/auth/forgot", json={"email": "chandra@utoronto.ca"}, headers=H)
    tok = reset_token()
    assert client.post("/api/auth/reset/check", json={"token": tok}, headers=H).get_json()["twoFactor"] is True
    assert client.post("/api/auth/reset", json={"token": tok, "password": "a whole new passphrase"}, headers=H).status_code == 401
    assert client.post("/api/auth/reset", json={"token": tok, "password": "a whole new passphrase", "code": later_code(secret)}, headers=H).status_code == 200


def test_reset_link_points_only_at_lecterns_own_address(client, user):
    """Someone asking for a reset with a made-up Host mustn't get a link to their own site."""
    r = client.post("/api/auth/forgot", json={"email": "chandra@utoronto.ca"}, headers=H, base_url="https://evil.example")
    assert r.status_code == 200 and not [m for m in mailer.sent if "new password" in m["subject"]]   # not sent at all
    import os
    os.environ["LECTERN_APP_URL"] = "https://lectern.changapp.net"
    try:
        client.post("/api/auth/forgot", json={"email": "chandra@utoronto.ca"}, headers=H, base_url="https://evil.example")
        assert "https://lectern.changapp.net/#reset=" in mailer.sent[-1]["body"] and "evil" not in mailer.sent[-1]["body"]
    finally:
        del os.environ["LECTERN_APP_URL"]


def test_reset_links_expire(client, user):
    client.post("/api/auth/forgot", json={"email": "chandra@utoronto.ca"}, headers=H)
    db.run("UPDATE resets SET expires = ?", (time.time() - 1,))
    assert client.post("/api/auth/reset", json={"token": reset_token(), "password": "a whole new passphrase"}, headers=H).status_code == 410


# ── Your account ─────────────────────────────────────────────────────
def test_change_password_signs_out_other_sessions(client, user):
    other = client.application.test_client()
    login(other)
    assert client.post("/api/auth/password", json={"current": "wrong", "password": "a whole new passphrase"}, headers=H).status_code == 403
    assert client.post("/api/auth/password", json={"current": PASSWORD, "password": "a whole new passphrase"}, headers=H).status_code == 200
    assert client.get("/api/auth/me").get_json()["signedIn"]
    assert other.get("/api/auth/me").get_json()["signedIn"] is False


def test_sessions_list_and_revoke(client, user):
    other = client.application.test_client()
    login(other)
    s = client.get("/api/auth/sessions").get_json()["sessions"]
    assert len(s) == 2 and sum(x["current"] for x in s) == 1
    client.post("/api/auth/sessions/revoke", json={"id": "others"}, headers=H)
    assert other.get("/api/auth/me").get_json()["signedIn"] is False
    assert client.get("/api/auth/me").get_json()["signedIn"]


def test_signed_out_requests_are_refused(client):
    assert client.get("/api/auth/sessions").status_code == 401
    assert client.get("/api/store/priv/git/trees/main").status_code == 401


# ── Admin ────────────────────────────────────────────────────────────
def test_admin_invites_and_manages(client, user):
    r = client.post("/api/admin/invites", json={"email": "ta@utoronto.ca"}, headers=H).get_json()
    assert r["link"].startswith("http://localhost/#invite=") and not r["emailed"]
    assert client.get("/api/admin/users").get_json()["invites"][0]["email"] == "ta@utoronto.ca"
    ta = client.application.test_client()
    tok = r["link"].split("#invite=")[1]
    assert ta.post("/api/auth/invite/accept", json={"token": tok, "name": "T A", "handle": "ta", "password": PASSWORD}, headers=H).status_code == 200
    assert ta.get("/api/admin/users").status_code == 403                     # not an admin
    uid = ta.get("/api/auth/me").get_json()["user"]["id"]
    assert client.post(f"/api/admin/users/{uid}", json={"action": "disable"}, headers=H).status_code == 403   # needs your password
    assert client.post(f"/api/admin/users/{uid}", json={"action": "disable", "password": PASSWORD}, headers=H).status_code == 200
    assert ta.get("/api/auth/me").get_json()["signedIn"] is False


def test_admin_cant_disable_themselves(client, user):
    for action in ("disable", "reset-2fa", "remove-admin"):
        r = client.post(f"/api/admin/users/{user['id']}", json={"action": action, "password": PASSWORD}, headers=H)
        assert r.status_code == 400, action


def test_inviting_an_admin_needs_your_password(client, user):
    assert client.post("/api/admin/invites", json={"email": "x@x.ca", "admin": True}, headers=H).status_code == 403
    assert client.post("/api/admin/invites", json={"email": "x@x.ca", "admin": True, "password": PASSWORD}, headers=H).status_code == 200


def test_big_bodies_are_refused_except_uploads(client, user):
    r = client.post("/api/auth/forgot", data=b'{"email": "' + b"a" * 400000 + b'"}', headers={**H, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_cli_invite(capsys):
    from server import cli
    cli.main(["invite", "first@x.ca", "--admin"])
    out = capsys.readouterr().out
    assert "#invite=" in out and db.one("SELECT is_admin FROM invites")["is_admin"] == 1


# ── Every request ────────────────────────────────────────────────────
def test_changes_need_lecterns_header(client, user):
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/login", json={"email": "a@x.ca", "password": "x"}).status_code == 403


def test_changes_from_another_site_are_refused(client, user):
    r = client.post("/api/auth/password", json={}, headers={**H, "Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/auth/password", json={}, headers={**H, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_plain_http_is_refused_away_from_localhost(client):
    r = client.post("/api/auth/login", json={"email": "a@x.ca", "password": PASSWORD}, headers=H, base_url="http://lectern.example.org")
    assert r.status_code == 403
    r = client.get("/", base_url="http://lectern.example.org")
    assert r.status_code == 301 and r.headers["Location"].startswith("https://")


def test_https_sets_a_host_only_secure_cookie_and_hsts(client):
    tok = auth.create_invite("s@x.ca")
    r = client.post("/api/auth/invite/accept", json={"token": tok, "name": "S", "handle": "ss", "password": PASSWORD}, headers=H, base_url="https://lectern.example.org")
    c = r.headers["Set-Cookie"]
    assert c.startswith("__Host-lectern=") and "Secure" in c and "HttpOnly" in c and "Path=/" in c and "Domain" not in c
    assert "max-age=31536000" in r.headers["Strict-Transport-Security"]


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/auth/me").headers["Cache-Control"] == "no-store"


def test_cli_import(client, user, tmp_path, capsys):
    from server import cli, store
    pub, priv = tmp_path / "courses", tmp_path / "courses-private"
    (pub / "csc258" / "f26").mkdir(parents=True); (pub / ".git").mkdir()
    (pub / "csc258" / "f26" / "info.html").write_text("<h1>hi</h1>"); (pub / ".git" / "config").write_text("x")
    (priv / "csc258" / "f26").mkdir(parents=True); (priv / "csc258" / "f26" / "grades.json").write_text("{}")
    cli.main(["import", "chandra@utoronto.ca", str(pub), str(priv)])
    assert store.Repo(user["id"], "pub").read_text("csc258/f26/info.html")[0] == "<h1>hi</h1>"
    assert [e["path"] for e in store.Repo(user["id"], "pub").walk() if e["type"] == "blob"] == ["csc258/f26/info.html"]
    assert store.Repo(user["id"], "priv").read_text("csc258/f26/grades.json")[0] == "{}"
