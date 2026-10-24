"""The course hub, end to end against the real server: the owner opens the course page in Lectern,
adds a weekly office hour and makes Lectures a signed-in-only tab, saves (course.json goes beside
info.html); a visitor then sees the hub with Lectures locked, the published address leads to the hub,
and the owner sees everything, with the staff bar. Asserts as it goes; screenshots in shots/.

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
PAGE = open(os.path.join(DEMO, "info.html"), encoding="utf-8").read()
DATA = open(os.path.join(DEMO, "course.json"), encoding="utf-8").read()
C = "[data-lt-tool='course'] "


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("pub", {"csc258/f26/info.html": PAGE, "csc258/f26/course.json": DATA})
        b = p.chromium.launch()

        def browser(name, width=1360):
            ctx = b.new_context(viewport={"width": width, "height": 900})
            block_cdns(ctx)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(f"{name} pageerror: {e}"))
            return pg

        # 1. The owner, in the Course Page Builder: the meeting times and the hub's tabs.
        me = browser("owner")
        srv.sign_in(me, hash="#/csc258/f26/course")
        me.wait_for_selector(C + ".e-tabs")
        heads = me.eval_on_selector_all(C + ".e-sechead .grow > :first-child", "els => els.map(e => e.textContent)")
        assert "Meeting Times & Office Hours" in heads, heads
        assert len(me.query_selector_all(C + ".e-meet:not(.e-mhead)")) == 5
        me.locator(C + ".e-tabs button", has_text="Lectures").click()
        expect(me.locator(C + ".e-tabs button", has_text="Lectures")).to_contain_text("Signed in")
        me.locator(C + "button", has_text="+ Add a Time").click()
        row = me.locator(C + ".e-meet:not(.e-mhead)").last
        row.locator("select").first.select_option("office")
        row.locator("select").nth(1).select_option("2")
        row.locator("input[type=time]").first.fill("15:00")
        row.locator("input[type=time]").nth(1).fill("16:00")
        row.locator("input").nth(3).fill("BA 2270")
        row.locator("input").nth(4).fill("Grace Hopper (TA)")
        me.locator(C + ".e-tabs").scroll_into_view_if_needed()
        me.screenshot(path=f"{OUT}/150-hub-tabs-editor.png")
        me.locator(C + ".e-sechead", has_text="Meeting Times").first.scroll_into_view_if_needed()
        me.screenshot(path=f"{OUT}/151-meetings-editor.png")
        me.keyboard.press("Control+s")
        me.wait_for_timeout(2500)
        saved = json.loads(srv.text("pub", "csc258/f26/course.json"))["page"]
        assert saved["tabs"] == {"lectures": "signed-in"}, saved.get("tabs")
        meet = [s for s in saved["sections"] if s["type"] == "meetings"][0]["items"]
        assert meet[-1] == {"kind": "office", "label": "", "day": "2", "start": "15:00", "end": "16:00", "where": "BA 2270", "who": "Grace Hopper (TA)"}, meet[-1]
        html = srv.text("pub", "csc258/f26/info.html")
        assert "cpb-type-meetings" in html and "Grace Hopper (TA)" in html
        print("1 saved: tabs", saved["tabs"], "| meetings", len(meet))

        # 2. A visitor: the published address leads to the hub; Lectures is locked.
        v = browser("visitor")
        v.goto(srv.base + "p/chandra/csc258/f26/info.html")
        v.wait_for_selector(".hb-tab")
        assert v.url.endswith("/c/chandra/csc258/f26/"), v.url
        expect(v.locator(".hb-tab[aria-selected=true]")).to_have_text("This week")
        v.screenshot(path=f"{OUT}/152-hub-week-visitor.png", full_page=True)
        v.click(".hb-tab:has-text('Lectures')")
        expect(v.locator(".hb-locked h2")).to_have_text("Lectures")
        v.screenshot(path=f"{OUT}/153-hub-locked.png")
        assert "lec03.pdf" not in v.content()
        assert v.locator(".hb-staff").is_hidden()
        v.click(".hb-tab:has-text('Overview')")
        expect(v.locator(".hb-main")).to_contain_text("Grace Hopper (TA)")
        print("2 visitor: lectures locked, overview has the new office hour")

        # 3. The owner on the hub: everything, the staff bar, and seeing it as a visitor.
        me.goto(srv.base + "c/chandra/csc258/f26/#lectures")
        me.wait_for_selector(".hb-week")
        expect(me.locator(".hb-staff")).to_contain_text("See it as a visitor")
        expect(me.locator(".hb-who")).to_contain_text("Instructor")
        me.screenshot(path=f"{OUT}/154-hub-lectures-owner.png")
        me.click("text=See it as a visitor")
        expect(me.locator(".hb-locked")).to_be_visible()
        print("3 owner: staff bar, preview as visitor")

        # 4. On a phone.
        ph = browser("phone", 390)
        ph.goto(srv.base + "c/chandra/csc258/f26/#overview")
        ph.wait_for_selector(".hb-t")
        assert ph.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "page scrolls sideways"
        ph.screenshot(path=f"{OUT}/155-hub-phone.png", full_page=True)
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
