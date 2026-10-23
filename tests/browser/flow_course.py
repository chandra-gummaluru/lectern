"""Course page: the weekly layout (lecture slots in thirds, No class, more hours, the evaluations row)
and opening an older page (its lecture cards become one hour each).
Run with the server going (python app.py), then: python tests/browser/flow_course.py [old-page.html]"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE

OLD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "old-course-page.html")

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"README.md": "x"}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"csc258/f26/info.html": open(OLD, encoding="utf-8").read()}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n, full=False: page.screenshot(path=f"{OUT}/{n}.png", full_page=full)
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/course"); page.reload(); page.wait_for_timeout(2500)
        C = "[data-lt-tool='course'] "
        shot("70-course-weeks")
        print("rows:", page.eval_on_selector_all(C + ".e-weekrow", "els => els.map(e => e.querySelector('.wr-name').textContent + ' ' + [...e.querySelectorAll('.wr-slots i')].map(i => i.className + ':' + i.offsetWidth).join(','))"))
        # Week 1: No class at the end, then take it out; a new lecture, 3 hours long
        page.click(C + ".e-weekrow >> nth=0"); page.wait_for_timeout(500); shot("71-week1")
        print("path:", page.inner_text("#lt-path").replace("\n", " "), "|", page.inner_text(C + ".e-hours"))
        page.click(C + ".e-addlec"); page.wait_for_timeout(500)   # a new lecture at the end, opens its page
        print("new lecture:", page.inner_text(C + ".e-sub-h"), "| path:", page.inner_text("#lt-path").replace("\n", " "))
        page.fill(C + "input[data-bindv$='.title']", "Logic review"); page.keyboard.press("Enter"); page.wait_for_timeout(200)
        page.click(C + "[data-act='lec-hours'][data-d='1']"); page.wait_for_timeout(200); page.click(C + "[data-act='lec-hours'][data-d='1']"); page.wait_for_timeout(300)
        print("hours:", page.inner_text(C + ".e-hrow"), "| + disabled at 3:", page.is_disabled(C + "[data-act='lec-hours'][data-d='1']"))
        page.click(C + "[data-act='lec-when']"); page.wait_for_timeout(300); page.click(".when-pop .wp-days button:not(.out) >> nth=9"); page.wait_for_timeout(200); page.keyboard.press("Escape"); page.wait_for_timeout(400)
        print("date:", page.inner_text(C + "[data-act='lec-when']"), "| card:", page.inner_text(C + ".cpb-cdate") if page.query_selector(C + ".cpb-cdate") else "-")
        shot("72-lecture-page")
        page.locator("#lt-path button.lt-step", has_text="Week 1").click(); page.wait_for_timeout(400)
        print("week1:", page.inner_text(C + ".e-hours"), page.eval_on_selector_all(C + ".e-lcell", "els => els.map(e => e.style.gridColumn + ' ' + (e.querySelector('.cpb-clabel') ? e.querySelector('.cpb-clabel').textContent : e.className))"))
        page.drag_and_drop(C + ".e-lcell[data-lj='1']", C + ".e-lcell[data-lj='0']"); page.wait_for_timeout(400); shot("73-week1-after")   # Lecture 01 first
        print("after drag:", page.eval_on_selector_all(C + ".e-lcell", "els => els.map(e => e.style.gridColumn + ' ' + (e.querySelector('.cpb-clabel') ? e.querySelector('.cpb-clabel').textContent : e.className))"))
        # Week 2: No class (a holiday)
        page.locator("#lt-path button.lt-step", has_text="Course Page").click(); page.wait_for_timeout(300)
        print("rows now:", page.eval_on_selector_all(C + ".e-weekrow", "els => els.map(e => e.querySelector('.wr-name').textContent + ' ' + [...e.querySelectorAll('.wr-slots i')].map(i => i.className + ':' + i.offsetWidth).join(','))"))
        shot("74-course-rows")
        page.click(C + ".e-weekrow >> nth=1"); page.wait_for_timeout(400)
        page.locator("#lt-path button.lt-step", has_text="Course Page").click(); page.wait_for_timeout(300)
        # A table: add and delete next to the selected cell
        T = C + "table.cpb-tbl >> nth=0"
        cols = lambda: page.locator(C + "table.cpb-tbl").first.evaluate("t => [...t.querySelectorAll('thead th.e-thc')].map(x => x.innerText.trim())")
        print("table cols:", cols(), "|", page.inner_text(C + ".e-tbar >> nth=0"))
        page.click(C + "th.e-thc[data-ci='1'] .ed"); page.wait_for_timeout(200)
        print("selected:", page.inner_text(C + ".e-twhere >> nth=0"))
        page.click(C + ".e-tbar [data-act='tadd'][data-what='col'] >> nth=0"); page.wait_for_timeout(300); page.keyboard.type("Room")
        print("after + column:", cols())
        page.click(C + "tr.e-spare [data-bind] >> nth=0"); page.keyboard.type("Ada"); page.wait_for_timeout(300)
        page.click(C + ".e-tbar [data-act='tadd'][data-what='row'] >> nth=0"); page.wait_for_timeout(300); page.keyboard.type("Ken")
        rows = lambda: page.locator(C + "table.cpb-tbl").first.evaluate("t => [...t.querySelectorAll('tbody tr.cpb-row:not(.e-spare)')].map(x => x.querySelector('td').innerText.trim())")
        print("rows:", rows(), "|", page.inner_text(C + ".e-twhere >> nth=0"))
        shot("77-table")
        page.click(C + ".e-tbar [data-act='tdel'][data-what='row'] >> nth=0"); page.wait_for_timeout(200)
        print("one click:", rows())
        page.click(C + ".e-tbar [data-act='tdel'][data-what='row'] >> nth=0"); page.wait_for_timeout(300)
        print("two clicks:", rows())
        page.click(C + "th.e-thc[data-ci='2'] .ed"); page.wait_for_timeout(200)
        page.click(C + ".e-tbar [data-act='tdel'][data-what='col'] >> nth=0"); page.wait_for_timeout(200); page.click(C + ".e-tbar [data-act='tdel'][data-what='col'] >> nth=0"); page.wait_for_timeout(300)
        print("col deleted:", cols())
        # Save, then look at the published page
        page.click("#lt-save"); page.wait_for_timeout(2500)
        okb = page.query_selector(C + "#pl-ok")
        if okb: okb.click(); page.wait_for_timeout(1500)
        r = gh.repos["chandra-gummaluru/courses"]; html = r.commits[r.head]["files"]["csc258/f26/info.html"]
        open(f"{OUT}/saved-info.html", "w").write(html)
        print("saved: lrows", html.count('class="cpb-lrow"'), "slots", html.count('class="cpb-slot'), "off", html.count("cpb-off"), "fade", html.count("cpb-lfade"), "erows", html.count("cpb-erow"))
        b.close()
    print("\n".join(errors) or "no page errors")

main()
