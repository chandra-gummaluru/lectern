"""Students: the offering's Students card is the class list (the gradebook's students).

1. Before any students: what each student has (identifier, email domain, a UTORid field), saved to grades.json.
2. Add a student; the fields are fixed now. Import a class list (one new student has no @domain email).
3. The card doesn't change or remove students: a student opens their page in the Gradebook, where they're
   deleted; the Gradebook shows the others for marks, and has no way to add students. A student added
   while the Gradebook is open shows when it opens again. Its Grade Settings have no Students card;
   a rule shown on the course page gets there when the gradebook is saved.
4. A student opens the course page, signs in there with their email and the code it emails them, and
   sees the signed-in tabs; a dropped student can't get a code.
Asserts as it goes; screenshots in shots/.

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
CSV = "Student Number,First Name,Last Name,Email,UTORid\n1002,Ben,Okafor,ben.okafor@mail.utoronto.ca,okaforb\n1003,Ana,Li,ana@gmail.com,lia\n"
S = "#lt-students "


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
        book = lambda: json.loads(srv.text("priv", "csc258/f26/grades.json") or "{}")
        srv.sign_in(me, hash="#/csc258/f26")

        # 1. What each student has
        me.wait_for_selector("#sf-change"); me.click("#sf-change"); me.wait_for_selector("#sf-id")
        me.fill("#sf-id", "Student Number")
        me.fill("#sf-dom", "@Mail.UToronto.ca")
        me.click("#sf-add"); me.locator("[data-sf]").last.fill("UTORid")
        me.screenshot(path=f"{OUT}/210a-fields-dialog.png")
        me.click(".lt-modal [data-ok]"); me.wait_for_timeout(900)
        expect(me.locator(".lt-st-fieldrow")).to_contain_text("Student Number, First Name, Last Name, Email (@mail.utoronto.ca), UTORid")
        F = book()["fields"]
        assert F["idLabel"] == "Student Number" and F["emailDomain"] == "mail.utoronto.ca" and [f["label"] for f in F["custom"]] == ["Email", "UTORid"], F
        me.locator("#lt-students").scroll_into_view_if_needed()
        me.screenshot(path=f"{OUT}/210-student-fields.png")
        print("1 fields:", F)

        # 2. Add one; then the fields are fixed. Import a class list.
        me.click("#st-add"); me.wait_for_selector("#sd-num")
        me.fill("#sd-num", "1001"); me.fill("#sd-first", "Maya"); me.fill("#sd-last", "Castillo")
        me.fill("#sd-email", "maya@gmail.com"); me.locator("[data-sd]").fill("castil12")
        me.click(".lt-modal [data-ok]")
        expect(me.locator("#sd-err")).to_contain_text("@mail.utoronto.ca")
        me.fill("#sd-email", "maya.castillo@mail.utoronto.ca"); me.click(".lt-modal [data-ok]")
        me.wait_for_selector(S + ".lt-st-list .lt-orow")
        assert not me.query_selector("#sf-change"), "the fields can still change"
        me.click("#st-import"); me.wait_for_selector(".lt-st-drop")
        me.set_input_files(".lt-st-drop input", files=[{"name": "classlist.csv", "mimeType": "text/csv", "buffer": CSV.encode()}])
        me.wait_for_selector("#im-sum")
        expect(me.locator("#im-sum")).to_contain_text("2 new students")
        expect(me.locator("#im-sum")).to_contain_text("1 has no @mail.utoronto.ca email")
        me.screenshot(path=f"{OUT}/211-import.png")
        me.click(".lt-modal [data-ok]"); me.wait_for_timeout(900)
        expect(me.locator(S + ".lt-st-list .lt-orow")).to_have_count(3)
        st = {s["num"]: s for s in book()["students"]}
        assert st["1002"]["f"] == {"email": "ben.okafor@mail.utoronto.ca", next(f["id"] for f in F["custom"] if f["label"] == "UTORid"): "okaforb"}, st["1002"]
        expect(me.locator(S + ".lt-orow", has_text="Li, Ana")).to_contain_text("can't sign in")
        me.locator("#lt-students").scroll_into_view_if_needed()
        me.screenshot(path=f"{OUT}/212-class-list.png")
        print("2 class list:", sorted(st))

        # 3. The card can't change or remove a student: clicking one opens their page in the gradebook, where
        #    they're deleted. A student added while the gradebook is open shows when it opens again.
        assert not me.query_selector(S + "[data-st-remove], " + S + "[data-st-edit]"), "the card still changes students"
        bk = book(); bk["evals"] = [{"id": "a1", "name": "Assignment 1", "short": "A1", "total": 10, "weight": 100}]
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(bk)})   # an evaluation (made in Evaluations), so the grades show
        me.reload(); me.wait_for_selector(S + ".lt-st-list")
        me.click(S + "[data-st-open='1003']")
        g = me.locator("[data-lt-tool=grades]")
        me.wait_for_selector("[data-lt-tool=grades] [data-ed=sremove]")
        expect(g.locator(".st-head h2")).to_have_text("Li, Ana")
        me.screenshot(path=f"{OUT}/213-student-page.png")
        me.click("[data-lt-tool=grades] [data-ed=sremove]"); me.click("[data-lt-tool=grades] [data-ed=sremove]")   # Delete takes two clicks
        me.keyboard.press("Control+s"); me.wait_for_timeout(2000)
        assert sorted(s["num"] for s in book()["students"]) == ["1001", "1002"], [s["num"] for s in book()["students"]]
        me.wait_for_selector("#st-add")   # deleted: back on the offering's page, where the student was opened from
        assert me.locator(S + "[data-st-open='1003']").count() == 0
        assert not me.query_selector("[data-lt-tool=grades] [data-act=imp-roster], [data-lt-tool=grades] [data-act=st-add]"), "the gradebook still adds students"
        assert not me.query_selector("[data-lt-tool=grades] #tb-view button"), "the gradebook still has Grades | Settings tabs"
        me.click("#st-add"); me.fill("#sd-num", "1004"); me.fill("#sd-first", "Raj"); me.fill("#sd-last", "Patel"); me.fill("#sd-email", "raj.patel@mail.utoronto.ca")
        me.click(".lt-modal [data-ok]"); me.wait_for_timeout(900)
        me.click("[data-part=book]"); me.wait_for_timeout(1200)
        expect(g).to_contain_text("Patel, Raj")
        me.click("[data-lt-tool=grades] [data-act=view][data-v=settings]")   # Settings, beside Upload Marks
        expect(g.locator("h1")).to_have_text("Grade Settings")
        assert "Each student is identified" not in g.inner_text(), "Grade Settings has the Students card"
        me.screenshot(path=f"{OUT}/213-grade-settings.png")
        # Rounding, shown on the course page: saving the gradebook puts it there (no course page save).
        me.click("[data-lt-tool=grades] [data-act=pol-step][data-v='1']")
        me.check("[data-lt-tool=grades] [data-pshow=round]")
        me.keyboard.press("Control+s"); me.wait_for_timeout(2500)
        pol = json.loads(srv.text("pub", "csc258/f26/course.json"))["page"]["scheme"]["policies"]
        assert [x["show"] for x in pol if x["id"] == "round"] == [True], pol
        hub = b.new_context().new_page(); hub.goto(srv.base + "c/chandra/csc258/f26/#about"); hub.wait_for_selector(".hb-main h2")
        expect(hub.locator(".hb-main")).to_contain_text("rounded to the nearest whole percent")
        hub.close()
        print("3 the gradebook shows them; its settings are the grade rules, and the course page gets them on save")

        # 4. A student signs in; a dropped one can't.
        stu = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
        stu.on("pageerror", lambda e: errors.append(f"student pageerror: {e}"))
        stu.goto(srv.base + "c/chandra/csc258/f26/#lectures"); stu.wait_for_selector(".hb-locked")
        stu.click(".hb-locked a:has-text('Sign in')")
        stu.wait_for_selector("#si-e")
        assert stu.url.endswith("/c/chandra/csc258/f26/sign-in"), stu.url
        stu.fill("#si-e", "maya.castillo@mail.utoronto.ca"); stu.click("#si-email button[type=submit]")
        stu.wait_for_selector("#si-c")
        code = re.search(r"\b(\d{6})\b", [m for m in mailer.sent if m["to"] == "maya.castillo@mail.utoronto.ca" and "code" in m["subject"]][-1]["body"]).group(1)
        stu.fill("#si-c", "000000" if code != "000000" else "111111"); stu.click("#si-code button[type=submit]")
        expect(stu.locator("#si-err2")).to_contain_text("isn't right")
        stu.fill("#si-c", code); stu.click("#si-code button[type=submit]")
        stu.wait_for_selector(".hs-sec")
        expect(stu.locator(".hb-who")).to_contain_text("maya.castillo@mail.utoronto.ca")
        stu.click("a.hs-more:has-text('See all weeks')")
        stu.wait_for_selector(".hs-wk")
        stu.screenshot(path=f"{OUT}/214-signed-in.png")
        me.locator("#lt-path button", has_text="csc258 / f26").click(); me.wait_for_selector(S + ".lt-st-list")
        expect(me.locator(S + ".lt-orow", has_text="Castillo, Maya")).to_contain_text("Signed in")
        print("4 the student signed in with the code, and sees Lectures")
        stu.click("#hb-acct"); stu.click("#hb-out"); stu.wait_for_timeout(800)
        stu.goto(srv.base + "c/chandra/csc258/f26/#activities")
        expect(stu.locator(".hb-locked")).to_be_visible()
        print("5 signed out")
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors


if __name__ == "__main__":
    main()
