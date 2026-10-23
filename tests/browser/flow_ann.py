"""An announcement: its date and time from the picker, and its Save button.
Run with the server going (python app.py), then: python tests/browser/flow_ann.py"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from flow_github import make_gh, OUT, BASE

def main():
    gh = make_gh(); errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1360, "height": 900}); gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort()); ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e))); page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3})); localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc108/f26/course"); page.reload(); page.wait_for_timeout(2500)
        C = "[data-lt-tool='course'] "
        page.locator(C + ".e-weekrow").first.click(); page.wait_for_timeout(400)
        page.locator(C + "button", has_text="Add announcement").first.click(); page.wait_for_timeout(400)
        page.keyboard.type("Room change"); page.wait_for_timeout(200)
        print("date now:", page.inner_text(C + "[data-act='ann-when']"))
        page.click(C + "[data-act='ann-when']"); page.wait_for_timeout(300)
        page.screenshot(path=f"{OUT}/180-ann-when.png")
        while not page.query_selector(".when-pop [data-day='2026-10-20']"): page.click(".when-pop [data-w='next']")
        page.click(".when-pop [data-day='2026-10-20']"); page.fill(".when-pop #wp-t", "9:30"); page.keyboard.press("Enter"); page.wait_for_timeout(400)
        print("picked:", page.inner_text(C + "[data-act='ann-when']"))
        page.click(C + "[data-act='ann-when']"); page.wait_for_timeout(200); page.fill(".when-pop #wp-t", ""); page.mouse.click(5, 700); page.wait_for_timeout(300)
        print("no time:", page.inner_text(C + "[data-act='ann-when']"))
        page.screenshot(path=f"{OUT}/181-ann-page.png", full_page=True)
        page.click(C + "[data-act='ann-save']"); page.wait_for_timeout(2500)
        r = gh.repos["chandra-gummaluru/courses"]; html = r.commits[r.head]["files"].get("csc108/f26/info.html", "")
        print("saved:", "Room change" in html, "Oct 20, 2026" in html, "| path:", page.inner_text("#lt-path").replace("\n", " "), "| status:", page.inner_text("#lt-status"))
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
