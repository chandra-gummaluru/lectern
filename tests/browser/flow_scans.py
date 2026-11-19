"""Print and Scan, end to end in a browser against the real server (harness.Server), on the demo course.

1. The owner loads the demo course, opens its midterm in the Exam Builder and clicks Print and Scan.
2. They download the student copy (kept as the printed copy); two students "write" it (test_autograde's pen
   on the printed pages, then "scanned"), and the scan is uploaded and marked.
3. They open a booklet, mark its written answers and confirm what the grader wasn't sure of, then send the
   marks to the gradebook (replacing the demo's own Test 1 marks).

    python tests/browser/flow_scans.py
Asserts as it goes; screenshots in shots/.
"""
import io, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
from playwright.sync_api import sync_playwright
from harness import Server, OUT, block_cdns


def answers(exam):
    """What two students write: everything right, and the first two questions wrong."""
    from server.autograde import grade
    import test_autograde as T
    L = {label: n for label, n in grade.leaves(exam, 0)}
    right = lambda n: next(o["id"] for o in n["options"] if o["correct"])
    comp = lambda n, kind: next(k for k, c in n["comps"].items() if c["kind"] == kind)
    good = {f"{L['1']['id']}.{right(L['1'])}": "fill", f"{L['2']['id']}:T": "fill",
            **{f"{L['3']['id']}.{o['id']}": "tick" for o in L["3"]["options"] if o["correct"]},
            f"{L['4']['id']}.{comp(L['4'], 'num')}": "84", f"{L['5']['id']}.{comp(L['5'], 'num')}": "0.375",
            **T.cells(f"{L['6']['id']}.{comp(L['6'], 'cells')}", "1101"),
            f"{L['7']['id']}.{comp(L['7'], 'frac')}:n": "3", f"{L['7']['id']}.{comp(L['7'], 'frac')}:d": "4",
            f"{L['9(a)']['id']}.{right(L['9(a)'])}": "fill", f"{L['9(b)']['id']}:T": "fill", f"{L['9(c)']['id']}.{comp(L['9(c)'], 'num')}": "30",
            f"{L['10']['id']}.{comp(L['10'], 'num')}": "10"}
    wrong = {k: v for k, v in good.items() if not k.startswith(L["1"]["id"]) and not k.startswith(L["2"]["id"])}
    wrong[f"{L['1']['id']}.{L['1']['options'][0]['id']}"] = "fill"
    wrong[f"{L['2']['id']}:F"] = "fill"
    return [good, wrong]


def scan_pdf(printed, people, ans, path):
    import numpy as np
    from PIL import Image
    import test_autograde as T
    from server.autograde import layout
    src = path + ".printed.pdf"
    open(src, "wb").write(printed)
    t = layout.load_template(src)
    rng = np.random.default_rng(5)
    pages = []
    for k, (who, a) in enumerate(zip(people, ans)):
        pages += [T.scanned(img, rng) for img in T.booklet(t, who, a, T.Pen(k + 11), rng)]
    ims = [Image.fromarray(x) for x in pages]
    ims[0].save(path, format="PDF", save_all=True, append_images=ims[1:], resolution=200)


def main():
    errors = []
    tmp = tempfile.mkdtemp(prefix="lectern-scans-")
    with Server() as srv, sync_playwright() as p:
        owner = srv.account()
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900}); block_cdns(ctx)
        me = ctx.new_page(); me.on("pageerror", lambda e: errors.append(f"owner: {e}"))
        srv.sign_in(me)
        d = me.evaluate("""() => fetch('/api/offerings/demo', {method: 'POST', headers: {'X-Lectern': '1'}}).then(r => r.json())""")
        t = d["term"]; off = f"demo101/{t}"
        print("1 the demo course:", off)

        # From the gradebook: Test 1's Scripts and Scans (its test script, then its scans) (no Open button in its head).
        G = "[data-lt-tool='grades'] "
        me.evaluate(f"location.hash = '#/{off}/evaluations'"); me.evaluate("location.reload()")
        me.wait_for_selector(G + ".erow[data-id='mt']", timeout=20000); me.click(G + ".erow[data-id='mt']")
        me.wait_for_selector(G + ".editor[data-eval='mt'] [data-scan-slot] #sc-file", state="attached", timeout=15000)
        me.locator(G + ".editor[data-eval='mt'] [data-scan-slot]").scroll_into_view_if_needed(); me.screenshot(path=f"{OUT}/scan-00-scripts.png")
        top = [" ".join(x.split()) for x in me.locator(G + ".editor[data-eval='mt'] .sc-top > *").all_inner_texts()]
        assert top == ["Edit Test Script", "Upload Scans"], top                        # two buttons: the script, Upload Scans
        sc = me.inner_text(G + ".editor[data-eval='mt'] [data-scan-slot]")
        assert "Upload whole booklets" not in sc and "printed" not in sc, sc              # no text above the card
        assert not me.query_selector(G + ".editor[data-eval='mt'] [data-doc]"), "its PDFs are in the Exam Builder"
        assert "Scans" not in [x.strip().title() for x in me.locator(G + ".editor[data-eval='mt'] h3.ed-sec").all_inner_texts()], "no Scans section of its own"
        assert me.locator(G + ".editor[data-eval='mt'] h3.ed-sec", has_text="Scripts and Scans").count() == 1
        assert "Upload Scans" in sc, sc
        assert not me.query_selector(G + "[data-act='ev-scans']"), "no Print and Scan button: the Scans are right there"

        # The Exam Builder's Print and Scan: the test is linked to Test 1, so it opens Test 1's page, at its Scans.
        me.evaluate(f"location.hash = '#/{off}/exams/midterm'"); me.evaluate("location.reload()")
        me.wait_for_selector("#tb-scans", timeout=20000)
        me.wait_for_timeout(800)
        assert "Which of these numbers is prime" in me.inner_text("[data-lt-tool='exams']"), "the demo's midterm is open"
        me.screenshot(path=f"{OUT}/scan-0-builder.png")
        tb = [x.strip() for x in me.locator("[data-lt-tool='exams'] #tb-right button").all_inner_texts()]
        assert tb == ["Student Copy", "Answer Key", "Marking Scheme", "Print and Scan"], tb

        # 2. The student copy, from the Exam Builder (kept as printed), written on by two students, scanned and uploaded.
        opened = []
        for doc in ("student", "key", "guide"):
            me.evaluate("window.__opened = []; window.open = u => { window.__opened.push(u); return null; }; 0")
            me.click(f"#tb-right [data-doc='{doc}']")
            if doc == "student":          # marked from scans: numbered booklets, or one copy to photocopy
                me.wait_for_selector("#nb-go:not([disabled])", timeout=10000)
                n = len([s_ for s_ in json.loads(srv.text("priv", f"{off}/grades.json"))["students"] if not s_.get("dropped")])
                assert me.input_value("#nb-n") == str(n) and me.inner_text("#nb-range") == f"Booklets 1 to {n}.", me.inner_text("#nb-range")
                me.screenshot(path=f"{OUT}/scan-0b-numbered.png")
                me.fill("#nb-n", "2"); assert me.inner_text("#nb-range") == "Booklets 1 to 2."
                me.click("#nb-go"); me.wait_for_function("window.__opened.length > 0", timeout=5000)
                url = me.evaluate("window.__opened[0]"); assert "booklets=2" in url and "print=1" in url, url
                nb = ctx.request.get(srv.base.rstrip("/") + url); assert nb.ok and nb.body()[:4] == b"%PDF"
                me.evaluate("window.__opened = []; 0")
                me.click(f"#tb-right [data-doc='{doc}']"); me.wait_for_selector("#nb-go:not([disabled])", timeout=10000)
                assert me.inner_text("#nb-range") == f"Booklets 3 to {n + 2}.", "carries on from the last printed"
                me.click("#nb-one")                                    # the rest of this walkthrough: one copy
            me.wait_for_function("window.__opened.length > 0", timeout=5000); opened.append(me.evaluate("window.__opened[0]"))
        assert all("/api/scans/pdf" in u and "exam=midterm" in u for u in opened), opened
        me.click("#tb-scans")
        me.wait_for_selector(G + ".editor[data-eval='mt'] [data-scan-slot] #sc-file", state="attached", timeout=15000)
        me.screenshot(path=f"{OUT}/scan-1-page.png", full_page=True)
        assert "print=1" in opened[0] and "print=1" not in opened[1], opened
        for href in opened[1:]:
            k = ctx.request.get(srv.base.rstrip("/") + href); assert k.ok and k.body()[:4] == b"%PDF"
        r = ctx.request.get(srv.base.rstrip("/") + opened[0])
        assert r.ok and r.body()[:4] == b"%PDF", r.status
        exam = json.loads(srv.text("priv", f"{off}/midterm/exam.json"))
        book = json.loads(srv.text("priv", f"{off}/grades.json"))
        people = book["students"][6:8]
        scan = os.path.join(tmp, "Class scan.pdf")
        scan_pdf(r.body(), people, answers(exam), scan)
        me.evaluate("location.reload()"); me.wait_for_selector(G + ".erow[data-id='mt']", timeout=20000); me.click(G + ".erow[data-id='mt']")
        me.wait_for_selector(G + "[data-scan-slot] #sc-file", state="attached", timeout=20000)
        assert json.loads(srv.text("priv", f"{off}/grades.json")) and "printed" not in me.inner_text(G + "[data-scan-slot]")
        greyed = me.locator(G + "[data-scan-slot] .sc-qlist.off [data-gq]")              # before any scans: listed, greyed out
        assert greyed.count() == 12 and greyed.first.is_disabled() and "No scans yet" in greyed.first.inner_text()
        me.set_input_files(G + "[data-scan-slot] #sc-file", scan)             # read as it comes in: no Mark button
        me.wait_for_selector(G + "[data-scan-slot] .sc-filelist", timeout=30000)
        assert not me.evaluate("window.Lectern.tools.grades.api.state().unsaved"), "uploading a scan doesn't change the gradebook"
        print("2 uploaded:", me.inner_text(G + "[data-scan-slot] .sc-filelist summary"))
        assert not me.query_selector(G + "[data-scan-slot] #sc-mark")
        me.wait_for_selector(G + "[data-scan-slot] .sc-scan-row .sc-spin", timeout=10000)
        me.locator(G + "[data-scan-slot]").scroll_into_view_if_needed(); me.screenshot(path=f"{OUT}/scan-2-marking.png")
        me.wait_for_selector(G + "[data-scan-slot] .sc-qlist:not(.off) [data-gq]", timeout=180000)       # read: its questions open
        me.wait_for_selector(G + "[data-scan-slot] .sc-scan-row .sc-spin", state="detached", timeout=180000)
        card = " ".join(me.inner_text(G + "[data-scan-slot] .sc-scan-row").split())
        n = len([s_ for s_ in book["students"] if not s_.get("dropped")])
        assert card == f"Booklets Scanned 2 / {n} scanned", card                     # the list's first row
        assert f"of the {n} students in the class" in me.get_attribute(G + "[data-scan-slot] .sc-scan-row .dc-t-meta", "title")
        print("  meter:", card.replace("\n", " | "))
        assert me.is_disabled(G + "[data-scan-slot] #sc-email"), "emailed once every booklet is graded"
        top = [" ".join(x.split()) for x in me.locator(G + "[data-scan-slot] .sc-top > *").all_inner_texts()]
        assert top == ["Edit Test Script", "Upload Scans", "Email Booklets"], top
        assert me.inner_text(G + "[data-scan-slot] .sc-qlist .dc-title").strip().lower() == "grading"   # not just questions
        mrow = " ".join(me.inner_text(G + "[data-scan-slot] .sc-qlist [data-match]").split())
        assert mrow == "Booklet Matching 0 / 2 matched", mrow                         # first in the list, like a question
        me.click(G + "[data-scan-slot] [data-match]"); me.wait_for_selector(".sc-book .sc-mcard")   # one booklet at a time
        assert me.inner_text(".sc-book .gr-kind").lower() == "booklet matching" and me.locator(".sc-mcard").count() == 1
        assert me.inner_text(".sc-book h2").startswith("Booklet 1") and "To Match" not in me.inner_text(".sc-book")
        me.screenshot(path=f"{OUT}/scan-2c-matching.png", full_page=True)
        me.select_option("#sc-mwho", people[0]["num"]); me.click("[data-mok]")                 # Okay: the next one
        me.wait_for_selector(".sc-book h2:has-text('Booklet 2')", timeout=10000)
        assert me.evaluate(f"document.querySelector('#sc-mwho option[value=\"{people[0]['num']}\"]').disabled"), "taken: greyed out"
        me.click("[data-mdone]"); me.wait_for_selector(G + "[data-scan-slot] .sc-scan-row")
        me.wait_for_selector(G + "[data-scan-slot] .sc-qlist [data-match]:has-text('1 / 2 matched')", timeout=10000)
        me.locator(G + "[data-scan-slot]").scroll_into_view_if_needed(); me.screenshot(path=f"{OUT}/scan-2b-marked.png")
        rows = {r_.get_attribute("data-gq"): r_.inner_text().replace("\n", " ") for r_ in me.locator(G + "[data-scan-slot] .sc-qlist [data-gq]").all()}
        print("  questions:", list(rows.values())[:4])
        assert rows["4"].endswith("1 / 2 read") and rows["8"].endswith("0 / 2 marked") and rows["1"].endswith("2 / 2 read"), rows
        assert not me.query_selector(G + "[data-scan-slot] #sc-fix, " + G + "[data-scan-slot] .lx-sec, " + G + "[data-scan-slot] [data-by]"), "no Fix Scans bar, Gradebook, Marked Booklets or By Booklet in it"
        h = me.evaluate(f"document.querySelector(`{G}[data-scan-slot] .sc-qlist .dc-threads`).clientHeight")
        assert h <= 340, ("the list scrolls in its own box", h)

        # A question the computer marks: check it against the scans, the answers it wasn't sure how to read, one at a time.
        me.click(G + "[data-scan-slot] [data-gq='4']"); me.wait_for_selector(".sc-book .gr-kind")
        assert me.inner_text(".sc-book .gr-kind").lower().startswith("marked by the computer"), me.inner_text(".sc-book .gr-kind")
        assert me.inner_text(".sc-book h2").startswith("Question 4") and me.locator(".sc-q").count() == 1, "one answer at a time"
        assert not me.locator(".sc-q .sc-qt:visible").count(), "no name: just the reading"
        me.screenshot(path=f"{OUT}/scan-3a-fix.png", full_page=True)
        copy = me.locator(".sc-q .dz-field input").first                  # it read 64: fix it to 84, then Okay
        copy.fill("84"); me.click("[data-fixok]"); me.wait_for_timeout(900)
        assert not me.locator(".sc-q").count() and me.locator(".sc-fixnext [data-fixgo]").count(), me.inner_text(".sc-book")
        print("  question 4 checked:", me.inner_text(".sc-fixnext"))
        me.click("[data-fixall]"); me.wait_for_timeout(300)                # every answer, if you ask
        assert me.locator(".sc-q").count() == 2, "every booklet's answer to question 4"
        me.locator("#lt-path button", has_text="Test 1").first.click(); me.wait_for_selector(G + "[data-scan-slot] [data-gq='10']")
        me.click(G + "[data-scan-slot] [data-gq='10']"); me.wait_for_selector(".sc-book [data-fixok]")
        me.click("[data-fixok]"); me.wait_for_timeout(300)                # a word nobody has typed yet: Okay says so
        assert me.locator(".sc-q").count() == 1
        print("  question 10 waits for the word")

        # A question marked by hand: the grader, every booklet's answer; the first student's gets full marks there.
        me.locator("#lt-path button", has_text="Test 1").first.click(); me.wait_for_selector(G + "[data-scan-slot] [data-gq='8']")
        me.locator(G + "[data-scan-slot] [data-gq='8']").click(); me.wait_for_selector(".sc-book .sc-q")
        assert "/questions/8" in me.evaluate("location.hash") and me.inner_text(".sc-book .gr-kind").lower() == "marked by hand"
        me.screenshot(path=f"{OUT}/scan-3b-question.png", full_page=True)
        print("  question 8:", me.inner_text(".sc-book .lt-req-meta"), "|", me.locator(".sc-q").count(), "answers to look at")
        assert me.locator(".sc-q").count() == 2
        me.locator(".sc-q").first.locator("[data-full]").click(); me.wait_for_timeout(600)
        assert me.locator(".sc-q").count() == 1, "the marked one leaves To Look At"
        me.click("[data-qshow='all']"); me.wait_for_timeout(200)
        assert me.locator(".sc-q").count() == 2 and me.locator(".sc-q.st-done").count() == 1
        me.locator(".sc-qwho").first.click(); me.wait_for_selector(".sc-book .sc-cover, .sc-book .sc-pick")
        assert "/scans/midterm/" in me.evaluate("location.hash") and "/questions/" not in me.evaluate("location.hash")

        # 3. Each booklet: mark what's left, then send.
        for n in (1, 2):
            me.evaluate(f"location.hash = '#/{off}/scans/midterm/{n}'")
            me.wait_for_selector(".sc-book .sc-q")
            if n == 1:
                me.screenshot(path=f"{OUT}/scan-4-booklet.png", full_page=True)
            print(f"3 booklet {n}:", me.inner_text(".sc-book h2"), "|", me.inner_text(".sc-book .lt-req-meta"))
            if "Unmatched" in me.inner_text(".sc-book h2"):   # not sure whose it is: the cover says, and they pick
                assert "XXXXXXXXXX" in me.inner_text(".sc-book .lt-req-meta")
                assert not me.locator("[data-cand]").count(), "no suggested students: just the dropdown"
                me.select_option("#sc-who", people[n - 1]["num"])
                me.wait_for_timeout(500)
                print("  whose: chosen", me.inner_text(".sc-book h2"))
            assert people[n - 1]["last"] in me.inner_text(".sc-book h2")
            me.screenshot(path=f"{OUT}/scan-4i-unsure-{n}.png", full_page=True)
            if n == 1:          # Question 8 by its rubric: each comment given sets the score (from zero); a note for the student
                q8 = lambda: me.locator(".sc-q[data-q='8']")
                for k in range(q8().locator("[data-rub]").count()):
                    q8().locator("[data-rub]").nth(k).click(); me.wait_for_timeout(500)
                assert q8().locator("[data-rub][aria-pressed='true']").count() == 2 and q8().locator(".sc-qh .sc-score input").input_value() == "3"
                q8().locator("[data-addn]").click(); me.wait_for_selector(".sc-q[data-q='8'] .sc-cnote-in")
                q8().locator(".sc-cnote-in").fill("Clear and complete."); q8().locator(".sc-cnote-in").press("Enter"); me.wait_for_timeout(400)
                q8().locator("[data-addc]").click(); me.wait_for_selector(".sc-q[data-q='8'] .sc-nd")
                q8().locator(".sc-nd").fill("0"); q8().locator(".sc-nt").fill("Good use of algebra")
                q8().locator("[data-csave]").click(); me.wait_for_timeout(900)
                assert q8().locator("[data-rub]").count() == 3 and q8().locator(".sc-qh .sc-score input").input_value() == "3"
                q8().locator(".sc-hist summary").click()                       # its edit history: who changed what, when
                hist = q8().locator(".sc-hist li").all_inner_texts()
                assert len(hist) >= 4 and "Gave +2 Adds them" in " ".join(hist) and "Note:" in " ".join(hist), hist
                q8().scroll_into_view_if_needed()
                me.screenshot(path=f"{OUT}/scan-4d-comments.png", full_page=True)
                pdf = me.request.get(srv.base.rstrip("/") + me.get_attribute(".sc-book a[href*='annotated']", "href"))
                assert pdf.ok and pdf.body()[:4] == b"%PDF"
                open(f"{OUT}/scan-4e-marked.pdf", "wb").write(pdf.body())
            if n == 2:          # picking their answer on the scan, and the two views of it
                assert not me.locator(".sc-q[data-q='1']").count(), "read with confidence: hidden until asked for"
                me.click("[data-sure]"); me.wait_for_selector(".sc-q[data-q='1']")
                q1 = lambda: me.locator(".sc-q[data-q='1']")                  # a wrong bubble; a person says they chose the right one
                assert q1().locator("[data-hot]").count() == 4 and q1().locator("[data-hot]:not(.right)[aria-pressed='true']").count() == 1
                q1().locator("[data-hot].right").click(); me.wait_for_timeout(700)           # two filled: wrong
                assert q1().locator("[data-hot][aria-pressed='true']").count() == 2 and q1().locator(".sc-qh .sc-score input").input_value() == "0"
                q1().locator("[data-hot]:not(.right)[aria-pressed='true']").click(); me.wait_for_timeout(700)   # the wrong one emptied
                assert q1().locator("[data-hot].right[aria-pressed='true']").count() == 1 and q1().locator(".sc-qh .sc-score input").input_value() == "2"
                assert not q1().locator(".sc-qh .sc-score").is_visible() and me.locator(".sc-q[data-q='8'] .sc-qh .sc-score").is_visible()   # scores: only where a person marks
                q1().screenshot(path=f"{OUT}/scan-4g-picked.png")
                q1().locator("[data-undo]").click(); me.wait_for_timeout(700)
                q2 = me.locator(".sc-q[data-q='2']")
                assert not q2.locator(".sc-cm, .sc-cap").count(), "a choice question: no comments, no note, no instructions"
                q2.screenshot(path=f"{OUT}/scan-4f-grader.png")
                assert me.locator(".lx-sec", has_text="Check What Was Read").count() and me.locator(".lx-sec", has_text="Mark by Hand").count()
                assert not me.locator("[data-view]").count()                     # one view: no Marked tab
            for _ in range(14):
                left = me.locator(".sc-q:not(.st-auto):not(.st-done)")
                if not left.count():
                    break
                q = left.first
                label = q.get_attribute("data-q")
                right_ = {"4": ["84"], "5": ["0.375"], "6": list("1101"), "7": ["3", "4"], "9(c)": ["30"]}
                if q.locator(".sc-rr[data-yes]").count():   # "Is this what it says?"
                    if n == 1 and label in right_:             # no: they type what it says (the right answer) in the copy
                        boxes = q.locator(":scope > .sc-pair .dz-field input")
                        for k, v in enumerate(right_[label]):
                            boxes.nth(k).fill(v)
                        boxes.nth(len(right_[label]) - 1).press("Enter")
                    else:
                        q.locator(".sc-rr[data-yes]").click()
                elif q.locator("[data-keep]").count():      # "Is there working worth part marks?" no
                    q.locator("[data-keep]").click()
                elif q.locator("[data-hotok]").count():     # "Which is their answer?": the bubbles on the scan
                    if n == 1:                              # the first student got it right: click the right ones
                        for _ in range(6):
                            off_ = q.locator("[data-hot].right[aria-pressed='false'], [data-hot]:not(.right)[aria-pressed='true']")
                            if not off_.count() or not q.locator("[data-hotok]").count():
                                break
                            off_.first.click(); me.wait_for_timeout(500)
                        if q.locator("[data-hotok]").count():
                            q.locator("[data-hotok]").click()
                    else:
                        q.locator("[data-hotok]").click()
                elif q.locator(".sc-bl [data-byes]").count():   # a blank of several the grader wasn't sure of: yes
                    q.locator(".sc-bl [data-byes]").first.click()
                elif q.locator(".sc-bl.st-manual .dz-field input").count():   # a blank of several with a word in it: they type just that one
                    f = q.locator(".sc-bl.st-manual .dz-field input").first
                    f.fill("Ottawa" if n == 1 else "Toronto"); f.press("Enter")
                    if n == 1:
                        me.screenshot(path=f"{OUT}/scan-4c-blanks.png", full_page=True)
                elif n == 1 or label == "8":
                    q.locator("[data-full]").click()
                else:
                    q.locator("[data-zero]").click()
                me.wait_for_timeout(450)
            me.wait_for_function("document.querySelector('.sc-book .lt-req-meta').textContent.includes('finished')")
        typed = me.locator(".sc-q", has_text="typed")
        print("  typed readings:", typed.count())
        me.screenshot(path=f"{OUT}/scan-5-finished.png", full_page=True)
        me.locator("#lt-path button", has_text="Test 1").first.click()         # back to Test 1: the marks go in by themselves,
        me.wait_for_selector(G + "[data-scan-slot] #sc-replace", timeout=15000)   # but not over the different ones there
        print("  differ:", me.inner_text(G + "[data-scan-slot] .sc-looks"))
        assert me.inner_text(G + "[data-scan-slot] #sc-email") == "Email 2 Booklets" and not me.is_disabled(G + "[data-scan-slot] #sc-email")
        me.click(G + "[data-scan-slot] #sc-replace")
        me.wait_for_selector(".lt-modal [data-yes]")
        print("  asks:", me.inner_text(".lt-modal h2"))
        me.click(".lt-modal [data-yes]")
        me.wait_for_timeout(1500)
        me.locator(G + "[data-scan-slot]").scroll_into_view_if_needed(); me.screenshot(path=f"{OUT}/scan-6-sent.png")
        book = json.loads(srv.text("priv", f"{off}/grades.json"))
        got = {s["num"]: book["marks"][s["num"]]["mt"] for s in people}
        print("  in the gradebook:", got)
        assert got[people[0]["num"]] == {"pts": 22}, got
        assert got[people[1]["num"]]["pts"] < 22
        shown = me.evaluate(f"window.Lectern.tools.grades.api.book().marks[{json.dumps(people[0]['num'])}].mt")
        assert shown == {"pts": 22}, ("the gradebook open here shows the marks just sent", shown)
        b.close()
    assert not errors, errors
    print("flow_scans: OK")


if __name__ == "__main__":
    main()
