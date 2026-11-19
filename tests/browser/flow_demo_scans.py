"""The demo course's scans: loading the demo reads its ten scanned midterm booklets, and its TA is there to
assign questions to. (Screenshots in shots/.)

    python tests/browser/flow_demo_scans.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from playwright.sync_api import sync_playwright
from harness import Server, OUT, block_cdns


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        me = ctx.new_page(); me.on("pageerror", lambda e: errors.append(str(e)))
        srv.sign_in(me)
        d = me.evaluate("""() => fetch('/api/offerings/demo', {method: 'POST', headers: {'X-Lectern': '1'}}).then(r => r.json())""")
        off = f"demo101/{d['term']}"
        G = "[data-lt-tool='grades'] "
        me.evaluate(f"location.hash = '#/{off}/evaluations'"); me.evaluate("location.reload()")
        me.wait_for_selector(G + ".erow[data-id='mt']", timeout=20000); me.click(G + ".erow[data-id='mt']")
        L = G + ".editor[data-eval='mt'] [data-scan-list] "
        me.wait_for_selector(L + ".sc-qlist:not(.off) [data-gq]", timeout=180000)
        me.wait_for_selector(L + ".sc-scan-row .sc-spin", state="detached", timeout=180000)
        me.wait_for_timeout(500)
        slot = G + ".editor[data-eval='mt'] [data-scan-slot]"
        print("scripts:", me.locator(G + ".editor[data-eval='mt'] h3.ed-sec").all_inner_texts(), "| slot:", me.locator(slot).count() and " ".join(me.inner_text(slot).split()))
        me.locator(slot).first.scroll_into_view_if_needed() if me.locator(slot).count() else None
        me.screenshot(path=f"{OUT}/demo-scans-0-scripts.png")
        scanned = " ".join(me.inner_text(L + ".sc-scan-row").split())
        print("scanned:", scanned)
        assert "10 / 30 scanned" in scanned, scanned
        secs = [x.strip().title() for x in me.locator(G + ".editor[data-eval='mt'] h3.ed-sec").all_inner_texts()]
        assert secs.index("Scripts And Scans") + 1 == secs.index("Marks"), secs        # its script, then its marks
        assert "Edit Test Script" in me.inner_text(slot)
        assert not me.query_selector(L + "[data-assign]"), "no Assign Graders button: the dropdowns are there"
        assert me.locator(L + "[data-gpk]").count() >= 10, "a graders dropdown on each question (the demo has a TA)"
        me.locator(L).scroll_into_view_if_needed(); me.screenshot(path=f"{OUT}/demo-scans-1.png")
        assert "Belle Curve" in me.inner_text(L), "the TA is a grader of questions 8 and 10"
        last = me.locator(L + "[data-gpk]").last
        last.scroll_into_view_if_needed(); last.locator("button").first.click(); me.wait_for_timeout(400)
        me.screenshot(path=f"{OUT}/demo-scans-2-pick.png")
        b.close()
    assert not errors, errors
    print("flow_demo_scans: OK")


if __name__ == "__main__":
    main()
