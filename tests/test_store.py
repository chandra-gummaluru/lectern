"""Each account's files: the builders' GitHub-style calls, answered from the server, and published pages.

Run with:  python -m pytest
"""
import base64
import json

from conftest import H, make_user
from server import store


def save(client, repo, files, message="Save", parent=None, force=False):
    """A save the way the builders make one: blobs → tree → commit → move the branch."""
    R = f"/api/store/{repo}"
    head = parent or client.get(f"{R}/git/ref/heads/main").get_json()["object"]["sha"]
    entries = []
    for path, text in files.items():
        if text is None:
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue
        b = client.post(f"{R}/git/blobs", json={"content": base64.b64encode(text.encode()).decode(), "encoding": "base64"}, headers=H)
        if b.status_code != 201:
            return b
        b = b.get_json()
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": b["sha"]})
    tree = client.post(f"{R}/git/trees", json={"base_tree": head, "tree": entries}, headers=H)
    if tree.status_code != 201:
        return tree
    tree = tree.get_json()
    commit = client.post(f"{R}/git/commits", json={"message": message, "tree": tree["sha"], "parents": [head]}, headers=H).get_json()
    return client.patch(f"{R}/git/refs/heads/main", json={"sha": commit["sha"], **({"force": True} if force else {})}, headers=H)


def read(client, repo, path):
    r = client.get(f"/api/store/{repo}/contents/{path}?ref=main")
    return base64.b64decode(r.get_json()["content"]).decode() if r.status_code == 200 else None


def test_save_and_read(client, user):
    assert save(client, "priv", {"csc258/f26/grades.json": '{"a": 1}'}).status_code == 200
    assert read(client, "priv", "csc258/f26/grades.json") == '{"a": 1}'
    tree = client.get("/api/store/priv/git/trees/main?recursive=1").get_json()["tree"]
    assert {"csc258", "csc258/f26", "csc258/f26/grades.json"} == {t["path"] for t in tree}
    f = client.get("/api/store/priv/contents/csc258/f26/grades.json").get_json()
    assert f["sha"] == [t for t in tree if t["type"] == "blob"][0]["sha"]


def test_a_save_on_an_old_version_is_refused(client, user):
    head = client.get("/api/store/priv/git/ref/heads/main").get_json()["object"]["sha"]
    assert save(client, "priv", {"a.json": "1"}, parent=head).status_code == 200
    r = save(client, "priv", {"a.json": "2"}, parent=head)                 # another tab, from before
    assert r.status_code == 422 and read(client, "priv", "a.json") == "1"
    assert save(client, "priv", {"a.json": "2"}, parent=head, force=True).status_code == 200


def test_delete_files_and_keep_history(client, user, tmp_path):
    save(client, "priv", {"csc258/f26/grades.json": "v1", "csc258/f26/x.json": "x"})
    save(client, "priv", {"csc258/f26/grades.json": None, "csc258/f26/x.json": None})
    assert read(client, "priv", "csc258/f26/grades.json") is None
    assert client.get("/api/store/priv/git/trees/main").get_json()["tree"] == []      # empty folders go too
    kept = list((tmp_path / "data" / "history").rglob("grades.json"))
    assert kept and kept[0].read_text() == "v1"


def test_accounts_dont_see_each_others_files(client, user):
    save(client, "priv", {"secret.json": "grades"})
    other = client.application.test_client()
    make_user(other, email="ta@x.ca", name="T A", handle="ta", admin=False)
    assert read(other, "priv", "secret.json") is None
    assert other.get("/api/store/priv/git/trees/main").get_json()["tree"] == []


def test_paths_cant_escape(client, user):
    for bad in ("../x", "a/../../x", ".git/config", "a//b", "/etc/passwd", "a\\b", "C:/x"):
        r = client.post("/api/store/priv/git/trees", json={"tree": [{"path": bad, "sha": None}]}, headers=H)
        assert r.status_code == 400, bad
    assert client.get("/api/store/priv/contents/../../secret.key").status_code in (400, 404)
    assert client.get("/api/store/other/git/trees/main").status_code == 404


def test_saves_need_lecterns_header(client, user):
    r = client.post("/api/store/priv/git/blobs", json={"content": "x", "encoding": "utf-8"})
    assert r.status_code == 403


def test_quota(client, user, monkeypatch):
    monkeypatch.setenv("LECTERN_QUOTA_MB", "0.001")   # about 1 KB
    assert save(client, "pub", {"small.txt": "x" * 100}).status_code == 200
    r = client.post("/api/store/pub/git/blobs", json={"content": "x" * 5000, "encoding": "utf-8"}, headers=H)
    assert r.status_code == 413


def test_a_full_account_can_still_delete_and_shrink(client, user, monkeypatch, tmp_path):
    monkeypatch.setenv("LECTERN_QUOTA_MB", "0.002")   # about 2 KB
    assert save(client, "pub", {"a.txt": "x" * 1500}).status_code == 200
    assert save(client, "pub", {"b.txt": "y" * 900}).status_code == 413          # full
    assert save(client, "pub", {"a.txt": "x" * 100}).status_code == 200          # smaller: fine
    assert save(client, "pub", {"a.txt": None}).status_code == 200               # deleting: fine


def test_old_versions_are_pruned_oldest_first(client, user, monkeypatch, tmp_path):
    monkeypatch.setenv("LECTERN_QUOTA_MB", "0.002")
    for k in range(8):
        assert save(client, "pub", {"a.txt": str(k) * 900}).status_code == 200      # each save keeps the last version
    hist = tmp_path / "data" / "history"
    kept = sum(f.stat().st_size for f in hist.rglob("*") if f.is_file())
    assert 0 < kept <= 2.1 * 1024 and any(f.read_text() == "6" * 900 for f in hist.rglob("a.txt"))


def test_copy_an_existing_file_by_its_sha(client, user):
    save(client, "priv", {"a/figures/f.png": "PNG"})
    sha = client.get("/api/store/priv/contents/a/figures/f.png").get_json()["sha"]
    R = "/api/store/priv"
    head = client.get(f"{R}/git/ref/heads/main").get_json()["object"]["sha"]
    t = client.post(f"{R}/git/trees", json={"tree": [{"path": "b/figures/f.png", "sha": sha}]}, headers=H).get_json()
    c = client.post(f"{R}/git/commits", json={"message": "copy", "tree": t["sha"], "parents": [head]}, headers=H).get_json()
    assert client.patch(f"{R}/git/refs/heads/main", json={"sha": c["sha"]}, headers=H).status_code == 200
    assert read(client, "priv", "b/figures/f.png") == "PNG"


def test_last_saved(client, user):
    save(client, "pub", {"csc258/f26/info.html": "<p>hi</p>"})
    c = client.get("/api/store/pub/commits?path=csc258/f26/info.html&sha=main&per_page=1").get_json()
    assert c[0]["commit"]["committer"]["date"].endswith("Z")
    assert client.get("/api/store/pub/commits?path=nope.html").get_json() == []


# ── Published pages ──────────────────────────────────────────────────
def test_course_pages_are_public_and_sandboxed(client, user):
    save(client, "pub", {"csc258/f26/info.html": "<h1>CSC258</h1>", "csc258/f26/notes.pdf": "%PDF"})
    anon = client.application.test_client()
    r = anon.get("/p/chandra/csc258/f26/info.html")
    assert r.status_code == 200 and b"CSC258" in r.data and r.mimetype == "text/html"
    csp = r.headers["Content-Security-Policy"]
    assert csp.startswith("sandbox") and "allow-same-origin" not in csp
    assert anon.get("/p/chandra/csc258/f26/notes.pdf").mimetype == "application/pdf"
    assert anon.get("/p/chandra/nope.html").status_code == 404
    assert anon.get("/p/nobody/csc258/f26/info.html").status_code == 404


def test_private_files_are_never_published(client, user):
    save(client, "priv", {"csc258/f26/grades.json": "{}"})
    assert client.get("/p/chandra/csc258/f26/grades.json").status_code == 404


def test_server_side_write_checks_the_version(client, user):
    r = store.Repo(user["id"], "priv")
    assert r.write_text("x.json", "1", None, "first")
    text, sha = r.read_text("x.json")
    assert not r.write_text("x.json", "2", None, "stale")
    assert r.write_text("x.json", "2", sha, "second") and r.read_text("x.json")[0] == "2"
