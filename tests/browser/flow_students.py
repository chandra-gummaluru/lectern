"""Students: the instructor adds them to the offering's class list (and emails them the course page's
link); a student opens the course page, signs in there with their email and the code it emails them,
and sees the signed-in tabs. Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_students.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = json.loads(open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json"), encoding="utf-8").read())
DATA["page"]["tabs"] = {"lectures": "signed-in"}


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        from server import mailer
        srv.account()
        srv.put("pub", {"csc258/f26/course.json": json.dumps(DATA)})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        me = ctx.new_page()
        me.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(me, hash="#/csc258/f26")
        me.wait_for_selector("#st-emails")
        me.fill("#st-emails", "maya.castillo@mail.utoronto.ca\nben.okafor@mail.utoronto.ca, oops")
        me.click("#st-add button[type=submit]")
        me.wait_for_selector(".lt-st-list .lt-orow")
        expect(me.locator(".lt-st-list .lt-orow")).to_have_count(2)
        expect(me.locator("#st-msg")).to_contain_text("oops")
        me.locator("#lt-students").scroll_into_view_if_needed()
        me.screenshot(path=f"{OUT}/210-class-list.png")
        print("1 class list:", me.eval_on_selector_all(".lt-st-list b", "e => e.map(x => x.textContent)"))

        st = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
        st.on("pageerror", lambda e: errors.append(f"student pageerror: {e}"))
        st.goto(srv.base + "c/chandra/csc258/f26/#lectures"); st.wait_for_selector(".hb-locked")
        st.click(".hb-locked a:has-text('Sign in')")
        st.wait_for_selector("#si-e")
        assert st.url.endswith("/c/chandra/csc258/f26/sign-in"), st.url
        st.fill("#si-e", "maya.castillo@mail.utoronto.ca"); st.click("#si-email button[type=submit]")
        st.wait_for_selector("#si-c")
        st.screenshot(path=f"{OUT}/211-code.png")
        code = re.search(r"\b(\d{6})\b", [m for m in mailer.sent if m["to"] == "maya.castillo@mail.utoronto.ca" and "code" in m["subject"]][-1]["body"]).group(1)
        st.fill("#si-c", "000000" if code != "000000" else "111111"); st.click("#si-code button[type=submit]")
        expect(st.locator("#si-err2")).to_contain_text("isn't right")
        st.fill("#si-c", code); st.click("#si-code button[type=submit]")
        st.wait_for_selector(".hb-tab")
        expect(st.locator(".hb-who")).to_contain_text("maya.castillo@mail.utoronto.ca")
        expect(st.locator(".hb-who")).to_contain_text("Student")
        st.click(".hb-tab:has-text('Lectures')")
        st.wait_for_selector(".hb-week")
        st.screenshot(path=f"{OUT}/212-signed-in.png")
        print("2 the student signed in with the code, and sees Lectures")
        st.click("#hb-out"); st.wait_for_timeout(800)
        st.click(".hb-tab:has-text('Lectures')")
        expect(st.locator(".hb-locked")).to_be_visible()
        print("3 signed out")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
