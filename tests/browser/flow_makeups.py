"""Makeups: an evaluation of its own, chosen in the original's policy with a part of its weight;
makeups and shifted weight together make up the original's weight.
Run with the server going (python app.py), then: python tests/browser/flow_makeups.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
from flow_links import ev

def main():
    old_mk = ev("mm", "Midterm makeup", "", "MM", "test", 0, "2026-10-28", "18:10"); old_mk["makeupFor"] = "mt"; old_mk["total"] = 20; old_mk["label"] = ""
    mt = ev("mt", "Midterm", "Midterm", "MT", "test", 20, "2026-10-21", "18:10"); mt["total"] = 20
    book = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
            "evals": [ev("a1", "Assignment 1", "Assignment", "A1", "assignment", 30), mt, old_mk, ev("fe", "Final Exam", "Final Exam", "FE", "test", 50)],
            "groups": [], "students": [{"num": "1", "first": "Maya", "last": "Castillo", "f": {}}, {"num": "2", "first": "Ken", "last": "Ito", "f": {}}],
            "marks": {"1": {"a1": {"pts": 10}, "mt": {"missed": True}, "mm": {"pts": 15}, "fe": {"pts": 10}}, "2": {"a1": {"pts": 10}, "mt": {"pts": 10}, "fe": {"pts": 10}}}, "overrides": {}}
    for e in book["evals"]: e["total"] = e.get("total") or 10
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(book)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        G = "[data-lt-tool='grades'] "
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/evaluations"); page.reload(); page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT}/150-evals-makeup.png", full_page=True)
        print("list:", page.eval_on_selector_all(G + ".erow", "e => e.map(x => x.querySelector('h3').textContent + (x.classList.contains('mkrow') ? ' [makeup]' : '') + ' | ' + x.querySelectorAll('p')[1].textContent)"))
        grade = lambda: page.evaluate("() => { const g = document.querySelector(\"[data-lt-tool='grades']\"); return 0; }")
        page.locator(G + ".erow", has_text="Midterm").first.click(); page.wait_for_timeout(500)
        print("rows:", page.eval_on_selector_all(G + "#rw-rows .rw-row", "e => e.map(x => x.innerText.replace(/\\n/g,' ').replace(/\\s+/g,' '))"))
        # makeup 15%, and 5% to the Final
        page.fill(G + "input[data-ed='share'][data-v='mm']", "15"); page.wait_for_timeout(300)
        page.check(G + "input[data-ed='rwto'][data-v='fe']"); page.wait_for_timeout(400)
        page.fill(G + "input[data-ed='share'][data-v='fe']", "5"); page.wait_for_timeout(400)
        page.screenshot(path=f"{OUT}/151-midterm-policy.png", full_page=True)
        print("together:", page.inner_text(G + ".rw-stay").replace("\n", " "))
        page.locator("#lt-path button.lt-step", has_text="Evaluations").click(); page.wait_for_timeout(500)
        print("midterm says:", page.locator(G + ".erow", has_text="Midterm").first.locator("p").nth(1).inner_text())
        # Maya: A1 10/10*30, makeup 15/20 for 15%, MT's 5% to the final (10/10 for 55%): 30 + 11.25 + 55 = 96.25
        page.evaluate("location.hash = '#/csc258/f26/gradebook'"); page.wait_for_timeout(1500)
        gr = page.eval_on_selector_all(G + "tr[data-s]", "e => e.map(r => r.querySelector('.c-name b').textContent + ': ' + r.querySelector('td[data-grade]').textContent.trim())")
        print("grades:", gr); assert len(gr) == 2, gr
        # New makeup from the editor
        page.evaluate("location.hash = '#/csc258/f26/evaluations'"); page.wait_for_timeout(1200)
        page.locator(G + ".erow", has_text="Assignment").first.click(); page.wait_for_timeout(400)
        page.click(G + "[data-ed='mode'][data-v='reweight']"); page.wait_for_timeout(300)
        page.click(G + "[data-ed='mkadd']"); page.wait_for_timeout(500)
        print("a1 rows:", page.eval_on_selector_all(G + "#rw-rows .rw-row.on", "e => e.map(x => x.innerText.replace(/\\n/g,' ').replace(/\\s+/g,' '))"))
        page.locator("#lt-path button.lt-step", has_text="Evaluations").click(); page.wait_for_timeout(500)
        print("list now:", page.eval_on_selector_all(G + ".erow", "e => e.map(x => x.querySelector('h3').textContent + (x.classList.contains('mkrow') ? ' [makeup]' : ''))"))
        page.locator(G + ".erow", has_text="Midterm").first.click(); page.wait_for_timeout(500)
        page.screenshot(path=f"{OUT}/152-makeup-ui.png", full_page=True)
        print("kinds:", page.eval_on_selector_all(G + "#rw-rows .rw-row.on", "e => e.map(x => [...x.querySelectorAll('.rw-kind button')].map(b => b.textContent + (b.getAttribute('aria-pressed') === 'true' ? '*' : '')).join('/'))"))
        page.keyboard.press("Control+s"); page.wait_for_timeout(2000)
        r = gh.repos["chandra-gummaluru/courses-private"]; saved = json.loads(r.commits[r.head]["files"]["csc258/f26/grades.json"])
        print("saved MT missed:", [e["missed"] for e in saved["evals"] if e["id"] == "mt"], "| makeups:", [(e["name"], e.get("makeupFor")) for e in saved["evals"] if e.get("makeupFor")])
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
