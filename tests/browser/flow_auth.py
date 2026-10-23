"""Accounts, end to end in a browser, against the real server (its own empty data folder):
an invitation → a new account → two-factor on → signed out → signed in with a code → a gradebook and a
course page saved to the server → the page published (sandboxed) → the session ends mid-work and signing
in again carries on → an admin invites someone. Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_auth.py
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, PASSWORD, block_cdns

BOOK = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
        "evals": [{"id": "a1", "name": "Assignment 1", "type": "assignment", "date": "2026-10-01", "weight": 10, "accom": {"standard": "", "alternate": True}}], "groups": [], "students": [], "marks": {}, "overrides": {}}


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        from server import auth, db, security
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 860})
        block_cdns(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" and "ERR_FAILED" not in m.text and "401" not in m.text else None)
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")

        # 1. The splash: a sign-in form, no GitHub.
        page.goto(srv.base); page.wait_for_selector("#sp-email", state="visible"); shot("a01-splash")
        assert "GitHub" not in page.inner_text("#splash")
        page.fill("#sp-email", "nobody@x.ca"); page.fill("#sp-pw", "not a real password"); page.click("#sp-go")
        expect(page.locator("#splash-status")).to_contain_text("don't match")
        print("wrong password:", page.inner_text("#splash-status"))

        # 2. An invitation link → a new account (the token is taken out of the address).
        tok = auth.create_invite("chandra@utoronto.ca")
        page.goto(srv.base + "#invite=" + tok)
        page.wait_for_selector("#iv-name"); shot("a02-invite")
        assert tok not in page.url, page.url
        page.fill("#iv-name", "Chandra Gummaluru")
        page.fill("#iv-handle", "chandra")
        page.fill("#iv-pw", "short"); page.fill("#iv-pw2", "short"); page.click("#iv-go")
        expect(page.locator("#splash-status")).to_contain_text("12 characters")
        page.fill("#iv-pw", PASSWORD); page.fill("#iv-pw2", PASSWORD); page.click("#iv-go")
        page.wait_for_selector(".lt-account"); shot("a03-account-new")
        assert page.evaluate("location.hash") == "#/account"
        cookie = [c for c in ctx.cookies() if c["name"] == "lectern_session"][0]
        assert cookie["httpOnly"] and cookie["sameSite"] == "Lax", cookie
        assert page.evaluate("document.cookie") == "", "the session cookie must not be readable by scripts"

        # 3. Two-factor on: password → QR → code → recovery codes.
        page.wait_for_selector("#ac-on[role=switch][aria-checked=false]"); shot("a03b-2fa-off")
        page.click("#ac-on"); page.fill("#tf-pw", PASSWORD); page.click(".lt-modal [type=submit]")
        page.wait_for_selector(".lt-qr svg"); shot("a04-2fa-qr")
        secret = page.inner_text(".lt-key code").replace(" ", "")
        page.fill("#tf-code", security.totp_now(secret)); page.click(".lt-modal [type=submit]")
        page.wait_for_selector(".lt-codes"); shot("a05-recovery-codes")
        codes = page.eval_on_selector_all(".lt-codes code", "els => els.map(e => e.textContent)")
        assert len(codes) == 10
        assert page.is_disabled("[data-done]")
        page.check("[data-saved]"); page.click("[data-done]")
        expect(page.locator(".lt-account")).to_contain_text("10 recovery codes left")
        assert page.get_attribute("#ac-off", "aria-checked") == "true"; shot("a05b-2fa-on")

        srv.user = db.one("SELECT * FROM users WHERE email = 'chandra@utoronto.ca'")
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(BOOK)})

        # 4. Sign out, then in with a code.
        page.click("#lt-acct"); page.click("[data-m='out']")
        page.wait_for_selector("#sp-email", state="visible")
        page.fill("#sp-email", "chandra@utoronto.ca"); page.fill("#sp-pw", PASSWORD); page.click("#sp-go")
        page.wait_for_selector("#sp2-code"); shot("a06-code-step")
        page.fill("#sp2-code", "000000"); page.click("#sp2-go")
        expect(page.locator("#splash-status")).to_contain_text("isn't right")
        db.run("UPDATE users SET totp_step = 0"); page.fill("#sp2-code", security.totp_now(secret)); page.click("#sp2-go")
        page.wait_for_selector("#app:not([hidden])"); page.wait_for_timeout(800); shot("a07-home")
        print("home:", page.inner_text(".lt-src"))
        assert "/p/chandra/" in page.inner_text(".lt-src")

        # 5. A gradebook and a course page, saved to the server.
        page.evaluate("location.hash = '#/csc258/f26/course'"); page.wait_for_timeout(2500); shot("a08-course")
        page.keyboard.press("Control+s"); page.wait_for_timeout(2000)
        html = srv.text("pub", "csc258/f26/info.html")
        assert html and "<html" in html.lower(), "the course page was saved on the server"
        req = re.findall(r'class="cpb-req"[^>]*href="([^"]+)"', html)
        print("request link:", req[:1])
        assert req and "r=chandra&" in req[0].replace("&amp;", "&"), req
        print("saved course page:", len(html), "bytes")

        # 6. Published, and sandboxed.
        r = page.request.get(srv.base + "p/chandra/csc258/f26/info.html")
        assert r.status == 200 and r.headers["content-security-policy"].startswith("sandbox"), r.headers
        pub = ctx.new_page(); pub.goto(srv.base + "p/chandra/csc258/f26/info.html"); pub.wait_for_timeout(500)
        pub.screenshot(path=f"{OUT}/a09-published.png")
        origin = pub.evaluate("origin"); print("published page's origin:", origin)
        assert origin == "null", "a published page runs in an origin of its own"
        pub.close()
        assert page.request.get(srv.base + "p/chandra/csc258/f26/grades.json").status == 404

        # 7. The session ends mid-work. (a) Lectern's own call (Home lists the courses): the sign-in-again
        # window, then the list. (b) A builder's call (the Grade Builder opening grades.json, through scope.js).
        def fresh_code():   # each code works once: let this one be used again (instead of waiting 30 s)
            db.run("UPDATE users SET totp_step = 0")
            return security.totp_now(secret)

        def sign_in_again():
            page.wait_for_selector("#ra-pw", timeout=8000)
            assert page.input_value("#ra-email") == "chandra@utoronto.ca"
            page.fill("#ra-pw", PASSWORD); page.click("#ra-go")
            page.wait_for_selector("#ra-code"); page.fill("#ra-code", fresh_code()); page.click("#ra-go")
            page.wait_for_selector("#ra-pw", state="detached", timeout=8000)
        db.run("DELETE FROM sessions")
        page.evaluate("location.hash = '#/'")
        page.wait_for_selector("#ra-pw", timeout=8000); shot("a10-sign-in-again")
        sign_in_again()
        page.wait_for_selector(".lt-card[data-k]", timeout=8000)
        print("(a) home after signing in again:", page.inner_text(".lt-card[data-k='0'] .lt-title"))
        db.run("DELETE FROM sessions")
        page.evaluate("location.hash = '#/csc258/f26/gradebook'")
        sign_in_again()
        page.wait_for_selector("body.lt-tool-grades", timeout=10000); page.wait_for_timeout(800); shot("a10b-grades-after")
        print("(b) gradebook open after signing in again:", page.evaluate("() => window.Lectern.tools.grades.api.state().path"))
        assert page.evaluate("() => window.Lectern.tools.grades.api.state().path") == "csc258/f26/grades.json"
        assert len(db.all_("SELECT 1 FROM sessions")) == 1

        # 8. The admin panel: its own admin (added as on the terminal), its own sign-in; no way in for an account.
        page.click("#lt-acct")
        assert not page.query_selector("[data-m='admin']"), "accounts have no admin menu"
        page.keyboard.press("Escape")
        from server import admin as adminmod
        ASECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
        adminmod.save_admin("root@utoronto.ca", "Root Admin", PASSWORD, ASECRET)
        ap = ctx.new_page()
        ap.goto(srv.base + "admin"); ap.wait_for_selector("#lxa-email", state="visible"); ap.screenshot(path=f"{OUT}/a11a-admin-signin.png")
        assert not ap.is_visible("#lxa-code"), "the code is asked for after the password"
        ap.fill("#lxa-email", "chandra@utoronto.ca"); ap.fill("#lxa-pw", PASSWORD); ap.click("#lxa-go")
        ap.wait_for_selector("#lxa-code", state="visible"); ap.screenshot(path=f"{OUT}/a11b-admin-code.png")
        ap.fill("#lxa-code", "123456"); ap.click("#lxa-go2")
        expect(ap.locator("#lxa-status")).to_contain_text("don't match an admin")      # an account isn't an admin
        ap.wait_for_selector("#lxa-pw", state="visible")                                # back to the password
        ap.fill("#lxa-email", "root@utoronto.ca"); ap.fill("#lxa-pw", PASSWORD); ap.click("#lxa-go")
        ap.fill("#lxa-code", security.totp_now(ASECRET)); ap.click("#lxa-go2")
        ap.wait_for_selector("#lxa-inv-email")
        ap.fill("#lxa-inv-email", "ta@utoronto.ca"); ap.click("#lxa-inv [type=submit]")
        ap.wait_for_selector("#lxa-inv-msg .lt-linkbox input"); ap.screenshot(path=f"{OUT}/a11-admin.png", full_page=True)
        link = ap.input_value("#lxa-inv-msg .lt-linkbox input")
        assert re.search(r"#invite=[\w-]{40,}", link), link
        expect(ap.locator("#lxa-page")).to_contain_text("ta@utoronto.ca")
        # Email settings: the form is there; a test that can't go through saves nothing.
        ap.wait_for_selector("#ml-host"); ap.locator("#lxa-mail").screenshot(path=f"{OUT}/a11c-admin-email.png")
        ap.fill("#ml-host", "localhost"); ap.fill("#ml-port", "1"); ap.select_option("#ml-sec", "none"); ap.click("#lxa-mail-f [type=submit]")
        ap.fill("#ap-pw", PASSWORD); ap.click(".lt-modal [type=submit]")
        expect(ap.locator(".lt-modal .lt-err")).to_contain_text("nothing was saved", timeout=30000)
        ap.click(".lt-modal [data-no]")
        assert not db.one("SELECT 1 FROM settings WHERE key = 'smtp'")
        # Deleting an account: their email typed out, and the admin's password.
        keep_user = srv.user; srv.account(email="gone@utoronto.ca", name="Gone Person", handle="gone", admin=False); srv.user = keep_user
        ap.reload(); ap.wait_for_selector("#lxa-page .lt-user")
        row = ap.locator(".lt-user", has_text="gone@utoronto.ca")
        row.locator("[data-act='delete']").click(); ap.wait_for_selector("#dl-email")
        assert ap.is_disabled(".lt-modal [type=submit]")
        ap.fill("#dl-email", "gone@utoronto.ca"); ap.fill("#dl-pw", PASSWORD); ap.screenshot(path=f"{OUT}/a11d-admin-delete.png")
        ap.click(".lt-modal [type=submit]")
        expect(ap.locator("#lt-toast-root")).to_contain_text("Deleted gone@utoronto.ca")
        assert not db.one("SELECT 1 FROM users WHERE email = 'gone@utoronto.ca'")
        expect(ap.locator("#lxa-page")).not_to_contain_text("gone@utoronto.ca")
        ap.close()

        # 9. Forgotten password (email printed, no SMTP): the reset link, with the 2FA code it needs.
        page.click("#lt-acct"); page.click("[data-m='out']"); page.wait_for_selector("#sp-forgot", state="visible")
        page.click("#sp-forgot"); page.fill("#fg-email", "chandra@utoronto.ca"); page.click("#fg-go")
        expect(page.locator("#sp-panel")).to_contain_text("If that email has a Lectern account")
        from server import mailer
        reset = re.search(r"#reset=([\w-]+)", mailer.sent[-1]["body"]).group(1)
        page.goto(srv.base + "#reset=" + reset); page.wait_for_selector("#rs-pw")
        page.fill("#rs-pw", "an entirely new passphrase"); page.fill("#rs-pw2", "an entirely new passphrase")
        page.fill("#rs-code", fresh_code()); page.click("#rs-go")
        expect(page.locator("#splash-status")).to_contain_text("password is changed")
        shot("a12-reset-done")

        # Phone
        m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mp = m.new_page(); mp.goto(srv.base); mp.wait_for_timeout(500); mp.screenshot(path=f"{OUT}/a13-splash-phone.png")
        b.close()
    print("\n".join(errors[:30]) or "no console errors")
    assert not [e for e in errors if e.startswith("pageerror")], errors
    print("flow_auth: OK")


if __name__ == "__main__":
    main()
