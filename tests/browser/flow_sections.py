"""The course's own words on its course page: the offering's title and description, written on its page in
Lectern (under its code; they save by themselves to <course>/<term>/about.json) and shown on the course page
(its About tab).

(The course page used to have sections of its own: Instructors & Contact, and any text or table sections you
added. Those are gone: the teaching team, with office hours, comes from the Teaching Team (flow_team.py), and
the About tab says what the title and description say.)
Run:  python tests/browser/flow_sections.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright, expect
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE, GRADES


def main():
    gh = FakeGitHub()
    gh.add(Repo("chandra-gummaluru/courses-private", True, {"csc258/f26/grades.json": json.dumps(GRADES)}))
    gh.add(Repo("chandra-gummaluru/courses", False, {"README.md": "x"}))
    priv = gh.repos["chandra-gummaluru/courses-private"]
    about = lambda: json.loads(priv.commits[priv.head]["files"].get("csc258/f26/about.json") or "null")
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        # 1. The offering's page: a title and a description, under the code.
        page.goto(BASE + "#/csc258/f26"); page.wait_for_selector("#lt-title")
        print("title box says:", page.get_attribute("#lt-title", "data-ph"))
        page.click("#lt-title"); page.keyboard.type("Computer Organization"); page.keyboard.press("Enter")
        desc = page.locator("#lt-desc [contenteditable]").first
        desc.click(); page.keyboard.type("How a computer works, from transistors to a processor running your code.")
        expect(page.locator("#lt-about-st")).to_have_text("Saved", timeout=8000)
        page.screenshot(path=f"{OUT}/170-title-description.png")
        a = about()
        print("about.json:", a)
        assert a and a["title"] == "Computer Organization" and "transistors" in a["description"]

        # 2. Still there after a reload.
        page.reload(); page.wait_for_selector("#lt-title")
        print("after reload:", page.inner_text("#lt-title"), "|", page.inner_text("#lt-desc")[:60])
        assert page.inner_text("#lt-title") == "Computer Organization" and "transistors" in page.inner_text("#lt-desc")

        # 3. The course page's About tab says it.
        r = page.request.get(BASE + "api/hub/chandra/csc258/f26", headers={"X-Lectern": "1"})
        assert r.ok, r.status
        d = r.json()
        print("course page About:", d["data"]["about"]["description"][:60])
        assert "transistors" in d["data"]["about"]["description"]
        page.goto(BASE + "c/chandra/csc258/f26/#about"); page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT}/171-about-tab.png", full_page=True)
        body = page.inner_text("body")
        print("About tab: description", "transistors" in body, "| title", "Computer Organization" in body)
        assert "transistors" in body
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_sections: OK")


if __name__ == "__main__":
    main()
