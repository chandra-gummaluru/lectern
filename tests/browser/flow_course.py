"""Course page: the weeks, end to end against the real server. The course page's Activities is the term week by
week (from Lectern's Activities, with its Reading Week divider); a week's page has its activities and what's due
that week, from the gradebook (once it's saved); deleting the divider in Activities (it asks first) takes the
break off the course page. Asserts as it goes; screenshots in shots/.

(This was the old course page builder's weekly layout: lecture slots, No class, hours, tables. The weeks are made
in Activities now (flow_lectures.py); the course page has nothing to edit, and tables are gone. An older page
opening, and becoming a course.json, is in flow_hub.py.)

Run:  python tests/browser/flow_course.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns
from flow_links import BOOK, DATA

HUB = "c/chandra/csc258/f26/"


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("pub", {"csc258/f26/course.json": DATA})
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(BOOK)})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        me = ctx.new_page()
        me.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        v = ctx.new_page()
        v.on("pageerror", lambda e: errors.append(f"course page: {e}"))

        # 1. The course page's Activities: the weeks, with their dates and topics, and the Reading Week between 6 and 7.
        v.goto(srv.base + HUB + "#activities"); v.wait_for_selector(".hs-wk")
        weeks = v.eval_on_selector_all(".hs-wk, .wk-break", "els => els.map(e => e.classList.contains('wk-break') ? '[' + e.textContent.trim() + ']' : e.querySelector('.hs-kick').textContent.trim())")
        print("1 weeks:", weeks)
        assert weeks[:6] == [f"Week {k}" for k in range(1, 7)] and weeks[6] == "[Reading Week]" and weeks[7] == "Week 7", weeks
        v.screenshot(path=f"{OUT}/70-course-weeks.png", full_page=True)

        # 2. Week 3, opened: its activities, and what's due that week from the gradebook (Assignment 1, Lab 2), once
        # it's saved (here: Assignment 1's weight changed, 15 → 20).
        G = "[data-lt-tool='grades'] "
        srv.sign_in(me, hash="#/csc258/f26/evaluations")
        me.wait_for_selector(G + ".erow[data-id='a1']"); me.click(G + ".erow[data-id='a1']")
        me.fill(G + "input[data-f='weight'][data-id='a1']", "20"); me.press(G + "input[data-f='weight'][data-id='a1']", "Tab"); me.wait_for_timeout(400)
        me.keyboard.press("Control+s"); me.wait_for_timeout(2500)
        units = json.loads(srv.text("pub", "csc258/f26/course.json"))["page"]["scheme"]["units"]
        print("2 scheme:", [(u["name"], u["weight"]) for u in units])
        assert units[0]["name"] == "Assignment 1" and units[0]["weight"] == 20, "the gradebook's evaluations went to course.json"
        v.goto(srv.base + HUB + "#week/2"); v.reload(); v.wait_for_selector(".wk-item, .hs-row"); v.wait_for_timeout(500)
        wk3 = v.inner_text(".hb-main")
        print("2 week 3:", wk3.replace("\n", " | ")[:400])
        assert "Week 3" in wk3 and "Logical devices" in wk3 and "Assignment 1" in wk3 and "Lab 2" in wk3, wk3
        v.screenshot(path=f"{OUT}/71-week3.png", full_page=True)

        # 3. Deleting the Reading Week divider in Activities: it asks first; then the course page has no break.
        me.evaluate("location.hash = '#/csc258/f26/lectures'"); me.wait_for_selector(".lx-break [data-del-break]")
        me.click(".lx-break [data-del-break]"); me.wait_for_selector(".lt-modal [data-yes]")
        print("3 asks:", me.inner_text(".lt-modal h2"))
        assert me.inner_text(".lt-modal h2") == "Delete this divider?"
        me.screenshot(path=f"{OUT}/72-delete-divider.png")
        me.click(".lt-modal [data-yes]"); me.wait_for_selector(".lx-break", state="detached"); me.wait_for_timeout(1500)
        saved = json.loads(srv.text("priv", "csc258/f26/lectures.json"))["weeks"]
        assert not any(w.get("isBreak") or w.get("break") or w.get("type") == "break" for w in saved), [w for w in saved if "label" not in w][:2]
        v.goto(srv.base + HUB + "#activities"); v.reload(); v.wait_for_selector(".hs-wk")
        assert not v.query_selector(".wk-break"), "the break is off the course page"
        print("   weeks now:", len(v.query_selector_all(".hs-wk")), "| breaks:", len(v.query_selector_all(".wk-break")))
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_course: OK")


if __name__ == "__main__":
    main()
