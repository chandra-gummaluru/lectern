"""The course hub, end to end against the real server.

1. The owner opens the course page in Lectern: the editor is the hub (its header and tabs). On Overview
   they add a weekly office hour; on Lectures they open a lecture and give it a title, and add a week;
   on Announcements they write one in the current week; Lectures becomes signed-in only (its tab's lock).
   Save writes course.json only (no info.html any more).
2. An older page (info.html only) opens, and saving it makes its course.json.
3. A visitor sees the hub with Lectures locked, the published address leads to the hub.
4. The owner sees everything, with the staff bar; and on a phone the page doesn't scroll sideways.
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

        # 1. The editor is the hub.
        me = browser("owner")
        srv.sign_in(me, hash="#/csc258/f26/course")
        me.wait_for_selector(C + ".hbe .hb-tabs")
        tabs = me.eval_on_selector_all(C + ".hbe-tab", "els => els.map(e => e.textContent.trim())")
        assert tabs == ["Overview", "This week", "Lectures", "Evaluations", "Announcements", "Policies", "My accommodations"], tabs
        assert "Overview" in me.inner_text("#lt-path")
        me.screenshot(path=f"{OUT}/160-editor-overview.png", full_page=True)

        # Overview: a weekly office hour.
        me.locator(C + "button", has_text="+ Add a Time").click()
        row = me.locator(C + ".e-meet:not(.e-mhead)").last
        row.locator("select").first.select_option("office")
        row.locator("select").nth(1).select_option("2")
        row.locator("input[type=time]").first.fill("15:00")
        row.locator("input[type=time]").nth(1).fill("16:00")
        row.locator("input").nth(3).fill("BA 2270")
        row.locator("input").nth(4).fill("Grace Hopper (TA)")

        # Lectures: signed-in only (the tab's lock), a lecture's title, a new week.
        me.click(C + ".hbe-tab[data-v=lectures]")
        me.click(C + ".hbe-tab[data-v=lectures] .hbe-vis")
        expect(me.locator(C + ".hbe-visline")).to_contain_text("Only people in the course")
        assert "Lectures" in me.inner_text("#lt-path")
        me.locator(C + ".hb-week").nth(6).locator(".hb-card").first.click()
        me.wait_for_selector(C + ".e-sub")
        assert "Lectures" in me.inner_text("#lt-path"), me.inner_text("#lt-path")
        me.fill(C + "[data-bindv$='.title']", "Adders and ALUs")
        me.locator("#lt-path button", has_text="Lectures").click()
        me.wait_for_selector(C + ".hbe")
        expect(me.locator(C + ".hb-week").nth(6)).to_contain_text("Adders and ALUs")
        weeks = me.locator(C + ".hb-week").count()
        me.locator(C + ".hbe-add", has_text="+ Add Week").click()
        me.wait_for_selector(C + ".e-sub")
        me.locator("#lt-path button", has_text="Lectures").click()
        assert me.locator(C + ".hb-week").count() == weeks + 1
        me.screenshot(path=f"{OUT}/161-editor-lectures.png")

        # Announcements: a new one, in the current week.
        me.click(C + ".hbe-tab[data-v=announcements]")
        wk = me.eval_on_selector(C + "#ann-week", "s => s.options[s.selectedIndex].textContent")
        assert wk.startswith("Week 7"), wk
        me.click(C + "[data-act=ann-new]")
        me.fill(C + "[data-bindv$='.title']", "Midterm rooms posted")
        me.locator("#lt-path button", has_text="Announcements").click()
        expect(me.locator(C + ".hb-ann").first).to_contain_text("Midterm rooms posted")
        me.screenshot(path=f"{OUT}/162-editor-announcements.png")
        # This week shows it, and the new office hour on Tuesday.
        me.click(C + ".hbe-tab[data-v=week]")
        expect(me.locator(C + ".hb-main")).to_contain_text("Midterm rooms posted")
        expect(me.locator(C + ".hb-days")).to_contain_text("Grace Hopper (TA)")
        me.screenshot(path=f"{OUT}/163-editor-week.png")

        me.keyboard.press("Control+s")
        me.wait_for_timeout(2500)
        saved = json.loads(srv.text("pub", "csc258/f26/course.json"))["page"]
        assert saved["tabs"] == {"lectures": "signed-in"}, saved.get("tabs")
        meet = [s for s in saved["sections"] if s["type"] == "meetings"][0]["items"]
        assert meet[-1] == {"kind": "office", "label": "", "day": "2", "start": "15:00", "end": "16:00", "where": "BA 2270", "who": "Grace Hopper (TA)"}, meet[-1]
        sched = [s for s in saved["sections"] if s["type"] == "schedule"][0]["weeks"]
        assert any(c["title"] == "Adders and ALUs" for w in sched for c in w.get("cards", []))
        assert any(a["title"] == "Midterm rooms posted" for w in sched if w.get("label") == "Week 7" for a in w.get("announcements", []))
        assert srv.text("pub", "csc258/f26/info.html") is None
        print("1 saved course.json: tabs", saved["tabs"], "| meetings", len(meet), "| weeks", len(sched))

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
        v.wait_for_selector(".hb-tab")
        assert v.url.endswith("/c/chandra/csc258/f26/"), v.url
        expect(v.locator(".hb-tab[aria-selected=true]")).to_have_text("This week")
        v.screenshot(path=f"{OUT}/164-hub-week-visitor.png", full_page=True)
        v.click(".hb-tab:has-text('Lectures')")
        expect(v.locator(".hb-locked h2")).to_have_text("Lectures")
        assert "Adders and ALUs" not in v.content()
        v.click(".hb-tab:has-text('Overview')")
        expect(v.locator(".hb-main")).to_contain_text("Grace Hopper (TA)")
        print("3 visitor: lectures locked, overview has the new office hour")

        # 4. The owner on the hub, and a phone.
        me.goto(srv.base + "c/chandra/csc258/f26/#lectures")
        me.wait_for_selector(".hb-week")
        expect(me.locator(".hb-staff")).to_contain_text("See it as a visitor")
        ph = browser("phone", 390)
        ph.goto(srv.base + "c/chandra/csc258/f26/#overview")
        ph.wait_for_selector(".hb-t")
        assert ph.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "page scrolls sideways"
        print("4 owner: staff bar; phone: no sideways scroll")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
