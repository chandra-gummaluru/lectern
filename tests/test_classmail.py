"""Emailing a class from Lectern, and each offering's own email settings."""
import json

import pytest

from conftest import H, make_user
from server import app, classmail, db, mailer, store

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
        "fields": {"idLabel": "Student number", "emailDomain": "mail.utoronto.ca",
                   "custom": [{"id": "email", "label": "Email"}, {"id": "sec", "label": "Section"}]},
        "evals": [], "groups": [], "marks": {}, "overrides": {},
        "students": [
            {"num": "1", "first": "Ada", "last": "Lovelace", "f": {"email": "ada@mail.utoronto.ca", "sec": "L0101"}},
            {"num": "2", "first": "Alan", "last": "Turing", "f": {"email": "alan@MAIL.utoronto.ca", "sec": "L0201"}},
            {"num": "3", "first": "Grace", "last": "Hopper", "f": {"email": "grace@gmail.com", "sec": "L0101"}},     # not at the domain
            {"num": "4", "first": "Ed", "last": "Dijkstra", "f": {"sec": "L0201"}},                                   # no email
            {"num": "5", "first": "Gone", "last": "Away", "f": {"email": "gone@mail.utoronto.ca"}, "dropped": True},
        ]}
CFG = {"host": "smtp.example.org", "port": "465", "security": "ssl", "user": "csc258@example.org", "from": "CSC258 <csc258@example.org>"}


@pytest.fixture()
def course(client, user):
    r = store.Repo(user["id"], "priv")
    r.commit({"csc258/f26/grades.json": json.dumps(BOOK).encode()}, "seed", r.head())
    return user


@pytest.fixture()
def smtp(monkeypatch):
    """No real SMTP: deliveries are recorded; the password "right" works."""
    out = {"one": [], "many": []}

    def deliver(to, subject, body, reply_to=None, cfg=None):
        out["one"].append((to, cfg))
        return "" if (cfg or {}).get("password") == "right" else "535 Authentication failed"

    def deliver_many(to_list, subject, body, reply_to=None, cfg=None, done=None):
        out["many"].append({"to": list(to_list), "subject": subject, "body": body, "reply_to": reply_to, "cfg": cfg})
        for t in to_list:
            done and done(t, "")
        return {}
    monkeypatch.setattr(mailer, "deliver", deliver)
    monkeypatch.setattr(mailer, "deliver_many", deliver_many)
    return out


def test_who_gets_it(client, course):
    j = client.get("/api/mail/chandra/csc258/f26").get_json()
    assert j["total"] == 2 and j["missingCount"] == 2 and j["domain"] == "mail.utoronto.ca"
    assert {m["num"] for m in j["missing"]} == {"3", "4"}                    # wrong domain, none; the dropped one isn't counted
    assert [s["name"] for s in j["sections"]] == ["L0101", "L0201"]


def test_offering_settings_test_first_and_are_kept_secret(client, course, smtp):
    U = "/api/mail/chandra/csc258/f26"
    r = client.post(f"{U}/settings", json={**CFG, "smtpPassword": "wrong"}, headers=H)
    assert r.status_code == 400 and "nothing was saved" in r.get_json()["error"]
    assert client.get(U).get_json()["settings"]["source"] == ""
    r = client.post(f"{U}/settings", json={**CFG, "smtpPassword": "right"}, headers=H)
    assert r.status_code == 200 and smtp["one"][-1][0] == course["email"]     # the test went to whoever saved it
    s = client.get(U).get_json()["settings"]
    assert s["source"] == "offering" and s["hasPassword"] and s["from"] == CFG["from"] and "right" not in json.dumps(s)
    assert "right" not in db.one("SELECT smtp FROM offering_mail")["smtp"]   # encrypted
    assert classmail.settings_for(course["id"], "csc258/f26")["password"] == "right"
    assert classmail.settings_for(course["id"], "csc108/w26")["source"] != "offering"   # only this offering
    # Blank password keeps it.
    assert client.post(f"{U}/settings", json={**CFG, "from": "Other <o@example.org>"}, headers=H).status_code == 200
    assert classmail.settings_for(course["id"], "csc258/f26")["password"] == "right"
    assert client.post(f"{U}/settings", json={"action": "remove"}, headers=H).status_code == 200
    assert classmail.settings_for(course["id"], "csc258/f26")["source"] != "offering"


def test_send_to_the_class(client, course, smtp):
    U = "/api/mail/chandra/csc258/f26"
    r = client.post(f"{U}/send", json={"to": "all", "subject": "Midterm", "body": "Room BA 1130."}, headers=H)
    assert r.status_code == 400 and r.get_json()["code"] == "no-smtp"       # no email set up anywhere
    client.post(f"{U}/settings", json={**CFG, "smtpPassword": "right"}, headers=H)
    r = client.post(f"{U}/send", json={"to": "all", "subject": "Midterm", "body": "Room BA 1130."}, headers=H)
    assert r.status_code == 200 and r.get_json()["total"] == 2
    m = smtp["many"][-1]
    assert sorted(m["to"]) == ["ada@mail.utoronto.ca", "alan@mail.utoronto.ca"]
    assert m["reply_to"] == course["email"] and m["cfg"]["from"] == CFG["from"]
    r = client.post(f"{U}/send", json={"to": "section:L0201", "subject": "Tutorial", "body": "Moved."}, headers=H)
    assert r.get_json()["total"] == 1 and smtp["many"][-1]["to"] == ["alan@mail.utoronto.ca"]
    assert client.post(f"{U}/send", json={"to": "section:nope", "subject": "x", "body": "y"}, headers=H).status_code == 400
    assert client.post(f"{U}/send", json={"to": "all", "subject": "a\nBcc: x@y.z", "body": "y"}, headers=H).status_code == 400
    sends = client.get(U).get_json()["sends"]
    assert sends[0]["subject"] == "Tutorial" and sends[0]["done"] and sends[0]["sent"] == 1


def test_only_instructors(client, course, smtp):
    ta = app.test_client()
    t = make_user(ta, email="ta@x.ca", name="T A", handle="ta")
    db.run("INSERT INTO members (owner_id, offering, user_id, role, added) VALUES (?, 'csc258/f26', ?, 'ta', 0)", (course["id"], t["id"]))
    U = "/api/mail/chandra/csc258/f26"
    assert ta.get(U).status_code == 403
    assert ta.post(f"{U}/send", json={"to": "all", "subject": "x", "body": "y"}, headers=H).status_code == 403
    assert ta.post(f"{U}/settings", json={**CFG, "smtpPassword": "right"}, headers=H).status_code == 403
    other = app.test_client()
    make_user(other, email="o@x.ca", name="O", handle="other")
    assert other.get(U).status_code == 404
    db.run("UPDATE members SET role = 'coordinator'")
    assert ta.get(U).status_code == 200


def test_accommodation_emails_use_the_offerings_settings(client, course, smtp):
    client.post("/api/mail/chandra/csc258/f26/settings", json={**CFG, "smtpPassword": "right"}, headers=H)
    cfg = classmail.settings_for(course["id"], "csc258/f26")
    assert cfg["from"] == CFG["from"] and cfg["host"] == CFG["host"]


def test_a_saved_announcement_is_emailed_to_its_students(client, course, smtp):
    U = "/api/mail/chandra/csc258/f26/announcement"
    r = client.post(U, json={"title": "Midterm rooms", "body": "**BA 1130**"}, headers=H)
    assert r.status_code == 200 and r.get_json()["emailed"] is False      # no email set up: saved, not emailed
    client.post("/api/mail/chandra/csc258/f26/settings", json={**CFG, "smtpPassword": "right"}, headers=H)
    r = client.post(U, json={"title": "Midterm rooms", "body": "**BA 1130**"}, headers=H)
    assert r.get_json()["emailed"] and r.get_json()["total"] == 2
    m = smtp["many"][-1]
    assert m["subject"] == "CSC258: Midterm rooms" and "BA 1130" in m["body"] and "/c/chandra/csc258/f26/#announcements" in m["body"]
    # For one section: its students.
    b = json.loads(json.dumps(BOOK)); b["students"][0]["groups"] = ["g1"]; b["students"][1]["groups"] = ["g2"]
    r_ = store.Repo(course["id"], "priv"); r_.commit({"csc258/f26/grades.json": json.dumps(b).encode()}, "x", r_.head())
    r = client.post(U, json={"title": "Tutorial", "body": "Moved.", "groups": ["g2"]}, headers=H)
    assert r.get_json()["total"] == 1 and smtp["many"][-1]["to"] == ["alan@mail.utoronto.ca"]
    # A TA: only for sections they run.
    ta = app.test_client()
    t = make_user(ta, email="ta@x.ca", name="T A", handle="ta")
    db.run("INSERT INTO members (owner_id, offering, user_id, role, added) VALUES (?, 'csc258/f26', ?, 'ta', 0)", (course["id"], t["id"]))
    assert ta.post(U, json={"title": "x", "body": "y"}, headers=H).status_code == 403
    r_.commit({"csc258/f26/groups.json": json.dumps({"format": "lectern-groups/1", "groups": [{"id": "g2", "name": "TUT1", "kind": "tutorial", "people": [str(t["id"])], "items": []}]}).encode()}, "g", r_.head())
    assert ta.post(U, json={"title": "x", "body": "y", "groups": ["g2"]}, headers=H).status_code == 200
    assert ta.post(U, json={"title": "x", "body": "y", "groups": ["g1"]}, headers=H).status_code == 403


def _book(user, **changes):
    b = json.loads(json.dumps(BOOK)); b.update(changes)
    r = store.Repo(user["id"], "priv")
    r.commit({"csc258/f26/grades.json": json.dumps(b).encode()}, "seed", r.head())


def test_marks_emailed_when_out_and_when_changed(client, course, smtp):
    U = "/api/mail/chandra/csc258/f26"
    client.post(f"{U}/settings", json={**CFG, "smtpPassword": "right"}, headers=H)
    mt = {"id": "mt", "name": "Test 1", "type": "test"}
    _book(course, evals=[mt], marks={"1": {"mt": {"pts": 30}}, "2": {"mt": {"pts": 40}}})
    # Not visible yet: nobody's emailed.
    assert client.post(f"{U}/grades", json={}, headers=H).get_json()["emailed"] == 0
    assert client.get(f"{U}/grades").get_json()["evals"]["mt"] == {"released": False, "told": 0, "waiting": 2, "changed": 0}
    _book(course, evals=[{**mt, "released": True}], marks={"1": {"mt": {"pts": 30}}, "2": {"mt": {"pts": 40}}})
    assert client.post(f"{U}/grades", json={}, headers=H).get_json()["emailed"] == 2
    sent = smtp["many"][-1]
    assert sorted(sent["to"]) == ["ada@mail.utoronto.ca", "alan@mail.utoronto.ca"] and "is out" in sent["subject"] and "#evaluation/mt" in sent["body"]
    assert client.post(f"{U}/grades", json={}, headers=H).get_json()["emailed"] == 0          # once
    # A mark changed: it waits for Email Them.
    _book(course, evals=[{**mt, "released": True}], marks={"1": {"mt": {"pts": 33}}, "2": {"mt": {"pts": 40}}})
    assert client.post(f"{U}/grades", json={}, headers=H).get_json()["emailed"] == 0
    assert client.get(f"{U}/grades").get_json()["evals"]["mt"]["changed"] == 1
    assert client.post(f"{U}/grades", json={"e": "mt", "changes": True}, headers=H).get_json()["emailed"] == 1
    assert smtp["many"][-1]["to"] == ["ada@mail.utoronto.ca"] and "changed" in smtp["many"][-1]["subject"]
    # Turned off in the email settings: none go out (and they're not saved up for later).
    client.post(f"{U}/prefs", json={"replyTo": "", "signature": "", "send": {"grades": False}}, headers=H)
    _book(course, evals=[{**mt, "released": True}], marks={"1": {"mt": {"pts": 34}}, "2": {"mt": {"pts": 40}}})
    assert client.post(f"{U}/grades", json={"e": "mt", "changes": True}, headers=H).get_json()["emailed"] == 0


def test_email_settings_reply_to_and_signature(client, course, smtp):
    U = "/api/mail/chandra/csc258/f26"
    client.post(f"{U}/settings", json={**CFG, "smtpPassword": "right"}, headers=H)
    assert client.get(f"{U}/prefs").get_json()["prefs"]["send"]["announcements"] is True
    assert client.post(f"{U}/prefs", json={"replyTo": "not an address"}, headers=H).status_code == 400
    p = client.post(f"{U}/prefs", json={"replyTo": "csc258@utoronto.ca", "signature": "— The CSC258 team", "send": {"announcements": False}}, headers=H).get_json()["prefs"]
    assert p["send"]["announcements"] is False and p["send"]["grades"] is True
    client.post(f"{U}/send", json={"to": "all", "subject": "Hi", "body": "Hello."}, headers=H)
    m = smtp["many"][-1]
    assert m["reply_to"] == "csc258@utoronto.ca" and m["body"].rstrip().endswith("— The CSC258 team")


def test_a_rich_text_signature_is_plain_text_and_html(client, course, smtp):
    U = "/api/mail/chandra/csc258/f26"
    client.post(f"{U}/settings", json={**CFG, "smtpPassword": "right"}, headers=H)
    client.post(f"{U}/prefs", json={"replyTo": "", "signature": "— **The CSC258 team**\n[Course page](https://example.com/c)"}, headers=H)
    client.post(f"{U}/send", json={"to": "all", "subject": "Hi", "body": "Hello <all>."}, headers=H)
    b = smtp["many"][-1]["body"]
    assert b.rstrip().endswith("— The CSC258 team\nCourse page (https://example.com/c)") and "**" not in b
    assert "<b>The CSC258 team</b>" in b.html and '<a href="https://example.com/c">Course page</a>' in b.html and "Hello &lt;all&gt;." in b.html
    msg = mailer._message({"from": "x@y.ca"}, "s@u.ca", "Hi", b)
    assert msg.is_multipart() and msg.get_body(("html",)) is not None
