"""Accommodation requests: the students' endpoints and the instructors' decisions, with GitHub and email faked.

Run with:  python -m pytest
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app, accommodations, ghapp, mailer  # noqa: E402

PRIV = "chandra/courses-private"
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
WHERE = {"r": "chandra/courses", "o": "csc258/f26", "e": "mt"}


class Fake:
    def __init__(self):
        self.files = {}
        self.commits = []
        self.pushers = {"ghu_teacher"}

    def read(self, full, path, token):
        assert token
        v = self.files.get((full, path))
        return (v["text"], v["sha"]) if v else (None, None)

    def write(self, full, path, text, sha, message, token):
        cur = self.files.get((full, path))
        if (cur and cur["sha"] != sha) or (not cur and sha):
            return False
        self.files[(full, path)] = {"text": text, "sha": f"s{len(self.commits) + 1}"}
        self.commits.append((full, path, message, token))
        return True


@pytest.fixture()
def gh(monkeypatch):
    f = Fake()
    f.files[(PRIV, "csc258/f26/grades.json")] = {"text": json.dumps(BOOK), "sha": "g1"}
    monkeypatch.setattr(ghapp, "installation_token", lambda full: "ghs_app")
    monkeypatch.setattr(ghapp, "read_file", f.read)
    monkeypatch.setattr(ghapp, "write_file", f.write)
    monkeypatch.setattr(ghapp, "can_push", lambda full, tok: tok in f.pushers)
    monkeypatch.setattr(ghapp, "request", lambda m, p, tok, body=None, auth="token": (200, {"login": "chandra"}) if p == "/user" else (404, None))
    monkeypatch.delenv("LECTERN_SMTP_HOST", raising=False)
    accommodations._books.clear()
    accommodations.limiter.reset()
    mailer.sent.clear()
    return f


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    return app.test_client()


def requests_of(gh):
    v = gh.files.get((PRIV, "csc258/f26/accommodations.json"))
    return json.loads(v["text"])["requests"] if v else []


def test_request_page(client):
    r = client.get("/request?r=chandra/courses&o=csc258/f26&e=mt")
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
    for bad in ({"r": "../x", "o": "csc258/f26", "e": "mt"}, {"r": "chandra/courses", "o": "csc258", "e": "mt"}, {"r": "chandra/courses", "o": "csc258/f26", "e": "a b"}):
        assert client.get("/api/accommodations/evaluation", query_string=bad).status_code == 400


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
    gh.files[(PRIV, "csc258/f26/grades.json")]["text"] = json.dumps(b)
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
    assert gh.commits[-1][3] == "ghs_app"   # written as the app
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
    real = gh.write

    def flaky(*a):
        calls["n"] += 1
        if calls["n"] == 1:
            gh.files[(PRIV, "csc258/f26/accommodations.json")] = {"text": json.dumps({"format": accommodations.FORMAT, "requests": [{"id": "r-other", "student": "1002", "eval": "a1", "kind": "alternate", "status": "pending"}]}), "sha": "x"}
            return False
        return real(*a)
    monkeypatch.setattr(ghapp, "write_file", flaky)
    assert client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"}).status_code == 201
    assert [x["id"] for x in requests_of(gh)][0] == "r-other" and len(requests_of(gh)) == 2


def decide(client, rid, decision, token="ghu_teacher", note=""):
    return client.post("/api/accommodations/decide", headers={"Authorization": f"Bearer {token}"} if token else {},
                       json={"repo": PRIV, "offering": "csc258/f26", "id": rid, "decision": decision, "note": note})


def test_decide(client, gh):
    rid = client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"}).get_json()["id"]
    r = decide(client, rid, "approved", note="See you Thursday at 6.")
    assert r.status_code == 200, r.get_json()
    rec = requests_of(gh)[0]
    assert rec["status"] == "approved" and rec["decidedBy"] == "chandra" and rec["note"] == "See you Thursday at 6." and rec["decided"]
    assert gh.commits[-1][3] == "ghu_teacher" and gh.commits[-1][2].startswith("Approve")   # the instructor's own commit
    m = mailer.sent[-1]
    assert m["to"] == "maya.castillo@mail.utoronto.ca" and m["subject"].endswith("approved") and "See you Thursday at 6." in m["body"]
    r = decide(client, rid, "rejected")
    assert requests_of(gh)[0]["status"] == "rejected" and mailer.sent[-1]["subject"].endswith("rejected")


def test_decide_needs_access(client, gh):
    rid = client.post("/api/accommodations/submit", json={**WHERE, **MAYA, "kind": "standard"}).get_json()["id"]
    assert decide(client, rid, "approved", token="").status_code == 401
    assert decide(client, rid, "approved", token="ghu_student").status_code == 403
    assert decide(client, "r-nope", "approved").status_code == 404
    assert decide(client, rid, "maybe").status_code == 400
    assert requests_of(gh)[0]["status"] == "pending"


def test_decide_is_not_open_to_other_sites(client, gh):
    r = client.options("/api/accommodations/decide")
    assert "Access-Control-Allow-Origin" not in r.headers


def test_config_says_what_is_set_up(client, monkeypatch):
    monkeypatch.delenv("LECTERN_GH_PRIVATE_KEY_FILE", raising=False)
    d = client.get("/api/github/config").get_json()
    assert d["requests"] is False and d["app_url"] == "http://localhost/"


def with_deadline(gh, by, at=""):
    b = json.loads(json.dumps(BOOK))
    b["evals"][0]["accom"].update(by=by, byTime=at)
    gh.files[(PRIV, "csc258/f26/grades.json")]["text"] = json.dumps(b)
    accommodations._books.clear()


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


def test_installation_token_signs_as_the_app(tmp_path, monkeypatch):
    """The app's JWT (signed with its key), swapped for a token for just that repository, then cached."""
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = tmp_path / "app.pem"
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    monkeypatch.setenv("LECTERN_GH_PRIVATE_KEY_FILE", str(pem))
    monkeypatch.setenv("LECTERN_GH_CLIENT_ID", "Iv1.abc")
    monkeypatch.delenv("LECTERN_GH_APP_ID", raising=False)
    ghapp._tokens.clear()
    calls = []

    def fake(method, path, token, body=None, auth="token"):
        calls.append((method, path, body, auth))
        claims = jwt.decode(token, key.public_key(), algorithms=["RS256"])
        assert claims["iss"] == "Iv1.abc" and claims["exp"] - claims["iat"] <= 600
        if path == "/repos/chandra/courses-private/installation":
            return 200, {"id": 77}
        if path == "/app/installations/77/access_tokens":
            return 201, {"token": "ghs_x"}
        return 404, None
    monkeypatch.setattr(ghapp, "request", fake)
    assert ghapp.installation_token("chandra/courses-private") == "ghs_x"
    assert calls[1][2] == {"repositories": ["courses-private"]} and calls[1][3] == "bearer"
    assert ghapp.installation_token("chandra/courses-private") == "ghs_x" and len(calls) == 2   # cached


def test_installation_token_without_a_key(monkeypatch):
    monkeypatch.delenv("LECTERN_GH_PRIVATE_KEY_FILE", raising=False)
    ghapp._tokens.clear()
    with pytest.raises(ghapp.GitHubError) as e:
        ghapp.installation_token("chandra/courses-private")
    assert e.value.status == 503
