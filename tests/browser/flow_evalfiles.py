"""An evaluation's files, added in Evaluations, show on the course page by themselves.

The owner opens Evaluations, opens the Midterm, uploads a file and adds a link, saves the gradebook;
the course hub (without saving the course page) shows both as the Midterm's buttons, and the upload
is in the offering's public files. Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_evalfiles.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json"), encoding="utf-8").read()
BOOK = open(os.path.join(ROOT, "sample-data/demo-courses-private/csc258/f26/grades.json"), encoding="utf-8").read()
G = "[data-lt-tool='grades'] "


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("pub", {"csc258/f26/course.json": DATA})
        srv.put("priv", {"csc258/f26/grades.json": BOOK})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        me = ctx.new_page()
        me.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(me, hash="#/csc258/f26/evaluations")
        me.wait_for_selector(G + ".erow")
        me.locator(G + ".erow", has_text="Midterm").first.click()
        me.wait_for_selector(G + ".editor[data-eval]")
        me.locator(G + "[data-ed=ef-up]").scroll_into_view_if_needed()
        with me.expect_file_chooser() as fc:
            me.click(G + "[data-ed=ef-up]")
        fc.value.set_files(files=[{"name": "Midterm practice.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 practice"}])
        me.wait_for_selector(G + ".ef-row")
        me.click(G + "[data-ed=ef-add]")
        me.locator(G + "[data-ed=ef-url]").last.fill("https://example.edu/formula-sheet.pdf")
        me.locator(G + "[data-ed=ef-label]").last.fill("Formula sheet")
        me.locator(G + ".ed-sec", has_text="Files and Links").scroll_into_view_if_needed()
        me.screenshot(path=f"{OUT}/170-eval-files.png")
        me.keyboard.press("Control+s"); me.wait_for_timeout(2500)
        book = json.loads(srv.text("priv", "csc258/f26/grades.json"))
        mt = [e for e in book["evals"] if e["id"] == "mt"][0]
        assert [f["label"] for f in mt["files"]] == ["Midterm-practice", "Formula sheet"] or [f["label"] for f in mt["files"]] == ["Midterm practice", "Formula sheet"], mt.get("files")
        up = mt["files"][0]["url"]
        assert up.endswith("/p/chandra/csc258/f26/evaluations/Midterm-practice.pdf"), up
        assert srv.repo("pub").read("csc258/f26/evaluations/Midterm-practice.pdf") == b"%PDF-1.4 practice"
        print("1 saved:", mt["files"])

        v = ctx.browser.new_context().new_page()
        v.goto(srv.base + "c/chandra/csc258/f26/#evaluations"); v.wait_for_selector(".hb-t")
        row = v.locator(".hb-t tr", has_text="Midterm").first
        expect(row.locator("a.hb-file")).to_have_count(2)
        v.screenshot(path=f"{OUT}/171-hub-eval-files.png", full_page=True)
        assert v.request.get(up).status == 200
        print("2 the hub shows them, without saving the course page")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
