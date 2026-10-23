"""Teaching teams, end to end against the real server: the owner adds a TA (who has an account) and
invites an instructor (who doesn't); the TA sees the offering on Home, enters a mark that saves, and
can't save a change to an evaluation; the new instructor makes their account from the link and lands
on the offering. Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_teams.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, PASSWORD, block_cdns

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOOK = open(os.path.join(ROOT, "sample-data/demo-courses-private/csc258/f26/grades.json"), encoding="utf-8").read()
PAGE = open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/info.html"), encoding="utf-8").read()
G = "[data-lt-tool='grades'] "


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        from server import db
        owner = srv.account()
        ta = srv.account(email="ta@utoronto.ca", name="Tara Assistant", handle="tara", admin=False)
        srv.user = owner
        srv.put("priv", {"csc258/f26/grades.json": BOOK, "csc108/w26/grades.json": BOOK})
        srv.put("pub", {"csc258/f26/info.html": PAGE})
        b = p.chromium.launch()

        def browser(name):
            ctx = b.new_context(viewport={"width": 1360, "height": 900})
            block_cdns(ctx)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(f"{name} pageerror: {e}"))
            return pg

        # 1. The owner: the offering's Teaching Team; add the TA, invite an instructor.
        own = browser("owner")
        srv.sign_in(own, hash="#/csc258/f26")
        own.wait_for_selector("#lt-team-add"); own.screenshot(path=f"{OUT}/t01-team-owner.png", full_page=True)
        def invite(email, role):
            own.fill("#lt-team-email", email); own.click(f"#lt-team-add button[data-newrole][data-v='{role}']"); own.click("#lt-team-add [type=submit]")
            own.wait_for_function("e => { const i = document.querySelector('#lt-team-msg .lt-linkbox input'); return i && i.value && i.value !== e; }", arg=getattr(invite, "last", ""))
            invite.last = own.input_value("#lt-team-msg .lt-linkbox input")
            return invite.last
        ta_link = invite("ta@utoronto.ca", "ta")
        link = invite("new.prof@utoronto.ca", "instructor")
        expect(own.locator("#lt-team")).to_contain_text("waiting for them to accept")
        own.screenshot(path=f"{OUT}/t02-team-added.png", full_page=True)
        print("invite link:", link[:60] + "…")

        # 2. The TA: Home shows it as Chandra's; no Settings, Delete or Accommodations; enter a mark.
        tp = browser("ta")
        tp.goto(ta_link); tp.wait_for_selector("#jn-in"); tp.screenshot(path=f"{OUT}/t02b-join.png")
        tp.click("#jn-in"); tp.wait_for_selector("#sp-pw", state="visible")
        print("TA's link says:", tp.inner_text("#splash-status"))
        assert "Sign in as" in tp.inner_text("#splash-status") and tp.input_value("#sp-email") == "ta@utoronto.ca"
        tp.fill("#sp-pw", PASSWORD); tp.click("#sp-go")
        tp.wait_for_selector("#lt-team .lt-orow"); tp.wait_for_timeout(500)
        assert tp.evaluate("location.hash") == "#/~chandra/csc258/f26", tp.evaluate("location.hash")
        tp.evaluate("location.hash = '#/'")
        tp.wait_for_selector(".lt-card[data-k]"); tp.screenshot(path=f"{OUT}/t03-ta-home.png")
        cards = tp.eval_on_selector_all(".lt-card[data-k] .lt-strip", "els => els.map(e => e.innerText.replace(/\\n/g, ' '))")
        print("TA's home:", cards)
        assert len(cards) == 1 and "csc258/f26" in cards[0] and "TA" in cards[0], cards     # not csc108
        tp.click(".lt-card[data-k='0']"); tp.wait_for_selector("#lt-team .lt-orow")
        assert tp.evaluate("location.hash") == "#/~chandra/csc258/f26"
        assert not tp.query_selector("[data-part='settings']") and not tp.query_selector("#lt-del-off") and not tp.query_selector("#lt-accom")
        tp.screenshot(path=f"{OUT}/t04-ta-offering.png", full_page=True)
        tp.click("[data-part='book']"); tp.wait_for_selector("body.lt-tool-grades"); tp.wait_for_timeout(1200)
        print("TA path:", tp.inner_text("#lt-path").replace("\n", " "))
        before = json.loads(srv.text("priv", "csc258/f26/grades.json"))
        sid = before["students"][0]["num"]
        cell = G + f"input.mk[data-s='{sid}'][data-e='a1']"
        if not tp.is_visible(cell):
            tp.click(G + "[data-act='fx-menu']"); tp.wait_for_timeout(300); tp.click(".dd-pop [data-pick='a1']"); tp.wait_for_timeout(500)
        tp.fill(cell, "17"); tp.press(cell, "Enter"); tp.wait_for_timeout(300)
        print("state before save:", tp.evaluate("() => window.Lectern.tools.grades.api.state()"), "| cell:", tp.input_value(cell))
        tp.keyboard.press("Control+s"); tp.wait_for_timeout(2000)
        print("after save modal:", tp.inner_text("#lt-modal-root")[:300].replace("\n", " "), "| toasts:", tp.inner_text("#lt-toast-root")[:200])
        after = json.loads(srv.text("priv", "csc258/f26/grades.json"))
        changed = [s for s in after["marks"] if after["marks"].get(s, {}).get("a1") != before["marks"].get(s, {}).get("a1")]
        print("TA's mark saved for:", changed, [after["marks"][s]["a1"] for s in changed])
        assert changed and {k: v for k, v in after.items() if k != "marks"} == {k: v for k, v in before.items() if k != "marks"}
        tp.screenshot(path=f"{OUT}/t05-ta-mark-saved.png")
        # A change to an evaluation isn't saved: Lectern says so first, and only the marks go.
        tp.evaluate("location.hash = '#/~chandra/csc258/f26/evaluations'"); tp.wait_for_timeout(1200)
        tp.click(G + ".erow:has(h3:text-is('Midterm'))"); tp.wait_for_timeout(600)
        tp.screenshot(path=f"{OUT}/t06a-ta-eval.png")
        w = tp.query_selector(G + "input[data-ed='weight'], " + G + "input[data-bind$='weight'], " + G + "input[data-f='weight']")
        print("weight field:", bool(w))
        if w:
            w.fill("99"); w.press("Tab"); tp.wait_for_timeout(300)
            print("unsaved after weight change:", tp.evaluate("() => window.Lectern.tools.grades.api.state().unsaved"))
            tp.keyboard.press("Control+s"); tp.wait_for_timeout(800)
            tp.screenshot(path=f"{OUT}/t06-ta-warned.png")
            msg = tp.inner_text("#lt-modal-root")
            print("TA saving a weight:", msg.replace("\n", " ")[:160])
            assert "Only marks are saved" in msg
            tp.click(".lt-modal [data-yes]"); tp.wait_for_timeout(2000)
            assert json.loads(srv.text("priv", "csc258/f26/grades.json"))["evals"] == before["evals"]
            print("weight on the server:", [e.get("weight") for e in json.loads(srv.text("priv", "csc258/f26/grades.json"))["evals"]][:3])

        # 3. The invited instructor makes an account and lands on the offering.
        ip = browser("instructor")
        ip.goto(link); ip.wait_for_selector("#jn-new"); ip.click("#jn-new"); ip.wait_for_selector("#iv-name")
        print("invite says:", ip.inner_text("#sp-iv p").strip())
        own.reload(); own.wait_for_selector("#lt-team .lt-orow")
        expect(own.locator("#lt-team")).to_contain_text("Tara Assistant")
        assert "CSC258 F26" in ip.inner_text("#sp-iv p")
        ip.fill("#iv-name", "New Prof"); ip.fill("#iv-handle", "newprof"); ip.fill("#iv-pw", PASSWORD); ip.fill("#iv-pw2", PASSWORD); ip.click("#iv-go")
        ip.wait_for_selector("#lt-team .lt-orow"); ip.wait_for_timeout(500)
        print("instructor lands on:", ip.evaluate("location.hash"))
        assert ip.evaluate("location.hash") == "#/~chandra/csc258/f26"
        assert ip.query_selector("#lt-accom") and ip.query_selector("#lt-team-add")
        ip.screenshot(path=f"{OUT}/t07-instructor.png", full_page=True)
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_teams: OK")


if __name__ == "__main__":
    main()
