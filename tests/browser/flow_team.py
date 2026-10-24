"""The teaching team's details, set in Lectern, on the course page.

The owner clicks themselves in the offering's Teaching Team, sets an office, a lecture section with two
weekly times and office hours; it saves by itself (team.json in the private files). The hub's About
shows the section with its times and teacher, the office hours, and the team; This week has the times
on their days. Asserts as it goes; screenshots in shots/.

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
DATA["page"]["sections"] = [s for s in DATA["page"]["sections"] if s["type"] != "meetings"]   # times come from the team now


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
        me.wait_for_selector("[data-person]")
        me.click("[data-person]")
        me.wait_for_selector("#tm-office")
        assert "Chandra Gummaluru" in me.inner_text("#lt-path")
        me.fill("#tm-office", "BA 4010")
        me.click("[data-add=lecture]")
        row = me.locator(".tm-row[data-i]").last
        row.locator('[data-k="section"]').fill("LEC0101")
        row.locator('[data-k="start"]').fill("10:00"); row.locator('[data-k="end"]').fill("11:00")
        row.locator('[data-k="where"]').fill("BA 1170")
        me.click("[data-add=lecture]")
        row = me.locator(".tm-row[data-i]").last
        row.locator('[data-k="section"]').fill("LEC0101")
        row.locator('[data-k="day"]').select_option("3")
        row.locator('[data-k="start"]').fill("10:00"); row.locator('[data-k="end"]').fill("11:00")
        me.click("[data-add=office]")
        row = me.locator(".tm-row[data-i]").last
        row.locator('[data-k="day"]').select_option("2")
        row.locator('[data-k="start"]').fill("14:00"); row.locator('[data-k="end"]').fill("16:00")
        me.wait_for_timeout(1500)
        expect(me.locator("#tm-status")).to_have_text("Saved")
        me.screenshot(path=f"{OUT}/190-member.png")
        info = json.loads(srv.text("priv", "csc258/f26/team.json"))["people"]
        mine = list(info.values())[0]
        assert mine["office"] == "BA 4010" and [(x["kind"], x["day"], x["start"]) for x in mine["times"]] == [("lecture", 1, "10:00"), ("lecture", 3, "10:00"), ("office", 2, "14:00")], mine
        print("1 saved:", mine)

        v = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
        v.goto(srv.base + "c/chandra/csc258/f26/#about"); v.wait_for_selector(".hb-main h2")
        sec = v.locator(".hb-sec").first
        expect(sec).to_contain_text("LEC0101"); expect(sec).to_contain_text("Mon 10:00–11:00"); expect(sec).to_contain_text("Wed 10:00–11:00"); expect(sec).to_contain_text("Chandra Gummaluru")
        expect(v.locator(".hb-main")).to_contain_text("BA 4010")
        v.wait_for_timeout(700); v.screenshot(path=f"{OUT}/191-hub-team.png", full_page=True)
        v.click(".hb-tab:has-text('This week')")
        expect(v.locator(".hb-days")).to_contain_text("LEC0101")
        expect(v.locator(".hb-days")).to_contain_text("Office hours")
        print("2 the hub shows the section, office hours and team; This week the times")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
