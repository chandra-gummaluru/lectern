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


def add_time(me, day, start, end, where=None):
    me.click("#gr-add")
    row = me.locator(".gr-item").last
    row.locator('[data-k="day"]').select_option(day)
    row.locator('[data-k="start"]').fill(start); row.locator('[data-k="start"]').press("Tab")
    row.locator('[data-k="end"]').fill(end); row.locator('[data-k="end"]').press("Tab")
    if where:
        row.locator('[data-k="where"]').fill(where); row.locator('[data-k="where"]').press("Tab")
    return row


def new_section(me, name):
    me.click("#lt-group-new"); me.fill("#gr-name", name); me.click(".lt-modal [data-ok]")
    me.wait_for_selector("#gr-add")


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

        # 1. Sections: a lecture section and a tutorial section (typed from their names), with their times.
        me.wait_for_selector("#lt-group-new")
        new_section(me, "LEC0101")
        expect(me.locator("#gr-kick")).to_have_text("Lecture Section")
        row = add_time(me, "1", "10 am", "11 am", "BA 1170")
        expect(row.locator('[data-k="start"]')).to_have_value("10:00")
        row = add_time(me, "3", "10:00", "11:00")   # the next one starts from the last: same times, same room
        expect(row.locator('[data-k="where"]')).to_have_value("BA 1170")
        me.wait_for_timeout(1500); expect(me.locator("#gr-status")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/190-group.png", full_page=True)
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        new_section(me, "TUT0101")
        expect(me.locator("#gr-kick")).to_have_text("Tutorial Section")
        add_time(me, "4", "3 pm", "4 pm", "BA 2135")
        me.wait_for_timeout(1500); expect(me.locator("#gr-status")).to_have_text("Saved")
        g = json.loads(srv.text("priv", "csc258/f26/groups.json"))["groups"]
        got = sorted((x["name"], x["kind"], tuple((i["day"], i["start"], i["end"], i["where"]) for i in x["items"])) for x in g)
        assert got == [("LEC0101", "lecture", ((1, "10:00", "11:00", "BA 1170"), (3, "10:00", "11:00", "BA 1170"))), ("TUT0101", "tutorial", ((4, "15:00", "16:00", "BA 2135"),))], got
        print("1 sections saved:", got)

        # 2. Their page: the sections they run (a dropdown), their office and office hours.
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        me.wait_for_selector("#lt-groups .lt-groups")
        expect(me.locator("#lt-groups")).to_contain_text("Mon, Wed 10:00–11:00 · BA 1170")
        me.click("[data-person]")
        me.wait_for_selector("#tm-office")
        me.click("#tm-runs")
        me.locator("#tm-runs-pick .pk-chk", has_text="LEC0101").locator("input").check()
        me.locator("#tm-runs-pick .pk-chk", has_text="TUT0101").locator("input").check()
        me.wait_for_timeout(300); me.screenshot(path=f"{OUT}/190b-run-by.png"); me.keyboard.press("Escape")
        me.wait_for_timeout(1500)
        expect(me.locator(".tm-runs")).to_contain_text("LEC0101")
        expect(me.locator(".tm-runs")).to_contain_text("Thu 15:00–16:00 · BA 2135")
        g = json.loads(srv.text("priv", "csc258/f26/groups.json"))["groups"]
        assert all(len(x["people"]) == 1 for x in g), g
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
        print("2 their page: the sections they run, and office hours saved")

        # 3. A student, in a lecture section and a tutorial section (they must be in one).
        me.locator("#lt-path button", has_text="csc258 / f26").click()
        me.wait_for_selector("#st-add")
        me.click("#st-add")
        me.fill("#sd-num", "1001"); me.fill("#sd-first", "Maya"); me.fill("#sd-last", "Castillo"); me.fill("#sd-email", "maya@mail.utoronto.ca")
        me.click(".lt-modal [data-ok]")
        expect(me.locator("#sd-err")).to_contain_text("sections")
        me.locator('.lt-modal [data-sd-k="lecture"]').select_option(label="LEC0101")
        me.locator('.lt-modal [data-sd-k="tutorial"]').select_option(label="TUT0101")
        me.screenshot(path=f"{OUT}/190c-student.png")
        me.click(".lt-modal [data-ok]")
        expect(me.locator("#lt-students .lt-orow", has_text="Castillo, Maya")).to_contain_text("LEC0101")
        st = json.loads(srv.text("priv", "csc258/f26/grades.json"))["students"]
        assert sorted(st[0]["groups"]) == sorted(x["id"] for x in g), st
        print("3 the student is in LEC0101 and TUT0101")

        # 4. The course page's About: the group with its times and who runs them; office hours; the team.
        v = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
        v.goto(srv.base + "c/chandra/csc258/f26/#about"); v.wait_for_selector(".hb-main h2")
        sec = v.locator(".hb-sec").first
        expect(sec).to_contain_text("LEC0101"); expect(sec).to_contain_text("Lecture Section"); expect(sec).to_contain_text("Mon 10:00–11:00"); expect(sec).to_contain_text("Wed 10:00–11:00")
        expect(v.locator(".hb-main")).to_contain_text("Tutorial Section"); expect(v.locator(".hb-main")).to_contain_text("Thu 15:00–16:00"); expect(sec).to_contain_text("Chandra Gummaluru")
        expect(v.locator(".hb-main")).to_contain_text("BA 4010")
        expect(v.locator(".hb-main")).to_contain_text("Office Hours")
        v.wait_for_timeout(700); v.screenshot(path=f"{OUT}/192-hub-groups.png", full_page=True)
        print("4 the hub shows the sections, office hours and team")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
