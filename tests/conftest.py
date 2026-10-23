"""Shared test setup: every test gets an empty data folder (database, files, server key)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app, auth, accommodations, db, mailer, security  # noqa: E402

H = {"X-Lectern": "1"}


@pytest.fixture(autouse=True)
def fresh_data(tmp_path, monkeypatch):
    monkeypatch.setenv("LECTERN_DATA_DIR", str(tmp_path / "data"))
    for k in ("LECTERN_SECRET_KEY", "LECTERN_APP_URL", "LECTERN_PAGES_URL", "LECTERN_SMTP_HOST", "LECTERN_QUOTA_MB"):
        monkeypatch.delenv(k, raising=False)
    db.reset_for_tests()
    security._key_cache.clear()
    auth.limiter.reset()
    auth.ghosts.reset()
    accommodations.limiter.reset()
    accommodations._books.clear()
    mailer.sent.clear()
    mailer.keep = True
    app.config["TESTING"] = True
    yield
    db.reset_for_tests()


@pytest.fixture()
def client():
    return app.test_client()


PASSWORD = "correct horse battery staple"


def make_user(client, email="chandra@utoronto.ca", name="Chandra Gummaluru", handle="chandra", admin=True, password=PASSWORD):
    """An account, made the way a person makes one: an invitation, then its link. Leaves client signed in."""
    tok = auth.create_invite(email, admin)
    r = client.post("/api/auth/invite/accept", json={"token": tok, "name": name, "handle": handle, "password": password}, headers=H)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["user"]


@pytest.fixture()
def user(client):
    return make_user(client)
