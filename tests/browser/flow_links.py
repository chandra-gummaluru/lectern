"""Cross-links, end to end against the real server: the course page's Evaluations is the gradebook's marking
scheme (it goes to course.json when the gradebook is saved); a linked document's total is its evaluation's out
of; Build opens an evaluation's handout, or starts its exam or handout. Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_links.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json"), encoding="utf-8").read()

def ev(i, name, label, short, typ, w, date="", time="", total=10, missed=None):
    return {"id": i, "name": name, "label": label, "title": "", "short": short, "type": typ, "total": total, "weight": w, "date": date, "time": time,
            "makeupFor": None, "missed": missed or {"mode": "zero", "to": [], "split": "custom"}, "shortAuto": False}

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
        "evals": [ev("a1", "Assignment 1", "Assignment", "A1", "assignment", 15, "2026-09-25", "23:59"),
                  ev("l1", "Lab 1", "Lab", "L1", "assignment", 0, "2026-09-18", "17:00"),
                  ev("l2", "Lab 2", "Lab", "L2", "assignment", 0, "2026-09-25", "17:00"),
                  ev("mt", "Midterm", "Midterm", "MT", "test", 30, "2026-10-21", "18:10", missed={"mode": "reweight", "to": [{"id": "fe", "share": 100}], "split": "custom"}),
                  ev("fe", "Final Exam", "Final Exam", "FE", "test", 45)],
        "groups": [{"id": "g1", "name": "Labs", "short": "Labs", "weight": 10, "keep": 1, "members": ["l1", "l2"]}],
        "students": [{"num": "1001", "first": "Maya", "last": "Castillo", "f": {}}], "marks": {"1001": {"a1": {"pts": 9}}}, "overrides": {}}
HANDOUT = {"format": "exam-builder/2", "settings": {"title": "Assignment 1", "layout": "handout", "link": "a1"}, "items": [], "total": 25}

G, X = "[data-lt-tool='grades'] ", "[data-lt-tool='exams'] "


def open_eval(page, eid):
    """The evaluation's own page (where Build is). Lectern opens the gradebook where it was left."""
    if "/evaluations" not in page.evaluate("location.hash"):
        page.evaluate("location.hash = '#/csc258/f26/evaluations'")
    page.wait_for_selector(G + ".erow, " + G + ".editor[data-eval]")
    ed = page.query_selector(G + ".editor[data-eval]")
    if ed and ed.get_attribute("data-eval") != eid:
        page.locator("#lt-path button.lt-step", has_text="Evaluations").click()
    if not page.query_selector(G + f".editor[data-eval='{eid}']"):
        page.wait_for_selector(G + f".erow[data-id='{eid}']"); page.click(G + f".erow[data-id='{eid}']")
    page.wait_for_selector(G + f".editor[data-eval='{eid}'] [data-act='ev-build']")


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(BOOK), "csc258/f26/a1/exam.json": json.dumps(HANDOUT)})
        srv.put("pub", {"csc258/f26/course.json": DATA})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n, full=False: page.screenshot(path=f"{OUT}/{n}.png", full_page=full)
        path = lambda: page.inner_text("#lt-path").replace("\n", " ")

        # 1. Assignment 1's out of comes from its handout (25), and can't be typed over.
        srv.sign_in(page, hash="#/csc258/f26/evaluations")
        open_eval(page, "a1")
        print("1 A1:", page.inner_text(G + ".editor[data-eval='a1']").split("Points")[1][:80].replace("\n", " "))
        expect(page.locator(G + ".editor[data-eval='a1']")).to_contain_text("Out of 25: the total marks of its handout")
        expect(page.locator(G + ".editor[data-eval='a1'] [data-act='ev-build']")).to_have_text("Open handout")
        shot("83-grades-build")

        # 2. Saving the gradebook puts its marking scheme on the course page.
        page.keyboard.press("Control+s"); page.wait_for_timeout(2500)
        g = json.loads(srv.text("priv", "csc258/f26/grades.json"))
        assert next(e for e in g["evals"] if e["id"] == "a1")["total"] == 25, "the handout's total is saved as A1's out of"
        sc = json.loads(srv.text("pub", "csc258/f26/course.json"))["page"]["scheme"]
        print("2 scheme units:", [(u.get("name"), u.get("weight")) for u in sc["units"]])
        assert [u["name"] for u in sc["units"]][:2] == ["Assignment 1", "Labs"], sc["units"]
        v = ctx.new_page(); v.goto(srv.base + "c/chandra/csc258/f26/#evaluations"); v.wait_for_selector(".hs-ev")
        txt = v.inner_text(".hb-main")
        print("   course page:", txt.replace("\n", " | ")[:200])
        assert "Assignment 1" in txt and "Labs" in txt and "Midterm" in txt and "15%" in txt, txt
        v.screenshot(path=f"{OUT}/80-course-scheme.png", full_page=True); v.close()

        # 3. Build the Midterm: a new exam, opened in the exam builder.
        open_eval(page, "mt"); page.click(G + ".editor[data-eval='mt'] [data-act='ev-build']")
        page.wait_for_selector("body.lt-tool-exams", timeout=15000); page.wait_for_timeout(1500)
        print("3 path:", path(), "| cover:", bool(page.query_selector(X + ".cover-blk")))
        assert "Exams" in path() or "Midterm" in path(), path()
        assert page.query_selector(X + ".cover-blk"), "a test's document is an exam (a cover page)"
        shot("84-built-exam")

        # 4. Lab 2: a handout (an assignment's document). The new exam isn't saved yet: Lectern may ask first.
        open_eval(page, "mt")
        print("4 midterm button now:", page.inner_text(G + ".editor[data-eval='mt'] [data-act='ev-build']"))
        open_eval(page, "l2"); page.click(G + ".editor[data-eval='l2'] [data-act='ev-build']"); page.wait_for_timeout(1000)
        if page.query_selector(".lt-modal [data-yes]"): page.click(".lt-modal [data-yes]"); page.wait_for_timeout(1000)
        page.wait_for_selector(X + ".ho-head", timeout=15000)
        print("5 path:", path(), "| handout head:", bool(page.query_selector(X + ".ho-head")), "| answer-space buttons:", len(page.query_selector_all(X + ".add-space")))
        shot("85-built-handout")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_links: OK")


if __name__ == "__main__":
    main()
