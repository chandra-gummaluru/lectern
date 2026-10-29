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
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" and "ERR_FAILED" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("dialog", lambda d: (errors.append(f"dialog: {d.message}"), d.accept()))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc108/f26/grades"); page.reload(); page.wait_for_timeout(2500)
        print("1 path:", page.inner_text("#lt-path").replace("\n", " "))
        # Save the new gradebook with Lectern's Save (Ctrl+S; also in the account menu).
        page.keyboard.press("Control+s"); page.wait_for_timeout(2000); shot("21-saved")
        files = gh.repos["chandra-gummaluru/courses-private"].commits[gh.repos["chandra-gummaluru/courses-private"].head]["files"]
        print("2 saved files:", sorted(files), gh.repos["chandra-gummaluru/courses-private"].log)

        # Make it unsaved: add an evaluation, then go to another gradebook.
        page.evaluate("location.hash = location.hash.replace(/\/(grades|gradebook)$/, '/evaluations')"); page.wait_for_timeout(1200); page.wait_for_timeout(300)
        page.click("[data-lt-tool='grades'] button:has-text('Add an evaluation')"); page.wait_for_timeout(500); shot("22-added")
        print("3 path:", page.inner_text("#lt-path").replace("\n", " "))
        # The builder's Home button → Lectern Home, and the bar shows what's unsaved.
        page.click("#lt-home"); page.wait_for_timeout(1200); shot("23-home-unsaved")
        print("4 hash:", page.evaluate("location.hash"), "| status:", page.inner_text("#lt-status"))
        # Ctrl+Z on Home must not reach the builder.
        page.keyboard.press("Control+z"); page.wait_for_timeout(200)
        page.evaluate("location.hash = '#/csc258/f26/grades'"); page.wait_for_timeout(800); shot("24-confirm")
        print("5 modal:", page.inner_text(".lt-modal") if page.query_selector(".lt-modal") else None)
        page.click(".lt-modal [data-no]"); page.wait_for_timeout(800)
        print("6 back to:", page.evaluate("location.hash"), "| path:", page.inner_text("#lt-path").replace("\n", " "))
        page.evaluate("location.hash = '#/csc258/f26/grades'"); page.wait_for_timeout(800)
        page.click(".lt-modal [data-yes]"); page.wait_for_timeout(1500); shot("25-opened-other")
        print("7 path:", page.inner_text("#lt-path").replace("\n", " "))
        # Dark mode look of Home
        page.emulate_media(color_scheme="dark"); page.evaluate("location.hash = '#/'"); page.wait_for_timeout(1200); shot("26-home-dark")
        page.evaluate("location.hash = '#/csc258/f26'"); page.wait_for_timeout(600); shot("27-offering-dark")
        page.emulate_media(color_scheme="light")
        # New exam dialog
        page.wait_for_timeout(1500); page.click("#lt-loose [data-exam='midterm']"); page.wait_for_timeout(2500); shot("29-exam-open")
        print("8 path:", page.inner_text("#lt-path").replace("\n", " "))
        # Phone: offering page
        page.set_viewport_size({"width": 390, "height": 844}); page.evaluate("location.hash = '#/'"); page.wait_for_timeout(900); shot("30-home-phone")
        page.evaluate("location.hash = '#/csc258/f26/grades'"); page.wait_for_timeout(1200); shot("31-grades-phone")
        b.close()
    print("\n".join(errors[:30]) or "no errors")

main()
