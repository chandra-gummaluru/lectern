"""The gradebook's course rules on the course page: its Settings choose which show (Show … on the course page,
its About tab); the course page, opened in Lectern and saved, carries them (course.json's scheme), and the
course page's About tab shows those, not the others.

(The course page used to have a Policies section of its own, with your own policies and a week row's
announcement count. Those are gone: rules come only from the gradebook now, and announcements have their own
part, tested in flow_ann.py.)
Run:  python tests/browser/flow_policies.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from fakegh import FakeGitHub, Repo
from flow_github import OUT, BASE
from flow_links import BOOK

G = "[data-lt-tool='grades'] "


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
        gh.attach(ctx)
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        def publish():
            """Save the gradebook, then open the course page (it takes the gradebook's rules) and save it."""
            page.keyboard.press("Control+s"); page.wait_for_timeout(1500)
            page.evaluate("location.hash = '#/csc258/f26/course'"); page.wait_for_selector("[data-lt-tool='course']"); page.wait_for_timeout(2500)
            page.keyboard.press("Control+s"); page.wait_for_timeout(2000)
            pub = gh.repos["chandra-gummaluru/courses"]
            assert "csc258/f26/course.json" in pub.commits[pub.head]["files"], "the course page was saved"
            r = page.request.get(BASE + "api/hub/chandra/csc258/f26", headers={"X-Lectern": "1"})
            assert r.ok, r.status
            d = r.json()["data"]
            assert "about" in d, f"the course page's data has no About: {sorted(d)}"
            return [x["title"] for x in d["about"]["rules"]]

        # 1. Settings: which rules show. By default the rules (automatic fail) do; rounding and ranges don't.
        page.goto(BASE + "#/csc258/f26/settings"); page.wait_for_selector(G + "[data-pshow='round']")
        shown = lambda: {k: page.is_checked(G + f"[data-pshow='{k}']") for k in ("ranges", "round", "rules")}
        print("show at first:", shown())
        assert shown() == {"ranges": False, "round": False, "rules": True}
        page.check(G + "[data-pshow='round']"); page.wait_for_timeout(300)
        page.locator(G + "[data-pshow='round']").scroll_into_view_if_needed()
        page.screenshot(path=f"{OUT}/130-policies-show.png")
        rules = publish()
        print("course page About, rounding on:", rules)
        assert "Rounding" in rules and "Grade Adjustments" not in rules and any(t in rules for t in ("Automatic Fail", "Course Grade Rules"))

        # 2. Rules off, ranges on.
        page.goto(BASE + "#/csc258/f26/settings"); page.wait_for_selector(G + "[data-pshow='rules']")
        page.uncheck(G + "[data-pshow='rules']"); page.check(G + "[data-pshow='ranges']"); page.wait_for_timeout(300)
        rules = publish()
        print("course page About, rules off and ranges on:", rules)
        assert "Grade Adjustments" in rules and "Rounding" in rules and not any(t in rules for t in ("Automatic Fail", "Course Grade Rules"))

        # 3. On the course page itself (as students see it), the About tab.
        page.goto(BASE + "c/chandra/csc258/f26/#about"); page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT}/131-about-tab.png", full_page=True)
        body = page.inner_text("body")
        print("About tab has Rounding:", "Rounding" in body, "| Grade Adjustments:", "Grade Adjustments" in body)
        b.close()
    print("\n".join(errors) or "no page errors")
    assert not errors
    print("flow_policies: OK")


if __name__ == "__main__":
    main()
