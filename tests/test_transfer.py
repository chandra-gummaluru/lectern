"""Exporting an offering, importing it as another (without its students), and loading the demo course."""
import io
import json
import zipfile
from datetime import date

import pytest

from conftest import H, make_user
from server import app, store, transfer
from test_hub import publish
from test_teams import add, member

OFF = "csc258/f26"


def seed(user):
    """An offering with a little of everything, students' things included."""
    publish(user)
    r = store.Repo(user["id"], "priv")
    book = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"}, "fields": {"idLabel": "Student Number", "custom": []},
            "evals": [{"id": "mt", "name": "Test 1", "date": "2026-10-28", "time": "18:10", "total": 50, "weight": 30, "released": True, "missed": {"mode": "zero"}}],
            "groups": [], "students": [{"num": "1000", "first": "Maya", "last": "S", "f": {"email": "maya@mail.utoronto.ca"}}],
            "marks": {"1000": {"mt": {"pts": 40}}}, "overrides": {"1000": {"mt": {"weight": 0}}}, "finals": {"1000": {"grade": 90}},
            "policies": {"show": {"sofar": True}}}
    r.commit({f"{OFF}/grades.json": json.dumps(book).encode(),
              f"{OFF}/about.json": json.dumps({"format": "lectern-about/2", "title": "Computer Organization", "description": "Gates to CPUs"}).encode(),
              f"{OFF}/lectures.json": json.dumps({"weeks": [{"label": "Week 1", "start": "2026-09-07", "end": "2026-09-11", "dates": "Sep 7 – 11", "cards": [
                  {"id": "l1", "title": "Gates", "files": [{"label": "Slides", "url": "https://example.edu/2026-09-07/lec01.pdf"}]}]}]}).encode(),
              f"{OFF}/announcements.json": json.dumps({"items": [{"id": "a1", "title": "Welcome", "date": "Sep 7, 2026, 09:00", "body": "Hi"}]}).encode(),
              f"{OFF}/accommodations.json": json.dumps({"requests": [{"email": "maya@mail.utoronto.ca"}]}).encode(),
              f"{OFF}/team.json": json.dumps({"people": {"1": {"office": "BA 1234"}}}).encode(),
              f"{OFF}/groups.json": json.dumps({"groups": [{"id": "g1", "name": "LEC0101", "people": [1], "items": [{"day": 1, "start": "10:00", "people": [1]}]}]}).encode(),
              f"{OFF}/midterm/exam.json": json.dumps({"format": "exam-builder/2", "meta": {"term": "Fall 2026", "date": "Wednesday, October 28, 2026, 18:10"}}).encode(),
              f"{OFF}/midterm/midterm.tex": "\\renewcommand{\\ExamDate}{Wednesday, October 28, 2026, 18:10} Fall 2026".encode()}, "seed", r.head())


def export_zip(client, off=OFF):
    r = client.get(f"/api/offerings/chandra/{off}/export")
    assert r.status_code == 200, r.get_json()
    return zipfile.ZipFile(io.BytesIO(r.data))


def test_an_export_has_the_setup_but_none_of_the_students(client, user):
    seed(user)
    z = export_zip(client)
    names = set(z.namelist())
    assert {"lectern-export.json", "pub/course.json", "priv/grades.json", "priv/about.json", "priv/lectures.json", "priv/groups.json", "priv/midterm/exam.json"} <= names
    assert not names & {"priv/accommodations.json", "priv/announcements.json", "priv/team.json"}
    man = json.loads(z.read("lectern-export.json"))
    assert man["format"] == "lectern-export/1" and (man["course"], man["term"], man["title"]) == ("csc258", "f26", "Computer Organization")
    b = json.loads(z.read("priv/grades.json"))
    assert b["students"] == [] and b["marks"] == {} and b["overrides"] == {} and b["finals"] == {}
    assert b["evals"][0]["weight"] == 30 and "released" not in b["evals"][0]
    gr = json.loads(z.read("priv/groups.json"))["groups"][0]
    assert "people" not in gr and "people" not in gr["items"][0] and gr["name"] == "LEC0101"
    assert b"maya" not in b"".join(z.read(n) for n in names)


def test_only_the_offerings_instructors_export_it(client, user):
    seed(user)
    ta, _ = member("ta@utoronto.ca", "tess")
    add(client, "ta@utoronto.ca", "ta", who=ta)
    assert ta.get(f"/api/offerings/chandra/{OFF}/export").status_code == 403
    assert app.test_client().get(f"/api/offerings/chandra/{OFF}/export").status_code == 401
    assert client.get("/api/offerings/chandra/csc258/w99/export").status_code == 404


def upload(client, data, path="/api/offerings/import", **form):
    return client.post(path, data={"file": (io.BytesIO(data), "x.lectern.zip"), **form}, headers=H, content_type="multipart/form-data")


def test_importing_into_a_new_term_moves_the_dates_by_whole_weeks(client, user):
    seed(user)
    z = client.get(f"/api/offerings/chandra/{OFF}/export").data
    p = upload(client, z, "/api/offerings/import/peek").get_json()["export"]
    assert (p["course"], p["term"], p["title"], p["exams"], p["hasGrades"]) == ("csc258", "f26", "Computer Organization", ["midterm"], True)
    r = upload(client, z, course="csc258", term="f27")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["weeks"] == 52   # Sep 7, 2026 → Sep 6, 2027: the same weekday
    pv = store.Repo(user["id"], "priv")
    b = json.loads(pv.read("csc258/f27/grades.json"))
    assert b["evals"][0]["date"] == "2027-10-27" and b["students"] == [] and b["course"] == {"code": "CSC258", "term": "Fall 2027"}
    w = json.loads(pv.read("csc258/f27/lectures.json"))["weeks"][0]
    assert (w["start"], w["dates"]) == ("2027-09-06", "Sept 6 – 10")
    assert w["cards"][0]["files"][0]["url"] == "https://example.edu/2026-09-07/lec01.pdf"   # a link is left alone
    e = json.loads(pv.read("csc258/f27/midterm/exam.json"))["meta"]
    assert e == {"term": "Fall 2027", "date": "Wednesday, October 27, 2027, 18:10"}
    assert pv.read("csc258/f27/midterm/midterm.tex").decode() == "\\renewcommand{\\ExamDate}{Wednesday, October 27, 2027, 18:10} Fall 2027"
    assert json.loads(pv.read("csc258/f27/about.json"))["title"] == "Computer Organization"
    assert pv.read("csc258/f27/accommodations.json") is None and pv.read("csc258/f27/announcements.json") is None
    assert json.loads(store.Repo(user["id"], "pub").read("csc258/f27/course.json"))["page"]["term"] == "Fall 2027"
    # The offering it came from is untouched; importing over one you have is refused.
    assert json.loads(pv.read(f"{OFF}/grades.json"))["students"]
    assert upload(client, z, course="csc258", term="f26").status_code == 409


def test_importing_without_moving_the_dates_and_under_another_name(client, user):
    seed(user)
    z = client.get(f"/api/offerings/chandra/{OFF}/export").data
    other = app.test_client(); u2 = make_user(other, "ana@utoronto.ca", "Ana B", "ana")
    r = upload(other, z, course="CSC258H1", term="w27", moveDates="0", title="Comp Org")
    assert r.status_code == 200 and r.get_json()["course"] == "csc258h1"
    pv = store.Repo(u2["id"], "priv")
    assert json.loads(pv.read("csc258h1/w27/grades.json"))["evals"][0]["date"] == "2026-10-28"
    assert json.loads(pv.read("csc258h1/w27/about.json"))["title"] == "Comp Org"


@pytest.mark.parametrize("bad, why", [(b"not a zip", "not a .zip"), (None, "no lectern-export.json")])
def test_import_refuses_what_isnt_an_export(client, user, bad, why):
    if bad is None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("priv/grades.json", "{}")
        bad = buf.getvalue()
    r = upload(client, bad, course="csc258", term="f27")
    assert r.status_code == 400 and why in r.get_json()["error"]
    assert upload(client, b"x", course="csc258", term="f27").status_code == 400
    assert app.test_client().post("/api/offerings/import", headers=H).status_code == 401


def test_a_hand_made_export_still_leaves_the_students_out(client, user):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("lectern-export.json", json.dumps({"format": "lectern-export/1", "course": "x", "term": "f26"}))
        z.writestr("priv/grades.json", json.dumps({"students": [{"num": "1"}], "marks": {"1": {}}, "evals": [{"id": "a", "released": True}]}))
        z.writestr("priv/accommodations.json", "{}")
        z.writestr("priv/.secret", "x")
        z.writestr("../evil.json", "x")
    assert upload(client, buf.getvalue(), course="x", term="f26").status_code == 200
    pv = store.Repo(user["id"], "priv")
    b = json.loads(pv.read("x/f26/grades.json"))
    assert b["students"] == [] and b["marks"] == {} and b["evals"] == [{"id": "a"}]
    assert pv.read("x/f26/accommodations.json") is None
    assert json.loads(pv.read("x/f26/about.json"))["title"] == ""


def test_the_terms_and_their_weeks():
    assert transfer.term_now(date(2026, 11, 14)) == "f26" and transfer.term_now(date(2027, 2, 1)) == "w27" and transfer.term_now(date(2027, 6, 1)) == "s27"
    assert transfer.term_monday("f26") == date(2026, 9, 7) and transfer.term_monday("w27") == date(2027, 1, 4)
    assert transfer.weeks_between("f26", "w27") == 17 and transfer.weeks_between("f26", "x") == 0
    assert transfer.shift_json({"d": "2026-09-07", "s": "Sep 7, 2026, 09:00", "u": "see 2026-09-07"}, 7) == {"d": "2026-09-14", "s": "Sep 14, 2026, 09:00", "u": "see 2026-09-07"}


def test_the_demo_course(client, user, monkeypatch):
    r = client.post("/api/offerings/demo", headers=H)
    assert r.status_code == 200, r.get_json()
    t = r.get_json()["term"]
    assert r.get_json()["course"] == "csc258-demo" and t == transfer.term_now()
    pv = store.Repo(user["id"], "priv")
    b = json.loads(pv.read(f"csc258-demo/{t}/grades.json"))
    assert len(b["students"]) > 20 and all(s["f"]["email"].endswith("@example.com") for s in b["students"])
    today = date.today().isoformat()
    out = {e["id"] for e in b["evals"] if e.get("released")}
    assert out == {e["id"] for e in b["evals"] if e.get("date") and e["date"] < today}
    assert all(set(m) <= out for m in b["marks"].values()) and b["policies"]["show"]["sofar"] is True
    assert json.loads(pv.read(f"csc258-demo/{t}/about.json"))["title"] == "Computer Organization (Demo)"
    assert pv.read(f"csc258-demo/{t}/midterm/exam.json")
    assert json.loads(store.Repo(user["id"], "pub").read(f"csc258-demo/{t}/course.json"))["page"]["code"] == "CSC258-DEMO"
    again = client.post("/api/offerings/demo", headers=H)
    assert again.status_code == 409 and again.get_json()["code"] == "have"
    # Its course page works, and its week 1 starts on its term's first Monday.
    j = client.get(f"/api/hub/chandra/csc258-demo/{t}").get_json()
    assert j["course"]["code"] == "CSC258-DEMO" and j["data"]["lectures"]["weeks"][0]["start"] == transfer.term_monday(t).isoformat()
