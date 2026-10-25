"""The course hub, end to end against the real server.

1. The owner opens the course page in Lectern: it's the hub (its header and tabs, This week first),
   with nothing to edit; Lectures becomes signed-in only (its tab's lock); Save writes course.json only.
   (What's on the page is made in Lectern's parts: flow_lectures.py, flow_parts.py, flow_team.py,
   flow_evalfiles.py.)
2. An older page (info.html only) opens, and saving it makes its course.json.
3. A visitor: the published address leads to the hub; Lectures is locked.
4. The owner sees everything, with the staff bar; on a phone the page doesn't scroll sideways.
Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_hub.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEMO = os.path.join(ROOT, "sample-data/demo-courses/csc258/f26")
OLD = open(os.path.join(DEMO, "info.html"), encoding="utf-8").read()
DATA = open(os.path.join(DEMO, "course.json"), encoding="utf-8").read()
C = "[data-lt-tool='course'] "
HOME = ["Announcements", "Activities", "Evaluations", "About the Course", "My Accommodations"]   # the home page's links
TABS = ["This week", "Announcements", "Activities", "Evaluations", "About", "My accommodations"]   # the course page builder (Lectern) still has its tabs


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("pub", {"csc258/f26/course.json": DATA, "csc108/f26/info.html": OLD})
        b = p.chromium.launch()

        def browser(name, width=1360):
            ctx = b.new_context(viewport={"width": width, "height": 900})
            block_cdns(ctx)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(f"{name} pageerror: {e}"))
            return pg

        # 1. The course page in Lectern is the hub.
        me = browser("owner")
        srv.sign_in(me, hash="#/csc258/f26/course")
        me.wait_for_selector(C + ".hbe .hb-tabs")
        tabs = me.eval_on_selector_all(C + ".hbe-tab", "els => els.map(e => e.textContent.trim())")
        assert tabs == TABS, tabs
        assert "This week" in me.inner_text("#lt-path")
        me.screenshot(path=f"{OUT}/160-editor-week.png", full_page=True)
        me.click(C + ".hbe-tab[data-v=lectures]")
        me.click(C + ".hbe-tab[data-v=lectures] .hbe-vis")
        expect(me.locator(C + ".hbe-tab[data-v=lectures] .hbe-vis")).to_have_class("hbe-vis on")
        assert "Activities" in me.inner_text("#lt-path")
        me.keyboard.press("Control+s")
        me.wait_for_timeout(2500)
        saved = json.loads(srv.text("pub", "csc258/f26/course.json"))["page"]
        assert saved["tabs"] == {"lectures": "signed-in"}, saved.get("tabs")
        assert srv.text("pub", "csc258/f26/info.html") is None
        print("1 saved course.json: tabs", saved["tabs"])

        # 2. An older page, info.html only: it opens, and saving makes course.json.
        me.evaluate("location.hash = '#/csc108/f26/course'")
        me.wait_for_timeout(1500)
        me.wait_for_selector(C + ".hbe")
        expect(me.locator(C + ".hb-title")).not_to_be_empty()
        me.keyboard.press("Control+s")
        me.wait_for_timeout(2500)
        made = srv.text("pub", "csc108/f26/course.json")
        assert made and json.loads(made)["page"]["sections"], "no course.json for the older page"
        print("2 older page saved as course.json")

        # 3. A visitor: the published address leads to the hub; Lectures is locked.
        v = browser("visitor")
        v.goto(srv.base + "p/chandra/csc258/f26/info.html")
        v.wait_for_selector(".hs-sec")
        assert v.url.endswith("/c/chandra/csc258/f26/"), v.url
        links = v.eval_on_selector_all(".hs-link b", "els => els.map(e => e.textContent.trim())")
        assert links == [x for x in HOME if x != "Announcements"], links   # the newest announcement has its See all instead
        v.screenshot(path=f"{OUT}/164-hub-home-visitor.png", full_page=True)
        assert v.query_selector(".hs-link:has-text('Activities') .hs-lock"), "Activities isn't locked on the home page"
        v.goto(srv.base + "c/chandra/csc258/f26/#activities")
        expect(v.locator(".hb-locked h2")).to_have_text("Activities")
        assert "lec03.pdf" not in v.content()
        v.goto(srv.base + "c/chandra/csc258/f26/#about")
        expect(v.locator(".hb-main")).to_contain_text("From transistors to processors")
        print("3 visitor: lectures locked, about shown")

        # 4. The owner on the hub, and a phone.
        me.goto(srv.base + "c/chandra/csc258/f26/#lectures")
        me.wait_for_selector(".hs-wk")
        expect(me.locator(".hb-staff")).to_contain_text("See it as a visitor")
        ph = browser("phone", 390)
        ph.goto(srv.base + "c/chandra/csc258/f26/#about")
        ph.wait_for_selector(".hb-person")
        assert ph.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "page scrolls sideways"
        print("4 owner: staff bar; phone: no sideways scroll")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
