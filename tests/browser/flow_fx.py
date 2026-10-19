"""The Gradebook's one-evaluation view: the course grade looks like any evaluation, no course column beside
an evaluation, and filters (leave out not submitted, and so on) for the table and the statistics.
Run with the server going (python app.py), then: python tests/browser/flow_fx.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
from flow_links import ev

def main():
    names = [("Maya", "Castillo"), ("Ken", "Ito"), ("Ada", "Love"), ("Sam", "Okafor"), ("Lee", "Park"), ("Ana", "Ruiz")]
    marks = {"1": {"a1": {"pts": 8}, "fe": {"pts": 7}}, "2": {"a1": {"missed": True}, "fe": {"status": "deferred"}}, "3": {"a1": {"pts": 3}, "fe": {"missed": True}},
             "4": {"a1": {"pts": 9}, "fe": {"pts": 9}}, "5": {"a1": {"status": "excused"}, "fe": {"pts": 4}}, "6": {"fe": {"pts": 6}}}
    book = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
            "evals": [ev("a1", "Assignment", "Assignment", "A1", "assignment", 50), ev("fe", "Final Exam", "Final Exam", "FE", "test", 50)], "groups": [],
            "students": [{"num": str(k + 1), "first": f, "last": l, "f": {}} for k, (f, l) in enumerate(names)], "marks": marks, "overrides": {}, "finals": {"6": {"code": "IPR"}}}
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
        heads = lambda: page.eval_on_selector_all(G + ".fx-grid thead th", "e => e.map(x => x.innerText.replace(/\\n/g, ' ').trim())")
        rows = lambda: page.eval_on_selector_all(G + ".fx-grid tbody tr[data-s]", "e => e.map(r => r.querySelector('.c-name b').textContent + ': ' + [...r.querySelectorAll('td')].slice(1).map(t => (t.querySelector('input') ? t.querySelector('input').value : t.innerText).trim()).join(' | '))")
        avg = lambda: page.inner_text(G + ".fx-avg").replace("\n", " ")
        print("grade heads:", heads()); print("grade rows:", rows()); print("grade avg:", avg())
        page.screenshot(path=f"{OUT}/210-fx-grade.png")
        page.click(G + "[data-act='fx-filter']"); page.wait_for_timeout(300); page.screenshot(path=f"{OUT}/211-fx-filter.png")
        page.check(".fx-fpop [data-fxf='codes']"); page.wait_for_timeout(300); page.check(".fx-fpop [data-fxf='notfinal']"); page.wait_for_timeout(300)
        print("filtered rows:", rows(), "| btn:", page.inner_text(G + ".fx-filt"), "| note:", page.inner_text(G + ".fx-fnote").replace("\n", " "))
        page.mouse.click(5, 300); page.wait_for_timeout(200)
        # an evaluation: no course column; leave out not submitted
        page.click(G + "[data-act='fx-menu']"); page.wait_for_timeout(300); page.click(".dd-pop [data-pick='a1']"); page.wait_for_timeout(500)
        print("a1 heads:", heads()); print("a1 rows:", rows()); print("a1 avg:", avg())
        page.click(G + "[data-act='fx-filter']"); page.wait_for_timeout(300); page.check(".fx-fpop [data-fxf='missed']"); page.wait_for_timeout(300)
        print("a1 no missed:", rows(), "|", avg())
        page.check(".fx-fpop [data-fxf='unmarked']"); page.wait_for_timeout(300); page.check(".fx-fpop [data-fxf='status']"); page.wait_for_timeout(300)
        print("a1 marked only:", rows(), "|", avg())
        page.screenshot(path=f"{OUT}/212-fx-a1.png")
        page.click(".fx-fpop [data-fxclear]"); page.wait_for_timeout(300)
        print("cleared:", len(rows()))
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
