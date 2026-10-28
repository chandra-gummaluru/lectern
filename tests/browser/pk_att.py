import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from harness import Server, OUT, block_cdns
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOOK = json.load(open(os.path.join(ROOT, "sample-data/demo-courses-private/csc258/f26/grades.json")))
BOOK["fields"] = {"idLabel": "Student number", "custom": [{"id": "email", "label": "Email"}]}
BOOK["students"] = [{"num": "1001", "first": "Maya", "last": "Castillo", "f": {"email": "maya@mail.utoronto.ca"}}, {"num": "1002", "first": "Zoë", "last": "Ng", "f": {"email": "zoe@mail.utoronto.ca"}}]
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
    b = browser("maya")
    # Maya adds her TCard on the course page.
    st = b.new_context(viewport={"width": 420, "height": 860}); block_cdns(st); pg = st.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(srv.base + "c/chandra/csc258/f26/sign-in"); pg.fill("#si-e", "maya@mail.utoronto.ca"); pg.keyboard.press("Enter"); pg.wait_for_timeout(700)
    from server import mailer
    code = re.search(r"\b(\d{6})\b", [m for m in mailer.sent if m["to"] == "maya@mail.utoronto.ca"][-1]["body"]).group(1)
    pg.fill("#si-c", code); pg.keyboard.press("Enter"); pg.wait_for_timeout(1200)
    pg.evaluate("location.hash = '#student-id'"); pg.wait_for_selector("#tc-in"); pg.screenshot(path=f"{OUT}/att-id-1.png")
    pg.fill("#tc-in", "2100 7012 3456 78"); pg.click("#tc-save"); pg.wait_for_selector(".tc-num"); pg.screenshot(path=f"{OUT}/att-id-2.png")
    print("card:", pg.inner_text(".tc-num"))
    # The instructor, on a phone: Take Attendance.
    ctx = b.new_context(viewport={"width": 1360, "height": 900}, permissions=["camera"]); block_cdns(ctx); me = ctx.new_page(); me.on("pageerror", lambda e: errs.append(str(e)))
    me.on("response", lambda r: errs.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    srv.sign_in(me, hash="#/csc258/f26/evaluations"); me.wait_for_timeout(2500)
    me.wait_for_selector("[data-lt-tool='grades'] .erow"); me.screenshot(path=f"{OUT}/att-0-list.png", full_page=True); me.locator("[data-lt-tool='grades'] .erow", has_text="Midterm").first.locator("[data-act=attend]").click(); me.wait_for_selector("#at-note"); me.wait_for_timeout(300); me.screenshot(path=f"{OUT}/att-1-overview.png")
    print("hash:", me.evaluate("location.hash"))
    me.fill("#at-note", "BA 1170, last names A–L"); me.wait_for_timeout(7000); print("note kept:", me.locator("#at-note").count() and me.input_value("#at-note")); me.screenshot(path=f"{OUT}/att-2-note.png")
    me.click("#at-go"); me.wait_for_selector(".at-panel.ask", timeout=20000); me.screenshot(path=f"{OUT}/att-3-ask.png")
    print("ask:", me.inner_text(".at-panel.ask h3"))
    me.click(".at-panel [data-yes]"); me.wait_for_selector(".at-panel.ok"); me.screenshot(path=f"{OUT}/att-4-ok.png")
    # The same card again, after a moment: already in.
    me.wait_for_selector(".at-panel.bad", timeout=20000); me.screenshot(path=f"{OUT}/att-5-already.png"); print("again:", me.inner_text(".at-panel.bad .at-why"))
    me.click(".at-panel [data-next]")
    # The editor redrawing (it takes the section out and puts it back): the camera keeps going.
    me.evaluate("() => { const s = document.querySelector('.at-sec'), p = s.parentNode; s.remove(); p.appendChild(s); }"); me.wait_for_timeout(800)
    print("video playing after redraw:", me.evaluate("() => !document.querySelector('#at-video').paused"))
    me.locator(".at-sec").scroll_into_view_if_needed(); me.screenshot(path=f"{OUT}/att-scan-in-editor.png")
    b2 = browser("zoe"); c2 = b2.new_context(viewport={"width": 420, "height": 860}, permissions=["camera"]); block_cdns(c2); ta = c2.new_page(); ta.on("pageerror", lambda e: errs.append(str(e)))
    srv.sign_in(ta, email="sam@utoronto.ca", hash="#/~chandra/csc258/f26/attendance/mt"); ta.wait_for_selector("#at-note"); ta.fill("#at-note", "BA 1180"); ta.click("#at-go")
    ta.wait_for_selector(".at-panel.find", timeout=20000); ta.fill("#at-q", "ng"); ta.wait_for_selector(".at-hit"); ta.screenshot(path=f"{OUT}/att-6-unknown.png")
    ta.click(".at-hit"); ta.wait_for_selector(".at-panel.ok"); print("ta:", ta.inner_text(".at-panel.ok"))
    ta.wait_for_timeout(1500); ta.click("#at-hand"); ta.fill("#at-q", "cast"); ta.wait_for_selector(".at-hit"); ta.click(".at-hit"); ta.wait_for_selector(".at-panel.bad"); print("hand dup:", ta.inner_text(".at-panel.bad .at-why"))
    ta.click("#at-stop"); ta.wait_for_selector("#at-note"); ta.wait_for_timeout(500)
    me.click("#at-stop"); me.wait_for_selector(".at-sess"); me.wait_for_timeout(800); me.screenshot(path=f"{OUT}/att-7-sessions.png", full_page=True)
    print("total:", me.inner_text("#at-meta"), "| trash:", me.locator(".at-del").count())
    me.locator(".at-del").first.click(); me.wait_for_timeout(300); me.locator(".at-sess").screenshot(path=f"{OUT}/att-del-armed.png"); me.locator(".at-del.armed").click(); me.wait_for_timeout(1500)
    print("after delete:", me.inner_text("#at-meta"), "| sessions:", me.locator(".at-row").count()); me.screenshot(path=f"{OUT}/att-del-after.png")
    print("errors:", errs)
