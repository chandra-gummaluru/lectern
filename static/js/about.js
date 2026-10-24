/* About: what the course page's About tab says, besides the teaching team (each person's page in the
   Teaching Team): the course's title and description, any sections of your own (a textbook, software,
   how to get help…), and the course-wide policies, with which of the gradebook's rules show.

     #/<course>/<term>/about

   Kept in the offering's private files, <course>/<term>/about.json:

     { "format": "lectern-about/1", "title", "code", "term", "school", "description": "Markdown",
       "sections": [ { "id", "heading", "body" } ], "policies": [ { "id", "heading", "body" } ],
       "rules": { "<gradebook rule id>": true | false } }

   An offering without one starts from its course page (course.json), and becomes an about.json with the
   first change. Changes save by themselves. Instructors change it; TAs see it. */

const uid = () => Math.random().toString(36).slice(2, 10);

function fromCoursePage(page) {
  page = page || {};
  const secs = page.sections || [], text = [], policies = [], rules = {};
  secs.forEach(s => {
    if (!s || s.hidden) return;
    if (s.type === "text") (s.blocks || []).forEach(b => { if (b && !b.table && ((b.heading || "").trim() || (b.body || "").trim())) text.push({ id: uid(), heading: b.heading || s.title || "", body: b.body || "" }); });
    if (s.type === "policies") {
      (s.blocks || []).forEach(b => { if (b && !b.table && !b.hidden && ((b.heading || "").trim() || (b.body || "").trim())) policies.push({ id: uid(), heading: b.heading || "", body: b.body || "" }); });
      Object.assign(rules, s.show || {});
    }
  });
  return { format: "lectern-about/1", title: page.title || "", code: page.code || "", term: page.term || "", school: page.school || "", description: page.description || "", sections: text, policies, rules };
}

export function aboutPage(ctx, r) {
  const { $, esc, pageHTML, toast, Store, area, canEdit, ICON, renderPath, steps, markdown, gradebookRules, termName } = ctx;
  const { c, t } = r, path = `${c}/${t}/about.json`, repo = area(Store.PRIV), edit = canEdit(c, t);
  const key = `${r.o || ""}/${c}/${t}`;
  const here = () => { const x = ctx.route(); return x.page === "about" && x.c === c && x.t === t; };
  const st = (aboutPage.state = aboutPage.state && aboutPage.state.key === key ? aboutPage.state : { key, data: null, sha: undefined });
  let rules = [];

  async function load() {
    pageHTML(`<div class="lt-in"><div class="lt-loading" style="min-height:200px">Reading…</div></div>`);
    try {
      rules = await gradebookRules(c, t).catch(() => []);
      if (!st.data) {
        const f = await Store.readFile(repo, path);
        if (f) { st.data = JSON.parse(f.text); st.sha = f.sha; }
        else {
          const pg = await Store.readText(area(Store.PUB), `${c}/${t}/course.json`).catch(() => null);
          let page = null; try { page = pg ? JSON.parse(pg).page : null; } catch (_) {}
          st.data = fromCoursePage(page); st.sha = null;
          if (!st.data.code) st.data.code = c.toUpperCase();
          if (!st.data.term) st.data.term = termName(t);
        }
      }
      ["sections", "policies"].forEach(k => { if (!Array.isArray(st.data[k])) st.data[k] = []; });
      if (!st.data.rules || typeof st.data.rules !== "object") st.data.rules = {};
    } catch (e) { if (here()) pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't read it. ${esc(e.message)}</p></div>`); return; }
    if (here()) draw();
  }

  let timer = 0, saving = null, again = false;
  function changed() { status("Saving…"); clearTimeout(timer); timer = setTimeout(save, 500); }
  async function save() {
    if (saving) { again = true; return; }
    saving = (async () => {
      try { st.sha = await Store.writeText(repo, path, JSON.stringify(st.data, null, 1) + "\n", "About", st.sha); status("Saved"); }
      catch (e) { status("Not saved", true); toast(e.conflict ? "About was changed somewhere else. Reload this page to see it; your last change wasn't saved." : `Couldn't save. ${e.message}`); }
      finally { saving = null; if (again) { again = false; save(); } }
    })();
  }
  function status(text, bad) { const el = $("#ab-status"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }

  const blocks = (k, what, eg) => {
    const list = st.data[k], dis = edit ? "" : " disabled";
    return `${list.map((b, i) => `<div class="lw-card lt-form ab-block" data-k="${k}" data-i="${i}">
        <div class="ab-block-h"><label class="grow">Heading<input type="text" data-f="heading" value="${esc(b.heading)}" placeholder="${esc(eg)}"${dis}></label>
          ${edit ? `<span class="lw-move"><button type="button" class="lt-btn lw-ic" data-mv="-1" aria-label="Move up"${i ? "" : " disabled"}>${ICON.up}</button><button type="button" class="lt-btn lw-ic" data-mv="1" aria-label="Move down"${i < list.length - 1 ? "" : " disabled"}>${ICON.down}</button><button type="button" class="lt-btn lt-trash lw-ic" data-del aria-label="Delete it">${ICON.trash}</button></span>` : ""}</div>
        <label>Text<textarea data-f="body" rows="4" placeholder="A blank line starts a new paragraph; - for bullets; **bold**, [a link](https://…)."${dis}>${esc(b.body)}</textarea></label>
      </div>`).join("")}${edit ? `<div class="lw-adds"><button type="button" class="lt-btn add" data-add="${k}">${ICON.plus}${what}</button></div>` : list.length ? "" : `<p class="lt-hint">None.</p>`}`;
  };

  function draw() {
    renderPath([...steps, { label: "About" }]);
    const d = st.data, dis = edit ? "" : " disabled";
    const shown = x => (x.id in d.rules ? !!d.rules[x.id] : !!x.show);
    pageHTML(`<div class="lt-in lt-lw lw-page ab-page">
      <div class="lt-off-head"><div><h1>About</h1><p class="lt-lede">The course page's About tab: the course, its activities and teaching team, and the course-wide policies.</p></div>
        <div class="lt-off-acts">${edit ? `<span class="lw-status" id="ab-status"></span>` : ""}</div></div>
      ${edit ? "" : `<p class="lt-note">As a TA you can see this; the instructors change it.</p>`}
      <h2 class="lw-h2">The Course</h2>
      <div class="lw-card lt-form">
        <label>Title<input type="text" id="ab-title" value="${esc(d.title)}" placeholder="e.g. Computer Organization"${dis}></label>
        <div class="lw-three"><label>Course code<input type="text" id="ab-code" value="${esc(d.code)}" placeholder="e.g. CSC258"${dis}></label>
          <label>Term<input type="text" id="ab-term" value="${esc(d.term)}" placeholder="e.g. Fall 2026"${dis}></label>
          <label>School<input type="text" id="ab-school" value="${esc(d.school)}" placeholder="e.g. University of Toronto"${dis}></label></div>
        <label>Description<textarea id="ab-desc" rows="4" placeholder="What the course is about: a few sentences."${dis}>${esc(d.description)}</textarea></label>
      </div>
      <h2 class="lw-h2">Activities and the Teaching Team</h2>
      <div class="lw-card"><p class="lt-part-text lw-help" style="padding-bottom: 0 !important;">These come from each person's page in the offering's Teaching Team: the lectures they teach, their tutorials, labs and office hours (in groups such as LEC0101), and how to reach them.</p></div>
      <h2 class="lw-h2">More About the Course</h2>
      ${blocks("sections", "Add a Section", "e.g. Textbook")}
      <h2 class="lw-h2">Course Policies</h2>
      ${rules.length ? `<div class="lw-card"><p class="lt-part-text lw-help">From the gradebook's settings: choose which show.</p>${rules.map(x => `<label class="ab-rule"><input type="checkbox" data-rule="${esc(x.id)}"${shown(x) ? " checked" : ""}${dis}><span><b>${esc(x.title)}</b>${esc(x.text)}</span></label>`).join("")}</div>` : ""}
      ${blocks("policies", "Add a Policy", "e.g. Late work")}
    </div>`);
    if (!edit) return;
    const bind = (id, k) => { const el = $(id); el.oninput = () => { d[k] = el.value.trim(); changed(); }; };
    bind("#ab-title", "title"); bind("#ab-code", "code"); bind("#ab-term", "term"); bind("#ab-school", "school");
    $("#ab-desc").oninput = e => { d.description = e.target.value; changed(); };
    const root = $(".ab-page");
    root.oninput = e => {
      const box = e.target.closest(".ab-block"), f = e.target.dataset.f; if (!box || !f) return;
      d[box.dataset.k][+box.dataset.i][f] = f === "body" ? e.target.value : e.target.value.trim(); changed();
    };
    root.querySelectorAll("[data-rule]").forEach(b => { b.onchange = () => { d.rules[b.dataset.rule] = b.checked; changed(); }; });
    root.querySelectorAll("[data-add]").forEach(b => { b.onclick = () => {
      d[b.dataset.add].push({ id: uid(), heading: "", body: "" }); changed(); draw();
      const all = root.ownerDocument.querySelectorAll(`.ab-block[data-k="${b.dataset.add}"] [data-f="heading"]`); if (all.length) all[all.length - 1].focus();
    }; });
    root.querySelectorAll(".ab-block").forEach(box => {
      const list = d[box.dataset.k], i = +box.dataset.i;
      box.querySelectorAll("[data-mv]").forEach(b => { b.onclick = () => { const j = i + Number(b.dataset.mv); [list[i], list[j]] = [list[j], list[i]]; changed(); draw(); }; });
      const del = box.querySelector("[data-del]"); if (del) del.onclick = () => { list.splice(i, 1); changed(); draw(); };
    });
  }

  load();
}
