"""An announcement, end to end against the real server: written on Lectern's Announcements page, its date
and time from the calendar (time typed, then cleared), saved (not emailed), then deleted (asks first).
Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_ann.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC108", "term": "Fall 2026"},
        "fields": {"idLabel": "Student number", "emailDomain": "", "custom": [{"id": "email", "label": "Email"}]},
        "evals": [], "groups": [], "students": [], "marks": {}, "overrides": {}}
PATH = "csc108/f26/announcements.json"


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("priv", {"csc108/f26/grades.json": json.dumps(BOOK)})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(page, hash="#/csc108/f26")
        page.wait_for_selector("#lt-anns"); page.click("#lt-anns")
        page.wait_for_selector("#an-new"); page.click("#an-new")
        page.wait_for_selector("#an-title")
        page.fill("#an-title", "Room change")
        expect(page.locator("#an-h")).to_have_text("Room change")
        print("date now:", page.inner_text("#an-when"))

        # The calendar: Oct 20, 2026, at 9:30.
        page.click("#an-when"); page.wait_for_selector(".lxw-pop")
        page.screenshot(path=f"{OUT}/180-ann-when.png")
        for _ in range(36):
            if page.query_selector(".lxw-pop [data-day='2026-10-20']"): break
            page.click(".lxw-pop [data-w='prev']" if page.evaluate("new Date() > new Date('2026-10-31')") else ".lxw-pop [data-w='next']")
        page.click(".lxw-pop [data-day='2026-10-20']")
        page.fill(".lxw-pop .lxw-t", "9:30"); page.keyboard.press("Enter")
        expect(page.locator("#an-when")).to_have_text("Tue, Oct 20, 2026 · 09:30")
        print("picked:", page.inner_text("#an-when"))
        # No time: the date alone.
        page.click("#an-when"); page.wait_for_selector(".lxw-pop .lxw-t")
        page.fill(".lxw-pop .lxw-t", ""); page.mouse.click(5, 700)
        expect(page.locator("#an-when")).to_have_text("Tue, Oct 20, 2026")
        print("no time:", page.inner_text("#an-when"))

        # The message, then Save (without emailing it).
        page.locator("#an-body [contenteditable]").first.click(); page.keyboard.type("We're in BA 1130 on Tuesday.")
        page.uncheck("#an-mail")
        page.screenshot(path=f"{OUT}/181-ann-page.png", full_page=True)
        page.click("#an-save")
        expect(page.locator("#lt-toast-root")).to_contain_text("Saved")
        saved = json.loads(srv.text("priv", PATH))["items"]
        print("saved:", [(x["title"], x["date"]) for x in saved])
        assert len(saved) == 1 and saved[0]["title"] == "Room change" and saved[0]["date"].startswith("Oct 20, 2026") and "BA 1130" in saved[0]["body"], saved
        print("path:", page.inner_text("#lt-path").replace("\n", " "))

        # Delete: it asks first; Cancel keeps it, Delete deletes it.
        page.wait_for_selector("#an-del"); page.click("#an-del")
        page.wait_for_selector(".lt-modal [data-yes]")
        print("asks:", page.inner_text(".lt-modal h2"))
        page.click(".lt-modal [data-no]"); page.wait_for_selector(".lt-modal", state="detached")
        assert len(json.loads(srv.text("priv", PATH))["items"]) == 1
        page.click("#an-del"); page.click(".lt-modal [data-yes]")
        page.wait_for_selector(".lx-empty")
        page.wait_for_timeout(1500)
        assert json.loads(srv.text("priv", PATH))["items"] == [], srv.text("priv", PATH)
        print("deleted")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_ann: OK")


if __name__ == "__main__":
    main()
