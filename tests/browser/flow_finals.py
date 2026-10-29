"""A student's course grade set by hand (a grade, or a special grade like IPR), course rules for work not
written or deferred, and deleting with two clicks.
Run with the server going (python app.py), then: python tests/browser/flow_finals.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
from flow_links import ev

def main():
    book = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
            "evals": [ev("a1", "Assignment", "Assignment", "A1", "assignment", 50), ev("fe", "Final Exam", "Final Exam", "FE", "test", 50)],
            "groups": [], "students": [{"num": "1", "first": "Maya", "last": "Castillo", "f": {}}, {"num": "2", "first": "Ken", "last": "Ito", "f": {}}, {"num": "3", "first": "Ada", "last": "Love", "f": {}, "notes": "An old note from before"}],
            "marks": {"1": {"a1": {"pts": 8}, "fe": {"pts": 7}}, "2": {"a1": {"pts": 9}, "fe": {"status": "deferred"}}, "3": {"a1": {"pts": 6}, "fe": {"missed": True}}}, "overrides": {}}
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(book)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1360, "height": 900}); gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort()); ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e))); page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3})); localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        G = "[data-lt-tool='grades'] "
        grades = lambda: page.eval_on_selector_all(G + "tr[data-s]", "e => e.map(r => r.querySelector('.c-name b').textContent + ': ' + r.querySelector('td[data-grade]').textContent.trim())")
        # Rules: deferred final → IPR; final not submitted → set to 40%
        page.goto(BASE + "#/csc258/f26/settings"); page.reload(); page.wait_for_timeout(2500)
        for when, eff in [("deferred", "code"), ("missed", "set")]:
            page.click(G + "[data-act='pol-fadd']"); page.wait_for_timeout(300)
            row = page.locator(G + "[data-fail]").last
            row.locator("select[data-pol='target']").select_option("fe"); page.wait_for_timeout(200)
            row = page.locator(G + "[data-fail]").last; row.locator("select[data-pol='when']").select_option(when); page.wait_for_timeout(200)
            row = page.locator(G + "[data-fail]").last; row.locator("select[data-pol='effect']").select_option(eff); page.wait_for_timeout(200)
            if eff == "set": row = page.locator(G + "[data-fail]").last; row.locator("input[data-pol='value']").fill("40"); page.wait_for_timeout(400)
        page.screenshot(path=f"{OUT}/200-rules.png", full_page=True)
        page.evaluate("location.hash = '#/csc258/f26/gradebook'"); page.wait_for_timeout(1200)
        print("with rules:", grades())
        # Hand-set: Maya 85, then Ken AII
        page.locator(G + ".c-name button", has_text="Castillo").click(); page.wait_for_timeout(500)
        page.click(G + ".fg-in"); page.keyboard.type("85"); page.keyboard.press("Enter"); page.wait_for_timeout(400)
        page.fill(G + "[data-ed='nt-text'], " + G + "[data-nt-rt] .rt-ed", "Remark accepted"); page.click(G + "[data-ed='nt-add']"); page.wait_for_timeout(300)
        page.fill(G + "[data-ed='nt-text'], " + G + "[data-nt-rt] .rt-ed", "Second note"); page.keyboard.press("Control+Enter"); page.wait_for_timeout(300)
        page.screenshot(path=f"{OUT}/201-student-grade.png")
        print("maya now:", page.input_value(G + ".fg-in"), "|", page.inner_text(G + "#fg-note"), "| notes:", page.eval_on_selector_all(G + ".nt-item", "e => e.map(x => x.innerText.replace(/\\n/g, ' / '))"))
        page.go_back(); page.wait_for_timeout(600)
        print("after hand-set:", grades())
        page.locator(G + ".c-name button", has_text="Castillo").click(); page.wait_for_timeout(500)
        page.fill(G + ".fg-in", ""); page.keyboard.press("Enter"); page.wait_for_timeout(300)
        print("maya cleared:", page.input_value(G + ".fg-in") or "(empty) placeholder " + page.get_attribute(G + ".fg-in", "placeholder"))
        page.go_back(); page.wait_for_timeout(600)
        page.locator(G + ".c-name button", has_text="Love").click(); page.wait_for_timeout(500)
        print("ada notes:", page.eval_on_selector_all(G + ".nt-item", "e => e.map(x => x.innerText.replace(/\\n/g, ' / '))"))
        page.go_back(); page.wait_for_timeout(600)
        page.locator(G + ".c-name button", has_text="Ito").click(); page.wait_for_timeout(500)
        page.select_option(G + "[data-ed='fg-code']", "AII"); page.wait_for_timeout(300)
        print("ken now:", page.input_value(G + ".fg-in"), "|", page.inner_text(G + "#fg-note"))
        page.screenshot(path=f"{OUT}/203-ken.png")
        # Delete asks first: Cancel keeps them; Delete deletes
        page.click(G + ".ed-acts [data-ed='sremove']"); page.wait_for_selector(".lt-modal [data-yes]")
        print("asks:", page.inner_text(".lt-modal").replace("\n", " | "))
        page.screenshot(path=f"{OUT}/202-delete-asks.png")
        page.click(".lt-modal [data-no]"); page.wait_for_timeout(200)
        assert page.query_selector(G + ".editor.student"), "Cancel keeps them"
        page.click(G + ".ed-acts [data-ed='sremove']"); page.click(".lt-modal [data-yes]"); page.wait_for_timeout(500)
        print("after Delete:", grades())
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
