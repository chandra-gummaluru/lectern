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
    assert [t["id"] for t in j["tabs"]] == ["week", "announcements", "lectures", "evaluations", "about", "accommodations"]
    assert set(j["data"]) == {"week", "announcements", "lectures", "evaluations", "about"}
    assert j["viewer"] == {"signedIn": False, "role": None, "name": "", "staff": False, "preview": False}
    # The page's old contact and meeting-time tables aren't shown: the teaching team's sections and times are.
    assert not [s for s in j["data"]["about"]["sections"] if s["type"] != "text"]
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
    assert vis["about"] == ("public", True)
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
    assert not [s for s in j["data"]["about"]["sections"] if s["type"] == "table"]
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
    assert [b["heading"] for b in j["data"]["about"]["policies"]] == ["Late work"]
    assert "Secret" not in json.dumps(j)


def test_evaluations_say_where_to_request_accommodations(client, user, anon):
    publish(user)
    rq = anon.get("/api/hub/chandra/csc258/f26").get_json()["data"]["evaluations"]["request"]
    assert rq["url"].endswith("/request") and rq["r"] == "chandra" and rq["o"] == "csc258/f26"


def test_evaluation_files_come_from_the_gradebook(client, user, anon):
    page = json.loads(json.dumps(SAMPLE["page"]))
    page["evalFiles"] = {"mt": [{"label": "Old practice", "url": "https://example.edu/old.pdf"}]}
    publish(user, page)
    book = {"evals": [{"id": "mt", "name": "Midterm", "files": [{"label": "Practice", "url": "https://example.edu/mt.pdf"}, {"label": "Empty", "url": ""}]},
                      {"id": "a1", "name": "A1"}], "students": [{"num": "1", "first": "Secret", "last": "Student"}], "marks": {"1": {"mt": {"pts": 3}}}}
    r = store.Repo(user["id"], "priv"); r.commit({"csc258/f26/grades.json": json.dumps(book).encode()}, "seed", r.head())
    j = anon.get("/api/hub/chandra/csc258/f26").get_json()
    assert j["data"]["evaluations"]["files"] == {"mt": [{"label": "Practice", "url": "https://example.edu/mt.pdf"}, {"label": "Old practice", "url": "https://example.edu/old.pdf"}]}
    assert "Secret" not in json.dumps(j)


def test_lectures_come_from_the_lectures_part(client, user, anon):
    publish(user)
    lec = {"format": "lectern-lectures/1", "weeks": [
        {"id": "a", "label": "Week 1", "start": "2026-09-07", "end": "2026-09-11", "topic": "Gates",
         "cards": [{"id": "x", "kind": "lecture", "label": "Lecture 01", "title": "Transistors", "files": [{"label": "Slides", "url": "https://example.edu/1.pdf"}]}]},
        {"id": "b", "isBreak": True, "text": "Reading Week"},
        {"id": "c", "label": "Week 2", "start": "2026-09-14", "end": "2026-09-18", "cards": []}]}
    r = store.Repo(user["id"], "priv"); r.commit({"csc258/f26/lectures.json": json.dumps(lec).encode()}, "seed", r.head())
    j = anon.get("/api/hub/chandra/csc258/f26").get_json()
    weeks = j["data"]["lectures"]["weeks"]
    assert [w["label"] for w in weeks] == ["Week 1", "Reading Week", "Week 2"]
    assert weeks[0]["dates"] == "Sept 7 – 11" and weeks[0]["cards"][0]["title"] == "Transistors"
    # The course page's announcement (Sep 7) lands in the week its date is in.
    ann = j["data"]["announcements"]["items"][0]
    assert ann["title"] == "Welcome to CSC258!" and ann["wi"] == 0 and ann["week"] == "Week 1"
    # Nothing else of the private files: lectures.json isn't served anywhere public.
    assert anon.get("/p/chandra/csc258/f26/lectures.json").status_code == 404


def test_the_teaching_team_on_the_course_page(client, user, anon):
    publish(user)
    ta, tu = member("alan@utoronto.ca", "alan")
    add(client, "alan@utoronto.ca", "ta", who=ta)
    info = {"people": {str(user["id"]): {"office": "BA 4010", "times": [{"kind": "lecture", "section": "LEC0101", "day": 1, "start": "10:00", "end": "11:00", "where": "BA 1170"}]},
                       str(tu["id"]): {"email": "alan@cs.example.edu", "times": [{"kind": "office", "day": "4", "start": "11:00", "end": "12:00", "where": "BA 3201"}]}}}
    r = store.Repo(user["id"], "priv"); r.commit({"csc258/f26/team.json": json.dumps(info).encode()}, "seed", r.head())
    team = anon.get("/api/hub/chandra/csc258/f26").get_json()["data"]["about"]["team"]
    assert [(p["name"], p["role"], p["email"]) for p in team] == [("Chandra Gummaluru", "instructor", "chandra@utoronto.ca"), ("ALAN", "ta", "alan@cs.example.edu")]
    assert team[0]["times"][0]["section"] == "LEC0101" and team[1]["times"][0]["day"] == 4
    info["people"][str(tu["id"])]["show"] = False
    r.commit({"csc258/f26/team.json": json.dumps(info).encode()}, "seed", r.head())
    assert len(anon.get("/api/hub/chandra/csc258/f26").get_json()["data"]["about"]["team"]) == 1


def test_announcements_come_from_the_announcements_part(client, user, anon):
    publish(user)
    items = [{"id": "a", "title": "Midterm rooms", "date": "Oct 28, 2026, 09:00", "body": "EX 100"}, {"id": "b", "title": "", "body": ""}]
    r = store.Repo(user["id"], "priv"); r.commit({"csc258/f26/announcements.json": json.dumps({"items": items}).encode()}, "seed", r.head())
    got = anon.get("/api/hub/chandra/csc258/f26").get_json()["data"]["announcements"]["items"]
    assert [(a["title"], a["week"]) for a in got] == [("Midterm rooms", "Week 7")]   # Oct 28 is in Week 7; the course page's own aren't shown


def test_about_from_the_about_part(client, user, anon):
    publish(user, with_tabs(overview="signed-in"))
    about = {"title": "Computer Organization!", "description": "Gates to CPUs.", "sections": [{"id": "t", "heading": "Textbook", "body": "Patt & Patel"}],
             "policies": [{"id": "p", "heading": "Late work", "body": "No."}, {"id": "q", "heading": "Hidden", "body": "x", "hidden": True}]}
    r = store.Repo(user["id"], "priv"); r.commit({"csc258/f26/about.json": json.dumps(about).encode()}, "seed", r.head())
    j = client.get("/api/hub/chandra/csc258/f26").get_json()
    a = j["data"]["about"]
    assert j["course"]["title"] == "Computer Organization!" and a["description"] == "Gates to CPUs."
    assert [b["heading"] for s in a["sections"] for b in s["blocks"]] == ["Textbook"] and [b["heading"] for b in a["policies"]] == ["Late work"]
    # Overview's old setting carries over to About: signed-in only.
    assert "about" not in anon.get("/api/hub/chandra/csc258/f26").get_json()["data"]
