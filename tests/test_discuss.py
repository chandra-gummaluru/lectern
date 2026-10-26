"""Discussions on the course page (discuss.py): posts and comments, anonymous to classmates, votes and moderation."""
from conftest import H
from server import app
from test_students import HUB, course, enrol, sign_in  # noqa: F401  (course is a fixture)

D = f"{HUB}/discussion"


def people(user):
    enrol(user, "maya@mail.utoronto.ca", "ben@mail.utoronto.ca")   # first names "maya", "ben"; numbers 1000, 1001
    maya, ben = app.test_client(), app.test_client()
    sign_in(maya, "maya@mail.utoronto.ca"); sign_in(ben, "ben@mail.utoronto.ca")
    return maya, ben


def test_only_people_in_the_course(client, course):
    assert app.test_client().get(f"{D}?t=eval:mt").status_code == 401
    assert app.test_client().post(D, json={"t": "eval:mt", "title": "x", "body": "y"}, headers=H).status_code == 401
    assert client.get(f"{D}?t=eval:mt").status_code == 200          # the owner
    assert client.get(f"{D}?t=nonsense").status_code == 400


def test_anonymous_to_classmates_not_to_the_teaching_team(client, course):
    maya, ben = people(course)
    r = maya.post(D, json={"t": "eval:mt", "title": "Question 3?", "body": "Truth table too?", "anon": True}, headers=H)
    assert r.status_code == 201, r.get_json()
    pid = r.get_json()["id"]
    me = r.get_json()["me"]
    assert me["kind"] == "student" and me["alias"].startswith("Anonymous ")
    seen = ben.get(f"{D}?t=eval:mt").get_json()["posts"][0]
    assert seen["who"]["name"] == me["alias"] and seen["who"]["anon"] and "real" not in seen["who"]
    staff = client.get(f"{D}?t=eval:mt").get_json()["posts"][0]
    assert staff["who"]["name"] == me["alias"] and staff["who"]["real"] == "maya S"
    # The alias is hers for the whole course: the same in another discussion.
    maya.post(D, json={"t": "ann:a1", "title": "Hi", "body": "x", "anon": True}, headers=H)
    assert ben.get(f"{D}?t=ann:a1").get_json()["posts"][0]["who"]["name"] == me["alias"]
    # Comments, nested: the teaching team's are marked as theirs.
    c = client.post(D, json={"t": "eval:mt", "parent": pid, "body": "Yes @{p:%d}, show it." % pid}, headers=H).get_json()
    reply = next(p for p in c["posts"] if p["parent"] == pid)
    assert reply["who"]["team"] and reply["who"]["role"] == "Instructor" and not reply["title"]
    names = ben.get(f"{D}?t=eval:mt").get_json()["names"]
    assert names[f"p:{pid}"]["name"] == me["alias"] and "real" not in names[f"p:{pid}"]
    assert client.get(f"{D}?t=eval:mt").get_json()["names"][f"p:{pid}"]["real"] == "maya S"
    # The teaching team mentions her by her number: classmates still see her alias here.
    client.post(D, json={"t": "eval:mt", "parent": pid, "body": "And @{s:1000}, bring a pencil."}, headers=H)
    assert ben.get(f"{D}?t=eval:mt").get_json()["names"]["s:1000"]["name"] == me["alias"]
    # A student can't mention someone by number.
    r = ben.post(D, json={"t": "eval:mt", "parent": pid, "body": "Who is @{s:1000}?"}, headers=H).get_json()
    assert "@{s:1000}" not in [p for p in r["posts"] if p["parent"] == pid][-1]["body"]
    assert ben.get(f"{HUB}/discussion/counts").get_json()["counts"] == {"eval:mt": 1, "ann:a1": 1}


def test_votes_and_the_teaching_teams_tools(client, course):
    maya, ben = people(course)
    pid = maya.post(D, json={"t": "act:l1", "title": "Slides?", "body": "Where are the slides?"}, headers=H).get_json()["id"]
    assert maya.post(D, json={"t": "act:l1", "body": "no title"}, headers=H).status_code == 400   # a post needs a title
    p = ben.post(f"{D}/{pid}/vote", json={"on": True}, headers=H).get_json()["posts"][0]
    assert p["votes"] == 1 and p["voted"]
    ben.post(f"{D}/{pid}/vote", json={"on": True}, headers=H)                                      # once each
    assert maya.get(f"{D}?t=act:l1").get_json()["posts"][0]["votes"] == 1
    assert ben.post(f"{D}/{pid}/moderate", json={"pin": True}, headers=H).status_code == 403
    p = client.post(f"{D}/{pid}/moderate", json={"pin": True, "endorse": True}, headers=H).get_json()["posts"][0]
    assert p["pinned"] and p["endorsed"]
    client.post(f"{D}/{pid}/moderate", json={"remove": True}, headers=H)
    gone = ben.get(f"{D}?t=act:l1").get_json()["posts"][0]
    assert gone["removed"] and gone["who"] is None and gone["body"] == ""
    assert client.get(f"{D}?t=act:l1").get_json()["posts"][0]["body"] == "Where are the slides?"   # the teaching team still sees it
    assert ben.post(f"{D}/{pid}/delete", json={}, headers=H).status_code == 403                    # only its author
    assert maya.post(f"{D}/{pid}/delete", json={}, headers=H).get_json()["posts"][0]["deleted"]
