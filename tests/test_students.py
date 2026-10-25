"""Students: each offering's class list (the gradebook's students), and signing in to its course page with an emailed code."""
import json
import re

import pytest

from conftest import H
from server import app, mailer, store, students
from test_hub import publish, with_tabs
from test_teams import add, member

API = "/api/students/chandra/csc258/f26"
HUB = "/api/hub/chandra/csc258/f26"


@pytest.fixture()
def course(client, user):
    publish(user, with_tabs(lectures="signed-in"))
    return user


def enrol(user, *emails, dropped=(), more=()):
    """The gradebook's students (the offering's Students card writes them)."""
    st = [{"num": str(1000 + i), "first": e.split("@")[0], "last": "S", "f": {"email": e}} for i, e in enumerate(emails)]
    st += [{"num": str(2000 + i), "first": e.split("@")[0], "last": "D", "f": {"email": e}, "dropped": True} for i, e in enumerate(dropped)]
    st += list(more)
    r = store.Repo(user["id"], "priv")
    r.commit({"csc258/f26/grades.json": json.dumps({"format": "grade-builder/1", "students": st, "evals": [], "marks": {}}).encode()}, "seed", r.head())


def code_for(email):
    m = [x for x in mailer.sent if x["to"] == email and "code" in x["subject"]]
    return re.search(r"\b(\d{6})\b", m[-1]["body"]).group(1)


def sign_in(c, email):
    assert c.post(f"{HUB}/code", json={"email": email}, headers=H).status_code == 200
    r = c.post(f"{HUB}/verify", json={"email": email, "code": code_for(email)}, headers=H)
    assert r.status_code == 200, r.get_json()
    return r


def test_the_class_list_is_the_gradebooks(client, course):
    enrol(course, "Maya@Mail.Utoronto.ca", "ben@mail.utoronto.ca", dropped=["gone@mail.utoronto.ca"],
          more=[{"num": "9", "first": "No", "last": "Email", "f": {}}])
    r = client.post(f"{API}/invite", json={}, headers=H)
    assert r.status_code == 200
    to = {m["to"] for m in mailer.sent}
    assert {"maya@mail.utoronto.ca", "ben@mail.utoronto.ca"} <= to and "gone@mail.utoronto.ca" not in to
    invite = [m for m in mailer.sent if m["to"] == "maya@mail.utoronto.ca"][-1]
    assert "/c/chandra/csc258/f26/" in invite["body"]
    lst = client.get(API).get_json()
    assert lst["link"].endswith("/c/chandra/csc258/f26/")
    # Only someone on it: not a dropped student, or a stranger.
    assert client.post(f"{API}/invite", json={"email": "gone@mail.utoronto.ca"}, headers=H).status_code == 404


def test_tas_see_it_but_cant_send_links(client, course):
    enrol(course, "maya@mail.utoronto.ca")
    ta, _ = member("alan@utoronto.ca", "alan")
    add(client, "alan@utoronto.ca", "ta", who=ta)
    assert ta.get(API).status_code == 200
    assert ta.post(f"{API}/invite", json={}, headers=H).status_code == 403
    other, _ = member("eve@utoronto.ca", "eve")
    assert other.get(API).status_code == 403


def test_dropped_students_cant_sign_in(client, course):
    enrol(course, "maya@mail.utoronto.ca", dropped=["gone@mail.utoronto.ca"])
    st = app.test_client()
    st.post(f"{HUB}/code", json={"email": "gone@mail.utoronto.ca"}, headers=H)
    assert not [m for m in mailer.sent if m["to"] == "gone@mail.utoronto.ca"]


def test_a_student_signs_in_with_a_code(client, course):
    enrol(course, "maya@mail.utoronto.ca")
    st = app.test_client()
    before = st.get(HUB).get_json()
    assert "lectures" not in before["data"] and before["signIn"] == "/c/chandra/csc258/f26/sign-in"
    assert st.get("/c/chandra/csc258/f26/sign-in").status_code == 200
    sign_in(st, "maya@mail.utoronto.ca")
    j = st.get(HUB).get_json()
    assert j["viewer"]["signedIn"] and j["viewer"]["role"] == "student" and j["viewer"]["name"] == "maya@mail.utoronto.ca"
    assert client.get(API).get_json()["state"]["maya@mail.utoronto.ca"]["last_in"] > 0
    assert "lectures" in j["data"] and "accommodations" in j["data"]
    # Not a Lectern session: nothing of Lectern opens.
    assert st.get("/api/auth/me").get_json().get("user") is None
    assert st.get(API).status_code == 401
    # Signing out ends it.
    st.post(f"{HUB}/sign-out", headers=H)
    assert not st.get(HUB).get_json()["viewer"]["signedIn"]


def test_the_answer_never_says_whos_in_the_course(client, course):
    enrol(course, "maya@mail.utoronto.ca")
    st = app.test_client()
    a = st.post(f"{HUB}/code", json={"email": "maya@mail.utoronto.ca"}, headers=H)
    b = st.post(f"{HUB}/code", json={"email": "stranger@mail.utoronto.ca"}, headers=H)
    assert a.status_code == b.status_code == 200 and a.get_json() == b.get_json()
    assert not [m for m in mailer.sent if m["to"] == "stranger@mail.utoronto.ca"]


def test_codes_are_one_use_expire_and_stop_after_wrong_tries(client, course, monkeypatch):
    enrol(course, "maya@mail.utoronto.ca")
    st = app.test_client()
    st.post(f"{HUB}/code", json={"email": "maya@mail.utoronto.ca"}, headers=H)
    good = code_for("maya@mail.utoronto.ca")
    bad = "000000" if good != "000000" else "111111"
    for _ in range(students.MAX_TRIES):
        assert st.post(f"{HUB}/verify", json={"email": "maya@mail.utoronto.ca", "code": bad}, headers=H).status_code == 400
    assert st.post(f"{HUB}/verify", json={"email": "maya@mail.utoronto.ca", "code": good}, headers=H).status_code == 400   # cancelled
    # A new code works once.
    sign_in(st, "maya@mail.utoronto.ca")
    used = code_for("maya@mail.utoronto.ca")
    assert app.test_client().post(f"{HUB}/verify", json={"email": "maya@mail.utoronto.ca", "code": used}, headers=H).status_code == 400
    # And expires.
    st2 = app.test_client()
    st2.post(f"{HUB}/code", json={"email": "maya@mail.utoronto.ca"}, headers=H)
    later = __import__("time").time() + students.CODE_MINUTES * 60 + 5
    monkeypatch.setattr(students.time, "time", lambda: later)
    assert st2.post(f"{HUB}/verify", json={"email": "maya@mail.utoronto.ca", "code": code_for("maya@mail.utoronto.ca")}, headers=H).status_code == 400


def test_a_student_session_is_for_that_course_only(client, course):
    enrol(course, "maya@mail.utoronto.ca")
    publish(course, None, path="csc108/f26")
    st = app.test_client()
    sign_in(st, "maya@mail.utoronto.ca")
    assert not st.get("/api/hub/chandra/csc108/f26").get_json()["viewer"]["signedIn"]


def test_taken_off_the_list_signs_them_out(client, course):
    enrol(course, "maya@mail.utoronto.ca")
    st = app.test_client()
    sign_in(st, "maya@mail.utoronto.ca")
    enrol(course, dropped=["maya@mail.utoronto.ca"])   # dropped in the Students card
    assert not st.get(HUB).get_json()["viewer"]["signedIn"]
    st.post(f"{HUB}/code", json={"email": "maya@mail.utoronto.ca"}, headers=H)
    assert not [m for m in mailer.sent if m["to"] == "maya@mail.utoronto.ca" and "code" in m["subject"]][1:]


def test_asking_for_codes_is_rate_limited(client, course):
    enrol(course, "maya@mail.utoronto.ca")
    st = app.test_client()
    codes = [st.post(f"{HUB}/code", json={"email": "maya@mail.utoronto.ca"}, headers=H).status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and 429 in codes[5:]


def test_a_student_sees_their_own_sections(client, course):
    """Signed in, a student in LEC0102 sees their section (not LEC0101), the people who run it (and the
    coordinators), and an evaluation on their section's date."""
    import json as _j
    from test_hub import SAMPLE
    ta, tu = member("alan@utoronto.ca", "alan")
    add(client, "alan@utoronto.ca", "ta", who=ta)
    tb, tbu = member("bea@utoronto.ca", "bea")
    add(client, "bea@utoronto.ca", "ta", who=tb)
    page = _j.loads(_j.dumps(SAMPLE["page"])); page["tabs"] = {"lectures": "signed-in"}
    e = page["scheme"]["evals"][0]; e["date"], e["dates"] = "2026-10-02", [{"groups": ["g2"], "date": "2026-10-05", "time": "18:00"}]
    publish(course, page)
    st = [{"num": "1", "first": "Maya", "last": "S", "f": {"email": "maya@mail.utoronto.ca"}, "groups": ["g2"]}]
    groups = {"groups": [{"id": "g1", "name": "LEC0101", "kind": "lecture", "people": [str(tu["id"])], "items": [{"id": "a", "day": 1, "start": "10:00", "end": "11:00", "where": "BA 1170"}]},
                         {"id": "g2", "name": "LEC0102", "kind": "lecture", "people": [str(tbu["id"])], "items": [{"id": "b", "day": 2, "start": "13:00", "end": "14:00", "where": "GB 120"}]}]}
    r = store.Repo(course["id"], "priv")
    r.commit({"csc258/f26/grades.json": _j.dumps({"format": "grade-builder/1", "students": st, "evals": [], "marks": {}}).encode(),
              "csc258/f26/groups.json": _j.dumps(groups).encode()}, "seed", r.head())
    s = app.test_client(); sign_in(s, "maya@mail.utoronto.ca")
    j = s.get(HUB).get_json()
    about = j["data"]["about"]
    assert [g["name"] for g in about["groups"]] == ["LEC0102"]
    names = [p["name"] for p in about["team"]]
    assert any("bea" in n.lower() for n in names) and not any("alan" in n.lower() for n in names), names
    assert all(x.get("sid") in (None, "g2") for p in about["team"] for x in p["times"])
    ev = next(x for x in j["data"]["evaluations"]["evals"] if x["id"] == e["id"])
    assert ev["date"] == "2026-10-05" and ev["time"] == "18:00" and "dates" not in ev
    staff = client.get(HUB).get_json()["data"]["about"]   # the teaching team: every section
    assert [g["name"] for g in staff["groups"]] == ["LEC0101", "LEC0102"]
