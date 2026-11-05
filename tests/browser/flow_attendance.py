"""Attendance at a test, end to end against the real server (harness.Server), with a fake camera.

1. The owner opens the Midterm in Evaluations, writes a session note and takes attendance. The camera
   (a made-up printed student card, played as a fake video) is read in the browser (OCR) and matched to
   the class list: they confirm it's Maya, and the same card read again says she's already in.
2. A TA, on a phone, starts their own session and enters Zoë by hand (the best match for "ng"); Maya,
   already in, can't be entered twice.
3. Back in the owner's editor: both sessions and their counts; deleting one takes its students out.

    python tests/browser/flow_attendance.py
Asserts as it goes; screenshots in shots/.
"""
import json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
from playwright.sync_api import sync_playwright
from harness import Server, OUT, block_cdns

MAYA = {"num": "1009876543", "first": "Maya", "last": "Castillo", "f": {"email": "maya@mail.utoronto.ca"}}
ZOE = {"num": "1001234567", "first": "Zoë", "last": "Ng", "f": {"email": "zoe@mail.utoronto.ca"}}


def book():
    with open(os.path.join(ROOT, "sample-data/demo-courses-private/csc258/f26/grades.json"), encoding="utf-8") as f:
        b = json.load(f)
    b["fields"] = {"idLabel": "Student number", "custom": [{"id": "email", "label": "Email"}]}
    b["students"] = [MAYA, ZOE]
    for e in b["evals"]:
        if e["id"] == "mt":
            e["title"] = "Midterm Test"
    return b


def card_video(p, path):
    """A printed student card (name and number, as the real ones have), as an MJPEG file Chromium can use
    for a fake camera: the same JPEG frame, over and over."""
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 640, "height": 480})
    pg.set_content(f"""<body style="margin:0;background:#fff;display:flex;align-items:center;justify-content:center;height:480px">
      <div style="font:600 34px Arial,sans-serif;line-height:1.5;color:#000;padding:30px;border:3px solid #000;border-radius:16px">
        STUDENT CARD<br>{MAYA['first']} {MAYA['last']}<br>{MAYA['num']}</div></body>""")
    frame = pg.screenshot(type="jpeg", quality=90); b.close()
    with open(path, "wb") as f:
        for _ in range(60):
            f.write(frame)


def main():
    errors = []
    video = os.path.join(tempfile.mkdtemp(prefix="lectern-cam-"), "card.mjpeg")
    with Server() as srv, sync_playwright() as p:
        card_video(p, video)
        owner = srv.account()
        sam = srv.account(email="sam@utoronto.ca", name="Sam Patel", handle="sam", admin=False)
        srv.user = owner
        from server import db
        db.run("INSERT INTO members (owner_id, offering, user_id, role, added) VALUES (?, 'csc258/f26', ?, 'ta', 0)", (owner["id"], sam["id"]))
        with open(os.path.join(ROOT, "sample-data/demo-courses/csc258/f26/course.json"), encoding="utf-8") as f:
            srv.put("pub", {"csc258/f26/course.json": f.read()})
        srv.put("priv", {"csc258/f26/grades.json": json.dumps(book())})
        b = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={video}"])

        # 1. The owner takes attendance with the camera.
        ctx = b.new_context(viewport={"width": 1360, "height": 900}, permissions=["camera"]); block_cdns(ctx)
        me = ctx.new_page(); me.on("pageerror", lambda e: errors.append(f"owner: {e}"))
        srv.sign_in(me, hash="#/csc258/f26/evaluations")
        me.wait_for_selector("[data-lt-tool='grades'] .erow")
        me.locator("[data-lt-tool='grades'] .erow", has_text="Midterm").first.click(); me.wait_for_selector("#at-note")
        me.fill("#at-note", "BA 1170, last names A-L"); me.wait_for_timeout(1500)
        assert me.input_value("#at-note") == "BA 1170, last names A-L", "the note stays while it's written"
        me.screenshot(path=f"{OUT}/att-1-overview.png")
        me.click("#at-go"); me.wait_for_selector(".at-panel.ask", timeout=60000)   # reading the card (OCR) takes a moment
        who = me.inner_text(".at-panel.ask h3"); print("1 the camera read:", who); me.screenshot(path=f"{OUT}/att-2-ask.png")
        assert "Castillo" in who, who
        me.click(".at-panel [data-yes]"); me.wait_for_selector(".at-panel.ok")
        me.wait_for_selector(".at-panel.bad", timeout=30000)   # the same card, read again
        again = me.inner_text(".at-panel.bad .at-why"); print("  read again:", again); me.screenshot(path=f"{OUT}/att-3-already.png")
        assert "already" in again.lower(), again
        me.click(".at-panel [data-next]")

        # 2. A TA, on a phone, enters a student by hand.
        c2 = b.new_context(viewport={"width": 420, "height": 860}, permissions=["camera"]); block_cdns(c2)
        ta = c2.new_page(); ta.on("pageerror", lambda e: errors.append(f"ta: {e}"))
        srv.sign_in(ta, email="sam@utoronto.ca", hash="#/~chandra/csc258/f26/attendance/mt")
        ta.wait_for_selector("#at-note"); ta.fill("#at-note", "BA 1180"); ta.click("#at-go"); ta.wait_for_timeout(1500)
        ta.click("#at-hand"); ta.fill("#at-q", "ng"); ta.wait_for_selector("#at-best h3")
        assert "Ng" in ta.inner_text("#at-best"), ta.inner_text("#at-best")
        ta.keyboard.press("Enter"); ta.wait_for_selector(".at-panel.ok"); ta.screenshot(path=f"{OUT}/att-4-hand.png")
        print("2 the TA entered:", ta.inner_text(".at-panel.ok").replace("\n", " / "))
        ta.wait_for_timeout(1500); ta.click("#at-hand"); ta.fill("#at-q", "cast"); ta.wait_for_selector("#at-best h3")
        assert ta.is_disabled(".at-panel [data-yes]"), "Maya's already in: no second entry"
        ta.click(".at-panel [data-cancel]")
        ta.locator("#lt-path button", has_text="Midterm").first.click(); ta.wait_for_selector("#at-note")   # leaving ends the TA's session

        # 3. The owner sees both sessions, then deletes one.
        me.go_back(); me.wait_for_selector(".at-sess"); me.wait_for_timeout(1500)
        rows = me.locator(".at-row").count(); total = me.inner_text("#at-meta")
        print("3 sessions:", rows, "| total:", total); me.screenshot(path=f"{OUT}/att-5-sessions.png", full_page=True)
        assert rows == 2, rows
        me.locator(".at-del").first.click(); me.wait_for_selector(".lt-modal [data-yes]"); me.click(".lt-modal [data-yes]"); me.wait_for_timeout(1500)
        print("  after deleting one:", me.locator(".at-row").count(), "|", me.inner_text("#at-meta")); me.screenshot(path=f"{OUT}/att-6-deleted.png")
        assert me.locator(".at-row").count() == 1 and me.inner_text("#at-meta") != total
        b.close()
    assert not errors, errors
    print("flow_attendance: OK")


if __name__ == "__main__":
    main()
