"""Server tests: the page, and the builders split into scoped parts.

Run with:  python -m pytest
"""
import os

import pytest

from server.scope_css import scope_css, split_selectors  # noqa: E402
from server.tools import TOOLS, split_tool  # noqa: E402
from server.paths import TOOLS_DIR  # noqa: E402


def test_index_has_splash_and_app(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Lectern" in html and "University of Toronto" in html
    assert 'id="sp-form"' in html and 'type="password"' in html and 'autocomplete="current-password"' in html
    assert "github" not in html.lower()
    assert 'id="lt-path"' in html
    assert r.headers["Cache-Control"].startswith("no-store")


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
