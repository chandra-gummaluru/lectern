"""Home (three newest as cards, the rest as a list, filters), a course offering's page (Course page,
Evaluations, Gradebook, Settings), and the gradebook's parts with Back.
Run with the server going (python app.py), then: python tests/browser/flow_parts.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
from flow_links import BOOK

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-utor-private", True, {
        "csc258/f26/grades.json": json.dumps(BOOK), "csc258/f26/old-quiz/exam.json": json.dumps({"settings": {"title": "Old quiz"}}),
        "csc108/w27/grades.json": json.dumps(BOOK), "csc258/f25/grades.json": json.dumps(BOOK), "csc258/w26/grades.json": json.dumps(BOOK), "csc108/f25/grades.json": json.dumps(BOOK)}))
    gh.add(Repo("chandra-gummaluru/courses-utor", False, {"csc258/f26/info.html": "x"}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png", full_page=True)
        path = lambda: page.inner_text("#lt-path").replace("\n", " ")
        G = "[data-lt-tool='grades'] "
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-utor-private', pub:'chandra-gummaluru/courses-utor'})); }""")
        page.reload(); page.wait_for_timeout(1500); shot("140-home")
        print("cards:", page.eval_on_selector_all(".lt-card[data-k] .lt-strip", "e => e.map(x => x.textContent.trim())"), "| list:", page.eval_on_selector_all(".lt-orow", "e => e.map(x => x.innerText.replace(/\\n/g,' '))"))
        page.select_option(".lt-filter[data-f='c']", "csc258"); page.wait_for_timeout(300)
        print("csc258 only:", page.eval_on_selector_all("[data-k]", "e => e.length"))
        page.select_option(".lt-filter[data-f='c']", ""); page.select_option(".lt-filter[data-f='t']", "f26"); page.wait_for_timeout(300); shot("141-home-f26")
        print("f26 only:", page.eval_on_selector_all("[data-k]", "e => e.length"))
        page.click(".lt-card[data-k='0']"); page.wait_for_timeout(1500); shot("142-offering")
        print("offering:", page.inner_text(".lt-off-head").replace("\n", " "), "| parts:", page.eval_on_selector_all(".lt-part h2", "e => e.map(x => x.textContent)"), "| loose:", page.inner_text("#lt-loose").replace("\n", " "))
        page.click("[data-part='evals']"); page.wait_for_timeout(2500); shot("143-evals")
        print("evals:", page.evaluate("location.hash"), "|", path(), "| tabs:", page.eval_on_selector_all(G + "#tb-view button", "e => e.map(x => x.textContent)"))
        page.locator(G + ".erow", has_text="Midterm").first.click(); page.wait_for_timeout(500)
        print("eval page:", path())
        page.go_back(); page.wait_for_timeout(800)
        print("back:", path())
        page.go_back(); page.wait_for_timeout(1200)
        print("back:", page.evaluate("location.hash"))
        page.click("[data-part='book']"); page.wait_for_timeout(1500); shot("144-gradebook")
        print("book:", page.evaluate("location.hash"), "|", path(), "| tabs:", page.eval_on_selector_all(G + "#tb-view button", "e => e.map(x => x.textContent)"))
        page.screenshot(path=f"{OUT}/146-gradebook-head.png")
        page.locator(G + ".c-name button").first.click(); page.wait_for_timeout(500)
        print("student:", path(), "| buttons:", page.eval_on_selector_all(G + ".editor.student .ed-acts button", "e => e.map(x => x.textContent || x.title)"))
        page.locator(G + ".editor.student .ed-acts button", has_text="Drop").click(); page.wait_for_timeout(300)
        print("after drop:", page.eval_on_selector_all(G + ".editor.student .ed-acts button", "e => e.map(x => x.textContent || x.title)"))
        page.go_back(); page.wait_for_timeout(600); print("back:", path())
        page.evaluate("location.hash = '#/csc258/f26'"); page.wait_for_timeout(800)
        page.click("[data-part='settings']"); page.wait_for_timeout(1500); shot("145-settings")
        print("settings:", page.evaluate("location.hash"), "|", path(), "| tabs:", page.eval_on_selector_all(G + "#tb-view button", "e => e.map(x => x.textContent)"))
        page.evaluate("location.hash = '#/csc258/f26/evaluations'"); page.wait_for_timeout(1200)
        page.locator(G + ".erow", has_text="Midterm").first.click(); page.wait_for_timeout(500); page.screenshot(path=f"{OUT}/147-eval-head.png"); page.click(G + ".ed-acts [data-act='ev-build']"); page.wait_for_timeout(2500)
        print("exam:", path())
        page.locator("#lt-path button.lt-step", has_text="Evaluations").click(); page.wait_for_timeout(1500)
        print("evals again:", page.evaluate("location.hash"), "|", path())
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
