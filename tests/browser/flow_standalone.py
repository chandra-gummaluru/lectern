"""The builders on their own (/tools/<name>.html): the pinned path strip, and section 10's fixes.
Run with the server going (python app.py), then: python tests/browser/flow_standalone.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE, EXAM

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
        "fields": {"idLabel": "Student number", "custom": []},
        "evals": [{"id": "e1", "name": "Midterm", "short": "MT", "total": 100, "weight": 100, "makeupFor": None, "missed": {"mode": "zero", "to": [], "split": "custom"}}],
        "groups": [], "students": [{"num": "1001", "first": "Maya", "last": "Castillo", "f": {}}, {"num": "1002", "first": "Ken", "last": "Ito", "f": {}}],
        "marks": {"1001": {"e1": {"pts": 42}}, "1002": {"e1": {"pts": 88}}}, "overrides": {}}

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(BOOK), "csc258/f26/midterm/exam.json": json.dumps(EXAM)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 860})
        ctx.route("https://api.github.com/**", gh.handle)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")
        path = lambda: page.inner_text("#pathbar").replace("\n", " ")
        page.goto(BASE + "tools/grades.html")
        page.evaluate("localStorage.setItem('grade-builder.github', JSON.stringify({repo:'chandra-gummaluru/courses-private', branch:'main', token:'t'}))")
        page.reload(); page.wait_for_timeout(1500); shot("50-grades-home")
        print("grades home:", path())
        page.click(".pcard[data-k='0']"); page.wait_for_timeout(1200); shot("51-grades-open")
        print("grades open:", path(), "| dock:", page.inner_text(".dock-bar").replace("\n", " "))
        page.click("#tb-view button[data-v='students']"); page.wait_for_timeout(400)
        page.click("text=Castillo"); page.wait_for_timeout(600); shot("52-grades-student")
        print("student:", path())
        page.click("#pathbar button.pb-s >> nth=1"); page.wait_for_timeout(400)
        print("back:", path())
        page.click("#tb-view button[data-v='grades']"); page.wait_for_timeout(500); shot("53-grades-grid")
        print("grade colour (42%):", page.eval_on_selector_all(".c-grade .gp", "els => els.map(e => e.textContent + ' ' + getComputedStyle(e).color)"))
        page.click("#tb-view button[data-v='stats']"); page.wait_for_timeout(500); shot("54-grades-stats")
        page.click("#pathbar button.pb-s >> nth=0"); page.wait_for_timeout(600)
        print("home again:", path())

        page.goto(BASE + "tools/course.html")
        page.evaluate("localStorage.setItem('course-page-builder.source', 'github'); localStorage.setItem('course-page-builder.github', JSON.stringify({repo:'chandra-gummaluru/courses', branch:'main', token:'t'}))")
        page.reload(); page.wait_for_timeout(1200)
        print("course home:", path())
        page.click("#h-new"); page.wait_for_timeout(500); shot("55-course-new-dialog")
        b.close()
    print("\n".join(errors) or "no page errors")

main()
