/* A teaching team member's page (#/<course>/<term>/team/<user id>): what students see about them on the
   course page's About tab. Their contact email and office, and their weekly times: the lecture sections
   they teach, tutorials and labs they run, office hours, each with its section, day, time and room.

   Kept in the offering's private files, <course>/<term>/team.json (the hub reads it, with the team itself):

     { "format": "lectern-team/1",
       "people": { "<user id>": { "email": "", "office": "BA 4010", "show": true,
                                  "times": [ { "id", "kind": "lecture", "section": "LEC0101", "day": 1,
                                               "start": "10:00", "end": "11:00", "where": "BA 1170" } ] } } }

   Their name and role come from their account and the team; email is their account's unless set here.
   Changes save by themselves. Instructors change anyone's; TAs see theirs. */

export const KINDS = [["lecture", "Lecture"], ["tutorial", "Tutorial"], ["lab", "Lab"], ["office", "Office hours"], ["other", "Other"]];
export const DAYS = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const uid = () => Math.random().toString(36).slice(2, 10);
const SECTION_HINT = { lecture: "e.g. LEC0101", tutorial: "e.g. TUT0102", lab: "e.g. PRA0101", office: "Optional", other: "e.g. Review session" };

export function teamMemberPage(ctx, r) {
  const { $, esc, pageHTML, toast, go, Store, area, canEdit, ICON, renderPath, steps, api, owner, ROLE_NAME } = ctx;
  const { c, t } = r, id = String(r.p || "");
  const path = `${c}/${t}/team.json`, repo = area(Store.PRIV);
  const edit = canEdit(c, t);
  const here = () => { const x = ctx.route(); return x.page === "team" && x.c === c && x.t === t && String(x.p) === id; };
  const st = (teamMemberPage.state = teamMemberPage.state && teamMemberPage.state.key === `${r.o || ""}/${c}/${t}` ? teamMemberPage.state : { key: `${r.o || ""}/${c}/${t}`, data: null, sha: undefined });

  async function load() {
    pageHTML(`<div class="lt-in"><div class="lt-loading" style="min-height:200px">Reading…</div></div>`);
    let team;
    try {
      const [f, tm] = await Promise.all([st.data ? null : Store.readFile(repo, path), api(`/api/teams/${encodeURIComponent(owner())}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`)]);
      if (!st.data) { st.data = f ? JSON.parse(f.text) : { format: "lectern-team/1", people: {} }; st.sha = f ? f.sha : null; }
      if (!st.data.people || typeof st.data.people !== "object") st.data.people = {};
      team = tm;
    } catch (e) { if (here()) pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't read the teaching team. ${esc(e.message)}</p></div>`); return; }
    const who = team.people.find(p => String(p.id) === id);
    if (!here()) return;
    if (!who) { renderPath([...steps, { label: "Teaching team" }]); pageHTML(`<div class="lt-in"><p class="lt-note">They're not on this offering's teaching team any more.</p></div>`); return; }
    draw(who, edit || false);
  }

  let timer = 0, saving = null, again = false;
  function changed() { status("Saving…"); clearTimeout(timer); timer = setTimeout(save, 500); }
  async function save() {
    if (saving) { again = true; return; }
    saving = (async () => {
      try { st.sha = await Store.writeText(repo, path, JSON.stringify(st.data, null, 1) + "\n", "Teaching team", st.sha); status("Saved"); }
      catch (e) { status("Not saved", true); toast(e.conflict ? "The teaching team's details were changed somewhere else. Reload this page to see them; your last change wasn't saved." : `Couldn't save. ${e.message}`); }
      finally { saving = null; if (again) { again = false; save(); } }
    })();
  }
  function status(text, bad) { const el = $("#tm-status"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }

  function draw(who, canChange) {
    renderPath([...steps, { label: who.name || who.email }]);
    const me = st.data.people[id] || {}, times = me.times || [], dis = canChange ? "" : " disabled";
    const opt = (list, v) => list.map(([k, n]) => `<option value="${k}"${String(v) === String(k) ? " selected" : ""}>${esc(n)}</option>`).join("");
    const days = DAYS.slice(1).map((d, k) => [String(k + 1), d]);
    pageHTML(`<div class="lt-in lt-lw lw-page tm-page">
      <div class="lt-off-head"><div><h1>${esc(who.name || who.email)}</h1><p class="lt-term-line">${esc(ROLE_NAME[who.role] || who.role)}</p></div>
        <div class="lt-off-acts">${canChange ? `<span class="lw-status" id="tm-status"></span>` : ""}</div></div>
      ${canChange ? "" : `<p class="lt-note">An instructor sets these.</p>`}
      <div class="lw-card lt-form">
        <label class="lt-check tm-show"><input type="checkbox" id="tm-show"${me.show === false ? "" : " checked"}${dis}> Show them on the course page</label>
        <div class="lw-two"><label>Email<input type="email" id="tm-email" value="${esc(me.email || "")}" placeholder="${esc(who.email)}"${dis}><small>For students. Blank: ${esc(who.email)}.</small></label>
          <label>Office<input type="text" id="tm-office" value="${esc(me.office || "")}" placeholder="e.g. BA 4010"${dis}></label></div>
      </div>
      <h2 class="lw-h2">Sections and Times</h2>
      <div class="lw-card"><p class="lt-part-text lw-help">The lecture sections they teach, the tutorials and labs they run, and their office hours: each one every week of the term. The course page puts them under their section, and This week on their days.</p>
        <div class="tm-times">${times.length ? `<div class="tm-row tm-head"><span>What</span><span>Section</span><span>Day</span><span>Starts</span><span>Ends</span><span>Where</span><span></span></div>` : ""}
        ${times.map((x, i) => `<div class="tm-row" data-i="${i}">
          <select data-k="kind" aria-label="What"${dis}>${opt(KINDS, x.kind)}</select>
          <input type="text" data-k="section" value="${esc(x.section || "")}" placeholder="${SECTION_HINT[x.kind] || ""}" aria-label="Section"${dis}>
          <select data-k="day" aria-label="Day"${dis}>${opt(days, x.day)}</select>
          <input type="time" data-k="start" value="${esc(x.start || "")}" aria-label="Starts"${dis}>
          <input type="time" data-k="end" value="${esc(x.end || "")}" aria-label="Ends"${dis}>
          <input type="text" data-k="where" value="${esc(x.where || "")}" placeholder="e.g. BA 1170" aria-label="Where"${dis}>
          ${canChange ? `<button type="button" class="lt-btn lt-trash lw-ic" data-del="${i}" aria-label="Remove it">${ICON.trash}</button>` : "<span></span>"}</div>`).join("") || `<p class="lt-hint">None yet.</p>`}</div>
        ${canChange ? `<div class="lw-adds">${KINDS.slice(0, 4).map(([k, n]) => `<button type="button" class="lt-btn add" data-add="${k}">${ICON.plus}${k === "office" ? "Office Hours" : `A ${n}`}</button>`).join("")}</div>` : ""}</div>
    </div>`);
    if (!canChange) return;
    const P = () => (st.data.people[id] = st.data.people[id] || {});
    const bind = (sel, k) => { const el = $(sel); el.oninput = el.onchange = () => { const v = el.value.trim(); if (v) P()[k] = v; else delete P()[k]; changed(); }; };
    bind("#tm-email", "email"); bind("#tm-office", "office");
    $("#tm-show").onchange = e => { if (e.target.checked) delete P().show; else P().show = false; changed(); };
    const box = $(".tm-times");
    box.oninput = box.onchange = e => {
      const row = e.target.closest(".tm-row[data-i]"); if (!row || !e.target.dataset.k) return;
      const x = P().times[+row.dataset.i], k = e.target.dataset.k;
      x[k] = k === "day" ? Number(e.target.value) : e.target.value.trim();
      if (k === "kind" && e.type === "change") { row.querySelector('[data-k="section"]').placeholder = SECTION_HINT[x.kind] || ""; }
      changed();
    };
    box.querySelectorAll("[data-del]").forEach(b => { b.onclick = () => { P().times.splice(+b.dataset.del, 1); changed(); draw(who, true); }; });
    $(".tm-page").querySelectorAll("[data-add]").forEach(b => { b.onclick = () => {
      const list = (P().times = P().times || []), last = list[list.length - 1];
      list.push({ id: uid(), kind: b.dataset.add, section: "", day: last ? last.day : 1, start: "", end: "", where: b.dataset.add === "office" ? P().office || "" : last ? last.where : "" });
      changed(); draw(who, true);
      const rows = document.querySelectorAll(".tm-row[data-i]"); const s = rows[rows.length - 1] && rows[rows.length - 1].querySelector('[data-k="section"]'); if (s) s.focus();
    }; });
  }

  load();
}
