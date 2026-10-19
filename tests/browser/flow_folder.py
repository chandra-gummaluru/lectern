"""Folder mode, with the browser's private file system standing in for a real folder."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
from flow_github import OUT, BASE

SETUP = """async () => {
  const root = await navigator.storage.getDirectory();
  for await (const [n] of root.entries()) await root.removeEntry(n, { recursive: true });
  const parent = await root.getDirectoryHandle('teaching', { create: true });
  const mk = async (path, text) => { const parts = path.split('/'); let d = parent; for (const p of parts.slice(0, -1)) d = await d.getDirectoryHandle(p, { create: true });
    const w = await (await d.getFileHandle(parts.at(-1), { create: true })).createWritable(); await w.write(text); await w.close(); };
  await mk('courses-private/csc258/f26/grades.json', JSON.stringify({ format: 'grade-builder/1', course: { code: 'CSC258', term: 'Fall 2026' }, evals: [], groups: [], students: [], marks: {}, overrides: {} }));
  await mk('courses/csc258/f26/slides.pdf', 'x');
  await mk('courses/.git/config', '[remote "origin"]\\n\\turl = https://github.com/chandra-gummaluru/courses.git\\n');
  window.showDirectoryPicker = async () => parent;
}"""

def main():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1360, "height": 860})
        ctx.route("https://cdnjs.cloudflare.com/**", lambda r: r.abort())
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=f"{OUT}/{n}.png")
        page.goto(BASE); page.wait_for_timeout(500)
        page.evaluate(SETUP)
        page.click("#splash-folder"); page.wait_for_timeout(1200); shot("40-local-home")
        print("status:", page.inner_text("#lt-status").replace("\n", " "))
        page.evaluate("location.hash = '#/csc258/f26'"); page.wait_for_timeout(600); shot("41-local-offering")
        page.click("[data-go='course']"); page.wait_for_timeout(2500); shot("42-local-course")
        print("path:", page.inner_text("#lt-path").replace("\n", " "))
        page.click("#lt-save"); page.wait_for_timeout(800); shot("43-local-save")
        ok = page.query_selector("[data-lt-tool='course'] #pl-ok")
        if ok: ok.click(); page.wait_for_timeout(1200)
        has = page.evaluate("""async () => { const r = await navigator.storage.getDirectory(); const d = await (await (await (await r.getDirectoryHandle('teaching')).getDirectoryHandle('courses')).getDirectoryHandle('csc258')).getDirectoryHandle('f26');
           try { const f = await (await d.getFileHandle('info.html')).getFile(); return f.size; } catch (e) { return String(e); } }""")
        print("info.html written:", has)
        page.evaluate("location.hash = '#/'"); page.wait_for_timeout(1200); shot("44-local-home-after")
        page.evaluate("location.hash = '#/csc258/f26/grades'"); page.wait_for_timeout(800); shot("45-local-grades")
        b.close()
    print("\n".join(errors[:30]) or "no errors")

main()
