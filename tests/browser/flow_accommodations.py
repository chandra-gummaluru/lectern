"""Accommodations, end to end: set them on an evaluation in Grades, see the course page's button, a student
asks through the form, the instructor approves it in Lectern.

Runs against the real server (harness.Server, in this process), with email printed instead of sent:
    python tests/browser/flow_accommodations.py
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo, BASE
from harness import OUT
from server import mailer, accommodations

PRIV, PUB = "chandra-gummaluru/courses-private", "chandra-gummaluru/courses"


def sample(path):
    with open(os.path.join(ROOT, "sample-data", path), encoding="utf-8") as f:
        return f.read()


def book():
    b = json.loads(sample("demo-courses-private/csc258/f26/grades.json"))
    b["fields"]["custom"] = [{"id": "email", "label": "Email"}]
    for s in b["students"]:
        s["f"] = {"email": f"{s['first'].lower()}.{s['last'].lower()}@mail.utoronto.ca"}
    # Lab 5's requests closed yesterday
    lab5 = next(e for e in b["evals"] if e["id"] == "l5")
    lab5["accom"] = {"approval": False, "alternate": True, "by": "2026-01-02", "byTime": "17:00"}
    return b


def main():
    gh = FakeGitHub()
    gh.add(Repo(PRIV, True, {"csc258/f26/grades.json": json.dumps(book())}))
    gh.add(Repo(PUB, False, {"README.md": "x", "csc258/f26/info.html": sample("demo-courses/csc258/f26/info.html")}))
    accommodations.BOOK_TTL = 0

    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        gh.attach(ctx)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda pg, n: pg.screenshot(path=f"{OUT}/{n}.png", full_page=True)

        # 1. Grades: the Midterm takes requests (standard needs approval; alternate too), until a date
        G = "[data-lt-tool='grades'] "
        page.goto(BASE + "#/csc258/f26/evaluations"); page.wait_for_timeout(2500)
        page.click(G + ".erow:has(h3:text-is('Midterm'))"); page.wait_for_timeout(700)
        # Its standard accommodation is its missed-work policy (a makeup, and weight moved to the final)
        print("standard:", page.inner_text(G + ".ed-sec:text('Accommodations') + .ed-help"))
        page.check(G + "input[data-acm='approval']"); page.wait_for_timeout(300)
        page.check(G + "input[data-acm='alternate']"); page.wait_for_timeout(300)
        # The deadline, with the same calendar as the evaluation's date
        page.click(G + "[data-ed='acm-when']"); page.wait_for_timeout(300)
        page.click("[data-day='2026-10-26']"); page.wait_for_timeout(200)
        page.fill("#wp-t", "5pm"); page.wait_for_timeout(200); page.screenshot(path=f"{OUT}/acc-01b-calendar.png"); page.press("#wp-t", "Enter"); page.wait_for_timeout(400)
        print("deadline button:", page.inner_text(G + "[data-ed='acm-when']"))
        # Lab 1 (in a group): nothing to request as standard
        page.click("#lt-path button:has-text('Evaluations')"); page.wait_for_timeout(500)
        page.click(G + ".erow:has(h3:text-is('Lab 1'))"); page.wait_for_timeout(500)
        assert page.is_disabled(G + "input[data-acm='approval']")
        print("lab 1:", page.inner_text(G + ".ed-sec:text('Accommodations') + .ed-help"))
        page.click("#lt-path button:has-text('Evaluations')"); page.wait_for_timeout(500)
        page.click(G + ".erow:has(h3:text-is('Midterm'))"); page.wait_for_timeout(600)
        page.locator(G + ".ed-sec:text('Accommodations')").scroll_into_view_if_needed(); shot(page, "acc-01-grades")
        page.keyboard.press("Control+s"); page.wait_for_timeout(2000)
        saved = json.loads(gh.repos[PRIV].commits[gh.repos[PRIV].head]["files"]["csc258/f26/grades.json"])
        mt = next(e for e in saved["evals"] if e["id"] == "mt")
        print("saved accom:", mt.get("accom"))
        assert mt["accom"] == {"approval": True, "alternate": True, "by": "2026-10-26", "byTime": "17:00",
                               "standard": "The makeup Midterm makeup counts for 12.5% and 12.5% moves to Final Exam."}

        # 2. The course page: a Request Accommodation button (for the Midterm), and Lab 5's deadline passed
        page.evaluate("location.hash = '#/csc258/f26/course'"); page.wait_for_timeout(3500)
        page.keyboard.press("Control+s"); page.wait_for_timeout(2000)
        info = gh.repos[PUB].commits[gh.repos[PUB].head]["files"]["csc258/f26/info.html"]
        assert 'class="cpb-req"' in info, "no request button on the course page"
        import re
        link = re.search(r'class="cpb-req" data-by="([^"]*)" href="([^"]+)"', info)
        print("button:", link.group(1), link.group(2))
        assert link.group(2).replace("&amp;", "&") == BASE + "request?r=chandra&o=csc258%2Ff26&e=mt"
        assert "The deadline for accommodation requests has passed." in info   # Lab 5
        pub = ctx.new_page(); pub.set_content(info); pub.wait_for_timeout(500)
        pub.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)"); pub.wait_for_timeout(200)
        pub.locator(".cpb-gev[data-ev=mt]").screenshot(path=f"{OUT}/acc-02-course-card.png")
        pub.locator(".cpb-scheme").screenshot(path=f"{OUT}/acc-02-course-scheme.png")
        print("on the page:", pub.locator(".cpb-req").count(), "buttons;", pub.locator(".cpb-req-off").count(), "closed notes")
        pub.close()

        # 3. A student asks
        st = ctx.new_page()
        st.on("pageerror", lambda e: errors.append(f"student pageerror: {e}"))
        url = link.group(2).replace("&amp;", "&")
        st.goto(url); st.wait_for_timeout(800); shot(st, "acc-03-who")
        print("form:", st.inner_text("#rq-course"), "|", st.inner_text("#rq-eval"))
        mia = next(s for s in book()["students"])
        st.fill("input[name=email]", "someone@gmail.com"); st.fill("input[name=id]", mia["num"]); st.fill("input[name=first]", mia["first"]); st.fill("input[name=last]", mia["last"])
        st.click("button[type=submit]"); st.wait_for_timeout(600)
        print("wrong email:", st.inner_text("#rq-err")); shot(st, "acc-04-not-found")
        st.fill("input[name=email]", mia["f"]["email"].upper())
        st.click("button[type=submit]"); st.wait_for_timeout(600); shot(st, "acc-05-choose")
        st.check("input[value=alternate]"); st.click("button[type=submit]"); st.wait_for_timeout(200)
        print("alternate without text:", st.inner_text("#rq-err"))
        st.check("input[value=standard]"); st.click("button[type=submit]"); st.wait_for_timeout(900); shot(st, "acc-06-sent")
        print("sent:", st.inner_text("#rq-card").replace("\n", " | "))
        print("receipt to:", mailer.sent[-1]["to"], "|", mailer.sent[-1]["subject"])
        st.click("#rq-again"); st.wait_for_timeout(300)
        st.check("input[value=alternate]"); st.fill("textarea[name=details]", "I also need a quiet room: I have an ADHD accommodation letter."); st.click("button[type=submit]"); st.wait_for_timeout(900)
        # Lab 5: closed
        st.goto(url.replace("e=mt", "e=l5")); st.wait_for_timeout(800); shot(st, "acc-07-closed")
        print("lab 5:", st.inner_text("#rq-card").replace("\n", " | "))
        # Lab 1: no requests
        st.goto(url.replace("e=mt", "e=l1")); st.wait_for_timeout(800); print("lab 1:", st.inner_text("#rq-card").replace("\n", " | "))
        # Phone
        ph = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
        ph.goto(url); ph.wait_for_timeout(800); ph.screenshot(path=f"{OUT}/acc-08-phone.png", full_page=True)

        # 4. The instructor decides
        page.evaluate("location.hash = '#/csc258/f26'"); page.wait_for_timeout(1500); shot(page, "acc-09-offering")
        print("offering:", page.inner_text("#lt-accom-sum"))
        page.click("#lt-accom"); page.wait_for_timeout(1500); shot(page, "acc-10-list")
        print("path:", page.inner_text("#lt-path").replace("\n", " "), "| cards:", page.locator(".lt-req").count())
        page.click(".lt-req:has-text('Standard accommodation') [data-decide=approved]"); page.wait_for_timeout(300)
        page.fill("#dc-note", "See you Thursday at 6 in BA 2135."); shot(page, "acc-11-dialog")
        page.click(".lt-modal [data-ok]"); page.wait_for_timeout(1200)
        print("toast:", page.inner_text("#lt-toast-root"))
        print("decision email:", mailer.sent[-1]["subject"], "|", "BA 2135" in mailer.sent[-1]["body"])
        page.click(".lt-req [data-decide=rejected]"); page.wait_for_timeout(300); page.click(".lt-modal [data-ok]"); page.wait_for_timeout(1200)
        page.click("[data-show=decided]"); page.wait_for_timeout(300); shot(page, "acc-12-decided")
        final = json.loads(gh.repos[PRIV].commits[gh.repos[PRIV].head]["files"]["csc258/f26/accommodations.json"])["requests"]
        print("file:", [(r["kind"], r["status"], r["decidedBy"]) for r in final])
        print("commits:", gh.repos[PRIV].log[-4:])
        assert [r["status"] for r in final if r["kind"] == "standard"] == ["approved"] and all(r["decidedBy"] == "Chandra Gummaluru" for r in final if r["status"] != "pending")
        b.close()
    print("\n".join(errors[:30]) or "no console errors")


if __name__ == "__main__":
    main()
