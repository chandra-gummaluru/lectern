"""The top bar stays the same inside the builders, and its one Save saves every builder with changes.
Run with the server going (python app.py), then: python tests/browser/flow_bar.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from flow_github import make_gh, OUT, BASE

def main():
    gh = make_gh()
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 860})
        gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("dialog", lambda d: (errors.append(f"dialog: {d.message}"), d.accept()))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")
        bar = lambda: page.inner_text("#lt-bar").replace("\n", " ")
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.reload(); page.wait_for_timeout(1500)
        print("home bar:", bar(), "| save enabled:", page.is_enabled("#lt-save"))
        page.evaluate("location.hash = '#/csc108/f26/course'"); page.wait_for_timeout(2500); shot("120-course-bar")
        print("course bar visible:", page.is_visible("#lt-bar"), "|", bar(), "| save enabled:", page.is_enabled("#lt-save"))
        print("builder Save visible:", page.is_visible("[data-lt-tool='course'] #save"), "| Copy HTML visible:", page.is_visible("[data-lt-tool='course'] #copy"))
        page.evaluate("location.hash = '#/csc108/f26/grades'"); page.wait_for_timeout(2500); shot("121-grades-bar")
        print("grades bar:", bar())
        page.evaluate("location.hash = '#/csc258/f26/exams/midterm'"); page.wait_for_timeout(2500); shot("122-exam-bar")
        print("exam bar:", bar())
        # Scroll: the bar and the strip stay put
        page.mouse.wheel(0, 900); page.wait_for_timeout(400); shot("123-exam-scrolled")
        print("bar top / strip top after scroll:", page.evaluate("[document.querySelector('#lt-bar').getBoundingClientRect().top, document.querySelector(\"[data-lt-tool='exams'] .tb\").getBoundingClientRect().top]"))
        page.keyboard.press("Control+s"); page.wait_for_timeout(3000); shot("124-saved")
        pv = gh.repos["chandra-gummaluru/courses-private"]; pb = gh.repos["chandra-gummaluru/courses"]
        print("private log:", pv.log, "\npublic log:", pb.log)
        print("after save:", bar(), "| save enabled:", page.is_enabled("#lt-save"))
        print("toasts:", page.eval_on_selector_all(".lt-toast", "els => els.map(e => e.textContent)"))
        page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(500); shot("125-exam-phone")
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
