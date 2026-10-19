"""Course page sections: Instructors & Contact always there (hide or delete it), a table's spare row,
and Add a section (text and tables).
Run with the server going (python app.py), then: python tests/browser/flow_sections.py"""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE

OLD = os.path.join(os.path.dirname(__file__), "old-course-page.html")

def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"README.md": "x"}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"csc258/f26/info.html": open(OLD, encoding="utf-8").read()}))
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        ctx.route("https://api.github.com/**", gh.handle)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        C = "[data-lt-tool='course'] "
        heads = lambda: page.eval_on_selector_all(C + ".e-sechead .grow > :first-child", "els => els.map(e => e.textContent)")
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/course"); page.reload(); page.wait_for_timeout(2500)
        print("sections:", heads())
        contact = page.locator(C + ".e-sechead", has_text="Instructors").first.locator("xpath=..")
        rows = lambda: contact.locator("tr.cpb-row").count()
        print("contact rows:", rows(), "| add text block?", contact.locator("button", has_text="text block").count(), "| add row?", contact.locator("button", has_text="Add row").count())
        cell = contact.locator("tr.cpb-row").last.locator("td").first
        cell.click(); page.keyboard.type("Dr. Ada Lovelace"); page.wait_for_timeout(300)
        print("after typing, rows:", rows(), "| focus still in:", page.evaluate("document.activeElement.dataset.bind"))
        page.keyboard.press("Tab"); page.keyboard.type("BA 4000"); page.wait_for_timeout(200)
        page.locator(C + ".e-addsec button").click(); page.wait_for_timeout(500)
        page.keyboard.type("Textbooks"); page.wait_for_timeout(200)
        last = page.locator(C + ".e-sechead").last.locator("xpath=..")
        print("new section buttons:", last.locator(".e-adds button").all_inner_texts())
        last.locator("button", has_text="+ Table").click(); page.wait_for_timeout(400)
        last = page.locator(C + ".e-sechead").last.locator("xpath=..")
        last.locator("tr.cpb-row").last.locator("td").first.click(); page.keyboard.type("Harris & Harris"); page.wait_for_timeout(300)
        last.locator("button", has_text="+ Text").click(); page.wait_for_timeout(400)
        page.keyboard.type("Optional reading."); page.wait_for_timeout(200)
        page.screenshot(path=f"{OUT}/170-sections.png", full_page=True)
        print("sections now:", heads())
        page.click("#lt-save"); page.wait_for_timeout(2500)
        r = gh.repos["chandra-gummaluru/courses"]; html = r.commits[r.head]["files"]["csc258/f26/info.html"]
        print("published: contact", "Ada Lovelace" in html, "| empty rows", len(re.findall(r'<tr class="cpb-row">\s*(<td[^>]*>\s*</td>\s*)+</tr>', html)), "| textbooks table", "Harris &amp; Harris" in html, "| text", "Optional reading" in html)
        page.reload(); page.wait_for_timeout(2500)
        last = page.locator(C + ".e-sechead").last.locator("xpath=..")
        print("reopened:", heads()[-1], "| blocks:", last.locator(".cpb-block").count(), "| table rows:", last.locator("tr.cpb-row").count(), "| unsaved:", page.inner_text("#lt-status"))
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
