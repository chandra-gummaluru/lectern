"""Server tests: pages, sign-in routes, and the builders split into scoped parts.

Run with:  python -m pytest
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app  # noqa: E402
from server.scope_css import scope_css, split_selectors  # noqa: E402
from server.tools import TOOLS, split_tool  # noqa: E402
from server.paths import TOOLS_DIR  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    for k in ("LECTERN_GH_CLIENT_ID", "LECTERN_GH_CLIENT_SECRET", "LECTERN_APP_URL"):
        monkeypatch.delenv(k, raising=False)
    app.config["TESTING"] = True
    return app.test_client()


def test_index_has_splash_and_app(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Lectern" in html and "University of Toronto" in html
    assert 'id="splash-signin"' in html and 'id="splash-folder"' in html
    assert 'id="lt-path"' in html
    assert r.headers["Cache-Control"].startswith("no-store")


def test_config_without_settings(client):
    d = client.get("/api/github/config").get_json()
    assert d["configured"] is False
    assert d["redirect_uri"] == "http://localhost/api/github/callback"


def test_config_with_settings(client, monkeypatch):
    monkeypatch.setenv("LECTERN_GH_CLIENT_ID", "Iv1.abc")
    monkeypatch.setenv("LECTERN_GH_CLIENT_SECRET", "s")
    monkeypatch.setenv("LECTERN_APP_URL", "https://lectern.changapp.net")
    d = client.get("/api/github/config").get_json()
    assert d["configured"] is True and d["client_id"] == "Iv1.abc"
    assert d["redirect_uri"] == "https://lectern.changapp.net/api/github/callback"


def test_callback_cancelled_returns_error_in_fragment(client):
    r = client.get("/api/github/callback?error=access_denied&state=xyz")
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert "#" in loc and "gh_error=" in loc and "state=xyz" in loc
    assert "?" not in loc.split("#")[0][len("http://localhost/"):]   # nothing in the query string


def test_callback_swaps_code_for_tokens(client, monkeypatch):
    monkeypatch.setenv("LECTERN_GH_CLIENT_ID", "id")
    monkeypatch.setenv("LECTERN_GH_CLIENT_SECRET", "secret")
    from server import login
    monkeypatch.setattr(login, "_exchange", lambda f: {"access_token": "ghu_1", "refresh_token": "ghr_1", "expires_in": 28800})
    r = client.get("/api/github/callback?code=abc&state=s1")
    loc = r.headers["Location"]
    assert "gh_access_token=ghu_1" in loc.split("#", 1)[1]
    assert "gh_refresh_token=ghr_1" in loc and "state=s1" in loc


def test_refresh_needs_a_token(client):
    assert client.post("/api/github/refresh", json={}).status_code == 400


def test_refresh(client, monkeypatch):
    monkeypatch.setenv("LECTERN_GH_CLIENT_ID", "id")
    monkeypatch.setenv("LECTERN_GH_CLIENT_SECRET", "secret")
    from server import login
    monkeypatch.setattr(login, "_exchange", lambda f: {"access_token": "ghu_2", "refresh_token": "ghr_2", "expires_in": 28800} if f.get("refresh_token") == "ghr_1" else {"error_description": "bad"})
    assert client.post("/api/github/refresh", json={"refresh_token": "ghr_1"}).get_json()["access_token"] == "ghu_2"
    assert client.post("/api/github/refresh", json={"refresh_token": "nope"}).status_code == 401


# ── Scoping ──────────────────────────────────────────────────────────

S = '[data-lt-tool="t"]'


def test_scope_roots_become_the_scope_element():
    out = scope_css(':root { --a: 1 } html, body { margin: 0 } body.dock-open .shell { x: y }', S)
    assert f'{S} {{ --a: 1 }}' in out
    assert f'{S}, {S} {{ margin: 0 }}' in out
    assert f'{S}.dock-open .shell' in out


def test_scope_theme_selectors_and_media():
    css = '@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) body.on-settings #stage { a: b } }'
    out = scope_css(css, S)
    assert out.startswith('@media (prefers-color-scheme: dark) {')
    assert f'{S}:not([data-theme="light"]).on-settings #stage' in out


def test_scope_keeps_strings_comments_and_nested_commas():
    out = scope_css('/* a { } */ .k { content: "{,}" } .a, .b:not(.c, .d) { z: 1 }', S)
    assert f'{S} .k {{ content: "{{,}}" }}' in out
    assert f'{S} .a, {S} .b:not(.c, .d)' in out
    assert '/*' not in out


def test_split_selectors():
    assert split_selectors('a, b:not(c, d), [x="1,2"]') == ['a', 'b:not(c, d)', '[x="1,2"]']


@pytest.mark.parametrize("name", list(TOOLS))
def test_each_builder_splits(name):
    with open(os.path.join(TOOLS_DIR, TOOLS[name]["file"]), encoding="utf-8") as f:
        parts = split_tool(f.read(), name)
    assert 'id="stage"' in parts["markup"] and 'id="save"' in parts["markup"]
    assert "<style" not in parts["markup"] and "<script" not in parts["markup"]
    assert "lectern.register(" in parts["script"]           # each builder has its Lectern section
    # Every rule is scoped: no selector starts outside the builder's element.
    for line in parts["css"].splitlines():
        if line.endswith("{") or "{" not in line or line.startswith("@"):
            continue
        sel = line.split("{", 1)[0]
        for s in split_selectors(sel):
            assert s.startswith(f'[data-lt-tool="{name}"]'), (name, s)


@pytest.mark.parametrize("name", list(TOOLS))
def test_builder_routes(client, name):
    meta = client.get(f"/tools/{name}.json").get_json()
    assert meta["name"] == name and meta["markup"]
    js = client.get(f"/tools/{name}.js").get_data(as_text=True)
    assert js.startswith(f'Lectern.define("{name}", function (document, window, fetch) {{')
    assert client.get(f"/tools/{name}.css").mimetype == "text/css"
    assert client.get(f"/tools/{name}.html").status_code == 200


def test_unknown_builder(client):
    assert client.get("/tools/nope.json").status_code == 404
