/* A teaching team member's page (#/<course>/<term>/team/<user id>): what students see about them on the
   course page's About tab. Their contact email and office, the sections they run (a dropdown of the
   offering's sections, kept with the sections: groups.js), and their office hours.

   Kept in the offering's private files, <course>/<term>/team.json (the hub reads it, with the team itself):

     { "format": "lectern-team/1",
       "people": { "<user id>": { "email": "", "office": "BA 4010", "show": true,
                                  "times": [ { "id", "kind": "office", "day": 2, "start": "14:00", "end": "15:00",
                                               "where": "BA 4010" } ] } } }

   (Older offerings kept everyone's lectures, tutorials and labs in "times" too, by section: the sections
   start from those.) Their name and role come from their account and the team; email is their
   account's unless set here. Changes save by themselves. Instructors change anyone's; TAs see theirs. */

export const KINDS = [["lecture", "Lecture"], ["tutorial", "Tutorial"], ["lab", "Lab"], ["office", "Office hours"], ["other", "Other"]];
import { parseTime } from "./when.js";
import { pickMany } from "./pick.js";
import { placeField, placeOf } from "./place.js";
import { SECTION_ICON, SECTION_NAME, sectionKind, sectionLabel, groupSummary, runsSection, runnersOf, changeGroups, sortSections } from "./groups.js";
const KIND_LABEL = { lecture: "Lecture", tutorial: "Tutorial", lab: "Lab", other: "Other" };
const DAY3 = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const itemLine = x => [[DAY3[x.day] || "", x.start ? (x.end ? `${x.start}–${x.end}` : x.start) : ""].filter(Boolean).join(" "), x.where].filter(Boolean).join(" · ") || "No time yet";
export const DAYS = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const uid = () => Math.random().toString(36).slice(2, 10);
const SECTION_HINT = { lecture: "e.g. LEC0101", tutorial: "e.g. TUT0102", lab: "e.g. PRA0101", office: "Optional", other: "e.g. Review sessions" };

export function teamMemberPage(ctx, r) {
  const { $, esc, pageHTML, toast, go, Store, area, canEdit, ICON, renderPath, steps, api, owner, ROLE_NAME, groups } = ctx;
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
      st.groups = groups ? await groups().catch(() => []) : [];
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
    // The sections they run (picked here, kept with the sections). Their office hours: their own, here.
    const G = sortSections(st.groups || []), run = G.filter(g => runsSection(g, id));
    const office = times.map((x, i) => [x, i]).filter(([x]) => x.kind === "office");
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
      <h2 class="lw-h2">Sections They Run</h2>
      <div class="lw-card">${G.length ? `<div class="lt-form tm-run-pick"><label>Sections<div id="tm-runs-pick"></div><small>The lecture, tutorial and lab sections they teach. Instructors and TAs see and change things for their sections' students.</small></label></div>` : ""}
        ${run.length ? `<div class="lt-olist tm-runs">${run.map(g => `<div class="lt-orow lt-user lt-sec-row"><button type="button" class="lt-user-who lt-user-open" data-group="${esc(g.id)}"><span class="lt-sec-ic" aria-hidden="true">${SECTION_ICON[sectionKind(g)]}</span><span class="lt-sec-t"><small>${esc(SECTION_NAME[sectionKind(g)])}</small><b>${esc(sectionLabel(g))}</b><span>${esc(groupSummary(g))}</span></span></button></div>`).join("")}</div>`
        : G.length ? "" : `<p class="lt-part-text lw-help">The offering has no sections yet: add them in Sections, on the offering's page.</p>`}</div>
      <h2 class="lw-h2">Office Hours</h2>
      <div class="lw-card"><p class="lt-part-text lw-help">Every week of the term. The course page shows them with their details, and on their days.</p>
        <div class="tm-times">${office.length ? `<div class="tm-row tm-head tm-oh"><span>Day</span><span>Starts</span><span>Ends</span><span>Where</span><span></span></div>` : ""}
        ${office.map(([x, i]) => `<div class="tm-row tm-oh" data-i="${i}">
          <select data-k="day" aria-label="Day"${dis}>${opt(days, x.day)}</select>
          <input type="text" data-k="start" value="${esc(x.start || "")}" placeholder="e.g. 2 pm" aria-label="Starts" autocomplete="off"${dis}>
          <input type="text" data-k="end" value="${esc(x.end || "")}" placeholder="e.g. 3 pm" aria-label="Ends" autocomplete="off"${dis}>
          <div class="tm-where" data-plc-i="${i}"></div>
          ${canChange ? `<button type="button" class="lt-btn lt-trash lw-ic" data-del="${i}" aria-label="Remove them">${ICON.trash}</button>` : "<span></span>"}</div>`).join("") || `<p class="lt-hint">None yet.</p>`}</div>
        ${canChange ? `<div class="lw-adds"><button type="button" class="lt-btn add" data-add="office">${ICON.plus}Add Office Hours</button></div>` : ""}</div>
    </div>`);
    document.querySelectorAll(".tm-page [data-group]").forEach(b => { b.onclick = () => go({ page: "groups", c, t, g: b.dataset.group }); });
    // Office hours' Where: a place (picked on the map, or typed) and a room.
    document.querySelectorAll(".tm-times [data-plc-i]").forEach(h => {
      const x = times[+h.dataset.plcI]; if (!x) return;
      placeField(h, { ...placeOf(x), disabled: !canChange, onChange: v => { const y = st.data.people[id].times[+h.dataset.plcI]; if (v.place) y.place = v.place; else delete y.place; y.room = v.room; y.where = v.where; changed(); } });
    });
    const pick = $("#tm-runs-pick");
    if (pick) pickMany(pick, { options: G.map(g => ({ value: g.id, label: sectionLabel(g), kick: SECTION_NAME[sectionKind(g)], icon: SECTION_ICON[sectionKind(g)] })), value: run.map(g => g.id),
      empty: "None", emptyHint: "They don't run a section", emptyIcon: SECTION_ICON.none, allowEmpty: true, label: "Sections they run", id: "tm-runs", disabled: !canChange,
      onChange: async v => {
        status("Saving…");
        try {
          const { data } = await changeGroups(Store, repo, c, t, d => { d.groups.forEach(g => { const on = v.includes(g.id), was = runnersOf(g); g.people = on ? [...new Set([...was, id])] : was.filter(p => p !== id); }); }, "Sections: who runs them");
          st.groups = data.groups; status("Saved");
          const list = document.querySelector(".tm-runs"), now = sortSections(data.groups).filter(g => runsSection(g, id));
          const html = now.length ? `<div class="lt-olist tm-runs">${now.map(g => `<div class="lt-orow lt-user lt-sec-row"><button type="button" class="lt-user-who lt-user-open" data-group="${esc(g.id)}"><span class="lt-sec-ic" aria-hidden="true">${SECTION_ICON[sectionKind(g)]}</span><span class="lt-sec-t"><small>${esc(SECTION_NAME[sectionKind(g)])}</small><b>${esc(sectionLabel(g))}</b><span>${esc(groupSummary(g))}</span></span></button></div>`).join("")}</div>` : "";
          if (list) list.outerHTML = html || '<div class="tm-runs" hidden></div>'; else if (html) pick.closest(".lw-card").insertAdjacentHTML("beforeend", html);
          document.querySelectorAll(".tm-page [data-group]").forEach(b => { b.onclick = () => go({ page: "groups", c, t, g: b.dataset.group }); });
        } catch (e) { status("Not saved", true); toast(`Couldn't save who runs the sections. ${e.message}`); }
      } });
    if (!canChange) return;
    const P = () => (st.data.people[id] = st.data.people[id] || {});
    const bind = (sel, k) => { const el = $(sel); el.oninput = el.onchange = () => { const v = el.value.trim(); if (v) P()[k] = v; else delete P()[k]; changed(); }; };
    bind("#tm-email", "email"); bind("#tm-office", "office");
    $("#tm-show").onchange = e => { if (e.target.checked) delete P().show; else P().show = false; changed(); };
    const box = $(".tm-times");
    box.oninput = box.onchange = e => {
      const row = e.target.closest(".tm-row[data-i]"); if (!row || !e.target.dataset.k) return;
      const x = P().times[+row.dataset.i], k = e.target.dataset.k;
      if ((k === "start" || k === "end") && e.type === "change") { const v = parseTime(e.target.value); if (v == null) { e.target.classList.add("bad"); toast("Type a time like 14:00 or 2 pm."); return; } e.target.classList.remove("bad"); e.target.value = v; x[k] = v; changed(); return; }
      if (k === "start" || k === "end") return;
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
