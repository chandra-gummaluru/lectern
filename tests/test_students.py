"""Students: each offering's class list, and signing in to its course page with an emailed code."""
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


def code_for(email):
    m = [x for x in mailer.sent if x["to"] == email and "code" in x["subject"]]
    return re.search(r"\b(\d{6})\b", m[-1]["body"]).group(1)


def sign_in(c, email):
    assert c.post(f"{HUB}/code", json={"email": email}, headers=H).status_code == 200
    r = c.post(f"{HUB}/verify", json={"email": email, "code": code_for(email)}, headers=H)
    assert r.status_code == 200, r.get_json()
    return r


def test_instructors_keep_the_class_list(client, course):
    r = client.post(f"{API}/add", json={"emails": "Maya@Mail.Utoronto.ca, ben@mail.utoronto.ca\nnot-an-email; maya@mail.utoronto.ca", "invite": True}, headers=H)
    assert r.get_json()["added"] == 2 and r.get_json()["bad"] == ["not-an-email"]
    lst = client.get(API).get_json()
    assert [s["email"] for s in lst["students"]] == ["ben@mail.utoronto.ca", "maya@mail.utoronto.ca"]
    assert lst["link"].endswith("/c/chandra/csc258/f26/")
    invite = [m for m in mailer.sent if m["to"] == "maya@mail.utoronto.ca"][-1]
    assert "/c/chandra/csc258/f26/" in invite["body"]


def test_tas_see_it_but_cant_change_it(client, course):
    ta, _ = member("alan@utoronto.ca", "alan")
    add(client, "alan@utoronto.ca", "ta", who=ta)
    assert ta.get(API).status_code == 200
    assert ta.post(f"{API}/add", json={"emails": "x@y.ca"}, headers=H).status_code == 403
    other, _ = member("eve@utoronto.ca", "eve")
    assert other.get(API).status_code == 403


def test_a_student_signs_in_with_a_code(client, course):
    client.post(f"{API}/add", json={"emails": "maya@mail.utoronto.ca"}, headers=H)
    st = app.test_client()
    before = st.get(HUB).get_json()
    assert "lectures" not in before["data"] and before["signIn"] == "/c/chandra/csc258/f26/sign-in"
    assert st.get("/c/chandra/csc258/f26/sign-in").status_code == 200
    sign_in(st, "maya@mail.utoronto.ca")
    j = st.get(HUB).get_json()
    assert j["viewer"]["signedIn"] and j["viewer"]["role"] == "student" and j["viewer"]["name"] == "maya@mail.utoronto.ca"
    assert "lectures" in j["data"] and "accommodations" in j["data"]
    # Not a Lectern session: nothing of Lectern opens.
    assert st.get("/api/auth/me").get_json().get("user") is None
    assert st.get(API).status_code == 401
    # Signing out ends it.
    st.post(f"{HUB}/sign-out", headers=H)
    assert not st.get(HUB).get_json()["viewer"]["signedIn"]


def test_the_answer_never_says_whos_in_the_course(client, course):
    client.post(f"{API}/add", json={"emails": "maya@mail.utoronto.ca"}, headers=H)
    st = app.test_client()
    a = st.post(f"{HUB}/code", json={"email": "maya@mail.utoronto.ca"}, headers=H)
    b = st.post(f"{HUB}/code", json={"email": "stranger@mail.utoronto.ca"}, headers=H)
    assert a.status_code == b.status_code == 200 and a.get_json() == b.get_json()
    assert not [m for m in mailer.sent if m["to"] == "stranger@mail.utoronto.ca"]


def test_codes_are_one_use_expire_and_stop_after_wrong_tries(client, course, monkeypatch):
    client.post(f"{API}/add", json={"emails": "maya@mail.utoronto.ca"}, headers=H)
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
    client.post(f"{API}/add", json={"emails": "maya@mail.utoronto.ca"}, headers=H)
    publish(course, None, path="csc108/f26")
    st = app.test_client()
    sign_in(st, "maya@mail.utoronto.ca")
    assert not st.get("/api/hub/chandra/csc108/f26").get_json()["viewer"]["signedIn"]


def test_taken_off_the_list_signs_them_out(client, course):
    client.post(f"{API}/add", json={"emails": "maya@mail.utoronto.ca"}, headers=H)
    st = app.test_client()
    sign_in(st, "maya@mail.utoronto.ca")
    client.post(f"{API}/remove", json={"email": "maya@mail.utoronto.ca"}, headers=H)
    assert not st.get(HUB).get_json()["viewer"]["signedIn"]
    st.post(f"{HUB}/code", json={"email": "maya@mail.utoronto.ca"}, headers=H)
    assert not [m for m in mailer.sent if m["to"] == "maya@mail.utoronto.ca" and "code" in m["subject"]][1:]


def test_asking_for_codes_is_rate_limited(client, course):
    client.post(f"{API}/add", json={"emails": "maya@mail.utoronto.ca"}, headers=H)
    st = app.test_client()
    codes = [st.post(f"{HUB}/code", json={"email": "maya@mail.utoronto.ca"}, headers=H).status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and 429 in codes[5:]
