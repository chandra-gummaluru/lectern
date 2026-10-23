"""Cross-links: the course page reads its marking scheme and each week's evaluations from Grades;
Build opens (or starts) an evaluation's exam or handout; a linked document's total is the evaluation's out of.
Run with the server going (python app.py), then: python tests/browser/flow_links.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE

def ev(i, name, label, short, typ, w, date="", time="", total=10, missed=None):
    return {"id": i, "name": name, "label": label, "title": "", "short": short, "type": typ, "total": total, "weight": w, "date": date, "time": time,
            "makeupFor": None, "missed": missed or {"mode": "zero", "to": [], "split": "custom"}, "shortAuto": False}

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
        "evals": [ev("a1", "Assignment 1", "Assignment", "A1", "assignment", 15, "2026-09-25", "23:59"),
                  ev("l1", "Lab 1", "Lab", "L1", "assignment", 0, "2026-09-18", "17:00"),
                  ev("l2", "Lab 2", "Lab", "L2", "assignment", 0, "2026-09-25", "17:00"),
                  ev("mt", "Midterm", "Midterm", "MT", "test", 30, "2026-10-21", "18:10", missed={"mode": "reweight", "to": [{"id": "fe", "share": 100}], "split": "custom"}),
                  ev("fe", "Final Exam", "Final Exam", "FE", "test", 45)],
        "groups": [{"id": "g1", "name": "Labs", "short": "Labs", "weight": 10, "keep": 1, "members": ["l1", "l2"]}],
        "students": [{"num": "1001", "first": "Maya", "last": "Castillo", "f": {}}], "marks": {"1001": {"a1": {"pts": 9}}}, "overrides": {}}
HANDOUT = {"format": "exam-builder/2", "settings": {"title": "Assignment 1", "layout": "handout", "link": "a1"}, "items": [], "total": 25}

def open_eval(page, G, eid):
    """The evaluation's own page (where Build is), from wherever the gradebook is."""
    if page.query_selector(G + f".editor[data-eval='{eid}']"): return
    if page.query_selector(G + ".editor[data-eval]"):
        page.locator("#lt-path button.lt-step", has_text="Evaluations").click(); page.wait_for_timeout(400)
    page.click(G + f".erow[data-id='{eid}']"); page.wait_for_timeout(500)

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(BOOK), "csc258/f26/a1/exam.json": json.dumps(HANDOUT)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"csc258/f26/info.html": open(os.path.join(os.path.dirname(__file__), "old-course-page.html"), encoding="utf-8").read()}))
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
        path = lambda: page.inner_text("#lt-path").replace("\n", " ")
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/course"); page.reload(); page.wait_for_timeout(2800)
        C, G, X = "[data-lt-tool='course'] ", "[data-lt-tool='grades'] ", "[data-lt-tool='exams'] "
        shot("80-course-with-scheme")
        print("1 status:", page.inner_text(C + "#status").replace("\n", " "))
        print("  week pills:", page.eval_on_selector_all(C + ".e-weekrow", "els => els.map(e => e.querySelector('.wr-name').textContent + ': ' + [...e.querySelectorAll('.wr-pill')].map(x => x.textContent).join(','))"))
        page.locator(C + ".e-sechead", has_text="Marking Scheme").first.scroll_into_view_if_needed(); page.wait_for_timeout(200); shot("81-scheme-editor")
        # Week 3: Assignment 1 and Lab 2 from Grades; give the assignment a submission link
        page.click(C + ".e-weekrow >> nth=2"); page.wait_for_timeout(500)
        print("2 week 3 evals:", page.eval_on_selector_all(C + ".e-gev-h", "els => els.map(e => e.textContent.trim())"))
        page.click(C + "button[data-path='evalFiles.a1']"); page.wait_for_timeout(300)
        page.fill(C + "input[data-bindv='evalFiles.a1.0.url']", "https://q.utoronto.ca/a1"); page.keyboard.press("Enter"); page.wait_for_timeout(300)
        shot("82-week3-evals")
        # Save the course page and look at what's published
        page.click("#lt-save"); page.wait_for_timeout(2500)
        okb = page.query_selector(C + "#pl-ok")
        if okb: okb.click(); page.wait_for_timeout(1500)
        if page.query_selector(C + ".modal button:has-text('Done')"): page.click(C + ".modal button:has-text('Done')"); page.wait_for_timeout(300)
        r = gh.repos["chandra-gummaluru/courses"]; html = r.commits[r.head]["files"]["csc258/f26/info.html"]
        open(f"{OUT}/saved-linked.html", "w").write(html)
        print("3 published: scheme table", "cpb-scheme" in html, "| gev cards", html.count('class="cpb-gev"'), "| a1 link", "q.utoronto.ca/a1" in html, "| students?", "Castillo" in html)
        # Edit in Grades: the gradebook, where Assignment 1's out of comes from its handout
        shot("86-before-edit"); print("edit buttons:", len(page.query_selector_all(C + "[data-act=edit-grades]")), page.query_selector(".modal, [data-lt-tool=course] .modal") is not None)
        page.click(C + "[data-act=edit-grades] >> nth=0"); page.wait_for_timeout(2000)
        print("4 path:", path(), "| row buttons:", page.eval_on_selector_all(G + ".erow[data-id='a1'] .ec-acts > *", "els => els.map(e => e.textContent.trim())"))
        print("  A1 out of:", page.eval_on_selector(G + ".erow[data-id='a1'] p:not(.er-when)", "e => e.textContent"))
        shot("83-grades-build")
        # Build the midterm: a new exam, named and dated
        open_eval(page, G, "mt"); page.click(G + ".ed-acts [data-act='ev-build']"); page.wait_for_timeout(3000)
        print("5 path:", path(), "| layout cover:", bool(page.query_selector(X + ".cover-blk")))
        shot("84-built-exam")
        # A handout from an assignment: Lab 2
        page.evaluate("location.hash = '#/csc258/f26/evaluations'"); page.wait_for_timeout(1500)
        if page.query_selector(".lt-modal [data-yes]"): page.click(".lt-modal [data-yes]"); page.wait_for_timeout(800)
        print("6 midterm button now:", (open_eval(page, G, "mt"), page.inner_text(G + ".ed-acts [data-act='ev-build']"))[1])
        open_eval(page, G, "l2"); page.click(G + ".ed-acts [data-act='ev-build']"); page.wait_for_timeout(1500)
        if page.query_selector(".lt-modal [data-yes]"): page.click(".lt-modal [data-yes]"); page.wait_for_timeout(1500)
        print("7 path:", path(), "| handout head:", bool(page.query_selector(X + ".ho-head")), "| answer-space buttons:", len(page.query_selector_all(X + ".add-space")))
        shot("85-built-handout")
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
