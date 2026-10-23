"""Course page: dragging weeks (they take the dates and numbers of where they land) and section dividers.
Run with the server going (python app.py), then: python tests/browser/flow_drag.py"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
OLD = os.path.join(os.path.dirname(__file__), "old-course-page.html")

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"README.md": "x"}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"csc258/f26/info.html": open(OLD, encoding="utf-8").read()}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1360, "height": 900}); gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort()); ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e))); page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3})); localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/course"); page.reload(); page.wait_for_timeout(2500)
        C = "[data-lt-tool='course'] "
        rows = lambda: page.eval_on_selector_all(C + ".e-weekrow, " + C + ".e-divider", "e => e.map(x => x.classList.contains('e-divider') ? '--' + (x.querySelector('.ed').textContent || 'divider') : x.querySelector('.wr-name').textContent + ' ' + ((x.querySelector('.wr-dates')||{}).textContent||'') + ' ' + x.querySelector('.wr-topic').textContent)")
        print("before:", rows())
        page.drag_and_drop(C + ".e-weekrow >> nth=2", C + ".e-weekrow >> nth=0", target_position={"x": 40, "y": 5}); page.wait_for_timeout(500)
        print("week 3 to top:", rows())
        page.locator(C + "button", has_text="+ Add section divider").click(); page.wait_for_timeout(300); page.keyboard.type("Part 2"); page.wait_for_timeout(200)
        page.drag_and_drop(C + ".e-divider .e-grip", C + ".e-weekrow >> nth=2", target_position={"x": 40, "y": 5}); page.wait_for_timeout(500)
        print("divider moved:", rows())
        page.screenshot(path=f"{OUT}/190-drag.png")
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__" and len(sys.argv) == 1:
    main()

def dates():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"README.md": "x"}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"csc258/f26/info.html": open(OLD, encoding="utf-8").read()}))
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1360, "height": 900}); gh.attach(ctx)
        page = ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e))); page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3})); localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/course"); page.reload(); page.wait_for_timeout(2500)
        C = "[data-lt-tool='course'] "
        page.locator(C + ".e-weekrow").first.click(); page.wait_for_timeout(400)
        page.click(C + "[data-act='dates']"); page.wait_for_timeout(300)
        page.click(".when-pop [data-day='2026-09-07']"); page.wait_for_timeout(150); page.screenshot(path=f"{OUT}/191-week-dates.png")
        page.click(".when-pop [data-day='2026-09-11']"); page.check(".when-pop #wp-next"); page.click(".when-pop [data-w='done']"); page.wait_for_timeout(400)
        print("week 1:", page.inner_text(C + "[data-act='dates']"))
        page.locator("#lt-path button.lt-step", has_text="Course Page").click(); page.wait_for_timeout(400)
        print("rows:", page.eval_on_selector_all(C + ".e-weekrow .wr-dates", "e => e.map(x => x.textContent)"))
        b.close(); print(errs or "no page errors")

def more():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"README.md": "x"}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"csc258/f26/info.html": open(OLD, encoding="utf-8").read()}))
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1360, "height": 900}); gh.attach(ctx)
        page = ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e))); page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3})); localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/course"); page.reload(); page.wait_for_timeout(2500)
        C = "[data-lt-tool='course'] "
        # table: move the Email column to the front, then add rows and move the second above the first
        cols = lambda: page.eval_on_selector_all(C + ".cpb-tbl >> nth=0", "t => [...t[0].querySelectorAll('th.e-thc .ed')].map(x => x.textContent)")
        tbl = page.locator(C + ".cpb-tbl").first; tbl.scroll_into_view_if_needed()
        tbl.locator("th.e-thc").nth(2).hover(); page.wait_for_timeout(150)
        page.drag_and_drop(C + ".cpb-tbl >> nth=0 >> th.e-thc >> nth=2 >> .e-tgrip", C + ".cpb-tbl >> nth=0 >> th.e-thc >> nth=0", target_position={"x": 5, "y": 10})
        page.wait_for_timeout(400); print("columns:", cols())
        cell = tbl.locator("tr.cpb-row").last.locator("td").first; cell.click(); page.keyboard.type("Ada"); page.wait_for_timeout(300)
        cell = page.locator(C + ".cpb-tbl").first.locator("tr.cpb-row").last.locator("td").first; cell.click(); page.keyboard.type("Bob"); page.wait_for_timeout(300)
        rows = lambda: page.eval_on_selector_all(C + ".cpb-tbl >> nth=0", "t => [...t[0].querySelectorAll('tr.cpb-row')].map(r => r.querySelector('td').textContent)")
        print("rows:", rows())
        page.locator(C + ".cpb-tbl").first.locator("tr.cpb-row").nth(1).hover()
        page.drag_and_drop(C + ".cpb-tbl >> nth=0 >> tr.cpb-row >> nth=1 >> .e-rgrip", C + ".cpb-tbl >> nth=0 >> tr.cpb-row >> nth=0", target_position={"x": 20, "y": 3})
        page.wait_for_timeout(400); print("rows after:", rows())
        # week page: delete at the top right; lectures dragged
        page.locator(C + ".e-weekrow").first.click(); page.wait_for_timeout(400)
        print("week top:", page.eval_on_selector_all(C + ".e-sub-acts button", "e => e.map(x => x.title)"), "| bottom moves:", page.locator(C + "button", has_text="Move earlier").count())
        lec = lambda: page.eval_on_selector_all(C + ".e-lcell", "e => e.map(x => (x.querySelector('.cpb-clabel')||{}).textContent || (x.classList.contains('e-free') ? 'free' : 'off'))")
        print("lectures:", lec())
        page.drag_and_drop(C + ".e-lcell[data-lj='1']", C + ".e-lcell[data-lj='0']"); page.wait_for_timeout(400); print("swapped:", lec())
        page.drag_and_drop(C + ".e-lcell[data-lj='1']", C + ".e-lcell.e-free"); page.wait_for_timeout(400); print("to free:", lec())
        page.screenshot(path=f"{OUT}/192-week-top.png")
        page.locator(C + ".cpb-card").first.click(); page.wait_for_timeout(400)
        print("lecture top:", page.eval_on_selector_all(C + ".e-sub-acts button", "e => e.map(x => x.title)"))
        b.close(); print(errs or "no page errors")

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "dates":
    dates()
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "more":
    more()
