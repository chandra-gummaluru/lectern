"""Accommodations, end to end against the real server (harness.Server, email recorded instead of sent):
set them on an evaluation in the gradebook, a student signed in to the course page asks (through its API:
the course page's own form is the hub's), and the instructor approves one and rejects the other in Lectern.

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

        # 2. A student signs in to the course page (the code it emails them), then asks what they can request.
        import re
        H = {"X-Lectern": "1", "Origin": srv.base.rstrip("/")}
        HUB = srv.base + "api/hub/chandra/csc258/f26"
        mia = book()["students"][0]; email = mia["f"]["email"].lower()
        sc = b.new_context(); stq = sc.request
        assert stq.post(HUB + "/code", data={"email": email}, headers=H).ok
        code = re.search(r"\b(\d{8})\b", [m for m in outbox if m["to"] == email and "code" in m["subject"]][-1]["body"]).group(1)
        assert stq.post(HUB + "/verify", data={"email": email, "code": code}, headers=H).ok
        outbox.clear()
        info = stq.get(HUB + "/accommodation?e=mt").json()
        print("midterm:", info["standard"], info["alternate"], info.get("deadline"))
        assert info["standard"]["approval"] and info["alternate"]
        assert stq.get(HUB + "/accommodation?e=l5").json()["deadline"]["passed"]
        # The old sign-in-free form is gone.
        assert page.request.get(srv.base + "request?r=chandra&o=csc258%2Ff26&e=mt").status == 404

        # 3. The student asks: the standard accommodation, then an alternate one.
        ask = lambda **d: stq.post(HUB + "/accommodation", data={"e": "mt", "id": mia["num"], "first": mia["first"], "last": mia["last"], **d}, headers=H)
        r = ask(id="0000000", kind="standard"); assert r.status == 400, r.status   # not their number
        r = ask(kind="alternate"); assert r.status == 400                          # says what
        assert ask(kind="standard").status == 201
        assert not outbox, "no receipt by email (it's in My Requests on the course page)"
        assert ask(kind="alternate", details="I also need a quiet room: I have an ADHD accommodation letter.").status == 201
        reqs = json.loads(srv.text("priv", "csc258/f26/accommodations.json"))["requests"]
        assert sorted(r["kind"] for r in reqs) == ["alternate", "standard"], reqs
        sc.close()

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
