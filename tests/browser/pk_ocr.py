import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from harness import Server, OUT, block_cdns
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOOK = json.load(open(os.path.join(ROOT, "sample-data/demo-courses-private/csc258/f26/grades.json")))
BOOK["fields"] = {"idLabel": "Student number", "custom": [{"id": "email", "label": "Email"}]}
BOOK["students"] = [{"num": "1009876543", "first": "Maya", "last": "Castillo", "f": {"email": "maya@mail.utoronto.ca"}}, {"num": "1001234567", "first": "Zoë", "last": "Ng", "f": {"email": "zoe@mail.utoronto.ca"}}]
for e in BOOK["evals"]:
    if e["id"] == "mt": e["title"] = "Midterm Test"
SP = "/tmp/claude-0/-home-claude/1e192234-afab-5dd7-adbc-0337c9ed1a4c/scratchpad"
errs = []
with Server() as srv, sync_playwright() as p:
    owner = srv.account(); sam = srv.account(email="sam@utoronto.ca", name="Sam Patel", handle="sam", admin=False)
    srv.user = owner
    from server import db as sdb
    sdb.run("INSERT INTO members (owner_id, offering, user_id, role, added) VALUES (?, 'csc258/f26', ?, 'ta', 0)", (owner["id"], sam["id"]))
    srv.put("pub", {"csc258/f26/course.json": open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json")).read()})
    srv.put("priv", {"csc258/f26/grades.json": json.dumps(BOOK)})
    def browser(video):
        return p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={SP}/{video}.y4m"])
    b = browser("tcard")
    ctx = b.new_context(viewport={"width": 360, "height": 760}, permissions=["camera"]); block_cdns(ctx); me = ctx.new_page(); me.on("pageerror", lambda e: errs.append(str(e)))
    me.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    srv.sign_in(me, hash="#/csc258/f26/attendance/mt"); me.wait_for_selector("#at-note"); me.fill("#at-note", "BA 1170"); me.click("#at-go")
    import time; t0 = time.time()
    me.wait_for_selector(".at-panel.ask, .at-panel.find", timeout=60000); print("read in %.1fs" % (time.time() - t0))
    me.screenshot(path=f"{OUT}/ocr-ask.png"); print("who:", me.inner_text(".at-panel h3") if me.locator(".at-panel h3").count() else me.inner_text(".at-panel"))
    me.click(".at-panel [data-yes]"); me.wait_for_selector(".at-panel.ok"); print("ok:", me.inner_text(".at-panel.ok"))
    me.wait_for_selector(".at-panel.bad", timeout=30000); print("again:", me.inner_text(".at-panel.bad .at-why"))
    print("errors:", errs)
