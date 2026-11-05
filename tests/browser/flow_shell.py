"""The shell, signed in: Home, a course offering, its gradebook, course page and an exam, on a phone too.
Run:  python tests/browser/flow_shell.py"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from walkthrough import make_walkthrough, BASE, OUT

def run(steps_filter=None):
    gh = make_walkthrough()
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 860})
        gh.attach(ctx)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")

        page.goto(BASE + "#/"); page.wait_for_timeout(1500); shot("03-home")
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
        # The course page: the offering page links to it as students see it (View Course Page); Lectern edits it here.
        assert page.get_attribute("#lt-view-page", "href"), "View Course Page"
        page.evaluate("location.hash = '#/csc258/f26/course'"); page.wait_for_timeout(3000); shot("08-course")
        print("path:", page.inner_text("#lt-path"))
        page.evaluate("location.hash = '#/csc258/f26/exams/midterm'"); page.wait_for_timeout(3500); shot("09-exam")
        print("path:", page.inner_text("#lt-path"))
        page.evaluate("location.hash = '#/'"); page.wait_for_timeout(1500); shot("10-home-again")

        # Phone
        m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        gh.attach(m)
        mp = m.new_page(); mp.goto(BASE + "#/"); mp.wait_for_timeout(1200); mp.screenshot(path=f"{OUT}/11-home-phone.png")
        b.close()
    print("\n".join(errors[:40]) or "no console errors")

if __name__ == "__main__":
    run()
