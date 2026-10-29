"""Accommodations, end to end against the real server (harness.Server, email recorded instead of sent):
set them on an evaluation in the gradebook, the public request endpoint says what can be asked, a student
asks through the request form, and the instructor approves one and rejects the other in Lectern.

    python tests/browser/flow_accommodations.py
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
from playwright.sync_api import sync_playwright, expect
from harness import Server, OUT, block_cdns


def sample(path):
    with open(os.path.join(ROOT, "sample-data", path), encoding="utf-8") as f:
        return f.read()


def book():
    b = json.loads(sample("demo-courses-private/csc258/f26/grades.json"))
    b["fields"]["custom"] = [{"id": "email", "label": "Email"}]
    b["fields"]["emailDomain"] = "mail.utoronto.ca"
    for s in b["students"]:
        s["f"] = {"email": f"{s['first'].lower()}.{s['last'].lower()}@mail.utoronto.ca"}
    # Lab 5's requests closed long ago
    lab5 = next(e for e in b["evals"] if e["id"] == "l5")
    lab5["accom"] = {"approval": False, "alternate": True, "by": "2026-01-02", "byTime": "17:00"}
    return b


def main():
    errors = []
    with Server() as srv, sync_playwright() as p:
        from server import accommodations, mailer
        accommodations.BOOK_TTL = 0
        # Email "set up", and recorded instead of sent.
        os.environ["LECTERN_SMTP_HOST"] = "smtp.example.org"
        outbox = []
        mailer.deliver = lambda to, subject, body, reply_to=None, cfg=None: (outbox.append({"to": to, "subject": subject, "body": str(body)}), "")[1]
        srv.account()
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(book())})
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        block_cdns(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda pg, n: pg.screenshot(path=f"{OUT}/{n}.png", full_page=True)
        srv.sign_in(page, hash="#/csc258/f26/evaluations")

        # 1. The gradebook: the Midterm takes requests (standard needs approval; alternate too), until a date
        G = "[data-lt-tool='grades'] "
        page.wait_for_selector(G + ".erow[data-id='mt']")
        page.click(G + ".erow[data-id='mt']"); page.wait_for_selector(G + "input[data-acm='approval']")
        # Its standard accommodation is its missed-work policy (a makeup, and weight moved to the final)
        print("standard:", page.inner_text(G + ".ed-sec:text('Accommodations') + .ed-help"))
        page.check(G + "input[data-acm='approval']"); page.wait_for_timeout(300)
        page.check(G + "input[data-acm='alternate']"); page.wait_for_timeout(300)
        # The deadline, with the same calendar as the evaluation's date
        page.click(G + "[data-ed='acm-when']"); page.wait_for_timeout(300)
        page.click("[data-day='2026-10-31']"); page.wait_for_timeout(200)
        page.fill("#wp-t", "5pm"); page.wait_for_timeout(200); page.screenshot(path=f"{OUT}/acc-01b-calendar.png"); page.press("#wp-t", "Enter"); page.wait_for_timeout(400)
        print("deadline button:", page.inner_text(G + "[data-ed='acm-when']"))
        # Lab 1 (in a group): nothing to request as standard
        page.evaluate("location.hash = '#/csc258/f26/evaluations'"); page.wait_for_timeout(500)
        page.click("#lt-path button:has-text('Evaluations')") if page.query_selector("#lt-path button:has-text('Evaluations')") else None
        page.wait_for_selector(G + ".erow[data-id='l1']"); page.click(G + ".erow[data-id='l1']"); page.wait_for_selector(G + "input[data-acm='approval']")
        assert page.is_disabled(G + "input[data-acm='approval']")
        print("lab 1:", page.inner_text(G + ".ed-sec:text('Accommodations') + .ed-help"))
        page.keyboard.press("Control+s"); page.wait_for_timeout(2000)
        saved = json.loads(srv.text("priv", "csc258/f26/grades.json"))
        mt = next(e for e in saved["evals"] if e["id"] == "mt")
        print("saved accom:", mt.get("accom"))
        assert {k: mt["accom"].get(k) for k in ("approval", "alternate", "by", "byTime")} == {"approval": True, "alternate": True, "by": "2026-10-31", "byTime": "17:00"}
        assert "Midterm makeup" in mt["accom"]["standard"] and "Final Exam" in mt["accom"]["standard"], mt["accom"]["standard"]

        # 2. What a student can ask for (the request form's first call): the Midterm; Lab 5's deadline passed.
        # (The course page's Request Accommodation button is the hub's now, for signed-in students: not tested here.)
        Q = "request?r=chandra&o=csc258%2Ff26&e="
        info = page.request.get(srv.base + "api/accommodations/evaluation?" + Q.split("?")[1] + "mt").json()
        print("midterm:", info["standard"], info["alternate"], info.get("deadline"))
        assert info["standard"]["approval"] and info["alternate"]
        l5 = page.request.get(srv.base + "api/accommodations/evaluation?" + Q.split("?")[1] + "l5").json()
        assert l5["deadline"]["passed"], l5

        # 3. A student asks, through the request form
        st = ctx.new_page()
        st.on("pageerror", lambda e: errors.append(f"student pageerror: {e}"))
        url = srv.base + Q + "mt"
        st.goto(url); st.wait_for_timeout(800); shot(st, "acc-03-who")
        print("form:", st.inner_text("#rq-course"), "|", st.inner_text("#rq-eval"))
        mia = book()["students"][0]
        st.fill("input[name=email]", "someone@gmail.com"); st.fill("input[name=id]", mia["num"]); st.fill("input[name=first]", mia["first"]); st.fill("input[name=last]", mia["last"])
        st.click("button[type=submit]"); st.wait_for_timeout(600)
        print("wrong email:", st.inner_text("#rq-err")); shot(st, "acc-04-not-found")
        st.fill("input[name=email]", mia["f"]["email"].upper())
        st.click("button[type=submit]"); st.wait_for_timeout(600); shot(st, "acc-05-choose")
        st.check("input[value=alternate]"); st.click("button[type=submit]"); st.wait_for_timeout(200)
        print("alternate without text:", st.inner_text("#rq-err"))
        st.check("input[value=standard]"); st.click("button[type=submit]"); st.wait_for_timeout(900); shot(st, "acc-06-sent")
        print("sent:", st.inner_text("#rq-card").replace("\n", " | "))
        assert not outbox, "no receipt by email (it's in My Requests on the course page)"
        st.click("#rq-again"); st.wait_for_timeout(300)
        st.check("input[value=alternate]"); st.fill("textarea[name=details]", "I also need a quiet room: I have an ADHD accommodation letter."); st.click("button[type=submit]"); st.wait_for_timeout(900)
        # Lab 5: closed
        st.goto(url.replace("e=mt", "e=l5")); st.wait_for_timeout(800); shot(st, "acc-07-closed")
        print("lab 5:", st.inner_text("#rq-card").replace("\n", " | "))
        # Phone
        ph = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
        ph.goto(url); ph.wait_for_timeout(800); ph.screenshot(path=f"{OUT}/acc-08-phone.png", full_page=True)
        reqs = json.loads(srv.text("priv", "csc258/f26/accommodations.json"))["requests"]
        assert sorted(r["kind"] for r in reqs) == ["alternate", "standard"], reqs

        # 4. The instructor decides: open each request, Decide, Approve or Reject, with a note
        page.evaluate("location.hash = '#/csc258/f26'"); page.wait_for_selector("#lt-accom"); page.wait_for_timeout(800); shot(page, "acc-09-offering")
        print("offering:", page.inner_text("#lt-accom-sum"))

        def decide(kind_text, pick, note=""):
            page.evaluate("location.hash = '#/csc258/f26/accommodations'"); page.wait_for_selector(".lt-rq-row")
            page.locator(".lt-rq-row", has_text=kind_text).locator("[data-req]").first.click(); page.wait_for_selector("#acc-reply")
            page.click("#acc-reply"); page.wait_for_selector("#acc-send")
            page.click(f"[data-pick='{pick}']")
            if note:
                page.click(".lt-req-rt [contenteditable]"); page.keyboard.type(note)
            shot(page, f"acc-11-{pick}")
            page.click("#acc-send")
            expect(page.locator("#lt-toast-root")).to_contain_text("Approved" if pick == "approved" else "Rejected")
        decide("Standard", "approved", "See you Thursday at 6 in BA 2135.")
        print("decision email:", outbox[-1]["subject"], "|", "BA 2135" in outbox[-1]["body"])
        assert "BA 2135" in outbox[-1]["body"]
        decide("Alternate", "rejected")
        shot(page, "acc-12-decided")
        final = json.loads(srv.text("priv", "csc258/f26/accommodations.json"))["requests"]
        print("file:", [(r["kind"], r["status"], r["decidedBy"]) for r in final])
        assert {r["kind"]: r["status"] for r in final} == {"standard": "approved", "alternate": "rejected"}
        assert all(r["decidedBy"] == "Chandra Gummaluru" for r in final)
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_accommodations: OK")


if __name__ == "__main__":
    main()
