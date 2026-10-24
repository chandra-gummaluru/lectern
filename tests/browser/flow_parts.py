"""Announcements and About, made in Lectern, on the course page; the course page itself is a preview
with each tab's visibility.

1. Announcements: it starts from the course page's own; a new one, dated in Week 7, saves by itself;
   the hub shows it in Announcements and in that week.
2. About: the description changes, a section and a policy are added; the hub's About shows them, and
   the gradebook-free page still works.
3. The course page (Lectern): the new tabs (This week first, About), nothing to edit, Lectures made
   signed-in only with its lock, saved; a visitor sees Lectures locked. Preview shows the visitor's view.
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
        me.click("#lt-anns"); me.wait_for_selector(".an-card")
        expect(me.locator(".an-card").first).to_contain_text("Welcome to CSC258!")
        me.click("#an-new"); me.wait_for_selector("#an-title")
        me.fill("#an-title", "Midterm rooms posted")
        me.fill("#an-date", "2026-10-27"); me.dispatch_event("#an-date", "change")
        me.fill("#an-time", "09:30"); me.dispatch_event("#an-time", "change")
        me.fill("#an-body", "Rooms by **last name**:\n\n- A–L: EX 100\n- M–Z: EX 200")
        me.wait_for_timeout(1500)
        expect(me.locator("#an-status")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/201-announcement.png")
        items = json.loads(srv.text("priv", "csc258/f26/announcements.json"))["items"]
        assert [a["title"] for a in items] == ["Welcome to CSC258!", "Midterm rooms posted"] and items[1]["date"] == "Oct 27, 2026, 09:30", items
        print("1 announcements:", [a["title"] for a in items])

        # 2. About
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        me.click("#lt-about"); me.wait_for_selector("#ab-desc")
        expect(me.locator("#ab-title")).to_have_value("Computer Organization")
        me.fill("#ab-desc", "From transistors to processors.")
        me.click("[data-add=sections]")
        me.locator('.ab-block[data-k=sections] [data-f=heading]').last.fill("Textbook")
        me.locator('.ab-block[data-k=sections] [data-f=body]').last.fill("Patt & Patel, *Introduction to Computing Systems*.")
        me.click("[data-add=policies]")
        me.locator('.ab-block[data-k=policies] [data-f=heading]').last.fill("Late work")
        me.locator('.ab-block[data-k=policies] [data-f=body]').last.fill("Not accepted.")
        me.wait_for_timeout(1500)
        expect(me.locator("#ab-status")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/202-about.png", full_page=True)
        ab = json.loads(srv.text("priv", "csc258/f26/about.json"))
        assert ab["description"] == "From transistors to processors." and ab["sections"][-1]["heading"] == "Textbook" and ab["policies"][-1]["heading"] == "Late work"
        print("2 about saved")

        v = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
        v.goto(srv.base + "c/chandra/csc258/f26/"); v.wait_for_selector(".hb-tab")
        tabs = v.eval_on_selector_all(".hb-tab", "els => els.map(e => e.textContent.trim())")
        assert tabs == ["This week", "Announcements", "Lectures", "Evaluations", "About", "My accommodations"], tabs
        expect(v.locator(".hb-tab[aria-selected=true]")).to_have_text("This week")
        expect(v.locator(".hb-main")).to_contain_text("Midterm rooms posted")   # Oct 27 is in Week 7, this week
        v.click(".hb-tab:has-text('About')")
        expect(v.locator(".hb-main")).to_contain_text("From transistors to processors.")
        expect(v.locator(".hb-main")).to_contain_text("Textbook")
        expect(v.locator(".hb-main")).to_contain_text("Not accepted.")
        v.screenshot(path=f"{OUT}/203-hub-about.png", full_page=True)
        print("3 the hub shows them")

        # 3. The course page: a preview, with each tab's visibility.
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        me.click("[data-go=course]"); me.wait_for_selector(C + ".hbe")
        tabs = me.eval_on_selector_all(C + ".hbe-tab", "els => els.map(e => e.textContent.trim())")
        assert tabs == ["This week", "Announcements", "Lectures", "Evaluations", "About", "My accommodations"], tabs
        for tb in ["week", "announcements", "lectures", "evaluations", "about"]:
            me.click(C + f".hbe-tab[data-v={tb}]")
            assert not me.query_selector(C + ".hb-main [data-act], " + C + ".hb-main .ed"), f"{tb} has editing in it"
        expect(me.locator(C + ".hb-main")).to_contain_text("Textbook")
        me.click(C + ".hbe-tab[data-v=lectures] .hbe-vis")
        me.click(C + "[data-act=preview]")
        me.click(C + ".hbe-tab[data-v=lectures]")
        expect(me.locator(C + ".hb-locked")).to_be_visible()
        me.screenshot(path=f"{OUT}/204-preview.png")
        me.click(C + "[data-act=preview]:has-text('Back')")
        me.keyboard.press("Control+s"); me.wait_for_timeout(2500)
        assert json.loads(srv.text("pub", "csc258/f26/course.json"))["page"]["tabs"] == {"lectures": "signed-in"}
        v.goto(srv.base + "c/chandra/csc258/f26/#lectures"); v.reload(); v.wait_for_selector(".hb-tab")
        expect(v.locator(".hb-locked h2")).to_have_text("Lectures")
        print("4 course page: view only, tabs' visibility saved")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
