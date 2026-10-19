"""Gradebook: no edit bar; a mark's status comes from the little menu in its cell.
Run with the server going (python app.py), then: python tests/browser/flow_cellst.py"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
src = open(os.path.join(os.path.dirname(__file__), "flow_fx.py")).read().split("def main")[0]
exec(src)
from flow_links import ev

def main():
    import json
    from playwright.sync_api import sync_playwright
    book = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
            "evals": [ev("a1", "Assignment", "Assignment", "A1", "assignment", 50), ev("fe", "Final Exam", "Final Exam", "FE", "test", 50)], "groups": [],
            "students": [{"num": "1", "first": "Maya", "last": "Castillo", "f": {}}, {"num": "2", "first": "Ken", "last": "Ito", "f": {}}],
            "marks": {"1": {"a1": {"pts": 8}}, "2": {"a1": {"missed": True}}}, "overrides": {}}
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(book)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1360, "height": 900}); ctx.route("https://api.github.com/**", gh.handle)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort()); ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e))); page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3})); localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        G = "[data-lt-tool='grades'] "
        page.goto(BASE + "#/csc258/f26/gradebook"); page.reload(); page.wait_for_timeout(2500)
        page.click(G + "[data-act='fx-menu']"); page.wait_for_timeout(300); page.click(".dd-pop [data-pick='a1']"); page.wait_for_timeout(500)
        print("edit bar shown:", page.is_visible(G + "#ctx"))
        page.click(G + "input.mk[data-s='1']"); page.wait_for_timeout(200)
        page.screenshot(path=f"{OUT}/230-cell-focus.png")
        page.click(G + ".mk-st[data-s='1']"); page.wait_for_timeout(300)
        print("menu:", page.eval_on_selector_all(".dd-pop button", "e => e.map(x => x.innerText.trim())"))
        page.screenshot(path=f"{OUT}/231-cell-menu.png")
        page.click(".dd-pop [data-st='excused']"); page.wait_for_timeout(400)
        print("maya:", page.evaluate("document.querySelector(\"[data-lt-tool='grades'] td.c-cell input[data-s='1']\").closest('td').className"))
        page.hover(G + "td.c-cell >> nth=1"); page.click(G + ".mk-st[data-s='2']"); page.wait_for_timeout(300); page.click(".dd-pop [data-st='']"); page.wait_for_timeout(400)
        print("ken:", page.evaluate("document.querySelector(\"[data-lt-tool='grades'] td.c-cell input[data-s='2']\").closest('td').className"))
        page.screenshot(path=f"{OUT}/232-cell-after.png")
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
