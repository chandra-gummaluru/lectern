"""The demo course, Export and Import, and a student's My Marks.

1. A new account's Home offers New, Import and the demo. Try the Demo Course: csc258-demo opens, in this term.
2. Home lists it, with no demo line any more. The gradebook's Settings have Grade So Far, turned on.
3. Export downloads csc258-demo-<term>.lectern.zip, without the students.
4. Import it: the dialog reads the file, suggests the next term, and says how far the dates move; it opens
   as a new offering with the setup and no students.
5. A demo student signs in to the course page and opens My Marks: their released marks, and their grade so
   far. The teaching team's view of My Marks says what students see.
Asserts as it goes; screenshots in shots/.

Run:  python tests/browser/flow_transfer.py
"""
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        from server import mailer, transfer
        srv.account()
        T = transfer.term_now()
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}, accept_downloads=True); block_cdns(ctx)
        me = ctx.new_page()
        me.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        srv.sign_in(me)

        # 1. A new account's Home, and the demo
        me.wait_for_selector("#lt-demo2")
        expect(me.locator(".lt-start .lt-card")).to_have_count(3)
        me.wait_for_timeout(800); me.screenshot(path=f"{OUT}/700-home-empty.png")
        me.click("#lt-demo2")
        me.wait_for_selector(".lt-off-h1")
        expect(me.locator(".lt-off-h1")).to_contain_text("CSC258-DEMO")
        expect(me.locator("#lt-export")).to_be_visible()
        me.wait_for_timeout(800)
        me.screenshot(path=f"{OUT}/701-demo-offering.png")
        book = json.loads(srv.text("priv", f"csc258-demo/{T}/grades.json"))
        out = [e["id"] for e in book["evals"] if e.get("released")]
        print("1 demo:", len(book["students"]), "students;", len(out), "evaluations released")

        # 2. Home lists it; the gradebook's Settings
        me.evaluate("location.hash = '#/'"); me.wait_for_selector(".lt-ochip")
        expect(me.locator(".lt-ochip", has_text="CSC258-DEMO")).to_have_count(1)
        expect(me.locator("#lt-demo")).to_have_count(0)
        me.evaluate(f"location.hash = '#/csc258-demo/{T}/settings'")
        me.wait_for_selector("[data-lt-tool='grades'] [data-pshow='sofar']")
        expect(me.locator("[data-lt-tool='grades'] [data-pshow='sofar']")).to_be_checked()
        me.locator("[data-lt-tool='grades'] [data-pshow='sofar']").scroll_into_view_if_needed()
        me.screenshot(path=f"{OUT}/702-grade-settings.png")
        print("2 settings: Grade So Far is on")

        # 3. Export
        me.evaluate(f"location.hash = '#/csc258-demo/{T}'"); me.wait_for_selector("#lt-export")
        with me.expect_download() as dl:
            me.click("#lt-export")
        path = dl.value.path(); name = dl.value.suggested_filename
        assert name == f"csc258-demo-{T}.lectern.zip", name
        z = zipfile.ZipFile(path)
        assert json.loads(z.read("priv/grades.json"))["students"] == [] and "priv/midterm/exam.json" in z.namelist()
        print("3 export:", name, len(z.namelist()), "files")

        # 4. Import it, as the next term
        me.evaluate("location.hash = '#/'"); me.wait_for_selector("#lt-imp:not([disabled])")
        me.click("#lt-imp"); me.wait_for_selector("#im-file")
        me.set_input_files("#im-file", path)
        me.wait_for_selector("#im-rest:not([hidden])")
        assert me.input_value("#im-c") == "csc258-demo" and me.input_value("#im-title") == "Computer Organization (Demo)"
        expect(me.locator("#im-move-n")).to_contain_text("later")
        me.fill("#im-c", "csc258"); me.fill("#im-title", "Computer Organization")
        me.screenshot(path=f"{OUT}/703-import.png")
        new_t = me.eval_on_selector("#im-s", "s => s.value") + me.input_value("#im-y")[-2:]
        me.click(".lt-modal [data-ok]")
        me.wait_for_selector(".lt-off-h1:has-text('CSC258')")
        me.wait_for_timeout(800)
        me.screenshot(path=f"{OUT}/704-imported.png")
        nb = json.loads(srv.text("priv", f"csc258/{new_t}/grades.json"))
        assert nb["students"] == [] and nb["evals"] and nb["course"]["code"] == "CSC258", nb["course"]
        print("4 import: csc258/" + new_t, len(nb["evals"]), "evaluations, no students")

        # 5. My Marks, for a demo student who has marks out
        s = next(x for x in book["students"] if any(book["marks"].get(x["num"], {}).get(e) for e in out))
        email = s["f"]["email"]
        stu = b.new_context(viewport={"width": 1200, "height": 900}).new_page()
        stu.on("pageerror", lambda e: errors.append(f"student pageerror: {e}"))
        hub = srv.base + f"c/chandra/csc258-demo/{T}/"
        stu.goto(hub + "#marks"); stu.wait_for_selector(".hb-locked")
        stu.goto(hub + "sign-in"); stu.fill("#si-e", email); stu.click("#si-email button[type=submit]")
        stu.wait_for_selector("#si-c")
        code = re.search(r"\b(\d{8})\b", [m for m in mailer.sent if m["to"] == email and "code" in m["subject"]][-1]["body"]).group(1)
        stu.fill("#si-c", code); stu.click("#si-code button[type=submit]")
        stu.wait_for_selector(".hs-sec")
        stu.click("a.hs-link:has-text('My Marks')")
        stu.wait_for_selector(".mm-sum")
        big = stu.locator(".mm-big b").inner_text()
        assert re.match(r"^\d+(\.\d)?%$", big), big
        expect(stu.locator(".mm-row .mm-mk:not(.mm-none)")).not_to_have_count(0)
        stu.wait_for_timeout(1200); stu.screenshot(path=f"{OUT}/705-my-marks.png", full_page=True)
        stu.set_viewport_size({"width": 390, "height": 844}); stu.wait_for_timeout(1200)
        stu.screenshot(path=f"{OUT}/706-my-marks-phone.png", full_page=True)
        stu.click("#hb-acct"); expect(stu.locator(".hb-menu a[href='#marks']")).to_be_visible()
        print("5 my marks:", s["first"], s["last"], "grade so far", big)

        me.goto(hub + "#marks"); me.wait_for_selector(".mm-note"); me.wait_for_timeout(1200)
        expect(me.locator(".mm-note")).to_contain_text("grade so far")
        me.screenshot(path=f"{OUT}/707-my-marks-staff.png")
        b.close()
    assert not errors, errors
    print("flow_transfer: OK")


if __name__ == "__main__":
    main()
