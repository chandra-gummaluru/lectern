"""Back and Forward (Lectern's pages and the pages inside a builder), the Home cards, and deleting a course offering.
Run with the server going (python app.py), then: python tests/browser/flow_nav.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
from flow_links import BOOK

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-utor-private", True, {"csc258/f26/grades.json": json.dumps(BOOK), "csc108/w27/grades.json": json.dumps(BOOK), "csc108/w27/final/exam.json": "{}"}))
    gh.add(Repo("chandra-gummaluru/courses-utor", False, {"csc258/f26/info.html": "x", "csc108/w27/slides.pdf": "x"}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 860})
        gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")
        path = lambda: page.inner_text("#lt-path").replace("\n", " ")
        G = "[data-lt-tool='grades'] "
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-utor-private', pub:'chandra-gummaluru/courses-utor'})); }""")
        page.reload(); page.wait_for_timeout(1500); shot("110-home-cards")
        page.click(".lt-card[data-k='0']"); page.wait_for_timeout(500)
        page.click("[data-part='book']"); page.wait_for_timeout(2500)
        page.locator("[data-lt-tool='grades']").get_by_text("Castillo").first.click(); page.wait_for_timeout(500)
        print("at:", path())
        steps = []
        for k in range(3):
            page.click(G + "[data-nav='-1']" if page.query_selector(G + "[data-nav='-1']") and page.is_visible(G + "[data-nav='-1']") else "#lt-bar [data-nav='-1']"); page.wait_for_timeout(1200)
            steps.append(path())
        print("back x3:", steps)
        page.click("#lt-bar [data-nav='1']" if page.is_visible("#lt-bar [data-nav='1']") else G + "[data-nav='1']"); page.wait_for_timeout(1500)
        print("forward:", path())
        shot("111-after-forward")
        # Delete csc108/w27
        page.evaluate("location.hash = '#/csc108/w27'"); page.wait_for_timeout(800)
        page.click("#lt-del-off"); page.wait_for_timeout(300); shot("112-delete-dialog")
        print("delete enabled before typing:", page.is_enabled(".lt-modal [data-ok]"))
        page.fill("#del-name", "csc108/w27"); page.click(".lt-modal [data-ok]"); page.wait_for_timeout(1500)
        pv = gh.repos["chandra-gummaluru/courses-utor-private"]; pb = gh.repos["chandra-gummaluru/courses-utor"]
        print("left in private:", sorted(pv.commits[pv.head]["files"]), "| public:", sorted(pb.commits[pb.head]["files"]), "| hash:", page.evaluate("location.hash"))
        print("cards:", page.eval_on_selector_all(".lt-card[data-k] .lt-strip", "els => els.map(e => e.textContent.trim())"))
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
