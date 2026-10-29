"""Activities (the course page's weeks): dragging a week to another place in the term, and a divider.
(Weeks used to be edited in the course page builder; they're on Activities now, lectures.json, which saves
by itself. Its old `dates` and `more` modes tested the builder's week and table editing, which is gone.)
Run:  python tests/browser/flow_drag.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE

LECT = {"format": "lectern-lectures/1", "weeks": [
    {"id": "w1", "label": "Week 1", "start": "2026-09-07", "end": "2026-09-11", "topic": "Intro", "cards": []},
    {"id": "w2", "label": "Week 2", "start": "2026-09-14", "end": "2026-09-18", "topic": "Logic", "cards": []},
    {"id": "b1", "isBreak": True, "text": "Reading Week"},
    {"id": "w3", "label": "Week 3", "start": "2026-09-21", "end": "2026-09-25", "topic": "Circuits", "cards": []},
]}
GRADES = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"}, "evals": [], "groups": [], "students": [], "marks": {}, "overrides": {}}


def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/lectures.json": json.dumps(LECT), "csc258/f26/grades.json": json.dumps(GRADES)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
    PRIV = gh.repos["chandra-gummaluru/courses-private"]
    saved = lambda: [w.get("label") or "--" + w.get("text", "") for w in json.loads(PRIV.commits[PRIV.head]["files"]["csc258/f26/lectures.json"])["weeks"]]
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1360, "height": 900}); gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "#/csc258/f26/activities"); page.wait_for_selector("[data-units] > [data-unit]")
        units = lambda: page.eval_on_selector_all("[data-units] > [data-unit]", "e => e.map(x => x.classList.contains('lx-break') ? '--' + ((x.querySelector('input') || {}).value || x.innerText.trim()) : x.querySelector('.lx-row.grp').innerText.split('\\n')[0].trim())")
        print("before:", units())
        # Week 3 to the top
        page.locator("[data-unit='w3'] .lx-row.grp").drag_to(page.locator("[data-unit='w1'] .lx-row.grp"), target_position={"x": 40, "y": 5}); page.wait_for_timeout(1500)
        print("week 3 to top:", units(), "| saved:", saved())
        assert saved()[0] == "Week 3", saved()
        # The divider: after Week 3 (now first), i.e. above Week 1
        page.locator("[data-unit='b1']").drag_to(page.locator("[data-unit='w1'] .lx-row.grp"), source_position={"x": 6, "y": 10}, target_position={"x": 40, "y": 5}); page.wait_for_timeout(1500)
        print("divider moved:", units(), "| saved:", saved())
        assert saved() == ["Week 3", "--Reading Week", "Week 1", "Week 2"], saved()
        page.screenshot(path=f"{OUT}/190-drag.png")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_drag: OK")


if __name__ == "__main__":
    main()
