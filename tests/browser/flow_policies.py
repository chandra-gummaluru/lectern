"""Course page: the Policies section (the gradebook's course rules, shown or hidden, and your own),
and the week rows' announcement count.
Run with the server going (python app.py), then: python tests/browser/flow_policies.py"""
import json, os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
from flow_links import BOOK

def main():
    book = json.loads(json.dumps(BOOK))
    book["policies"] = {"round": {"step": 1, "dir": "nearest"},
                        "buckets": [{"id": "b1", "from": 48, "to": 49.99, "value": 50}],
                        "autofail": [{"id": "a1", "target": "fe", "below": 40, "effect": "cap", "value": 47}, {"id": "a2", "target": "g:g1", "below": 50, "effect": "set", "value": 45}]}
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(book)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
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
        page.goto(BASE)
        page.evaluate("""() => { sessionStorage.setItem('lectern.github', JSON.stringify({access_token:'tok', refresh_token:'r', expires_at: Date.now()+8*3600e3}));
                                 localStorage.setItem('lectern.repos', JSON.stringify({priv:'chandra-gummaluru/courses-private', pub:'chandra-gummaluru/courses'})); }""")
        page.goto(BASE + "#/csc258/f26/course"); page.reload(); page.wait_for_timeout(2500)
        print("sections:", page.eval_on_selector_all(C + ".e-sechead .grow > :first-child", "els => els.map(e => e.textContent)"))
        pol = page.locator(C + ".e-sechead", has_text="Policies").first
        pol.scroll_into_view_if_needed()
        # open it in the editor if collapsed
        print("rules:", page.eval_on_selector_all(C + ".e-gpol", "els => els.map(e => e.querySelector('b').textContent + ' [' + e.querySelector('.e-eye span').textContent + '] ' + e.querySelector('p').textContent)"))
        page.locator(C + ".e-gpol", has_text="Rounding").locator(".e-eye").click(); page.wait_for_timeout(300)
        page.locator(C + "button", has_text="+ Add policy").click(); page.wait_for_timeout(400)
        page.locator(C + "[data-lt-tool='course'] .cpb-block textarea, " + C + ".cpb-block textarea").last.fill("Late work loses 10% a day."); page.wait_for_timeout(200)
        page.locator(C + "button", has_text="+ Add policy").click(); page.wait_for_timeout(400)
        page.locator(C + ".cpb-block textarea").last.fill("Secret: I round up borderline cases."); page.wait_for_timeout(200)
        page.locator(C + ".cpb-block").last.locator(".e-eye").click(); page.wait_for_timeout(300)
        page.locator(C + ".e-sechead", has_text="Policies").first.scroll_into_view_if_needed(); page.wait_for_timeout(200)
        page.screenshot(path=f"{OUT}/130-policies-editor.png")
        # an announcement in week 1, for the week row
        page.locator(C + ".e-weekrow").first.click(); page.wait_for_timeout(400)
        page.locator(C + "button", has_text="Add announcement").first.click(); page.wait_for_timeout(400)
        page.keyboard.type("Welcome"); page.wait_for_timeout(200)
        print("path:", page.inner_text("#lt-path").replace("\n", " "))
        page.locator("#lt-path button.lt-step", has_text="Course Page").click(); page.wait_for_timeout(500)
        print("week row:", page.inner_text(C + ".e-weekrow").replace("\n", " "), "| ann:", page.get_attribute(C + ".wr-ann", "title"))
        page.locator(C + ".e-weekrow").first.screenshot(path=f"{OUT}/131-week-row.png")
        page.click("#lt-save"); page.wait_for_timeout(2500)
        r = gh.repos["chandra-gummaluru/courses"]; html = r.commits[r.head]["files"]["csc258/f26/info.html"]
        sec = html[html.find("cpb-type-policies"):]
        sec = sec[:sec.find("</details>")]
        print("published headings:", re.findall(r'<h3[^>]*>([^<]*)</h3>', sec))
        print("late shown:", "Late work" in sec, "| secret in visible text:", "Secret" in re.sub(r'data-json="[^"]*"', "", sec), "| rounding shown:", "rounded to the nearest" in sec, "| ranges shown:", "becomes 50" in re.sub(r'data-json="[^"]*"', "", sec))
        page.reload(); page.wait_for_timeout(2500)
        head = page.locator(C + ".e-sechead", has_text="Marking Scheme").first
        print("scheme controls:", head.locator(".e-secctl").inner_text().replace("\n", " "))
        head.locator("[data-act='sec-vis']").click(); page.wait_for_timeout(300)
        page.screenshot(path=f"{OUT}/132-sections.png", full_page=True)
        page.click("#lt-save"); page.wait_for_timeout(2500)
        html = r.commits[r.head]["files"]["csc258/f26/info.html"] if False else gh.repos["chandra-gummaluru/courses"].commits[gh.repos["chandra-gummaluru/courses"].head]["files"]["csc258/f26/info.html"]
        print("scheme hidden in file:", 'cpb-type-scheme" data-hidden' in html)
        page.reload(); page.wait_for_timeout(2500)
        print("still hidden:", page.locator(C + ".e-sechead", has_text="Marking Scheme").first.locator("[data-act='sec-vis'] span").inner_text())
        print("add buttons:", page.eval_on_selector_all(C + ".e-addsec button", "e => e.map(x => x.textContent)"))
        page.locator(C + ".e-addsec button").click(); page.wait_for_timeout(500)
        print("sections now:", page.eval_on_selector_all(C + ".e-sechead .grow > :first-child", "els => els.map(e => e.textContent)"))
        page.screenshot(path=f"{OUT}/133-add-section.png")
        print("after reopen rules:", page.eval_on_selector_all(C + ".e-gpol .e-eye span", "els => els.map(e => e.textContent)"), "| own:", page.eval_on_selector_all(C + ".cpb-block .e-eye span", "els => els.map(e => e.textContent)"), "| unsaved:", page.inner_text("#lt-status"))
        b.close()
    print("\n".join(errors) or "no page errors")

if __name__ == "__main__":
    main()
