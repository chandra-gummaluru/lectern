"""The demo course loaded, deleted and loaded again, in one sitting: its description saves (Lectern keeps nothing of
the last one: the version of about.json it read, its attendance, discussions or scans).

    python tests/browser/flow_demo_again.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from playwright.sync_api import sync_playwright
from harness import Server, OUT, block_cdns


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        from server import transfer
        transfer.DEMO_SCANS = False
        srv.account()
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        me = ctx.new_page(); me.on("pageerror", lambda e: errors.append(str(e)))
        srv.sign_in(me)

        def load():
            me.evaluate("location.hash = '#/'"); me.wait_for_selector("#lt-demo, #lt-demo2", timeout=20000)
            me.click("#lt-demo, #lt-demo2 >> nth=0")
            me.wait_for_selector("#lt-desc [contenteditable]", timeout=20000)

        def describe(text):
            ed = me.locator("#lt-desc [contenteditable]").first
            ed.click(); me.keyboard.press("Control+a"); me.keyboard.type(text)
            me.wait_for_selector("#lt-about-st:has-text('Saved'), #lt-about-st:has-text('Not saved')", timeout=10000)
            return me.inner_text("#lt-about-st")

        load()
        assert describe("The first demo.") == "Saved"
        t = me.evaluate("location.hash").split("/")[2]
        me.click("#lt-del-off"); me.fill("#del-name", f"demo101/{t}"); me.click(".lt-modal [data-ok]")
        me.wait_for_selector("#lt-demo, #lt-demo2", timeout=20000)
        load()
        said = describe("The second demo.")
        me.screenshot(path=f"{OUT}/demo-again.png")
        assert said == "Saved", said
        assert "The second demo." in srv.text("priv", f"demo101/{t}/about.json")
        b.close()
    assert not errors, errors
    print("flow_demo_again: OK")


if __name__ == "__main__":
    main()
