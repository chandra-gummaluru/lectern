import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo

OUT = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(OUT, exist_ok=True)
BASE = "http://localhost:5002/"

GRADES = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
          "evals": [], "groups": [], "students": [], "marks": {}, "overrides": {}}
EXAM = {"format": "exam-builder/2", "settings": {"title": "Midterm", "courseCode": "CSC258"}, "items": []}

def make_gh():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {
        "csc258/f26/grades.json": json.dumps(GRADES),
        "csc258/f26/midterm/exam.json": json.dumps(EXAM),
        "csc108/w26/grades.json": json.dumps({**GRADES, "course": {"code": "CSC108", "term": "Winter 2026"}}),
    }))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x", "csc108/f26/notes.pdf": "x"}))
    gh.add(Repo("chandra-gummaluru/courses-utor", False, {"README.md": "x"}))
    return gh

def run(steps_filter=None):
    gh = make_gh()
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 860})
        ctx.route("https://api.github.com/**", gh.handle)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")

        page.goto(BASE); page.wait_for_timeout(900); shot("01-splash")
        page.click("#splash-signin"); page.wait_for_timeout(300)
        print("splash status:", page.inner_text("#splash-status"))

        # Pretend the sign-in came back.
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3})); localStorage.removeItem('lectern.repos'); }""")
        page.goto(BASE + "#/"); page.reload(); page.wait_for_timeout(1500); shot("02-setup")
        page.select_option("#lt-repo", "chandra-gummaluru/courses"); page.wait_for_timeout(200)
        page.click("#lt-done"); page.wait_for_timeout(1200); shot("03-home")
        print("path:", page.inner_text("#lt-path"))
        page.click(".lt-card[data-k='0']"); page.wait_for_timeout(500); shot("04-offering")
        print("path:", page.inner_text("#lt-path"))

        page.click("[data-part='book']"); page.wait_for_timeout(2500); shot("05-grades")
        print("path:", page.inner_text("#lt-path"), "| hash", page.evaluate("location.hash"))
        # Students view
        shot("06-grades-students")
        print("path:", page.inner_text("#lt-path"))
        page.mouse.wheel(0, 600); page.wait_for_timeout(300); shot("06b-scrolled")

        page.click("#lt-path button.lt-step >> nth=1"); page.wait_for_timeout(600); shot("07-back-offering")
        print("path:", page.inner_text("#lt-path"))
        page.click("[data-go='course']"); page.wait_for_timeout(3000); shot("08-course")
        print("path:", page.inner_text("#lt-path"))
        page.evaluate("location.hash = '#/csc258/f26/exams/midterm'"); page.wait_for_timeout(3500); shot("09-exam")
        print("path:", page.inner_text("#lt-path"))
        page.evaluate("location.hash = '#/'"); page.wait_for_timeout(1500); shot("10-home-again")

        # Phone
        m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mp = m.new_page(); mp.goto(BASE); mp.wait_for_timeout(900); mp.screenshot(path=f"{OUT}/11-splash-phone.png")
        b.close()
    print("\n".join(errors[:40]) or "no console errors")
    print("calls:", len(gh.calls))

if __name__ == "__main__":
    run()
