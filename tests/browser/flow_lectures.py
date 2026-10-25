"""Lectures, end to end: the weeks and their lectures are made in Lectern's Lectures part, and the course
page shows them (Lectures and This week) without being edited.

The owner opens Lectures (it starts from the course page's weeks), opens a lecture and changes its title,
uploads its slides, adds a week and a lecture in it; it all saves by itself, to lectures.json in the
private files. The hub shows the changes; the course page editor's Lectures tab shows them too and has
nothing to edit. A TA sees Lectures but can't change it. Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_lectures.py
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
        me.wait_for_selector("#lt-lectures")
        me.screenshot(path=f"{OUT}/180-offering.png")
        me.click("#lt-lectures")
        me.wait_for_selector(".lx-group")
        assert me.locator(".lx-group").count() == 12 and me.locator(".lx-break").count() == 1
        assert "Activities" in me.inner_text("#lt-path")
        me.screenshot(path=f"{OUT}/181-lectures.png")
        assert srv.text("priv", "csc258/f26/lectures.json") is None   # nothing saved until something changes

        # A lecture: a new title, and its slides uploaded.
        me.locator(".lx-group").nth(6).locator("[data-lec]").first.click()
        me.wait_for_selector("#lw-title")
        me.fill("#lw-title", "Adders and ALUs")
        with me.expect_file_chooser() as fc:
            me.click("#lw-up")
        fc.value.set_files(files=[{"name": "lec13.pdf", "mimeType": "application/pdf", "buffer": b"%PDF lec13"}])
        me.wait_for_selector("[data-fu]")
        me.screenshot(path=f"{OUT}/182-lecture.png")
        me.wait_for_timeout(1500)
        expect(me.locator("#lw-status")).to_have_text("Saved")
        saved = json.loads(srv.text("priv", "csc258/f26/lectures.json"))
        wk7 = [w for w in saved["weeks"] if w.get("label") == "Week 7"][0]
        assert wk7["cards"][0]["title"] == "Adders and ALUs" and wk7["cards"][0]["files"][0]["url"].endswith("/p/chandra/csc258/f26/lectures/lec13.pdf"), wk7["cards"][0]
        print("1 a lecture changed and its slides uploaded; saved by itself")

        # A new week, with a lecture in it.
        me.locator("#lt-path button", has_text="Activities").click()
        me.click("[data-add-week]")
        me.wait_for_selector("#lw-topic")
        expect(me.locator("#lw-label")).to_have_value("Week 13")
        assert me.get_attribute("#lw-start-f", "data-date") == "2026-12-07", me.get_attribute("#lw-start-f", "data-date")
        expect(me.locator("#lw-start")).to_have_text("Mon, Dec 7, 2026")
        me.fill("#lw-topic", "Review")
        me.click("[data-add-kind=lecture]")
        me.wait_for_selector("#lw-title")
        expect(me.locator("#lw-label")).to_have_value("Lecture 25")
        me.fill("#lw-title", "Course review")
        me.wait_for_timeout(1500)
        me.locator("#lt-path button", has_text="Activities").click()
        me.wait_for_selector(".lx-group")
        expect(me.locator(".lx-group").last).to_contain_text("Course review")
        # Drag it to Week 12, before that week's first lecture; and drag Week 13 above Week 12.
        src = me.locator(".lx-group").last.locator("[data-lec]").first
        dst = me.locator(".lx-group").nth(11).locator("[data-lec]").first
        src.drag_to(dst, target_position={"x": 40, "y": 5})
        me.wait_for_timeout(1500)
        saved = json.loads(srv.text("priv", "csc258/f26/lectures.json"))["weeks"]
        w12, w13 = [w for w in saved if w.get("label") == "Week 12"][0], [w for w in saved if w.get("label") == "Week 13"][0]
        assert w12["cards"][0]["title"] == "Course review" and w13["cards"] == [], (w12["cards"][0], w13["cards"])
        expect(me.locator(".lx-group").last.locator(".lx-none")).to_be_visible()
        me.locator(".lx-group").last.locator(".lx-row.grp").drag_to(me.locator(".lx-group").nth(11).locator(".lx-row.grp"), target_position={"x": 40, "y": 5})
        me.wait_for_timeout(1500)
        labels = [w.get("label") for w in json.loads(srv.text("priv", "csc258/f26/lectures.json"))["weeks"] if not w.get("isBreak")]
        assert labels[-2:] == ["Week 13", "Week 12"], labels
        print("2b dragged a lecture to another week, and a week up")
        me.screenshot(path=f"{OUT}/183-lectures-after.png")
        print("2 a week and a lecture added")

        # The hub shows it, and the course page editor's Lectures tab: nothing to edit there.
        v = b.new_context().new_page()
        v.goto(srv.base + "c/chandra/csc258/f26/#lectures"); v.wait_for_selector(".hb-week")
        expect(v.locator(".hb-main")).to_contain_text("Adders and ALUs")
        expect(v.locator(".hb-main")).to_contain_text("Course review")
        assert v.request.get(srv.base + "p/chandra/csc258/f26/lectures/lec13.pdf").status == 200
        me.evaluate("location.hash = '#/csc258/f26/course'")
        me.wait_for_selector(C + ".hbe")
        me.click(C + ".hbe-tab[data-v=lectures]")
        expect(me.locator(C + ".hb-main")).to_contain_text("Course review")
        assert not me.query_selector(C + ".hb-main [data-act]"), "the Lectures tab has editing in it"
        me.screenshot(path=f"{OUT}/184-editor-lectures.png")
        print("3 the hub and the course page show it; the course page has nothing to edit")

        # A TA sees it and can't change it.
        srv.account(email="ta@utoronto.ca", name="Tara Assistant", handle="tara", admin=False)
        from server import db
        db.run("INSERT INTO members (owner_id, offering, user_id, role, added) VALUES (?, ?, ?, ?, ?)",
               (db.one("SELECT id FROM users WHERE handle='chandra'")["id"], "csc258/f26", db.one("SELECT id FROM users WHERE handle='tara'")["id"], "ta", 0))
        ta = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ta)
        tp = ta.new_page()
        srv.sign_in(tp, email="ta@utoronto.ca", hash="#/~chandra/csc258/f26/lectures")
        tp.wait_for_selector(".lx-group")
        assert not tp.query_selector("[data-add-week]")
        expect(tp.locator(".lt-note")).to_contain_text("You can look at the activities")
        print("4 a TA sees Lectures, read-only")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
