"""Teaching teams: instructors and TAs on someone else's course offering, enforced by the server."""
import base64
import json

import pytest

from conftest import H, PASSWORD, make_user
from server import app, auth, db, mailer, store
from test_store import save, read

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC258"}, "evals": [{"id": "mt", "name": "Midterm", "weight": 30}],
        "students": [{"num": "1001", "first": "Maya", "last": "Castillo"}], "marks": {}, "overrides": {}}


@pytest.fixture()
def course(client, user):
    """chandra owns csc258/f26 (and csc108/w26, not shared); a gradebook, an exam, requests, a course page."""
    r = store.Repo(user["id"], "priv")
    r.commit({"csc258/f26/grades.json": json.dumps(BOOK).encode(), "csc258/f26/midterm/exam.json": b"{}",
              "csc258/f26/accommodations.json": b'{"requests": []}', "csc108/w26/grades.json": b"{\"secret\": 108}"}, "seed", r.head())
    p = store.Repo(user["id"], "pub")
    p.commit({"csc258/f26/info.html": b"<h1>258</h1>"}, "seed", p.head())
    return user


def member(email, handle):
    c = app.test_client()
    u = make_user(c, email=email, name=handle.upper(), handle=handle)
    return c, u


def add(client, email, role, off="csc258/f26", who=None):
    """Ask email to join; when who (their signed-in client) is given, they accept the link."""
    r = client.post(f"/api/teams/chandra/{off}/add", json={"email": email, "role": role}, headers=H)
    if who is not None and r.status_code == 200:
        tok = r.get_json()["link"].split("#join=")[1]
        j = who.post("/api/teams/join", json={"token": tok}, headers=H)
        assert j.status_code == 200, j.get_json()
    return r


def book_with(c, area, path, change):
    b = json.loads(read(c, area, path))
    change(b)
    return json.dumps(b)


def test_add_existing_account_who_accepts(client, course):
    ta, tu = member("ta@x.ca", "ta")
    r = client.post("/api/teams/chandra/csc258/f26/add", json={"email": "ta@x.ca", "role": "ta"}, headers=H)
    assert r.status_code == 200 and "#join=" in r.get_json()["link"]
    assert ta.get("/api/teams/mine").get_json()["shared"] == []                 # not until they accept
    assert client.get("/api/teams/chandra/csc258/f26").get_json()["invites"][0]["email"] == "ta@x.ca"
    tok = r.get_json()["link"].split("#join=")[1]
    info = ta.post("/api/teams/join/check", json={"token": tok}, headers=H).get_json()
    assert "hasAccount" not in info and info["offering"] == "csc258/f26" and info["role"] == "ta"
    assert ta.post("/api/teams/join", json={"token": tok}, headers=H).status_code == 200
    assert ta.get("/api/teams/mine").get_json()["shared"] == [{"owner": "chandra", "ownerName": "Chandra Gummaluru", "offering": "csc258/f26", "role": "ta"}]
    assert ta.post("/api/teams/join", json={"token": tok}, headers=H).status_code == 410   # once


def test_join_needs_the_invited_email(client, course):
    other, _ = member("other@x.ca", "other")
    r = add(client, "ta@x.ca", "ta").get_json()
    j = other.post("/api/teams/join", json={"token": r["link"].split("#join=")[1]}, headers=H)
    assert j.status_code == 403 and "ta@x.ca" in j.get_json()["error"]


def test_invitation_makes_an_account_on_the_team(client, course):
    tok = add(client, "new@x.ca", "instructor").get_json()["link"].split("#join=")[1]
    c = app.test_client()
    info = c.post("/api/teams/join/check", json={"token": tok}, headers=H).get_json()
    assert info["handle"] == "new" and info["canCreate"]
    d = c.post("/api/teams/join/create", json={"token": tok, "name": "New Person", "handle": "newp", "password": PASSWORD}, headers=H).get_json()
    assert d["team"] == {"owner": "chandra", "offering": "csc258/f26"}
    assert c.get("/api/teams/mine").get_json()["shared"][0]["role"] == "instructor"


def test_the_answer_doesnt_reveal_accounts(client, course):
    member("ta@x.ca", "ta")
    a = client.post("/api/teams/chandra/csc258/f26/add", json={"email": "ta@x.ca", "role": "ta"}, headers=H).get_json()
    b = client.post("/api/teams/chandra/csc258/f26/add", json={"email": "nobody@x.ca", "role": "ta"}, headers=H).get_json()
    assert set(a) == set(b) == {"ok", "emailed", "link"}


def test_no_invitations_for_offerings_that_dont_exist(client, course):
    s, _ = member("s@x.ca", "someone")
    r = s.post("/api/teams/someone/zzz/q99/add", json={"email": "stranger@evil.example", "role": "instructor"}, headers=H)
    assert r.status_code == 409


def test_a_removed_instructors_invitations_stop_working(client, course):
    ins, iu = member("ins@x.ca", "ins")
    add(client, "ins@x.ca", "instructor", who=ins)
    tok = add(ins, "alt@x.ca", "instructor").get_json()["link"].split("#join=")[1]
    client.post("/api/teams/chandra/csc258/f26/remove", json={"user": iu["id"]}, headers=H)
    c = app.test_client()
    assert c.post("/api/teams/join/check", json={"token": tok}, headers=H).status_code == 410
    assert c.post("/api/teams/join/create", json={"token": tok, "name": "Alt", "handle": "alt", "password": PASSWORD}, headers=H).status_code == 410


def test_team_invitations_leave_account_invitations_alone(client, course):
    tok = auth.create_invite("boss@x.ca", True)
    add(client, "boss@x.ca", "ta")
    assert client.application.test_client().post("/api/auth/invite/check", json={"token": tok}, headers=H).status_code == 200


def test_a_tas_marks_are_only_marks(client, course):
    ta, _ = member("ta@x.ca", "ta")
    add(client, "ta@x.ca", "ta", who=ta)
    def evil(b):
        b["marks"] = {"1001": {"mt": {"pts": 20, "status": 'x"><img src=https://evil.example/?', "note": "<b>"}, "zz": {"pts": 1}},
                      "9999": {"mt": {"pts": 5}}}
    assert save(ta, "chandra.priv", {"csc258/f26/grades.json": book_with(ta, "chandra.priv", "csc258/f26/grades.json", evil)}).status_code == 200
    assert json.loads(read(client, "priv", "csc258/f26/grades.json"))["marks"] == {"1001": {"mt": {"pts": 20}}}


def test_a_ta_cant_upload_into_the_public_files(client, course):
    ta, _ = member("ta@x.ca", "ta")
    add(client, "ta@x.ca", "ta", who=ta)
    assert ta.post("/api/store/chandra.pub/git/blobs", json={"content": "x", "encoding": "utf-8"}, headers=H).status_code == 403
    big = "x" * (5 * 1024 * 1024)
    assert ta.post("/api/store/chandra.priv/git/blobs", json={"content": big, "encoding": "utf-8"}, headers=H).status_code in (403, 413)


def test_ta_sees_only_that_offering(client, course):
    ta, _ = member("ta@x.ca", "ta")
    add(client, "ta@x.ca", "ta", who=ta)
    paths = {e["path"] for e in ta.get("/api/store/chandra.priv/git/trees/main").get_json()["tree"]}
    assert "csc258/f26/grades.json" in paths and "csc258/f26/midterm/exam.json" in paths
    assert not any(p.startswith("csc108") for p in paths)
    assert "csc258/f26/accommodations.json" not in paths            # students' requests: instructors only
    assert read(ta, "chandra.priv", "csc108/w26/grades.json") is None
    assert read(ta, "chandra.priv", "csc258/f26/accommodations.json") is None
    assert read(ta, "chandra.pub", "csc258/f26/info.html") == "<h1>258</h1>"


def test_ta_can_enter_marks_only(client, course):
    ta, _ = member("ta@x.ca", "ta")
    add(client, "ta@x.ca", "ta", who=ta)
    marks = book_with(ta, "chandra.priv", "csc258/f26/grades.json", lambda b: b["marks"].update({"1001": {"mt": {"pts": 27}}}))
    assert save(ta, "chandra.priv", {"csc258/f26/grades.json": marks}).status_code == 200
    assert json.loads(read(client, "priv", "csc258/f26/grades.json"))["marks"]["1001"]["mt"]["pts"] == 27
    # Anything else in a TA's gradebook is left as it was: only the marks are taken.
    sneaky = book_with(ta, "chandra.priv", "csc258/f26/grades.json", lambda b: (b["evals"][0].update(weight=50), b["marks"].update({"1001": {"mt": {"pts": 30}}})))
    assert save(ta, "chandra.priv", {"csc258/f26/grades.json": sneaky}).status_code == 200
    saved = json.loads(read(client, "priv", "csc258/f26/grades.json"))
    assert saved["evals"][0]["weight"] == 30 and saved["marks"]["1001"]["mt"]["pts"] == 30
    assert save(ta, "chandra.priv", {"csc258/f26/grades.json": "not json"}).status_code == 403
    for path, text in (("csc258/f26/midterm/exam.json", "{\"x\": 1}"), ("csc258/f26/new.json", "{}"), ("csc258/f26/grades.json", None)):
        assert save(ta, "chandra.priv", {path: text}).status_code == 403, path
    assert save(ta, "chandra.pub", {"csc258/f26/info.html": "<h1>hacked</h1>"}).status_code == 403
    assert save(ta, "chandra.priv", {"csc108/w26/grades.json": "{}"}).status_code == 403


def test_instructor_can_do_everything_in_the_offering(client, course):
    ins, _ = member("ins@x.ca", "ins")
    add(client, "ins@x.ca", "instructor", who=ins)
    assert save(ins, "chandra.pub", {"csc258/f26/info.html": "<h1>new</h1>"}).status_code == 200
    assert save(ins, "chandra.priv", {"csc258/f26/midterm/exam.json": "{\"v\": 2}"}).status_code == 200
    assert read(ins, "chandra.priv", "csc258/f26/accommodations.json") is not None
    assert save(ins, "chandra.priv", {"csc108/w26/grades.json": "{}"}).status_code == 403   # not another offering
    assert client.get("/p/chandra/csc258/f26/info.html").data == b"<h1>new</h1>"


def test_a_copy_by_sha_cant_reach_other_offerings(client, course):
    ins, _ = member("ins@x.ca", "ins")
    add(client, "ins@x.ca", "instructor", who=ins)
    sha = client.get("/api/store/priv/contents/csc108/w26/grades.json").get_json()["sha"]
    R = "/api/store/chandra.priv"
    head = ins.get(f"{R}/git/ref/heads/main").get_json()["object"]["sha"]
    t = ins.post(f"{R}/git/trees", json={"tree": [{"path": "csc258/f26/stolen.json", "sha": sha}]}, headers=H).get_json()
    c = ins.post(f"{R}/git/commits", json={"message": "x", "tree": t["sha"], "parents": [head]}, headers=H).get_json()
    assert ins.patch(f"{R}/git/refs/heads/main", json={"sha": c["sha"]}, headers=H).status_code == 422


def test_strangers_see_nothing(client, course):
    s, _ = member("s@x.ca", "stranger")
    assert s.get("/api/store/chandra.priv/git/trees/main").status_code == 404
    assert s.get("/api/teams/chandra/csc258/f26").status_code == 404
    assert add(s, "x@x.ca", "ta").status_code == 404


def test_only_instructors_manage_the_team(client, course):
    ta, tu = member("ta@x.ca", "ta")
    ins, iu = member("ins@x.ca", "ins")
    add(client, "ta@x.ca", "ta", who=ta)
    add(client, "ins@x.ca", "instructor", who=ins)
    assert add(ta, "y@x.ca", "ta").status_code == 403
    assert ta.post("/api/teams/chandra/csc258/f26/role", json={"user": tu["id"], "role": "instructor"}, headers=H).status_code == 403
    assert add(ins, "y@x.ca", "ta").status_code == 200                                   # an instructor can
    assert ins.post("/api/teams/chandra/csc258/f26/remove", json={"user": course["id"]}, headers=H).status_code == 400   # not the owner
    assert ta.post("/api/teams/chandra/csc258/f26/remove", json={"user": tu["id"]}, headers=H).status_code == 200      # leaving
    assert ta.get("/api/store/chandra.priv/git/trees/main").status_code == 404


def test_instructors_decide_accommodations_tas_cant(client, course):
    ta, _ = member("ta@x.ca", "ta")
    ins, _ = member("ins@x.ca", "ins")
    add(client, "ta@x.ca", "ta", who=ta); add(client, "ins@x.ca", "instructor", who=ins)
    store.Repo(course["id"], "priv").write_text("csc258/f26/accommodations.json",
        json.dumps({"requests": [{"id": "r-1", "student": "1001", "evalName": "Midterm", "kind": "alternate", "details": "x",
                                  "first": "Maya", "email": "m@x.ca", "status": "pending"}]}),
        store.Repo(course["id"], "priv").read_text("csc258/f26/accommodations.json")[1], "seed")
    body = {"owner": "chandra", "offering": "csc258/f26", "id": "r-1", "decision": "approved"}
    assert ta.post("/api/accommodations/decide", json=body, headers=H).status_code == 403
    r = ins.post("/api/accommodations/decide", json=body, headers=H)
    assert r.status_code == 200 and r.get_json()["request"]["decidedBy"] == "INS"


def test_a_ta_cant_wipe_the_marks(client, course):
    ta, _ = member("ta@x.ca", "ta")
    add(client, "ta@x.ca", "ta", who=ta)
    many = {"format": "grade-builder/1", "evals": [{"id": f"e{i}"} for i in range(30)], "students": [{"num": "1"}],
            "marks": {"1": {f"e{i}": {"pts": 1} for i in range(30)}}}
    r = store.Repo(course["id"], "priv")
    r.commit({"csc258/f26/grades.json": json.dumps(many).encode()}, "seed", r.head())
    wiped = book_with(ta, "chandra.priv", "csc258/f26/grades.json", lambda b: b.update(marks={}))
    assert save(ta, "chandra.priv", {"csc258/f26/grades.json": wiped}).status_code == 403
    one = book_with(ta, "chandra.priv", "csc258/f26/grades.json", lambda b: b["marks"]["1"].pop("e3"))
    assert save(ta, "chandra.priv", {"csc258/f26/grades.json": one}).status_code == 200   # clearing a typo is fine


def test_new_accounts_can_be_limited_to_domains(client, course, monkeypatch):
    monkeypatch.setenv("LECTERN_TEAM_DOMAINS", "utoronto.ca")
    tok = add(client, "someone@gmail.com", "ta").get_json()["link"].split("#join=")[1]
    c = app.test_client()
    assert c.post("/api/teams/join/check", json={"token": tok}, headers=H).get_json()["canCreate"] is False
    r = c.post("/api/teams/join/create", json={"token": tok, "name": "S", "handle": "someone", "password": PASSWORD}, headers=H)
    assert r.status_code == 403
    tok = add(client, "ta@mail.utoronto.ca", "ta").get_json()["link"].split("#join=")[1]
    assert c.post("/api/teams/join/create", json={"token": tok, "name": "T", "handle": "tee", "password": PASSWORD}, headers=H).status_code == 200


def test_members_uploads_dont_fill_the_owners_space(client, course, monkeypatch):
    monkeypatch.setenv("LECTERN_QUOTA_MB", "1")
    ta, _ = member("ta@x.ca", "ta")
    add(client, "ta@x.ca", "ta", who=ta)
    for _ in range(3):
        assert ta.post("/api/store/chandra.priv/git/blobs", json={"content": "x" * 200000, "encoding": "utf-8"}, headers=H).status_code == 201
    assert save(client, "priv", {"csc258/f26/notes.json": "y" * 300000}).status_code == 200


def test_inline_contents_are_uploads(client, course):
    ta, _ = member("ta@x.ca", "ta")
    add(client, "ta@x.ca", "ta", who=ta)
    r = ta.post("/api/store/chandra.pub/git/trees", json={"tree": [{"path": "csc258/f26/info.html", "content": "<h1>x</h1>"}]}, headers=H)
    assert r.status_code == 403


def test_staff_see_but_change_nothing(client, course):
    st, _ = member("staff@x.ca", "stf")
    add(client, "staff@x.ca", "staff", who=st)
    team = client.get("/api/teams/chandra/csc258/f26").get_json()
    assert [p["role"] for p in team["people"] if p["email"] == "staff@x.ca"] == ["staff"]
    assert read(st, "chandra.priv", "csc258/f26/grades.json") is not None
    assert read(st, "chandra.pub", "csc258/f26/info.html") == "<h1>258</h1>"
    assert read(st, "chandra.priv", "csc258/f26/accommodations.json") is None    # students' requests: instructors only
    def mark(b):
        b["marks"] = {"1001": {"mt": {"pts": 20}}}
    r = save(st, "chandra.priv", {"csc258/f26/grades.json": book_with(st, "chandra.priv", "csc258/f26/grades.json", mark)})
    assert r.status_code == 403   # not even marks
    assert st.post("/api/teams/chandra/csc258/f26/add", json={"email": "x@y.ca", "role": "ta"}, headers=H).status_code == 403
    # An instructor can make someone staff, or back.
    uid = [p["id"] for p in team["people"] if p["email"] == "staff@x.ca"][0]
    assert client.post("/api/teams/chandra/csc258/f26/role", json={"user": uid, "role": "ta"}, headers=H).status_code == 200
    assert client.post("/api/teams/chandra/csc258/f26/role", json={"user": uid, "role": "staff"}, headers=H).status_code == 200
