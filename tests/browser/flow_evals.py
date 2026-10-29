"""Grades: each evaluation's type, label and date, and names that follow the label.
Run with the server going (python app.py), then: python tests/browser/flow_evals.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE

def ev(i, name, short, w):
    return {"id": f"e{i}", "name": name, "short": short, "total": 10, "weight": w, "makeupFor": None, "missed": {"mode": "zero", "to": [], "split": "custom"}}

OLD = {"format": "grade-builder/1", "course": {"code": "CSC258", "term": "Fall 2026"},
       "evals": [ev(1, "Assignment 1", "A1", 10), ev(2, "Assignment 2", "A2", 10), ev(3, "Lab 1: Gates", "L1", 5), ev(4, "Midterm", "MT", 30), ev(5, "Final Exam", "FE", 45)],
       "groups": [], "students": [], "marks": {}, "overrides": {}}

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(OLD)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png", full_page=True)
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/gradebook"); page.reload(); page.wait_for_timeout(2500)
        G = "[data-lt-tool='grades'] "
        page.evaluate(r"location.hash = location.hash.replace(/\/(grades|gradebook)$/, '/evaluations')"); page.wait_for_timeout(1200); page.wait_for_timeout(400); shot("60-evals-list")
        rows = page.eval_on_selector_all(G + ".erow", "els => els.map(e => e.querySelector('h3').textContent + ' | ' + (e.querySelector('.er-when')||{}).textContent)")
        print("migrated:", rows)
        # A new evaluation: same type and label as the last one (Final Exam, a Test)
        page.click(G + "[data-act='evadd']"); page.wait_for_timeout(500)
        print("new:", page.inner_text(G + ".ed-head h2"), "| path:", page.inner_text("#lt-path").replace("\n", " "))
        lab = page.locator(G + "input[data-f='label']"); lab.fill("Lab"); page.wait_for_timeout(300)
        print("after label Lab:", page.inner_text(G + ".ed-head h2"), "| help:", page.inner_text(G + "#name-help"))
        page.fill(G + "input[data-f='title']", "Flip-flops"); page.wait_for_timeout(200)
        page.click(G + "button[data-ed='etype'][data-v='assignment']"); page.wait_for_timeout(300)
        page.click(G + "[data-ed='when']"); page.wait_for_timeout(300)
        page.screenshot(path=f"{OUT}/64-when-picker.png")
        while not page.query_selector(G + ".when-pop [data-day='2026-10-30']"): page.click(G + ".when-pop [data-w='next']")
        page.click(G + ".when-pop [data-day='2026-10-30']"); page.wait_for_timeout(200)
        print("picked:", page.inner_text(G + "[data-ed='when']"))
        page.fill(G + "#wp-t", "17:00"); page.keyboard.press("Enter"); page.wait_for_timeout(300)
        print("typed 17:00:", page.inner_text(G + "[data-ed='when']"))
        page.click(G + "[data-ed='when']"); page.wait_for_timeout(200); page.fill(G + "#wp-t", ""); page.wait_for_timeout(200); page.screenshot(path=f"{OUT}/65-no-time.png"); page.keyboard.press("Escape"); page.wait_for_timeout(300)
        print("no time:", page.inner_text(G + "[data-ed='when']"))
        page.click(G + "[data-ed='when']"); page.wait_for_timeout(200); page.fill(G + "#wp-t", "23:59"); page.wait_for_timeout(200); page.mouse.click(5, 700); page.wait_for_timeout(300)
        print("after title+type:", page.inner_text(G + ".ed-head h2"), "| when:", page.inner_text(G + "[data-ed='when']"), "| path:", page.inner_text("#lt-path").replace("\n", " "))
        shot("61-eval-editor")
        page.fill(G + "input[data-f='total']", "?"); page.wait_for_timeout(300)
        print("out of ?:", page.input_value(G + "input[data-f='total']"))

        page.click("#lt-path button.lt-step >> text=Evaluations") if page.query_selector("#lt-path button.lt-step >> text=Evaluations") else None
        page.wait_for_timeout(400); shot("62-evals-after")
        print("list:", page.eval_on_selector_all(G + ".erow h3", "els => els.map(e => e.textContent)"))
        # Save, and look at the file
        page.keyboard.press("Control+s"); page.wait_for_timeout(2000)
        okb = page.query_selector(G + "#pl-ok")
        if okb: okb.click(); page.wait_for_timeout(1200)
        r = gh.repos["chandra-gummaluru/courses-private"]; book = json.loads(r.commits[r.head]["files"]["csc258/f26/grades.json"])
        print("saved:", [(e["name"], e["label"], e["type"], e["short"], e.get("date"), e.get("time"), "num" in e) for e in book["evals"]])
        new = book["evals"][-1]
        assert (new["label"], new["title"], new["type"], new.get("date"), new.get("time")) == ("Lab", "Flip-flops", "assignment", "2026-10-30", "23:59"), new
        page.set_viewport_size({"width": 390, "height": 844}); page.click(G + ".erow >> nth=5"); page.wait_for_timeout(500)
        page.screenshot(path=f"{OUT}/63-eval-editor-phone.png")
        b.close()
    print("\n".join(errors) or "no page errors")

main()
