"""Attendance: sessions, scans (a card → its student), once per evaluation however many scan, and students'
own cards from the course page."""
from conftest import H, make_user
from server import app, db
from server.attendance import card_of
from test_accommodations import Teacher, hub_student, HUB  # noqa: F401
import pytest


@pytest.fixture()
def gh():
    return Teacher()


def ta(gh):
    c = app.test_client()
    t = make_user(c, email="sam@utoronto.ca", name="Sam Patel", handle="sam")
    db.run("INSERT INTO members (owner_id, offering, user_id, role, added) VALUES (?, 'csc258/f26', ?, 'ta', 0)", (gh.user["id"], t["id"]))
    return c


def P(c, path, **d):
    return c.post(f"/api/attendance{path}", json={"owner": "chandra", "offering": "csc258/f26", "e": "mt", **d}, headers=H)


def test_card_numbers():
    assert card_of(" 2100 7012-3456 ") == "210070123456" and card_of("a21007b") == "21007" and card_of("abc12") == "ABC12"


def test_two_people_take_attendance_and_each_student_is_in_once(gh):
    me, sam = gh.client, ta(gh)
    s1 = P(me, "/start", note="BA 1170").get_json()["session"]
    s2 = P(sam, "/start", note="Last names M–Z").get_json()["session"]
    # Maya's card isn't registered: the scanner finds her by hand and registers it to her.
    assert P(me, "/lookup", card="A123456B").get_json() == {"card": "123456", "student": None}
    r = sam.get("/api/attendance/search?owner=chandra&offering=csc258/f26&e=mt&q=cast")
    assert [x["num"] for x in r.get_json()["students"]] == ["1001"]
    assert sam.get("/api/attendance/search?owner=chandra&offering=csc258/f26&e=mt&q=away").get_json()["students"] == []   # dropped
    r = P(me, "/mark", session=s1["id"], student="1001", card="123456")
    assert r.status_code == 200 and r.get_json()["count"] == 1
    # The same card again, on the other phone: it's Maya, already in.
    got = P(sam, "/lookup", card="123456").get_json()
    assert got["student"]["num"] == "1001" and got["already"]["by"] == "Chandra Gummaluru"
    r = P(sam, "/mark", session=s2["id"], student="1001")
    assert r.status_code == 409 and r.get_json()["code"] == "already" and "already entered by Chandra Gummaluru" in r.get_json()["error"]
    # The card was wrong: it's Zoë's. Registering it to her moves it.
    assert P(sam, "/mark", session=s2["id"], student="1002", card="123456", hand=True).get_json()["count"] == 1
    assert P(me, "/lookup", card="123456").get_json()["student"]["num"] == "1002"
    # Someone else's session, or a stopped one: no.
    assert P(me, "/mark", session=s2["id"], student="1002").status_code == 404
    assert P(sam, "/stop", session=s2["id"]).get_json()["count"] == 1
    assert P(sam, "/mark", session=s2["id"], student="1001").status_code == 409
    o = me.get("/api/attendance?owner=chandra&offering=csc258/f26&e=mt").get_json()
    assert o["total"] == 2 and o["enrolled"] == 2 and [(s["by"], s["note"], s["count"], bool(s["stopped"])) for s in o["sessions"]] == [
        ("Chandra Gummaluru", "BA 1170", 1, False), ("Sam Patel", "Last names M–Z", 1, True)]


def test_only_the_teaching_team(gh, client):
    assert client.get("/api/attendance?offering=csc258/f26&e=mt").status_code == 401
    other = app.test_client(); make_user(other, email="x@utoronto.ca", name="X", handle="xx")
    assert P(other, "/start").status_code == 404
    assert P(gh.client, "/start", e="nope").status_code == 404


def test_a_student_registers_their_card(gh):
    st = hub_student("maya.castillo@mail.utoronto.ca")
    assert st.get(f"{HUB}/tcard").get_json() == {"card": ""}
    assert st.post(f"{HUB}/tcard", json={"card": "12"}, headers=H).status_code == 400
    assert st.post(f"{HUB}/tcard", json={"card": "2100 7012 3456"}, headers=H).get_json()["card"] == "210070123456"
    assert st.get(f"{HUB}/tcard").get_json()["card"] == "210070123456"
    assert P(gh.client, "/lookup", card="210070123456").get_json()["student"]["num"] == "1001"
    zoe = hub_student("zoe.ng@mail.utoronto.ca")
    r = zoe.post(f"{HUB}/tcard", json={"card": "210070123456"}, headers=H)
    assert r.status_code == 409 and r.get_json()["code"] == "taken"
    assert st.post(f"{HUB}/tcard", json={"card": "1"}).status_code == 403   # not from the course page
