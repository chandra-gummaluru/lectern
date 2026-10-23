"""Emailing the class, end to end against the real server (SMTP replaced by a recorder):
the gradebook's Settings get the email domain; the Students page says who's missing one; a student's
email is set on their page; the offering page's Email the Class gets its own email settings (a test
email first) and sends to everyone, one email each, replies to the instructor. Screenshots in shots/.

Run:  python tests/browser/flow_mail.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
        "fields": {"idLabel": "Student number", "custom": [{"id": "sec", "label": "Section"}]},
        "evals": [], "groups": [], "marks": {}, "overrides": {},
        "students": [
            {"num": "1", "first": "Ada", "last": "Lovelace", "f": {"email": "ada@mail.utoronto.ca", "sec": "L0101"}},
            {"num": "2", "first": "Alan", "last": "Turing", "f": {"email": "alan@gmail.com", "sec": "L0201"}},
            {"num": "3", "first": "Grace", "last": "Hopper", "f": {"sec": "L0101"}},
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
        srv.sign_in(page, hash="#/csc258/f26/settings")

        # 1. Settings: Email is built in; set the domain.
        page.wait_for_selector(G + "input[data-fl='emailDomain']")
        page.fill(G + "input[data-fl='emailDomain']", "@Mail.UToronto.ca"); page.wait_for_timeout(600)
        page.locator(G + ".set-card").first.screenshot(path=f"{OUT}/m01-settings-email.png")
        assert not page.query_selector(G + "[data-act='fld-del'][data-id='email']"), "Email can't be deleted"
        page.keyboard.press("Control+s"); page.wait_for_timeout(1500)
        saved = json.loads(srv.text("priv", "csc258/f26/grades.json"))
        print("domain saved:", saved["fields"]["emailDomain"], [f["id"] for f in saved["fields"]["custom"]])
        assert saved["fields"]["emailDomain"] == "mail.utoronto.ca" and saved["fields"]["custom"][0]["id"] == "email"

        # 2. The gradebook says who's missing one; set Grace's on her page.
        page.evaluate("location.hash = '#/csc258/f26/gradebook'"); page.wait_for_selector(G + ".notice")
        page.screenshot(path=f"{OUT}/m02-students-missing.png")
        note = page.inner_text(G + ".notice")
        print("gradebook note:", note.replace("\n", " ")[:200])
        assert "2 students don't have an @mail.utoronto.ca email" in note
        page.click(G + ".notice [data-num='3']"); page.wait_for_selector(G + "input[data-ed='email']")
        page.fill(G + "input[data-ed='email']", "grace@mail.utoronto.ca"); page.press(G + "input[data-ed='email']", "Tab"); page.wait_for_timeout(400)
        page.screenshot(path=f"{OUT}/m03-student-email.png")
        page.keyboard.press("Control+s"); page.wait_for_timeout(1500)
        saved = json.loads(srv.text("priv", "csc258/f26/grades.json"))
        assert next(s for s in saved["students"] if s["num"] == "3")["f"]["email"] == "grace@mail.utoronto.ca"

        # 3. The offering page: Email the Class.
        page.evaluate("location.hash = '#/csc258/f26'"); page.wait_for_selector("#lt-mail-set")
        txt = page.inner_text("#lt-mail")
        print("email part:", txt.replace("\n", " ")[:220])
        assert "2 students" in txt and "1 enrolled student doesn't" in txt and page.is_disabled("#lt-mail-new")
        page.locator("#lt-mail").screenshot(path=f"{OUT}/m04-mail-part.png")
        page.click("#lt-mail-set"); page.wait_for_selector("#ms-host")
        page.fill("#ms-host", "smtp.example.org"); page.select_option("#ms-sec", "ssl"); page.fill("#ms-port", "465")
        page.fill("#ms-user", "csc258@example.org"); page.fill("#ms-pw", "wrong"); page.fill("#ms-from", "CSC258 <csc258@example.org>")
        page.click(".lt-modal [type=submit]")
        expect(page.locator(".lt-modal .lt-err")).to_contain_text("nothing was saved")
        page.fill("#ms-pw", "right"); page.screenshot(path=f"{OUT}/m05-mail-settings.png"); page.click(".lt-modal [type=submit]")
        page.wait_for_selector("#ms-host", state="detached")
        assert tried[-1][0] == "chandra@utoronto.ca"
        page.wait_for_selector("#lt-mail-new:not([disabled])")
        page.click("#lt-mail-new"); page.wait_for_selector("#cm-subj")
        print("to options:", page.eval_on_selector_all("#cm-to option", "os => os.map(o => o.textContent)"))
        page.fill("#cm-subj", "Midterm room"); page.fill("#cm-body", "The midterm is in BA 1130.")
        page.screenshot(path=f"{OUT}/m06-compose.png")
        page.click(".lt-modal [type=submit]"); page.wait_for_selector("[data-yes]"); page.click("[data-yes]")
        expect(page.locator("#lt-toast-root")).to_contain_text("Sending to 2 students")
        page.wait_for_selector("#lt-mail .lt-mail-log"); page.wait_for_timeout(300)
        page.locator("#lt-mail").screenshot(path=f"{OUT}/m07-sent.png")
        print("sent:", sent[-1])
        assert sorted(sent[-1]["to"]) == ["ada@mail.utoronto.ca", "grace@mail.utoronto.ca"]
        assert sent[-1]["reply_to"] == "chandra@utoronto.ca" and sent[-1]["from"] == "CSC258 <csc258@example.org>"
        expect(page.locator("#lt-mail .lt-mail-log")).to_contain_text("Midterm room")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_mail: OK")


if __name__ == "__main__":
    main()
