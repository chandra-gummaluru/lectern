"""Accommodation requests: the students' endpoints and the instructors' decisions, with email faked.

Run with:  python -m pytest
"""
import json

import pytest

from conftest import H, make_user
from server import app, accommodations, mailer, store  # noqa: E402

BOOK = {
    "format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
    "fields": {"idLabel": "Student number", "custom": [{"id": "email", "label": "Email"}]},
    "evals": [
        {"id": "mt", "name": "Midterm", "type": "test", "date": "2026-10-21", "time": "18:00",
         "accom": {"standard": "Write it the next day", "approval": True, "alternate": False}},
        {"id": "a1", "name": "Assignment 1", "type": "assignment", "accom": {"standard": "48-hour extension", "approval": False, "alternate": True}},
        {"id": "l1", "name": "Lab 1", "type": "assignment"},
    ],
    "students": [
        {"num": "1001", "first": "Maya", "last": "Castillo", "f": {"email": "maya.castillo@mail.utoronto.ca"}},
        {"num": "1002", "first": "Zoë", "last": "Ng", "f": {"email": "zoe.ng@mail.utoronto.ca"}},
        {"num": "1003", "first": "Gone", "last": "Away", "dropped": True, "f": {"email": "gone@mail.utoronto.ca"}},
    ],
    "marks": {}, "overrides": {},
}
MAYA = {"email": "Maya.Castillo@mail.utoronto.ca", "id": "1001", "first": "maya", "last": "CASTILLO"}
WHERE = {"r": "chandra", "o": "csc258/f26", "e": "mt"}


class Teacher:
    """The instructor: an account with this gradebook in its files, and a signed-in client."""
    def __init__(self):
        self.client = app.test_client()
        self.user = make_user(self.client)
        self.repo = store.Repo(self.user["id"], "priv")
        self.put("csc258/f26/grades.json", json.dumps(BOOK))

    def put(self, path, text):
        self.repo.commit({path: text.encode()}, "test", self.repo.head())
        accommodations._books.clear()

    def text(self, path):
        return self.repo.read_text(path)[0]


@pytest.fixture()
def gh():
    return Teacher()


def requests_of(gh):
    v = gh.text("csc258/f26/accommodations.json")
    return json.loads(v)["requests"] if v else []


def test_request_page(client):
    r = client.get("/request?r=chandra&o=csc258/f26&e=mt")
    assert r.status_code == 200 and 'id="rq"' in r.get_data(as_text=True)


def test_evaluation_info(client, gh):
    d = client.get("/api/accommodations/evaluation", query_string=WHERE).get_json()
    assert d["course"] == {"code": "CSC258", "term": "Fall 2026"}
    assert d["evaluation"]["name"] == "Midterm" and d["idLabel"] == "Student number"
    assert d["standard"] == {"text": "Write it the next day", "approval": True} and d["alternate"] is False
    # Nothing about students goes out here
    assert "Maya" not in json.dumps(d)


def test_evaluation_without_requests(client, gh):
    r = client.get("/api/accommodations/evaluation", query_string={**WHERE, "e": "l1"})
    assert r.status_code == 404
    assert client.get("/api/accommodations/evaluation", query_string={**WHERE, "o": "csc999/f26"}).status_code == 404


def test_bad_links(client, gh):
    for bad in ({"r": "../x", "o": "csc258/f26", "e": "mt"}, {"r": "chandra", "o": "csc258", "e": "mt"}, {"r": "chandra", "o": "csc258/f26", "e": "a b"}):
        assert client.get("/api/accommodations/evaluation", query_string=bad).status_code == 400
    assert client.get("/api/accommodations/evaluation", query_string={**WHERE, "r": "nobody"}).status_code == 404
    # A course page saved before Lectern had its own accounts says what to do
    old = client.get("/api/accommodations/evaluation", query_string={**WHERE, "r": "chandra/courses"})
    assert old.status_code == 400 and "save it again" in old.get_json()["error"]


def test_cors_for_students(client, gh):
    r = client.get("/api/accommodations/evaluation", query_string=WHERE)
    assert r.headers["Access-Control-Allow-Origin"] == "*"
    pre = client.options("/api/accommodations/verify")
    assert pre.status_code in (200, 204) and pre.headers["Access-Control-Allow-Origin"] == "*" and "POST" in pre.headers["Access-Control-Allow-Methods"]


def test_verify_matches_all_four_ignoring_case_and_accents(client, gh):
    r = client.post("/api/accommodations/verify", json={**WHERE, **MAYA})
    assert r.status_code == 200 and r.get_json()["first"] == "Maya"
    zoe = {"email": "zoe.ng@mail.utoronto.ca", "id": "1002", "first": "Zoe", "last": "Ng"}
    assert client.post("/api/accommodations/verify", json={**WHERE, **zoe}).status_code == 200


@pytest.mark.parametrize("change", [{"email": "maya@gmail.com"}, {"id": "1002"}, {"first": "Mia"}, {"last": "Castile"}])
def test_verify_refuses_any_mismatch(client, gh, change):
    r = client.post("/api/accommodations/verify", json={**WHERE, **MAYA, **change})
    assert r.status_code == 404 and "Student number" in r.get_json()["error"].replace("student number", "Student number")


def test_verify_refuses_dropped_students(client, gh):
    gone = {"email": "gone@mail.utoronto.ca", "id": "1003", "first": "Gone", "last": "Away"}
    assert client.post("/api/accommodations/verify", json={**WHERE, **gone}).status_code == 404


def test_verify_needs_an_email_field(client, gh):
    b = json.loads(json.dumps(BOOK)); b["fields"]["custom"] = []
    gh.put("csc258/f26/grades.json", json.dumps(b))
    r = client.post("/api/accommodations/verify", json={**WHERE, **MAYA})
    assert r.status_code == 409 and r.get_json()["code"] == "no-email"


def test_verify_is_rate_limited(client, gh):
    for _ in range(accommodations.LIMITS["verify"][0]):
        client.post("/api/accommodations/verify", json={**WHERE, **MAYA, "first": "x"})
    assert client.post("/api/accommodations/verify", json={**WHERE, **MAYA}).status_code == 429


def test_submit_standard(client, gh):
    r = client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"})
    assert r.status_code == 201, r.get_json()
    d = r.get_json()
    assert d["email"] == "maya.castillo@mail.utoronto.ca" and d["emailed"] is False   # no SMTP in tests
    [rec] = requests_of(gh)
    assert rec["kind"] == "standard" and rec["standard"] == "Write it the next day" and rec["status"] == "pending"
    assert rec["student"] == "1001" and rec["first"] == "Maya" and rec["evalName"] == "Midterm" and rec["course"] == "CSC258"
    assert gh.repo.read_text("csc258/f26/accommodations.json")[0]   # in the instructor's private files
    # A receipt, to the email on file
    assert mailer.sent[-1]["to"] == "maya.castillo@mail.utoronto.ca" and "received" in mailer.sent[-1]["subject"]
    assert "Write it the next day" in mailer.sent[-1]["body"] and rec["id"] in mailer.sent[-1]["body"]


def test_submit_standard_twice_is_refused(client, gh):
    client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"})
    r = client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"})
    assert r.status_code == 409 and r.get_json()["code"] == "duplicate"
    assert len(requests_of(gh)) == 1


def test_submit_alternate(client, gh):
    a1 = {**WHERE, "e": "a1"}
    assert client.post("/api/accommodations/submit", json={**a1, **MAYA, "kind": "alternate"}).status_code == 400   # says what
    assert client.post("/api/accommodations/submit", json={**a1, **MAYA, "kind": "standard"}).status_code == 400    # no approval needed
    r = client.post("/api/accommodations/submit", json={**a1, **MAYA, "kind": "alternate", "details": "A week, for a surgery."})
    assert r.status_code == 201
    # Another one is fine: each request is its own
    assert client.post("/api/accommodations/submit", json={**a1, **MAYA, "kind": "alternate", "details": "And a quiet room."}).status_code == 201
    assert [x["details"] for x in requests_of(gh)] == ["A week, for a surgery.", "And a quiet room."]


def test_alternate_not_offered(client, gh):
    r = client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "alternate", "details": "x"})
    assert r.status_code == 400 and not requests_of(gh)


def test_submit_wrong_person(client, gh):
    r = client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "id": "1002", "kind": "standard"})
    assert r.status_code == 404 and not requests_of(gh) and not mailer.sent


def test_submit_retries_when_the_file_changed(client, gh, monkeypatch):
    calls = {"n": 0}
    real = store.Repo.write_text

    def flaky(self, *a):
        calls["n"] += 1
        if calls["n"] == 1:   # the instructor saves the file just as the student's request goes in
            gh.put("csc258/f26/accommodations.json", json.dumps({"format": accommodations.FORMAT, "requests": [{"id": "r-other", "student": "1002", "eval": "a1", "kind": "alternate", "status": "pending"}]}))
        return real(self, *a)
    monkeypatch.setattr(store.Repo, "write_text", flaky)
    assert client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"}).status_code == 201
    assert [x["id"] for x in requests_of(gh)][0] == "r-other" and len(requests_of(gh)) == 2 and calls["n"] == 2


def decide(c, rid, decision, note="", headers=H):
    return c.post("/api/accommodations/decide", headers=headers, json={"offering": "csc258/f26", "id": rid, "decision": decision, "note": note})


def test_decide(client, gh):
    rid = client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"}).get_json()["id"]
    r = decide(gh.client, rid, "approved", note="See you Thursday at 6.")
    assert r.status_code == 200, r.get_json()
    rec = requests_of(gh)[0]
    assert rec["status"] == "approved" and rec["decidedBy"] == "Chandra Gummaluru" and rec["note"] == "See you Thursday at 6." and rec["decided"]
    m = mailer.sent[-1]
    assert m["to"] == "maya.castillo@mail.utoronto.ca" and m["subject"].endswith("approved") and "See you Thursday at 6." in m["body"]
    r = decide(gh.client, rid, "rejected", note="Sorry, I've had to reject it.")
    rec = requests_of(gh)[0]
    assert rec["status"] == "rejected" and mailer.sent[-1]["subject"].endswith("rejected")
    # The earlier decision stays, as history.
    assert [(h["status"], h["note"]) for h in rec["history"]] == [("approved", "See you Thursday at 6.")] and rec["history"][0]["decidedBy"] == "Chandra Gummaluru"
    decide(gh.client, rid, "approved")
    assert [h["status"] for h in requests_of(gh)[0]["history"]] == ["approved", "rejected"]


def test_decide_needs_access(client, gh):
    rid = client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"}).get_json()["id"]
    assert decide(client, rid, "approved").status_code == 401                 # a student isn't signed in
    other = app.test_client()
    make_user(other, email="ta@x.ca", name="T A", handle="ta")
    assert decide(other, rid, "approved").status_code == 404                  # someone else's course: not theirs to see
    assert decide(gh.client, rid, "approved", headers={}).status_code == 403  # not from Lectern's page
    assert decide(gh.client, "r-nope", "approved").status_code == 404
    assert decide(gh.client, rid, "maybe").status_code == 400
    assert requests_of(gh)[0]["status"] == "pending"


def test_decide_is_not_open_to_other_sites(client, gh):
    r = client.options("/api/accommodations/decide")
    assert "Access-Control-Allow-Origin" not in r.headers


def test_config_says_what_is_set_up(client):
    d = client.get("/api/config").get_json()
    assert d["email"] is False and d["app_url"] == "http://localhost/" and d["pages"] == "http://localhost/p/"


def with_deadline(gh, by, at=""):
    b = json.loads(json.dumps(BOOK))
    b["evals"][0]["accom"].update(by=by, byTime=at)
    gh.put("csc258/f26/grades.json", json.dumps(b))


def test_deadline_open(client, gh, monkeypatch):
    monkeypatch.setenv("LECTERN_TIMEZONE", "America/Toronto")
    with_deadline(gh, "2026-10-19", "17:00")
    # 16:59 in Toronto on Oct 19 (UTC-4)
    monkeypatch.setattr(accommodations, "clock", lambda: 1792443540.0)
    d = client.get("/api/accommodations/evaluation", query_string=WHERE).get_json()
    assert d["deadline"]["passed"] is False and d["deadline"]["text"] == "Monday, October 19, 2026, 17:00"
    assert client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"}).status_code == 201


def test_deadline_passed(client, gh, monkeypatch):
    monkeypatch.setenv("LECTERN_TIMEZONE", "America/Toronto")
    with_deadline(gh, "2026-10-19", "17:00")
    monkeypatch.setattr(accommodations, "clock", lambda: 1792443540.0 + 120)   # 17:01
    d = client.get("/api/accommodations/evaluation", query_string=WHERE).get_json()
    assert d["deadline"]["passed"] is True
    for path in ("verify", "submit"):
        r = client.post(f"/api/accommodations/{path}", json={**WHERE, **MAYA, "kind": "standard"})
        assert r.status_code == 410 and r.get_json()["code"] == "closed" and "has passed" in r.get_json()["error"]
    assert not requests_of(gh)


def test_deadline_without_time_is_end_of_day(client, gh, monkeypatch):
    monkeypatch.setenv("LECTERN_TIMEZONE", "America/Toronto")
    with_deadline(gh, "2026-10-19")
    monkeypatch.setattr(accommodations, "clock", lambda: 1792443540.0 + 6 * 3600)   # 22:59
    assert client.get("/api/accommodations/evaluation", query_string=WHERE).get_json()["deadline"] == {"date": "2026-10-19", "time": "23:59", "text": "Monday, October 19, 2026, 23:59", "passed": False}


# ── From the course page, signed in ──────────────────────────────────
HUB = "/api/hub/chandra/csc258/f26"


def hub_student(email):
    from test_students import code_for
    c = app.test_client()
    assert c.post(f"{HUB}/code", json={"email": email}, headers=H).status_code == 200
    assert c.post(f"{HUB}/verify", json={"email": email, "code": code_for(email)}, headers=H).status_code == 200
    return c


def test_a_signed_in_student_asks_on_the_course_page(gh):
    # Not signed in: no.
    assert app.test_client().get(f"{HUB}/accommodation?e=a1").status_code == 401
    st = hub_student("maya.castillo@mail.utoronto.ca")
    info = st.get(f"{HUB}/accommodation?e=a1").get_json()
    assert info["alternate"] and info["idLabel"] == "Student number"
    # Their number and name must be theirs (their email is the one they signed in with).
    r = st.post(f"{HUB}/accommodation", json={"e": "a1", "id": "1002", "first": "Maya", "last": "Castillo", "kind": "alternate", "details": "x"}, headers=H)
    assert r.status_code == 400 and r.get_json()["code"] == "mismatch"
    md = "Writing it **later**, see [my note](https://example.com/note) ![pic](https://x/y.png) <script>x</script>"
    r = st.post(f"{HUB}/accommodation", json={"e": "a1", "id": "1001", "first": "Maya", "last": "Castillo", "kind": "alternate", "details": md}, headers=H)
    assert r.status_code == 201, r.get_json()
    got = requests_of(gh)[-1]
    assert got["student"] == "1001" and got["kind"] == "alternate"
    assert got["details"] == "Writing it **later**, see [my note](https://example.com/note)  x"
    # Someone else's number with Maya's session: no.
    r = st.post(f"{HUB}/accommodation", json={"e": "mt", "id": "1002", "first": "Zoë", "last": "Ng", "kind": "standard"}, headers=H)
    assert r.status_code == 400


def test_a_student_sees_only_their_own_requests(gh):
    assert app.test_client().get(f"{HUB}/accommodations").status_code == 401
    st = hub_student("maya.castillo@mail.utoronto.ca")
    assert st.get(f"{HUB}/accommodations").get_json()["requests"] == []
    st.post(f"{HUB}/accommodation", json={"e": "a1", "id": "1001", "first": "Maya", "last": "Castillo", "kind": "alternate", "details": "Later, please."}, headers=H)
    mine = st.get(f"{HUB}/accommodations").get_json()["requests"]
    assert len(mine) == 1 and mine[0]["eval"] == "a1" and mine[0]["status"] == "pending" and mine[0]["details"] == "Later, please." and "email" not in mine[0]
    other = hub_student("zoe.ng@mail.utoronto.ca")
    assert other.get(f"{HUB}/accommodations").get_json()["requests"] == []
