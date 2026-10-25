"""Coordinators, instructors, TAs and staff, with activity groups.

An instructor runs LEC0101's lecture (groups.json): they add an activity for LEC0101 (saved), can't change
everyone's activities (read-only), and write an announcement only for LEC0101. A TA marks everyone, and the
gradebook tells them which students aren't in their groups. Staff see the Accommodations. Asserts as it
goes; screenshots in shots/.

Run:  python tests/browser/flow_roles.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGE = open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json"), encoding="utf-8").read()
BOOK = json.loads(open(os.path.join(ROOT, "sample-data/demo-courses-private/csc258/f26/grades.json"), encoding="utf-8").read())


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        from server import db
        owner = srv.account()
        def member(email, handle, role):
            u = srv.account(email=email, name=handle.title(), handle=handle, admin=False)
            db.run("INSERT INTO members (owner_id, offering, user_id, role, added_by, added) VALUES (?, ?, ?, ?, ?, ?)", (owner["id"], "csc258/f26", u["id"], role, owner["id"], time.time()))
            return u
        ins, ta, stf = member("ins@utoronto.ca", "ins", "instructor"), member("ta@utoronto.ca", "tee", "ta"), member("staff@utoronto.ca", "stf", "staff")
        srv.user = owner
        groups = {"format": "lectern-groups/1", "groups": [
            {"id": "g1", "name": "LEC0101", "items": [{"id": "i1", "kind": "lecture", "day": 1, "start": "10:00", "end": "11:00", "people": [str(ins["id"]), str(ta["id"])]}]},
            {"id": "g2", "name": "LEC0201", "items": []}]}
        for k, s in enumerate(BOOK["students"]):
            s["groups"] = ["g1"] if k % 2 == 0 else ["g2"]
        srv.put("pub", {"csc258/f26/course.json": PAGE})
        lec = {"format": "lectern-lectures/1", "weeks": [
            {"id": "w1", "label": "Week 1", "start": "2026-09-07", "end": "2026-09-11", "topic": "Gates",
             "cards": [{"id": "a1", "kind": "lecture", "label": "Lecture 01", "title": "Everyone's lecture", "files": []}]},
            {"id": "w2", "label": "Week 2", "start": "2026-09-14", "end": "2026-09-18", "cards": []}]}
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(BOOK), "csc258/f26/groups.json": json.dumps(groups), "csc258/f26/lectures.json": json.dumps(lec),
                         "csc258/f26/announcements.json": json.dumps({"format": "lectern-announcements/1", "items": [{"id": "w", "title": "Welcome", "date": "Sep 7, 2026, 09:00", "body": "Hi."}]})})
        b = p.chromium.launch()
        def browser(email):
            ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
            pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
            srv.sign_in(pg, email=email, hash="#/~chandra/csc258/f26/activities")
            return pg

        # 1. The instructor: their group's activity; everyone's is read-only.
        ip = browser("ins@utoronto.ca")
        ip.wait_for_selector(".lx-group")
        expect(ip.locator(".lx-note")).to_contain_text("LEC0101")
        assert not ip.query_selector("[data-add-week]")
        ip.locator(".lx-row.grp").first.click(); ip.wait_for_selector("[data-add-activity]")
        ip.click("[data-add-activity]"); ip.wait_for_selector("#lw-title")
        expect(ip.locator("#lw-group")).to_have_value("g1")
        assert ip.eval_on_selector_all("#lw-group option", "o => o.map(x => x.textContent)") == ["LEC0101 only"]
        ip.fill("#lw-title", "Section review"); ip.wait_for_timeout(1500)
        expect(ip.locator("#lw-status")).to_have_text("Saved")
        lec = json.loads(srv.text("priv", "csc258/f26/lectures.json"))
        mine = [c for w in lec["weeks"] for c in w.get("cards", []) if c.get("title") == "Section review"]
        assert mine and mine[0]["group"] == "g1", mine
        ip.screenshot(path=f"{OUT}/r01-instructor-activity.png", full_page=True)
        ip.locator("#lt-path button", has_text="Week 1").click(); ip.wait_for_timeout(500)
        ip.locator(".lx-lec[data-lec]").first.click(); ip.wait_for_selector("#lw-title")
        assert ip.is_disabled("#lw-title"), "everyone's activity can be changed by an instructor"
        print("1 instructor: added LEC0101's activity; everyone's is read-only")

        # 2. Their announcement: for LEC0101 only.
        ip.evaluate("location.hash = '#/~chandra/csc258/f26/announcements'"); ip.wait_for_selector("#an-new")
        ip.click("#an-new"); ip.wait_for_selector("#an-title")
        ip.fill("#an-title", "LEC0101: room change")
        assert ip.eval_on_selector_all("#an-group option", "o => o.map(x => x.textContent)") == ["LEC0101 only"]
        ip.wait_for_timeout(1500)
        expect(ip.locator("#an-status")).to_have_text("Saved")
        a = [x for x in json.loads(srv.text("priv", "csc258/f26/announcements.json"))["items"] if x.get("title") == "LEC0101: room change"]
        assert a and a[0]["group"] == "g1", a
        print("2 instructor: an announcement for LEC0101")

        # 3. The TA: everyone's marks; students not in their groups say so.
        tp = browser("ta@utoronto.ca")
        tp.evaluate("location.hash = '#/~chandra/csc258/f26/gradebook'")
        tp.wait_for_selector("[data-lt-tool=grades] .nm-tag")
        n = tp.locator("[data-lt-tool=grades] .nm-tag").count()
        assert n == len([s for s in BOOK["students"] if s["groups"] == ["g2"]]), n
        tp.screenshot(path=f"{OUT}/r02-ta-gradebook.png")
        print(f"3 TA: {n} students marked as not in their groups")

        # 4. Staff: the Accommodations.
        sp = browser("staff@utoronto.ca")
        sp.evaluate("location.hash = '#/~chandra/csc258/f26'"); sp.wait_for_selector("#lt-accom")
        print("4 staff see the Accommodations")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
