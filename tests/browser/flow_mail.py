"""Emailing the class, end to end against the real server (SMTP replaced by a recorder): the offering's
Email card gets its own sender (a test email to you first; a failing one saves nothing), then a new
announcement is emailed to every student with an email at the gradebook's domain, one email each, with
replies to the instructor. Screenshots in shots/.

Run:  python tests/browser/flow_mail.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
        "fields": {"idLabel": "Student number", "emailDomain": "mail.utoronto.ca", "custom": [{"id": "email", "label": "Email"}, {"id": "sec", "label": "Section"}]},
        "evals": [], "groups": [], "marks": {}, "overrides": {},
        "students": [
            {"num": "1", "first": "Ada", "last": "Lovelace", "f": {"email": "ada@mail.utoronto.ca", "sec": "L0101"}},
            {"num": "2", "first": "Alan", "last": "Turing", "f": {"email": "alan@gmail.com", "sec": "L0201"}},       # not at the domain: not emailed
            {"num": "3", "first": "Grace", "last": "Hopper", "f": {"email": "grace@mail.utoronto.ca", "sec": "L0101"}},
        ]}
G = "[data-lt-tool='grades'] "


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        from server import mailer
        tried, sent = [], []
        mailer.deliver = lambda to, subject, body, reply_to=None, cfg=None: (tried.append((to, cfg)), "" if (cfg or {}).get("password") == "right" else "535 Authentication failed")[1]
        mailer.deliver_many = lambda to_list, subject, body, reply_to=None, cfg=None, done=None: (sent.append({"to": list(to_list), "subject": subject, "reply_to": reply_to, "from": (cfg or {}).get("from")}), [done and done(t, "") for t in to_list], {})[2]
        srv.account()
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(BOOK)})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        block_cdns(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(page, hash="#/csc258/f26")

        # 1. The offering's Email card: its own sender. A test that fails saves nothing; one that works is kept.
        page.wait_for_selector("#lt-email #em-edit")
        page.locator("#lt-email").screenshot(path=f"{OUT}/m01-email-card.png")
        page.click("#lt-email #em-edit"); page.wait_for_selector("#em-host")
        page.fill("#em-from", "CSC258 <csc258@example.org>"); page.fill("#em-host", "smtp.example.org"); page.select_option("#em-sec", "ssl")
        page.fill("#em-port", "465"); page.fill("#em-user", "csc258@example.org"); page.fill("#em-pw", "wrong")
        page.click("#em-save")
        expect(page.locator("#em-err")).to_contain_text("nothing was saved")
        page.fill("#em-pw", "right"); page.locator("#lt-email").screenshot(path=f"{OUT}/m02-email-sender.png"); page.click("#em-save")
        page.wait_for_selector("#em-host", state="detached")
        assert tried[-1][0] == "chandra@utoronto.ca", tried[-1]
        expect(page.locator("#lt-email")).to_contain_text("CSC258 <csc258@example.org>")
        page.locator("#lt-email").screenshot(path=f"{OUT}/m03-email-saved.png")

        # 2. A new announcement, emailed to the students with an email at the domain (not Alan, @gmail.com).
        page.evaluate("location.hash = '#/csc258/f26/announcements'"); page.wait_for_selector("#an-new")
        page.click("#an-new"); page.wait_for_selector("#an-title")
        page.fill("#an-title", "Midterm room")
        page.click("#an-body [contenteditable]"); page.keyboard.type("The midterm is in BA 1130.")
        page.wait_for_timeout(300)
        assert page.is_checked("#an-mail"), "a new announcement is emailed by default"
        page.screenshot(path=f"{OUT}/m04-announcement.png")
        page.click("#an-save")
        expect(page.locator("#lt-toast-root")).to_contain_text("emailed to 2 students")
        print("sent:", sent[-1])
        assert sorted(sent[-1]["to"]) == ["ada@mail.utoronto.ca", "grace@mail.utoronto.ca"]
        assert sent[-1]["reply_to"] == "chandra@utoronto.ca" and sent[-1]["from"] == "CSC258 <csc258@example.org>"
        assert "Midterm room" in sent[-1]["subject"]
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_mail: OK")


if __name__ == "__main__":
    main()
