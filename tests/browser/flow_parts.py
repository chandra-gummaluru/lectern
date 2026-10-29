"""Announcements and the offering's title and description, made in Lectern, on the course page; the course
page itself is a preview with each tab's visibility.

1. Announcements: it starts from the course page's own; a new one, dated in Week 7, saves by itself;
   the hub shows it in Announcements and in that week.
2. The offering's page: no About or Course Page cards, and no Settings; its title and description are
   changed under its code and save by themselves; the hub's header and About show them.
3. View Course Page: the course page itself (the hub), in a new tab.
4. A new offering asks for its title, and starts with it.
Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_parts.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json"), encoding="utf-8").read()
C = "[data-lt-tool='course'] "


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("pub", {"csc258/f26/course.json": DATA})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        me = ctx.new_page()
        me.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(me, hash="#/csc258/f26")
        me.wait_for_selector("#lt-anns")
        me.screenshot(path=f"{OUT}/200-offering.png", full_page=True)

        # 1. Announcements
        me.click("#lt-anns"); me.wait_for_selector("[data-an]")
        expect(me.locator("[data-an]").first).to_contain_text("Welcome to CSC258!")
        me.click("#an-new"); me.wait_for_selector("#an-title")
        me.fill("#an-title", "Midterm rooms posted")
        # When: the calendar, as in Evaluations (to October 2026, the 27th, then the time typed).
        me.click("#an-when")
        for _ in range(24):
            if me.inner_text(".lxw-head b") == "October 2026": break
            me.click(".lxw-head [data-w=%s]" % ("prev" if me.evaluate("new Date().getFullYear() * 12 + new Date().getMonth()") > 2026 * 12 + 9 else "next"))
        me.click(".lxw-days [data-day='2026-10-27']")
        me.fill(".lxw-t", "9:30 am"); me.press(".lxw-t", "Enter")
        expect(me.locator("#an-when")).to_have_text("Tue, Oct 27, 2026 · 09:30")
        me.click("#an-body .rt-ed")   # the message: rich text (bold, italic, links, lists)
        me.keyboard.type("Rooms by "); me.keyboard.press("Control+b"); me.keyboard.type("last name"); me.keyboard.press("Control+b"); me.keyboard.type(": see the list.")
        expect(me.locator("#an-status")).to_have_text("Not saved yet")   # kept only when it's saved
        assert len(json.loads(srv.text("priv", "csc258/f26/announcements.json") or '{"items":[1]}')["items"]) != 2
        me.screenshot(path=f"{OUT}/201-announcement.png")
        me.click("#an-save"); me.wait_for_timeout(1500)
        items = json.loads(srv.text("priv", "csc258/f26/announcements.json"))["items"]
        assert [a["title"] for a in items] == ["Welcome to CSC258!", "Midterm rooms posted"] and items[1]["date"] == "Oct 27, 2026, 09:30" and "**last name**" in items[1]["body"], items
        print("1 announcements:", [a["title"] for a in items])

        # 2. The offering's page: title and description under the code
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        me.wait_for_selector("#lt-desc")
        assert not me.query_selector("#lt-about-open, [data-go=course], [data-part=settings].lt-off-acts, .lt-off-acts [data-part]"), "old cards or Settings are still there"
        assert me.locator(".lt-part-head h2").all_inner_texts()[:4] == ["Announcements", "Activities", "Evaluations", "Gradebook"], me.locator(".lt-part-head h2").all_inner_texts()
        expect(me.locator("#lt-title")).to_have_text("Computer Organization")
        me.fill("#lt-title", "Computer Organization and Design")
        me.fill("#lt-desc .rt-ed", "From transistors to processors.")
        me.wait_for_timeout(1500)
        expect(me.locator("#lt-about-st")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/202-offering-about.png")
        ab = json.loads(srv.text("priv", "csc258/f26/about.json"))
        assert ab["title"] == "Computer Organization and Design" and ab["description"] == "From transistors to processors.", ab
        print("2 title and description saved")

        v = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
        v.goto(srv.base + "c/chandra/csc258/f26/"); v.wait_for_selector(".hs-sec")
        links = v.eval_on_selector_all(".hs-link b", "els => els.map(e => e.textContent.trim())")
        assert links[:3] == ["All Announcements", "All Weeks", "Evaluations"], links   # under the newest announcement and this week: their All rows
        expect(v.locator(".hb-main")).to_contain_text("Midterm rooms posted")   # the newest announcement, in full
        v.click(".hs-row:has-text('About the Course')")
        expect(v.locator(".ab-desc")).to_contain_text("From transistors to processors.")   # on About the Course
        expect(v.locator(".hb-title")).to_have_text("CSC258: Computer Organization and Design")
        expect(v.locator(".hb-sub")).to_have_text("Fall 2026 · University of Toronto")
        v.screenshot(path=f"{OUT}/203-hub-about.png", full_page=True)
        print("3 the hub shows them")

        # 3. View Course Page: the course page itself, in a new tab.
        with me.context.expect_page() as np:
            me.click("#lt-view-page")
        cp = np.value; cp.wait_for_selector(".hs-sec")
        assert cp.url.split("#")[0].endswith("/c/chandra/csc258/f26/"), cp.url
        expect(cp.locator(".hb-title")).to_have_text("CSC258: Computer Organization and Design")
        cp.close()
        print("4 View Course Page opens the course page")

        # 4. A new offering: its title first.
        me.click("#lt-home"); me.wait_for_selector("#lt-new"); me.click("#lt-new")
        me.fill("#no-c", "csc369"); me.click(".lt-modal [data-ok]")
        expect(me.locator("#no-err")).to_contain_text("title")
        me.fill("#no-title", "Operating Systems")
        me.fill("#no-dom", "@mail.utoronto.ca"); me.fill("#no-more", "UTORid, Email")   # what each student has (Email they have already)
        me.screenshot(path=f"{OUT}/204-new-offering-dialog.png")
        me.click(".lt-modal [data-ok]")
        me.wait_for_selector("#lt-title")
        expect(me.locator("#lt-title")).to_have_text("Operating Systems")
        t = me.evaluate("location.hash").split("/")[-1]
        assert json.loads(srv.text("priv", f"csc369/{t}/about.json"))["title"] == "Operating Systems"
        F = json.loads(srv.text("priv", f"csc369/{t}/grades.json"))["fields"]
        assert F["idLabel"] == "Student Number" and F["emailDomain"] == "mail.utoronto.ca" and [f["label"] for f in F["custom"]] == ["Email", "UTORid"], F
        me.screenshot(path=f"{OUT}/205-new-offering.png")
        print("5 new offering made with its title:", t)
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
