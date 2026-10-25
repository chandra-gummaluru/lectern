"""The teaching team and the activity groups, set in Lectern, on the course page.

The owner adds an activity group (LEC0101) on the offering's page, gives it two weekly lectures and a
tutorial (times typed as "10 am", "3 pm"), and says they run them; on their own page they set an office and
office hours, and see what they run. A student is added in the group. It all saves by itself (groups.json,
team.json, grades.json in the private files). The hub's About shows the group with its times and who runs
them, the office hours, and the team. Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_team.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = json.loads(open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json"), encoding="utf-8").read())
DATA["page"]["sections"] = [s for s in DATA["page"]["sections"] if s["type"] != "meetings"]   # times come from the groups now


def activity(me, day, start, end, where=None, kind=None):
    me.click("#gr-add")
    row = me.locator(".gr-item").last
    if kind:
        row.locator('[data-k="kind"]').select_option(kind)
    row.locator('[data-k="day"]').select_option(day)
    row.locator('[data-k="start"]').fill(start); row.locator('[data-k="start"]').press("Tab")
    row.locator('[data-k="end"]').fill(end); row.locator('[data-k="end"]').press("Tab")
    if where:
        row.locator('[data-k="where"]').fill(where); row.locator('[data-k="where"]').press("Tab")
    return row


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("pub", {"csc258/f26/course.json": json.dumps(DATA)})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        me = ctx.new_page()
        me.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(me, hash="#/csc258/f26")

        # 1. An activity group, its activities, and who runs them.
        me.wait_for_selector("#lt-group-new")
        me.click("#lt-group-new"); me.fill("#gr-name", "LEC0101"); me.click(".lt-modal [data-ok]")
        me.wait_for_selector("#gr-add")
        row = activity(me, "1", "10 am", "11 am", "BA 1170")
        expect(row.locator('[data-k="start"]')).to_have_value("10:00")
        row.locator(".gr-chip", has_text="Chandra Gummaluru").click()
        row = activity(me, "3", "10:00", "11:00")   # the next one starts from the last: same room, same people
        expect(row.locator('[data-k="where"]')).to_have_value("BA 1170")
        expect(row.locator(".gr-chip[aria-pressed=true]")).to_have_count(1)
        activity(me, "4", "3 pm", "4 pm", "BA 2135", kind="tutorial")
        me.wait_for_timeout(1500)
        expect(me.locator("#gr-status")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/190-group.png", full_page=True)
        g = json.loads(srv.text("priv", "csc258/f26/groups.json"))["groups"]
        assert [x["name"] for x in g] == ["LEC0101"], g
        got = sorted((x["kind"], x["day"], x["start"], x["end"], x["where"], len(x["people"])) for x in g[0]["items"])
        assert got == [("lecture", 1, "10:00", "11:00", "BA 1170", 1), ("lecture", 3, "10:00", "11:00", "BA 1170", 1), ("tutorial", 4, "15:00", "16:00", "BA 2135", 1)], got
        print("1 group saved:", got)

        # 2. Their page: what they run (from the group), their office and office hours.
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        me.wait_for_selector("#lt-groups .lt-groups")
        expect(me.locator("#lt-groups")).to_contain_text("2 lectures, 1 tutorial")
        me.click("[data-person]")
        me.wait_for_selector("#tm-office")
        expect(me.locator(".tm-runs")).to_contain_text("LEC0101 · Lecture")
        expect(me.locator(".tm-runs")).to_contain_text("Thu 15:00–16:00 · BA 2135")
        me.fill("#tm-office", "BA 4010")
        me.click("[data-add=office]")
        row = me.locator(".tm-row[data-i]").last
        row.locator('[data-k="day"]').select_option("2")
        row.locator('[data-k="start"]').fill("2 pm"); row.locator('[data-k="start"]').press("Tab")
        row.locator('[data-k="end"]').fill("16:00"); row.locator('[data-k="end"]').press("Tab")
        me.wait_for_timeout(1500)
        expect(me.locator("#tm-status")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/191-member.png", full_page=True)
        mine = list(json.loads(srv.text("priv", "csc258/f26/team.json"))["people"].values())[0]
        assert mine["office"] == "BA 4010" and [(x["kind"], x["day"], x["start"], x["end"]) for x in mine["times"]] == [("office", 2, "14:00", "16:00")], mine
        print("2 their page: what they run, and office hours saved")

        # 3. A student, in the group (they must be in one).
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        me.wait_for_selector("#st-add")
        me.click("#st-add")
        me.fill("#sd-num", "1001"); me.fill("#sd-first", "Maya"); me.fill("#sd-last", "Castillo"); me.fill("#sd-email", "maya@mail.utoronto.ca")
        me.click(".lt-modal [data-ok]")
        expect(me.locator("#sd-err")).to_contain_text("activity groups")
        me.locator(".lt-modal [data-sd-g]").first.check()
        me.click(".lt-modal [data-ok]")
        expect(me.locator("#lt-students .lt-orow", has_text="Castillo, Maya")).to_contain_text("LEC0101")
        st = json.loads(srv.text("priv", "csc258/f26/grades.json"))["students"]
        assert st[0]["groups"] == [g[0]["id"]], st
        print("3 the student is in LEC0101")

        # 4. The course page's About: the group with its times and who runs them; office hours; the team.
        v = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
        v.goto(srv.base + "c/chandra/csc258/f26/#about"); v.wait_for_selector(".hb-main h2")
        sec = v.locator(".hb-sec").first
        expect(sec).to_contain_text("LEC0101"); expect(sec).to_contain_text("Mon 10:00–11:00"); expect(sec).to_contain_text("Wed 10:00–11:00")
        expect(sec).to_contain_text("Tutorial Thu 15:00–16:00"); expect(sec).to_contain_text("Chandra Gummaluru")
        expect(v.locator(".hb-main")).to_contain_text("BA 4010")
        expect(v.locator(".hb-main")).to_contain_text("Office Hours")
        v.wait_for_timeout(700); v.screenshot(path=f"{OUT}/192-hub-groups.png", full_page=True)
        print("4 the hub shows the group, office hours and team")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
