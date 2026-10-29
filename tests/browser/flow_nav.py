"""Back and Forward (Lectern's pages and the pages inside the gradebook), the Home cards, and deleting a course
offering (typing its name), end to end against the real server. Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_nav.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns
from flow_links import BOOK


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        srv.account()
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(BOOK), "csc108/w27/grades.json": json.dumps(BOOK), "csc108/w27/final/exam.json": "{}"})
        srv.put("pub", {"csc108/w27/slides.pdf": "x"})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 860}); block_cdns(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")
        path = lambda: page.inner_text("#lt-path").replace("\n", " ")
        G = "[data-lt-tool='grades'] "
        srv.sign_in(page)
        page.wait_for_selector(".lt-card[data-k]"); shot("110-home-cards")
        cards = page.eval_on_selector_all(".lt-card[data-k] .lt-strip", "els => els.map(e => e.textContent.trim())")
        print("cards:", cards)
        assert any("csc258" in c for c in cards) and any("csc108" in c for c in cards), cards

        # Home → csc108/w27 → its gradebook → a student's page; then Back three times, and Forward.
        page.locator(".lt-card[data-k]", has_text="w27").first.click()
        page.wait_for_selector("[data-part='book']"); page.click("[data-part='book']")
        page.wait_for_selector(G + ".c-name button", timeout=15000)
        page.locator(G + ".c-name button", has_text="Castillo").first.click(); page.wait_for_timeout(600)
        at = path(); print("at:", at)
        assert at.endswith("Castillo, Maya"), at
        back = "#lt-bar [data-nav='-1']"
        steps = []
        for _ in range(3):
            page.click(back); page.wait_for_timeout(900); steps.append(path())
        print("back x3:", steps)
        assert steps[0].endswith("Gradebook") and steps[1].endswith("csc108 / w27") and steps[2] == "Home", steps
        page.click("#lt-bar [data-nav='1']"); page.wait_for_timeout(900)
        print("forward:", path())
        assert path().endswith("csc108 / w27"), path()
        shot("111-after-forward")

        # Delete csc108/w27: Delete stays off until its name is typed.
        page.wait_for_selector("#lt-del-off"); page.click("#lt-del-off")
        page.wait_for_selector("#del-name"); shot("112-delete-dialog")
        assert page.is_disabled(".lt-modal [data-ok]"), "Delete before typing the name"
        page.fill("#del-name", "csc108/w27"); page.click(".lt-modal [data-ok]")
        expect(page.locator("#lt-toast-root")).to_contain_text("Deleted csc108/w27")
        page.wait_for_selector(".lt-card[data-k]"); page.wait_for_timeout(500)
        priv, pub = srv.files("priv"), srv.files("pub")
        print("left in private:", sorted(priv), "| public:", sorted(pub), "| hash:", page.evaluate("location.hash"))
        assert not any(k.startswith("csc108/w27/") for k in list(priv) + list(pub)) and "csc258/f26/grades.json" in priv
        cards = page.eval_on_selector_all(".lt-card[data-k] .lt-strip", "els => els.map(e => e.textContent.trim())")
        print("cards:", cards)
        assert not any("w27" in c for c in cards), cards
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_nav: OK")


if __name__ == "__main__":
    main()
