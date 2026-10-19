"""The exam builder in Lectern: no top-bar row; zoom with Ctrl/⌘ and the wheel or keys, Fit to Window appears once
zoomed; the exam's settings sit in the edit bar and above the first page; solutions and rubric always shown; the eye shows the student preview.
Run with the server going (python app.py), then: python tests/browser/flow_examui.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
from flow_links import BOOK, open_eval

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(BOOK)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1360, "height": 900}); ctx.route("https://api.github.com/**", gh.handle)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort()); ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e))); page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3})); localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        G, X = "[data-lt-tool='grades'] ", "[data-lt-tool='exams'] "
        path = lambda: page.inner_text("#lt-path").replace("\n", " ")
        page.goto(BASE + "#/csc258/f26/evaluations"); page.reload(); page.wait_for_timeout(2500)
        open_eval(page, G, "mt"); page.click(G + ".ed-acts [data-act='ev-build']"); page.wait_for_timeout(3000)
        page.mouse.click(5, 880); page.wait_for_timeout(200)
        print("path:", path(), "| top row shown:", page.is_visible(X + ".tb"), "| float:", page.eval_on_selector_all(X + ".float-in button", "e => e.map(x => x.textContent.trim() || x.getAttribute('aria-label'))"))
        print("edit bar:", page.inner_text(X + "#ctx").replace("\n", " "))
        page.screenshot(path=f"{OUT}/220-exam-ui.png")
        z = lambda: page.evaluate("getComputedStyle(document.querySelector(\"[data-lt-tool='exams'] .shell\")).getPropertyValue('--zoom')")
        page.mouse.move(600, 500); page.keyboard.down("Control"); page.mouse.wheel(0, -300); page.keyboard.up("Control"); page.wait_for_timeout(300)
        print("after ctrl+wheel: zoom", z(), "| float:", page.eval_on_selector_all(X + ".float-in button", "e => e.map(x => x.textContent.trim() || x.getAttribute('aria-label'))"))
        page.screenshot(path=f"{OUT}/221-exam-zoomed.png")
        page.click(X + ".fl-fit"); page.wait_for_timeout(300)
        print("after Fit: zoom", z(), "| fit shown:", bool(page.query_selector(X + ".fl-fit")))
        page.keyboard.press("Control+Equal"); page.wait_for_timeout(300); print("ctrl+=: zoom", z(), "| fit shown:", bool(page.query_selector(X + ".fl-fit")))
        page.keyboard.press("Control+0"); page.wait_for_timeout(300); print("ctrl+0: zoom", z(), "| fit shown:", bool(page.query_selector(X + ".fl-fit")))
        page.click(X + ".addbar [data-act='add-q']"); page.wait_for_timeout(500)
        print("editing: solution shown", bool(page.query_selector(X + ".pq-sol")), "| rubric shown", bool(page.query_selector(X + ".pq-mark")), "| sheet:", page.evaluate("document.querySelector(\"[data-lt-tool='exams'] #sheet\").className"))
        page.screenshot(path=f"{OUT}/222-exam-edit.png")
        page.click(X + ".fl-eye"); page.wait_for_timeout(500)
        print("preview: solution shown", bool(page.query_selector(X + ".pq-sol")), "| rubric", bool(page.query_selector(X + ".pq-mark")), "| addbar", page.is_visible(X + ".addbar"), "| path:", path(), "| bar:", page.inner_text(X + "#ctx").replace("\n", " "))
        page.screenshot(path=f"{OUT}/224-exam-preview.png")
        page.click(X + ".fl-eye"); page.wait_for_timeout(400)
        print("eye again:", page.evaluate("document.querySelector(\"[data-lt-tool='exams'] #sheet\").className"), page.eval_on_selector_all(X + ".float-in button", "e => e.map(x => x.className + ':' + x.getAttribute('aria-pressed'))"))
        page.mouse.click(5, 880); page.wait_for_timeout(200)
        page.select_option(X + "#set-ver-n", "2"); page.wait_for_timeout(400)
        print("versions 2: bar", page.inner_text(X + "#ctx").replace("\n", " "))
        page.uncheck(X + "#set-pnum"); page.wait_for_timeout(300)
        page.click(X + "[data-act='topsp'][data-v='0.5']"); page.wait_for_timeout(300); page.click(X + "[data-act='topsp'][data-v='0.5']"); page.wait_for_timeout(300)
        page.click(X + "[data-act='tex-toggle']"); page.wait_for_timeout(300)
        page.fill(X + "textarea[data-set='macros']", "\\newcommand{\\R}{\\mathbb{R}}"); page.wait_for_timeout(300)
        page.click(X + ".cx-seg [data-v='handout']"); page.wait_for_timeout(400)
        page.screenshot(path=f"{OUT}/225-exam-docbar.png")
        print("settings now:", page.evaluate("(() => { const s = Lectern.tools ? null : null; return null; })()"))
        page.click(X + ".cx-seg [data-v='exam']"); page.wait_for_timeout(400)
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
