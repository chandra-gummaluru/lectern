"""Announcements and the offering's title and description, made in Lectern, on the course page; the course
page itself is a preview with each tab's visibility.

1. Announcements: it starts from the course page's own; a new one, dated in Week 7, saves by itself;
   the hub shows it in Announcements and in that week.
2. The offering's page: no About or Course Page cards, and no Settings; its title and description are
   changed under its code and save by themselves; the hub's header and About show them.
3. View Course Page (Lectern): the new tabs (This week first, About), nothing to edit, Lectures made
   signed-in only with its lock, saved; a visitor sees Lectures locked. Preview shows the visitor's view.
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
        me.fill("#an-body", "Rooms by **last name**:\n\n- A–L: EX 100\n- M–Z: EX 200")
        me.wait_for_timeout(1500)
        expect(me.locator("#an-status")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/201-announcement.png")
        items = json.loads(srv.text("priv", "csc258/f26/announcements.json"))["items"]
        assert [a["title"] for a in items] == ["Welcome to CSC258!", "Midterm rooms posted"] and items[1]["date"] == "Oct 27, 2026, 09:30", items
        print("1 announcements:", [a["title"] for a in items])

        # 2. The offering's page: title and description under the code
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        me.wait_for_selector("#lt-desc")
        assert not me.query_selector("#lt-about-open, [data-go=course], [data-part=settings].lt-off-acts, .lt-off-acts [data-part]"), "old cards or Settings are still there"
        assert me.locator(".lt-part-head h2").all_inner_texts()[:4] == ["Lectures", "Announcements", "Evaluations", "Gradebook"], me.locator(".lt-part-head h2").all_inner_texts()
        expect(me.locator("#lt-title")).to_have_value("Computer Organization")
        me.fill("#lt-title", "Computer Organization and Design")
        me.fill("#lt-desc .rt-ed", "From transistors to processors.")
        me.wait_for_timeout(1500)
        expect(me.locator("#lt-about-st")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/202-offering-about.png")
        ab = json.loads(srv.text("priv", "csc258/f26/about.json"))
        assert ab["title"] == "Computer Organization and Design" and ab["description"] == "From transistors to processors.", ab
        print("2 title and description saved")

        v = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
        v.goto(srv.base + "c/chandra/csc258/f26/"); v.wait_for_selector(".hb-tab")
        tabs = v.eval_on_selector_all(".hb-tab", "els => els.map(e => e.textContent.trim())")
        assert tabs == ["This week", "Announcements", "Lectures", "Evaluations", "About", "My accommodations"], tabs
        expect(v.locator(".hb-tab[aria-selected=true]")).to_have_text("This week")
        expect(v.locator(".hb-main")).to_contain_text("Midterm rooms posted")   # Oct 27 is in Week 7, this week
        v.click(".hb-tab:has-text('About')")
        expect(v.locator(".hb-main")).to_contain_text("From transistors to processors.")
        expect(v.locator(".hb-title")).to_have_text("Computer Organization and Design")
        expect(v.locator(".hb-sub")).to_contain_text("CSC258")
        v.screenshot(path=f"{OUT}/203-hub-about.png", full_page=True)
        print("3 the hub shows them")

        # 3. The course page: a preview, with each tab's visibility.
        me.click("#lt-view-page"); me.wait_for_selector(C + ".hbe")
        expect(me.locator(C + ".hb-title")).to_have_text("Computer Organization and Design")
        tabs = me.eval_on_selector_all(C + ".hbe-tab", "els => els.map(e => e.textContent.trim())")
        assert tabs == ["This week", "Announcements", "Lectures", "Evaluations", "About", "My accommodations"], tabs
        for tb in ["week", "announcements", "lectures", "evaluations", "about"]:
            me.click(C + f".hbe-tab[data-v={tb}]")
            assert not me.query_selector(C + ".hb-main [data-act], " + C + ".hb-main .ed"), f"{tb} has editing in it"
        expect(me.locator(C + ".hb-main")).to_contain_text("From transistors to processors.")
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

        # 4. A new offering: its title first.
        me.click("#lt-home"); me.wait_for_selector("#lt-new"); me.click("#lt-new")
        me.fill("#no-c", "csc369"); me.click(".lt-modal [data-ok]")
        expect(me.locator("#no-err")).to_contain_text("title")
        me.fill("#no-title", "Operating Systems"); me.click(".lt-modal [data-ok]")
        me.wait_for_selector("#lt-title")
        expect(me.locator("#lt-title")).to_have_value("Operating Systems")
        t = me.evaluate("location.hash").split("/")[-1]
        assert json.loads(srv.text("priv", f"csc369/{t}/about.json"))["title"] == "Operating Systems"
        me.screenshot(path=f"{OUT}/205-new-offering.png")
        print("5 new offering made with its title:", t)
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
