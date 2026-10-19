"""Folder mode for all three builders: Grades and Exams read and save files in the private folder,
the course page gets its marking scheme from the gradebook there. The browser's private file system
stands in for a real folder. Run with the server going (python app.py)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from flow_github import OUT, BASE
from flow_links import BOOK

SETUP = """async (book) => {
  const root = await navigator.storage.getDirectory();
  for await (const [n] of root.entries()) await root.removeEntry(n, { recursive: true });
  const parent = await root.getDirectoryHandle('teaching', { create: true });
  const mk = async (path, text) => { const parts = path.split('/'); let d = parent; for (const p of parts.slice(0, -1)) d = await d.getDirectoryHandle(p, { create: true });
    const w = await (await d.getFileHandle(parts.at(-1), { create: true })).createWritable(); await w.write(text); await w.close(); };
  await mk('courses-private/csc258/f26/grades.json', book);
  await mk('courses/csc258/f26/slides.pdf', 'x');
  window.showDirectoryPicker = async () => parent;
}"""
LS = """async () => {
  const out = [];
  const walk = async (d, p) => { for await (const [n, h] of d.entries()) { const q = p ? p + '/' + n : n; if (h.kind === 'directory') await walk(h, q); else out.push(q + ' ' + (await h.getFile()).size); } };
  await walk(await (await navigator.storage.getDirectory()).getDirectoryHandle('teaching'), '');
  return out.sort();
}"""

def open_eval(page, G, eid):
    """The evaluation's own page (where Build is), from wherever the gradebook is."""
    if page.query_selector(G + f".editor[data-eval='{eid}']"): return
    if page.query_selector(G + ".editor[data-eval]"):
        page.locator("#lt-path button.lt-step", has_text="Evaluations").click(); page.wait_for_timeout(400)
    page.click(G + f".erow[data-id='{eid}']"); page.wait_for_timeout(500)

def main():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 900})
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        ctx.route("https://api.github.com/**", lambda r: (errors.append(f"went to GitHub: {r.request.url}"), r.abort()))
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")
        path = lambda: page.inner_text("#lt-path").replace("\n", " ")
        G, X, C = "[data-lt-tool='grades'] ", "[data-lt-tool='exams'] ", "[data-lt-tool='course'] "
        page.goto(BASE); page.wait_for_timeout(500)
        page.evaluate(SETUP, json.dumps(BOOK))
        page.click("#splash-folder"); page.wait_for_timeout(1200)
        page.evaluate("location.hash = '#/csc258/f26'"); page.wait_for_timeout(700); shot("90-folder-offering")
        print("1 notes left:", page.inner_text("#lt-page").count("sign in with GitHub"))
        page.click("[data-part='book']"); page.wait_for_timeout(2500); shot("91-folder-grades")
        print("2 path:", path(), "| evals:", page.eval_on_selector_all(G + ".erow h3", "els => els.map(e => e.textContent)"))
        # change a weight and save into the folder
        page.evaluate("location.hash = location.hash.replace(/\/(grades|gradebook)$/, '/evaluations')"); page.wait_for_timeout(1200); page.wait_for_timeout(400)
        print("  evals:", page.eval_on_selector_all(G + ".erow h3", "els => els.map(e => e.textContent)"))
        page.click(G + ".erow[data-id='fe']"); page.wait_for_timeout(400)
        page.fill(G + "input[data-f='weight']", "40"); page.wait_for_timeout(200)
        print("  status:", page.inner_text(G + "#status").replace("\n", " "))
        page.click("#lt-save"); page.wait_for_timeout(2500)
        print("  save button:", page.inner_text(G + "#pl-ok") if page.query_selector(G + "#pl-ok") else None)
        if page.query_selector(G + "#pl-ok"): page.click(G + "#pl-ok"); page.wait_for_timeout(1200)
        saved = json.loads(page.evaluate("""async (path) => { let d = await (await navigator.storage.getDirectory()).getDirectoryHandle('teaching'); const parts = path.split('/'), name = parts.pop();
            for (const p of parts) d = await d.getDirectoryHandle(p); return await (await (await d.getFileHandle(name)).getFile()).text(); }""", "courses-private/csc258/f26/grades.json"))
        print("3 saved weight:", [e["weight"] for e in saved["evals"] if e["id"] == "fe"], "| status:", page.inner_text(G + "#status").replace("\n", " "))
        # Build the midterm and save it into the folder
        page.click("#lt-path button.lt-step >> nth=2"); page.wait_for_timeout(400)
        open_eval(page, G, "mt"); page.click(G + ".ed-acts [data-act='ev-build']"); page.wait_for_timeout(2500)
        print("4 path:", path())
        page.click("#lt-save"); page.wait_for_timeout(2500)
        if page.query_selector(X + "#pl-ok"): page.click(X + "#pl-ok"); page.wait_for_timeout(2000)
        shot("92-folder-exam-saved")
        print("5 files:", [f for f in page.evaluate(LS) if f.startswith("courses-private/")])
        if page.query_selector(X + ".modal button.primary"): page.click(X + ".modal button.primary"); page.wait_for_timeout(300)
        # back in Grades: the midterm has its exam
        page.evaluate("location.hash = '#/csc258/f26/evaluations'"); page.wait_for_timeout(1500)
        print("6 midterm button:", (open_eval(page, G, "mt"), page.inner_text(G + ".ed-acts [data-act='ev-build']"))[1])
        # the course page's marking scheme comes from the gradebook in the folder
        page.evaluate("location.hash = '#/csc258/f26/course'"); page.wait_for_timeout(2500)
        print("7 scheme section:", bool(page.query_selector(C + ".e-from")), "| pills:", page.eval_on_selector_all(C + ".wr-pill", "els => els.map(e => e.textContent)"))
        b.close()
    print("\n".join(errors) or "no page errors, nothing sent to GitHub")

main()
