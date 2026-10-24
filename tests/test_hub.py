"""The course hub: the course page in tabs, from course.json, with signed-in-only tabs kept private."""
import json
import os

import pytest

from conftest import H, make_user
from server import app, store
from test_teams import add, member

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = json.load(open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json"), encoding="utf-8"))


def publish(user, page=None, path="csc258/f26"):
    p = store.Repo(user["id"], "pub")
    files = {f"{path}/info.html": b"<div class='cpb-page'>258</div>"}
    if page is not False:
        files[f"{path}/course.json"] = json.dumps({"format": "lectern-course/1", "page": page or SAMPLE["page"]}).encode()
    p.commit(files, "seed", p.head())


def with_tabs(**tabs):
    page = json.loads(json.dumps(SAMPLE["page"]))
    page["tabs"] = tabs
    return page


@pytest.fixture()
def anon():
    return app.test_client()


def test_the_hub_page_and_its_api(client, user, anon):
    publish(user)
    r = anon.get("/c/chandra/csc258/f26/")
    assert r.status_code == 200 and b"/static/js/hub.js" in r.data
    j = anon.get("/api/hub/chandra/csc258/f26").get_json()
    assert j["course"]["code"] == "CSC258" and j["course"]["year"] == 2026
    assert [t["id"] for t in j["tabs"]] == ["overview", "week", "lectures", "evaluations", "announcements", "policies", "accommodations"]
    assert set(j["data"]) == {"overview", "week", "lectures", "evaluations", "announcements", "policies"}
    assert j["viewer"] == {"signedIn": False, "role": None, "name": "", "staff": False, "preview": False}
    meets = [s for s in j["data"]["overview"]["sections"] if s["type"] == "meetings"][0]["items"]
    assert any(m["kind"] == "office" and m["day"] == 1 for m in meets)
    weeks = j["data"]["week"]["weeks"]
    assert weeks[0]["start"] == "2026-09-07" and any(w["isBreak"] for w in weeks)
    assert j["data"]["announcements"]["items"][0]["title"] == "Welcome to CSC258!"
    assert j["data"]["evaluations"]["units"]


def test_no_course_json_no_hub(client, user, anon):
    publish(user, page=False)
    assert anon.get("/c/chandra/csc258/f26/").status_code == 404
    assert anon.get("/api/hub/chandra/csc258/f26").status_code == 404
    assert anon.get("/c/nobody/csc258/f26/").status_code == 404
    # The old page is still served as it was.
    assert anon.get("/p/chandra/csc258/f26/info.html").status_code == 200


def test_the_published_address_leads_to_the_hub(client, user, anon):
    publish(user)
    for path in ("/p/chandra/csc258/f26/info.html", "/p/chandra/csc258/f26/", "/p/Chandra/csc258/f26/index.html"):
        r = anon.get(path)
        assert r.status_code == 302 and r.headers["Location"].endswith("/c/chandra/csc258/f26/"), path
    # The data only through the API (which leaves out what a visitor can't see).
    assert anon.get("/p/chandra/csc258/f26/course.json").status_code == 404


def test_signed_in_tabs_stay_private(client, user, anon):
    publish(user, with_tabs(lectures="signed-in", announcements="signed-in", accommodations="public"))
    j = anon.get("/api/hub/chandra/csc258/f26").get_json()
    vis = {t["id"]: (t["visibility"], t["open"]) for t in j["tabs"]}
    assert vis["lectures"] == ("signed-in", False) and vis["announcements"] == ("signed-in", False)
    assert vis["accommodations"] == ("signed-in", False)   # always signed-in only
    assert vis["overview"] == ("public", True)
    assert "lectures" not in j["data"] and "announcements" not in j["data"]
    blob = json.dumps(j)
    assert "lec03.pdf" not in blob and "Welcome to CSC258" not in blob
    # This week's calendar has no lectures in it.
    assert all(set(w) <= {"i", "label", "dates", "start", "end", "isBreak"} for w in j["data"]["week"]["weeks"])


def test_the_teaching_team_sees_everything_and_can_preview(client, user, anon):
    publish(user, with_tabs(lectures="signed-in"))
    j = client.get("/api/hub/chandra/csc258/f26").get_json()
    assert j["viewer"]["signedIn"] and j["viewer"]["role"] == "owner" and j["viewer"]["staff"]
    assert "lectures" in j["data"] and "accommodations" in j["data"]
    p = client.get("/api/hub/chandra/csc258/f26?as=public").get_json()
    assert p["viewer"]["preview"] and not p["viewer"]["signedIn"] and "lectures" not in p["data"]
    ta, _ = member("alan@utoronto.ca", "alan")
    add(client, "alan@utoronto.ca", "ta", who=ta)
    t = ta.get("/api/hub/chandra/csc258/f26").get_json()
    assert t["viewer"]["role"] == "ta" and "lectures" in t["data"]


def test_someone_elses_account_is_a_visitor(client, user):
    publish(user, with_tabs(lectures="signed-in"))
    other, _ = member("someone@utoronto.ca", "someone")
    j = other.get("/api/hub/chandra/csc258/f26").get_json()
    assert not j["viewer"]["signedIn"] and "lectures" not in j["data"]


def test_hidden_sections_and_bad_links(client, user, anon):
    page = json.loads(json.dumps(SAMPLE["page"]))
    for s in page["sections"]:
        if s["type"] == "table":
            s["hidden"] = True
    page["sections"][0]["weeks"][1]["cards"][0]["files"] = [{"label": "x", "url": ""}, {"label": "Slides", "url": "lec.pdf"}]
    publish(user, page)
    j = anon.get("/api/hub/chandra/csc258/f26").get_json()
    assert not [s for s in j["data"]["overview"]["sections"] if s["type"] == "table"]
    assert j["data"]["lectures"]["weeks"][1]["cards"][0]["files"] == [{"label": "Slides", "url": "lec.pdf"}]
    assert j["pages"].endswith("/p/chandra/csc258/f26/")


def test_junk_course_json(client, user, anon):
    p = store.Repo(user["id"], "pub")
    p.commit({"csc258/f26/course.json": b"not json"}, "seed", p.head())
    assert anon.get("/api/hub/chandra/csc258/f26").status_code == 404
    p.commit({"csc258/f26/course.json": json.dumps({"page": {"title": "x", "sections": [{"type": "schedule", "weeks": [7, None, {"cards": "no"}]}, "junk"]}}).encode()}, "seed", p.head())
    j = anon.get("/api/hub/chandra/csc258/f26").get_json()
    assert j["data"]["lectures"]["weeks"][0]["cards"] == []


def test_hidden_policies_stay_off_the_page(client, user, anon):
    page = json.loads(json.dumps(SAMPLE["page"]))
    pol = [s for s in page["sections"] if s["type"] == "policies"][0]
    pol["blocks"] = [{"heading": "Late work", "body": "10% a day."}, {"heading": "Note to self", "body": "Secret", "hidden": True}]
    publish(user, page)
    j = anon.get("/api/hub/chandra/csc258/f26").get_json()
    assert [b["heading"] for b in j["data"]["policies"]["sections"][0]["blocks"]] == ["Late work"]
    assert "Secret" not in json.dumps(j)


def test_evaluations_say_where_to_request_accommodations(client, user, anon):
    publish(user)
    rq = anon.get("/api/hub/chandra/csc258/f26").get_json()["data"]["evaluations"]["request"]
    assert rq["url"].endswith("/request") and rq["r"] == "chandra" and rq["o"] == "csc258/f26"
