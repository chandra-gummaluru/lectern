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
