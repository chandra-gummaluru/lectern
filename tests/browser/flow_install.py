"""Install Lectern: the service worker takes over the site, the account menu offers Install Lectern when the
browser has an install offer (or on an iPhone/iPad, where it says how), and offline, opening Lectern shows
"You're offline" instead of the browser's error.
Run:  python tests/browser/flow_install.py"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from harness import Server, OUT, block_cdns

FAKE_OFFER = """() => { const e = new Event('beforeinstallprompt', { cancelable: true });
  e.prompt = () => { window.__prompted = true; }; e.userChoice = Promise.resolve({ outcome: 'accepted' });
  window.dispatchEvent(e); }"""


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800}); block_cdns(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(page)
        page.wait_for_function("navigator.serviceWorker.controller !== null || navigator.serviceWorker.ready.then(() => true)")
        scope = page.evaluate("navigator.serviceWorker.ready.then(r => r.scope)")
        print("service worker scope:", scope); assert scope == srv.base

        # No install offer yet: no menu item
        page.click("#lt-acct"); assert not page.is_visible("[data-m='install']"); page.keyboard.press("Escape")
        # The browser offers it: Install Lectern appears, and uses the offer once
        page.evaluate(FAKE_OFFER)
        page.click("#lt-acct"); page.wait_for_selector("[data-m='install']"); page.screenshot(path=f"{OUT}/install-menu.png")
        page.click("[data-m='install']"); page.wait_for_timeout(300)
        assert page.evaluate("window.__prompted === true"); print("toast:", page.inner_text("#lt-toast-root"))
        page.click("#lt-acct"); assert not page.is_visible("[data-m='install']"); page.keyboard.press("Escape")

        # Offline: opening Lectern shows the offline page
        page.reload(); page.wait_for_function("navigator.serviceWorker.controller !== null")
        ctx.set_offline(True); page.reload()
        print("offline:", page.inner_text("h1")); assert page.inner_text("h1") == "You're offline"
        page.screenshot(path=f"{OUT}/install-offline.png")
        ctx.set_offline(False); ctx.close()

        # An iPhone: no install offer, so it says how (Share, Add to Home Screen)
        ip = b.new_context(**p.devices["iPhone 13"]); block_cdns(ip)
        page = ip.new_page(); page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(page)
        page.click("#lt-acct"); page.click("[data-m='install']"); page.wait_for_selector(".lt-modal")
        print("iPhone:", page.inner_text(".lt-modal p")); page.screenshot(path=f"{OUT}/install-iphone.png")
        b.close()
    assert not errors, errors
    print("flow_install: OK")


if __name__ == "__main__":
    main()
