/* Sections: an offering's lecture, tutorial and lab sections, e.g. LEC0101, meeting Monday and
   Wednesday at 13:00 in BA 1170. Each section has a type; a student is in at most one section of each type
   (one lecture section, one tutorial section…: the class list says which). Who runs a section is set on
   each person's page in the teaching team (the sections they run, a dropdown).

     The offering's page: the Sections card (groupsCard), each section opening its page:
     #/<course>/<term>/sections/<id>   one section: its name, type and weekly meeting times (day, times, where)

   Kept in the offering's private files, <course>/<term>/groups.json:

     { "format": "lectern-groups/1",
       "groups": [ { "id", "name": "LEC0101", "kind": "lecture", "people": ["12"],
                     "items": [ { "id", "day": 1, "start": "13:00", "end": "14:00", "where": "BA 1170" } ] } ] }

   (Older files: "activity groups" whose meeting times each had a kind and their own "people"; read as
   sections, typed from their name or times, run by everyone their times listed. An offering without one
   starts from its team's older times, team.json.) The course page (server/hub.py) shows each section. */

import { parseTime } from "./when.js";
import { placeField, placeOf } from "./place.js";

export const SECTION_KINDS = [["lecture", "Lecture"], ["tutorial", "Tutorial"], ["lab", "Lab"]];
export const SECTION_NAME = Object.fromEntries(SECTION_KINDS.map(([k, n]) => [k, `${n} Section`]));
export const GROUP_KINDS = [["lecture", "Lecture"], ["tutorial", "Tutorial"], ["lab", "Lab"], ["other", "Other"]];   // (team.js's older times)
export const DAYS = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const DAY3 = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const KIND_SHORT = Object.fromEntries(SECTION_KINDS);
const uid = () => Math.random().toString(36).slice(2, 10);
const ic = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const SECTION_ICON = {
  lecture: ic('<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8"/>'),
  tutorial: ic('<path d="M4 5h11a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3v-3H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M19 9h1a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-1v3l-3-3h-3"/>'),
  lab: ic('<path d="M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7.5 15h9"/>'),
  none: ic('<circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="8.5"/>'),
};
export const GROUP_ICON = ic('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>');
// A section's type: its own, or (older files) from its name (LEC…, TUT…, PRA… or LAB…), or its times' kinds;
// else a lecture section.
export function sectionKind(g) { const k = guessKind(g); return k || "lecture"; }
function guessKind(g) {
  if (g && KIND_SHORT[g.kind]) return g.kind;
  const n = String((g && g.name) || "").trim().toUpperCase();
  for (const [pre, k] of [["LEC", "lecture"], ["TUT", "tutorial"], ["PRA", "lab"], ["LAB", "lab"]]) if (n.startsWith(pre)) return k;
  const ks = ((g && g.items) || []).map(x => x && x.kind).filter(k => ["lecture", "tutorial", "lab"].includes(k));
  if (!ks.length) return "";
  const n2 = {}; ks.forEach(k => { n2[k] = (n2[k] || 0) + 1; });
  return Object.entries(n2).sort((a, b) => b[1] - a[1])[0][0];
}
export const kindFromName = name => guessKind({ name });   // "" when its name doesn't say
// Who runs it: its people (or, older files, everyone its times listed).
export const runnersOf = g => (Array.isArray(g.people) ? g.people.map(String) : [...new Set((g.items || []).flatMap(x => (x.people || []).map(String)))]);
export const runsSection = (g, id) => runnersOf(g).includes(String(id));
const hm = x => (x.start ? (x.end ? `${x.start}–${x.end}` : x.start) : "");
// "Mon 13:00–14:00" (and where), for a list.
export const itemText = x => [DAY3[x.day] || "", hm(x)].filter(Boolean).join(" ") + (x.where ? ` · ${x.where}` : "");
// A section's times in a line: "Mon, Wed 13:00–14:00 · BA 1170" (or each time, when they differ).
export function groupSummary(g) {
  const I = (g.items || []).slice().sort((a, b) => (a.day || 9) - (b.day || 9) || String(a.start).localeCompare(String(b.start)));
  if (!I.length) return "No meeting times yet";
  const same = I.every(x => hm(x) === hm(I[0]) && (x.where || "") === (I[0].where || ""));
  if (same) return [[...new Set(I.map(x => DAY3[x.day]).filter(Boolean))].join(", "), hm(I[0])].filter(Boolean).join(" ") + (I[0].where ? ` · ${I[0].where}` : "");
  return I.map(itemText).join(", ");
}
// "LEC0101", "TUT0102 (Tutorial)": a section's name with its type, for lists of several types.
export const sectionLabel = g => g.name || "Untitled section";
export const sortSections = G => G.slice().sort((a, b) => SECTION_KINDS.findIndex(([k]) => k === sectionKind(a)) - SECTION_KINDS.findIndex(([k]) => k === sectionKind(b)) || String(a.name).localeCompare(String(b.name), undefined, { numeric: true }));

// ── Reading and writing groups.json ──────────────────────────────────
const blank = () => ({ format: "lectern-groups/1", groups: [] });
function clean(d) {
  if (!d || !Array.isArray(d.groups)) d = blank();
  d.groups = d.groups.filter(g => g && typeof g === "object").map(g => {
    const kind = sectionKind(g), people = runnersOf(g);
    const items = (Array.isArray(g.items) ? g.items : []).filter(x => x && typeof x === "object").map(x => { const { people: _, kind: __, ...y } = x; return { ...y, id: String(x.id || uid()) }; });
    return { ...g, id: String(g.id || uid()), name: String(g.name || ""), kind, people, items };
  });
  return d;
}
// From team.json's older times: each person's lectures, tutorials and labs, as sections by their section's name.
function fromTeam(team) {
  const d = blank(), byName = new Map();
  Object.entries((team && team.people) || {}).forEach(([pid, me]) => ((me && me.times) || []).forEach(x => {
    if (!x || x.kind === "office") return;
    const name = String(x.section || "").trim() || (SECTION_NAME[x.kind] || "Section");
    let g = byName.get(name.toLowerCase());
    if (!g) { g = { id: uid(), name, kind: KIND_SHORT[x.kind] ? x.kind : kindFromName(name), people: [], items: [] }; byName.set(name.toLowerCase(), g); d.groups.push(g); }
    if (!g.people.includes(pid)) g.people.push(pid);
    if (!g.items.some(y => y.day === Number(x.day) && y.start === (x.start || "") && y.end === (x.end || "") && y.where === (x.where || "")))
      g.items.push({ id: uid(), day: Number(x.day) || 0, start: x.start || "", end: x.end || "", where: x.where || "" });
  }));
  return d;
}
export async function readGroups(Store, repo, c, t) {
  const f = await Store.readFile(repo, `${c}/${t}/groups.json`);
  if (f) { let d = null; try { d = JSON.parse(f.text); } catch (_) {} return { data: clean(d), sha: f.sha, made: true }; }
  let team = null; try { const tf = await Store.readFile(repo, `${c}/${t}/team.json`); team = tf ? JSON.parse(tf.text) : null; } catch (_) {}
  return { data: clean(fromTeam(team)), sha: null, made: false };
}
// Change groups.json: read it as it is now, change it, write it back (once more if it changed meanwhile).
export async function changeGroups(Store, repo, c, t, fn, msg = "Sections") {
  for (let k = 0; ; k++) {
    const { data, sha } = await readGroups(Store, repo, c, t);
    const r = fn(data);
    if (r === false) return { data, changed: false };
    try { await Store.writeText(repo, `${c}/${t}/groups.json`, JSON.stringify(data, null, 1) + "\n", msg, sha); return { data, changed: true, r }; }
    catch (e) { if (!e.conflict || k) throw e; }
  }
}
// Sections by name (any case), making the ones that aren't there yet: for a class list's sections. Each name
// may come with the type its column says ({ name, kind }); else its name says (LEC…, TUT…, PRA…).
export async function groupIdsFor(Store, repo, c, t, names) {
  const want = new Map();
  names.forEach(n => { const o = typeof n === "object" && n ? n : { name: n }; const name = String(o.name || "").trim(); if (name && !want.has(name.toLowerCase())) want.set(name.toLowerCase(), { name, kind: KIND_SHORT[o.kind] ? o.kind : "" }); });
  if (!want.size) return new Map();
  const { data } = await changeGroups(Store, repo, c, t, d => {
    let added = false;
    want.forEach(({ name, kind }) => {
      if (d.groups.some(g => g.name.toLowerCase() === name.toLowerCase())) return;
      const k0 = kindFromName(name);
      d.groups.push({ id: uid(), name, kind: k0 || (KIND_SHORT[kind] ? kind : "lecture"), people: [], items: [] }); added = true;
    });
    return added ? undefined : false;
  }, "Sections (from a class list)");
  return new Map(data.groups.map(g => [g.name.toLowerCase(), g.id]));
}
// A student's sections, keeping one of each type (the last one given wins).
export function oneOfEach(ids, G) {
  const by = new Map();
  (ids || []).map(String).forEach(id => { const g = G.find(x => x.id === id); if (g) by.set(sectionKind(g), id); });
  return [...by.values()];
}

// ── The card on the offering's page ──────────────────────────────────
export async function groupsCard(ctx, c, t) {
  const { box, esc, toast, modal, go, Store, repo, lead, ICON, here, students } = ctx;
  let G, S = [];
  try { [G, S] = await Promise.all([readGroups(Store, repo, c, t), students().catch(() => [])]); }
  catch (e) { if (here()) box.innerHTML = `<p class="lt-note err">Couldn't read the sections. ${esc(e.message)}</p>`; return; }
  if (!here()) return;
  const count = id => S.filter(s => !s.dropped && (s.groups || []).includes(id)).length;
  const groups = sortSections(G.data.groups);
  box.innerHTML = `<div class="lt-st-head"><p class="lt-part-text">The course's lecture, tutorial and lab sections, e.g. LEC0101, with their weekly times. A student is in one section of each type; who runs each is set on their page in the teaching team.</p>
      ${lead ? `<div class="lt-st-acts"><button type="button" class="lt-btn add" id="lt-group-new">${ICON.plus}Add a Section</button></div>` : ""}</div>
    ${groups.length ? `<div class="lt-olist lt-groups">${groups.map(g => { const n = count(g.id), k = sectionKind(g); return `<div class="lt-orow lt-user lt-sec-row"><button type="button" class="lt-user-who lt-user-open" data-group="${esc(g.id)}"><span class="lt-sec-ic" aria-hidden="true">${SECTION_ICON[k]}</span><span class="lt-sec-t"><small>${esc(SECTION_NAME[k])}</small><b>${esc(sectionLabel(g))}</b><span>${esc(groupSummary(g))}</span></span></button>
      <span class="lt-orow-r lt-group-n">${n} student${n === 1 ? "" : "s"}</span></div>`; }).join("")}</div>` : `<p class="lt-hint">No sections yet.</p>`}`;
  box.querySelectorAll("[data-group]").forEach(b => { b.onclick = () => go({ page: "groups", c, t, g: b.dataset.group }); });
  const add = box.querySelector("#lt-group-new");
  if (add) add.onclick = () => modal(`<h2>Add a Section</h2>
      <div class="lt-form"><label>Name<input type="text" id="gr-name" placeholder="e.g. LEC0101" autocomplete="off" spellcheck="false"><small>As the class list names it.</small></label>
        <label>Type<select id="gr-kind">${SECTION_KINDS.map(([k]) => `<option value="${k}" data-icon="${esc(SECTION_ICON[k])}">${esc(SECTION_NAME[k])}</option>`).join("")}</select></label></div>
      <p class="lt-err" id="gr-err"></p>
      <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn primary" data-ok>Add</button></div>`, (m, close) => {
    const inp = m.querySelector("#gr-name"), kind = m.querySelector("#gr-kind"), err = m.querySelector("#gr-err");
    let typed = false;
    kind.addEventListener("change", () => { typed = true; });
    inp.addEventListener("input", () => { const k = kindFromName(inp.value); if (!typed && k) kind.value = k; });
    m.querySelector("[data-no]").onclick = close;
    const ok = async () => {
      const name = inp.value.trim(); if (!name) { err.textContent = "Give it a name, e.g. LEC0101."; return inp.focus(); }
      const id = uid();
      try {
        const r = await changeGroups(Store, repo, c, t, d => { if (d.groups.some(g => g.name.toLowerCase() === name.toLowerCase())) return false; d.groups.push({ id, name, kind: kind.value, people: [], items: [] }); });
        if (!r.changed) { err.textContent = `There's a section called ${name} already.`; return; }
      } catch (e) { err.textContent = `Couldn't save it. ${e.message}`; return; }
      close(); go({ page: "groups", c, t, g: id });
    };
    m.querySelector("[data-ok]").onclick = ok;
    inp.addEventListener("keydown", e => { if (e.key === "Enter") ok(); });
    inp.focus();
  });
}

// ── A section's page ─────────────────────────────────────────────────
export function groupPage(ctx, r) {
  const { $, esc, pageHTML, toast, confirmBox, go, Store, repo, canEdit, ICON, renderPath, steps, team, students } = ctx;
  const { c, t } = r, edit = canEdit(c, t), key = `${r.o || ""}/${c}/${t}`;
  const here = () => { const x = ctx.route(); return x.page === "groups" && x.c === c && x.t === t && x.g === r.g; };
  const st = (groupPage.state = groupPage.state && groupPage.state.key === key ? groupPage.state : { key, data: null, sha: undefined });

  async function load() {
    pageHTML(`<div class="lt-in"><div class="lt-loading" style="min-height:200px">Reading the sections…</div></div>`);
    try {
      const [G, P, S] = await Promise.all([readGroups(Store, repo, c, t), team().catch(() => []), students().catch(() => [])]);
      st.data = G.data; st.sha = G.sha; st.people = P; st.students = S;
    } catch (e) { if (here()) pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't read the sections. ${esc(e.message)}</p></div>`); return; }
    if (here()) draw();
  }
  let timer = 0, saving = null, again = false;
  function changed() { status("Saving…"); clearTimeout(timer); timer = setTimeout(save, 500); }
  async function save() {
    if (saving) { again = true; return; }
    saving = (async () => {
      try { st.sha = await Store.writeText(repo, `${c}/${t}/groups.json`, JSON.stringify(st.data, null, 1) + "\n", "Sections", st.sha); status("Saved"); }
      catch (e) { status("Not saved", true); toast(e.conflict ? "The sections were changed somewhere else. Reload this page to see them; your last change wasn't saved." : `Couldn't save. ${e.message}`); }
      finally { saving = null; if (again) { again = false; save(); } }
    })();
  }
  function status(text, bad) { const el = $("#gr-status"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }

  function draw() {
    const g = st.data.groups.find(x => x.id === r.g);
    if (!g) { renderPath([...steps, { label: "Section" }]); pageHTML(`<div class="lt-in"><p class="lt-note">This section isn't there any more.</p></div>`); return; }
    const crumbs = () => renderPath([...steps, { label: sectionLabel(g) }]); crumbs();
    const dis = edit ? "" : " disabled", P = st.people || [], n = (st.students || []).filter(s => !s.dropped && (s.groups || []).includes(g.id)).length, k = sectionKind(g);
    const opt = (list, v) => list.map(([key2, nm]) => `<option value="${key2}"${String(v) === String(key2) ? " selected" : ""}>${esc(nm)}</option>`).join("");
    const days = DAYS.slice(1).map((d, i) => [String(i + 1), d]);
    const items = g.items.slice().sort((a, b) => (a.day || 9) - (b.day || 9) || String(a.start).localeCompare(String(b.start)));
    const who = runnersOf(g).map(id => P.find(p => String(p.id) === String(id))).filter(Boolean);
    const row = x => `<div class="gr-item" data-it="${esc(x.id)}">
        <span class="lx-kicon" aria-hidden="true">${SECTION_ICON[k]}</span>
        <div class="gr-item-b"><div class="gr-grid gr-grid4">
            <label class="lx-f">Day<select data-k="day"${dis}><option value="0"${x.day ? "" : " selected"}>Choose</option>${opt(days, x.day)}</select></label>
            <label class="lx-f">Starts<input type="text" data-k="start" value="${esc(x.start || "")}" placeholder="e.g. 1 pm" autocomplete="off"${dis}></label>
            <label class="lx-f">Ends<input type="text" data-k="end" value="${esc(x.end || "")}" placeholder="e.g. 2 pm" autocomplete="off"${dis}></label>
            <div class="lx-f gr-where">Where<div data-plc="${esc(x.id)}"></div></div>
          </div></div>
        ${edit ? `<button type="button" class="lx-ic quiet" data-del-it="${esc(x.id)}" title="Remove this time" aria-label="Remove this time">${ICON.trash}</button>` : ""}
      </div>`;
    pageHTML(`<div class="lt-in"><div class="lx ed">
      ${edit ? "" : `<p class="lt-note lx-note">You can look at the sections; the coordinators change them.</p>`}
      <div class="lx-editor" style="--c:#c99a06">
        <div class="lx-ed-head"><span class="lx-kicon big" id="gr-ic" aria-hidden="true">${SECTION_ICON[k]}</span><div class="gr-tt"><p class="gr-kind" id="gr-kick">${esc(SECTION_NAME[k])}</p><h2 id="gr-h">${esc(sectionLabel(g))}</h2></div>
          <span class="lx-acts">${edit ? `<span class="lx-status" id="gr-status"></span><button type="button" class="lx-ic" id="gr-del" title="Delete this section" aria-label="Delete this section">${ICON.trash}</button>` : ""}</span></div>
        <div class="lx-grid gr-top">
          <div class="lx-f">Type<div class="lx-seg" role="group" aria-label="Type">${SECTION_KINDS.map(([v, l]) => `<button type="button" data-kind="${v}" aria-pressed="${k === v}"${dis}>${esc(l)}</button>`).join("")}</div></div>
          <label class="lx-f">Name<input type="text" id="gr-name" value="${esc(g.name)}" placeholder="e.g. LEC0101"${dis}></label></div>
        <p class="lx-help">${n} student${n === 1 ? " is" : "s are"} in it: the class list says who (Students, on the offering's page). A student is in one ${esc(SECTION_NAME[k].toLowerCase())}.</p>
        <h3 class="lx-sec">Run By</h3>
        <p class="lx-help">${who.length ? `${who.map(p => `<button type="button" class="lt-link" data-person="${esc(p.id)}">${esc(p.name || p.email)}</button>`).join(", ")}. ` : "No one yet. "}Who runs each section is set on their page: Teaching Team, on the offering's page.</p>
        <h3 class="lx-sec">Meeting Times</h3>
        <p class="lx-help">Every week of the term. The course page shows the section with its times.</p>
        <div class="gr-items">${items.map(row).join("") || `<p class="lx-none gr-none">No meeting times yet.</p>`}</div>
        ${edit ? `<div class="lx-adds"><button type="button" class="lx-btn add" id="gr-add">${ICON.plus}Add a Time</button></div>` : ""}
      </div>
    </div></div>`);
    document.querySelectorAll(".lx-editor [data-person]").forEach(b => { b.onclick = () => go({ page: "team", c, t, p: b.dataset.person }); });
    // Where: a place (picked on the map, or typed) and a room.
    document.querySelectorAll(".gr-items [data-plc]").forEach(h => {
      const x = g.items.find(y => y.id === h.dataset.plc); if (!x) return;
      placeField(h, { ...placeOf(x), disabled: !edit, onChange: v => { if (v.place) x.place = v.place; else delete x.place; x.room = v.room; x.where = v.where; changed(); } });
    });
    if (!edit) return;
    const name = $("#gr-name");
    name.oninput = () => { g.name = name.value.trim(); $("#gr-h").textContent = sectionLabel(g); crumbs(); changed(); };
    document.querySelectorAll("[data-kind]").forEach(b => { b.onclick = () => { if (g.kind === b.dataset.kind) return; g.kind = b.dataset.kind; changed(); draw(); }; });
    const box = $(".gr-items");
    box.addEventListener("change", e => {
      const it = e.target.closest("[data-it]"), key2 = e.target.dataset.k; if (!it || !key2) return;
      const x = g.items.find(y => y.id === it.dataset.it); if (!x) return;
      if (key2 === "start" || key2 === "end") { const v = parseTime(e.target.value); if (v == null) { e.target.classList.add("bad"); toast("Type a time like 13:00 or 1 pm."); return; } e.target.classList.remove("bad"); x[key2] = v; e.target.value = v; }
      else if (key2 === "day") x.day = Number(e.target.value) || 0;
      else x[key2] = e.target.value.trim();
      changed();
    });
    box.addEventListener("click", e => { const del = e.target.closest("[data-del-it]"); if (del) { g.items = g.items.filter(y => y.id !== del.dataset.delIt); changed(); draw(); } });
    $("#gr-add").onclick = () => {
      const last = g.items[g.items.length - 1];
      const x = { id: uid(), day: 0, start: last ? last.start : "", end: last ? last.end : "", where: last ? last.where : "", ...(last && last.place ? { place: { ...last.place } } : {}), ...(last && (last.place || last.room) ? { room: last.room || "" } : {}) };
      g.items.push(x); changed(); draw();
      const sel = document.querySelector(`[data-it="${x.id}"] [data-k="day"]`); if (sel) sel.focus();
    };
    $("#gr-del").onclick = async () => {
      if (!await confirmBox(`Delete ${g.name || "this section"}?`, "Its times go from the course page, and its students aren't in it any more.", "Delete")) return;
      st.data.groups = st.data.groups.filter(y => y !== g); changed(); go({ page: "offering", c, t });
    };
  }

  load();   // afresh each time: who runs it is changed on people's pages
}
