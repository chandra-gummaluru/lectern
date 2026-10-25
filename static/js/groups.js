/* Activity groups: an offering's sections, each a set of weekly activities, e.g. LEC0101: its lectures on
   Monday, Wednesday and Friday at 13:00, and its tutorial on Thursday at 15:00. Each activity says who runs
   it (people on the teaching team). Every student is in one or more groups (the class list says which).

     The offering's page: the Activity Groups card (groupsCard), each group opening its page:
     #/<course>/<term>/groups/<id>     one group: its name, and its activities (type, day, times, where, who)

   Kept in the offering's private files, <course>/<term>/groups.json:

     { "format": "lectern-groups/1",
       "groups": [ { "id", "name": "LEC0101",
                     "items": [ { "id", "kind": "lecture", "day": 1, "start": "13:00", "end": "14:00",
                                  "where": "BA 1170", "people": ["12"] } ] } ] }

   An offering without one starts from its team's older times (team.json: each person's lectures, tutorials
   and labs, by their group), and becomes a groups.json with the first change. Office hours aren't in groups:
   they're each person's own (their page). The course page (server/hub.py) shows each group with its times. */

import { parseTime } from "./when.js";

export const GROUP_KINDS = [["lecture", "Lecture"], ["tutorial", "Tutorial"], ["lab", "Lab"], ["other", "Other"]];
export const DAYS = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const DAY3 = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const KIND_NAME = Object.fromEntries(GROUP_KINDS);
const uid = () => Math.random().toString(36).slice(2, 10);
const ic = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const KIND_ICON = {
  lecture: ic('<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8"/>'),
  tutorial: ic('<path d="M4 5h11a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3v-3H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M19 9h1a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-1v3l-3-3h-3"/>'),
  lab: ic('<path d="M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7.5 15h9"/>'),
  other: ic('<circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="8.5"/>'),
};
export const GROUP_ICON = ic('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>');
const CARET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const kindOf = x => (KIND_NAME[x.kind] ? x.kind : "other");
const hm = x => (x.start ? (x.end ? `${x.start}–${x.end}` : x.start) : "");
// "Mon 13:00–14:00" (and where), for a list.
export const itemText = x => [DAY3[x.day] || "", hm(x)].filter(Boolean).join(" ") + (x.where ? ` · ${x.where}` : "");
// A group in a line: "3 lectures, 1 tutorial · Mon, Wed, Fri 13:00–14:00…"
export function groupSummary(g) {
  const I = g.items || [];
  if (!I.length) return "No activities yet";
  const n = {}; I.forEach(x => { const k = kindOf(x); n[k] = (n[k] || 0) + 1; });
  const what = GROUP_KINDS.filter(([k]) => n[k]).map(([k, name]) => `${n[k]} ${name.toLowerCase()}${n[k] === 1 ? "" : k === "other" ? "" : "s"}`).join(", ");
  const days = [...new Set(I.slice().sort((a, b) => (a.day || 9) - (b.day || 9)).map(x => DAY3[x.day]).filter(Boolean))].join(", ");
  return [what, days].filter(Boolean).join(" · ");
}

// ── Reading and writing groups.json ──────────────────────────────────
const blank = () => ({ format: "lectern-groups/1", groups: [] });
function clean(d) {
  if (!d || !Array.isArray(d.groups)) d = blank();
  d.groups = d.groups.filter(g => g && typeof g === "object").map(g => ({ ...g, id: String(g.id || uid()), name: String(g.name || ""), items: (Array.isArray(g.items) ? g.items : []).filter(x => x && typeof x === "object").map(x => ({ ...x, id: String(x.id || uid()), people: (Array.isArray(x.people) ? x.people : []).map(String) })) }));
  return d;
}
// From team.json's older times: each person's lectures, tutorials and labs, put in groups by their group's name.
function fromTeam(team) {
  const d = blank(), byName = new Map();
  Object.entries((team && team.people) || {}).forEach(([pid, me]) => ((me && me.times) || []).forEach(x => {
    if (!x || x.kind === "office") return;
    const name = String(x.section || "").trim() || (KIND_NAME[x.kind] || "Other");
    let g = byName.get(name.toLowerCase());
    if (!g) { g = { id: uid(), name, items: [] }; byName.set(name.toLowerCase(), g); d.groups.push(g); }
    const same = g.items.find(y => y.kind === kindOf(x) && y.day === Number(x.day) && y.start === (x.start || "") && y.end === (x.end || "") && y.where === (x.where || ""));
    if (same) { if (!same.people.includes(pid)) same.people.push(pid); }
    else g.items.push({ id: uid(), kind: kindOf(x), day: Number(x.day) || 0, start: x.start || "", end: x.end || "", where: x.where || "", people: [pid] });
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
export async function changeGroups(Store, repo, c, t, fn, msg = "Activity groups") {
  for (let k = 0; ; k++) {
    const { data, sha } = await readGroups(Store, repo, c, t);
    const r = fn(data);
    if (r === false) return { data, changed: false };
    try { await Store.writeText(repo, `${c}/${t}/groups.json`, JSON.stringify(data, null, 1) + "\n", msg, sha); return { data, changed: true, r }; }
    catch (e) { if (!e.conflict || k) throw e; }
  }
}
// Groups by name (any case), making the ones that aren't there yet: for a class list's sections.
export async function groupIdsFor(Store, repo, c, t, names) {
  const want = [...new Set(names.map(n => String(n || "").trim()).filter(Boolean))];
  if (!want.length) return new Map();
  const { data } = await changeGroups(Store, repo, c, t, d => {
    let added = false;
    want.forEach(n => { if (!d.groups.some(g => g.name.toLowerCase() === n.toLowerCase())) { d.groups.push({ id: uid(), name: n, items: [] }); added = true; } });
    return added ? undefined : false;
  }, "Activity groups (from a class list)");
  return new Map(data.groups.map(g => [g.name.toLowerCase(), g.id]));
}

// ── The card on the offering's page ──────────────────────────────────
export async function groupsCard(ctx, c, t) {
  const { box, esc, toast, modal, go, Store, repo, lead, ICON, here, students } = ctx;
  let G, S = [];
  try { [G, S] = await Promise.all([readGroups(Store, repo, c, t), students().catch(() => [])]); }
  catch (e) { if (here()) box.innerHTML = `<p class="lt-note err">Couldn't read the activity groups. ${esc(e.message)}</p>`; return; }
  if (!here()) return;
  const count = id => S.filter(s => !s.dropped && (s.groups || []).includes(id)).length;
  const groups = G.data.groups.slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  box.innerHTML = `<div class="lt-st-head"><p class="lt-part-text">The course's sections, e.g. LEC0101: each a group of weekly lectures, tutorials and labs, with who runs each one. Every student is in one or more groups.</p>
      ${lead ? `<div class="lt-st-acts"><button type="button" class="lt-btn add" id="lt-group-new">${ICON.plus}Add an Activity Group</button></div>` : ""}</div>
    ${groups.length ? `<div class="lt-olist lt-groups">${groups.map(g => { const n = count(g.id); return `<div class="lt-orow lt-user"><button type="button" class="lt-user-who lt-user-open" data-group="${esc(g.id)}"><b>${esc(g.name || "Untitled group")}</b><span>${esc(groupSummary(g))}</span></button>
      <span class="lt-orow-r lt-group-n">${n} student${n === 1 ? "" : "s"}</span></div>`; }).join("")}</div>` : `<p class="lt-hint">No activity groups yet.</p>`}`;
  box.querySelectorAll("[data-group]").forEach(b => { b.onclick = () => go({ page: "groups", c, t, g: b.dataset.group }); });
  const add = box.querySelector("#lt-group-new");
  if (add) add.onclick = () => modal(`<h2>Add an Activity Group</h2>
      <div class="lt-form"><label>Name<input type="text" id="gr-name" placeholder="e.g. LEC0101" autocomplete="off" spellcheck="false"><small>Its section, as the class list names it.</small></label></div>
      <p class="lt-err" id="gr-err"></p>
      <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn primary" data-ok>Add</button></div>`, (m, close) => {
    const inp = m.querySelector("#gr-name"), err = m.querySelector("#gr-err");
    m.querySelector("[data-no]").onclick = close;
    const ok = async () => {
      const name = inp.value.trim(); if (!name) { err.textContent = "Give it a name, e.g. LEC0101."; return inp.focus(); }
      const id = uid();
      try {
        const r = await changeGroups(Store, repo, c, t, d => { if (d.groups.some(g => g.name.toLowerCase() === name.toLowerCase())) return false; d.groups.push({ id, name, items: [] }); });
        if (!r.changed) { err.textContent = `There's a group called ${name} already.`; return; }
      } catch (e) { err.textContent = `Couldn't save it. ${e.message}`; return; }
      close(); go({ page: "groups", c, t, g: id });
    };
    m.querySelector("[data-ok]").onclick = ok;
    inp.addEventListener("keydown", e => { if (e.key === "Enter") ok(); });
    inp.focus();
  });
}

// ── A group's page ───────────────────────────────────────────────────
export function groupPage(ctx, r) {
  const { $, esc, pageHTML, toast, confirmBox, go, Store, repo, canEdit, ICON, renderPath, steps, team, students } = ctx;
  const { c, t } = r, edit = canEdit(c, t), key = `${r.o || ""}/${c}/${t}`;
  const here = () => { const x = ctx.route(); return x.page === "groups" && x.c === c && x.t === t && x.g === r.g; };
  const st = (groupPage.state = groupPage.state && groupPage.state.key === key ? groupPage.state : { key, data: null, sha: undefined });

  async function load() {
    pageHTML(`<div class="lt-in"><div class="lt-loading" style="min-height:200px">Reading the activity groups…</div></div>`);
    try {
      const [G, P, S] = await Promise.all([readGroups(Store, repo, c, t), team().catch(() => []), students().catch(() => [])]);
      st.data = G.data; st.sha = G.sha; st.people = P; st.students = S;
    } catch (e) { if (here()) pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't read the activity groups. ${esc(e.message)}</p></div>`); return; }
    if (here()) draw();
  }
  let timer = 0, saving = null, again = false;
  function changed() { status("Saving…"); clearTimeout(timer); timer = setTimeout(save, 500); }
  async function save() {
    if (saving) { again = true; return; }
    saving = (async () => {
      try { st.sha = await Store.writeText(repo, `${c}/${t}/groups.json`, JSON.stringify(st.data, null, 1) + "\n", "Activity groups", st.sha); status("Saved"); }
      catch (e) { status("Not saved", true); toast(e.conflict ? "The activity groups were changed somewhere else. Reload this page to see them; your last change wasn't saved." : `Couldn't save. ${e.message}`); }
      finally { saving = null; if (again) { again = false; save(); } }
    })();
  }
  function status(text, bad) { const el = $("#gr-status"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }

  function draw() {
    const g = st.data.groups.find(x => x.id === r.g);
    if (!g) { renderPath([...steps, { label: "Activity group" }]); pageHTML(`<div class="lt-in"><p class="lt-note">This activity group isn't there any more.</p></div>`); return; }
    const crumbs = () => renderPath([...steps, { label: g.name || "Untitled group" }]); crumbs();
    const dis = edit ? "" : " disabled", P = st.people || [], n = (st.students || []).filter(s => !s.dropped && (s.groups || []).includes(g.id)).length;
    const opt = (list, v) => list.map(([k, nm]) => `<option value="${k}"${String(v) === String(k) ? " selected" : ""}>${esc(nm)}</option>`).join("");
    const days = DAYS.slice(1).map((d, k) => [String(k + 1), d]);
    const items = g.items.slice().sort((a, b) => (a.day || 9) - (b.day || 9) || String(a.start).localeCompare(String(b.start)));
    // Who runs it: a dropdown of the teaching team, each ticked or not.
    const whoText = x => { const n = (x.people || []).map(id => (P.find(p => String(p.id) === String(id)) || {}).name).filter(Boolean); return n.length ? n.join(", ") : "No one yet"; };
    const row = x => `<div class="gr-item" data-it="${esc(x.id)}">
        <span class="lx-kicon" aria-hidden="true">${KIND_ICON[kindOf(x)]}</span>
        <div class="gr-item-b">
          <div class="gr-grid">
            <label class="lx-f">Type<select data-k="kind"${dis}>${opt(GROUP_KINDS, kindOf(x))}</select></label>
            <label class="lx-f">Day<select data-k="day"${dis}><option value="0"${x.day ? "" : " selected"}>Choose</option>${opt(days, x.day)}</select></label>
            <label class="lx-f">Starts<input type="text" data-k="start" value="${esc(x.start || "")}" placeholder="e.g. 1 pm" autocomplete="off"${dis}></label>
            <label class="lx-f">Ends<input type="text" data-k="end" value="${esc(x.end || "")}" placeholder="e.g. 2 pm" autocomplete="off"${dis}></label>
            <label class="lx-f">Where<input type="text" data-k="where" value="${esc(x.where || "")}" placeholder="e.g. BA 1170" autocomplete="off"${dis}></label>
          </div>
          <div class="gr-who"><span class="lx-f">Run by<span class="gr-dd">${P.length ? `<button type="button" class="gr-dd-btn" data-who-open aria-haspopup="listbox" aria-expanded="false"${dis}><span>${esc(whoText(x))}</span>${CARET}</button>` : `<span class="lt-hint">No one on the teaching team yet.</span>`}</span></span></div>
        </div>
        ${edit ? `<button type="button" class="lx-ic quiet" data-del-it="${esc(x.id)}" title="Remove this activity" aria-label="Remove this activity">${ICON.trash}</button>` : ""}
      </div>`;
    pageHTML(`<div class="lt-in"><div class="lx ed">
      ${edit ? "" : `<p class="lt-note lx-note">As a TA you can look at the activity groups; the instructors change them.</p>`}
      <div class="lx-editor" style="--c:#c99a06">
        <div class="lx-ed-head"><span class="lx-kicon big" aria-hidden="true">${GROUP_ICON}</span><h2 id="gr-h">${esc(g.name || "Untitled group")}</h2>
          <span class="lx-acts">${edit ? `<span class="lx-status" id="gr-status"></span><button type="button" class="lx-ic" id="gr-del" title="Delete this activity group" aria-label="Delete this activity group">${ICON.trash}</button>` : ""}</span></div>
        <div class="lx-grid one"><label class="lx-f">Name<input type="text" id="gr-name" value="${esc(g.name)}" placeholder="e.g. LEC0101"${dis}></label></div>
        <p class="lx-help">${n} student${n === 1 ? " is" : "s are"} in it: the class list says who (Students, on the offering's page).</p>
        <h3 class="lx-sec">Activities</h3>
        <p class="lx-help">Each one every week of the term, and who runs it. The course page shows the group with its times.</p>
        <div class="gr-items">${items.map(row).join("") || `<p class="lx-none gr-none">No activities yet.</p>`}</div>
        ${edit ? `<div class="lx-adds"><button type="button" class="lx-btn add" id="gr-add">${ICON.plus}Add an Activity</button></div>` : ""}
      </div>
    </div></div>`);
    if (!edit) return;
    const name = $("#gr-name");
    name.oninput = () => { g.name = name.value.trim(); $("#gr-h").textContent = g.name || "Untitled group"; crumbs(); changed(); };
    const box = $(".gr-items");
    box.addEventListener("change", e => {
      const it = e.target.closest("[data-it]"), k = e.target.dataset.k; if (!it || !k) return;
      const x = g.items.find(y => y.id === it.dataset.it); if (!x) return;
      if (k === "start" || k === "end") { const v = parseTime(e.target.value); if (v == null) { e.target.classList.add("bad"); toast("Type a time like 13:00 or 1 pm."); return; } e.target.classList.remove("bad"); x[k] = v; e.target.value = v; }
      else if (k === "day") x.day = Number(e.target.value) || 0;
      else if (k === "kind") { x.kind = e.target.value; it.querySelector(".lx-kicon").innerHTML = KIND_ICON[kindOf(x)]; }
      else x[k] = e.target.value.trim();
      changed();
    });
    let pop = null;
    const close = () => { if (pop) { pop.closest(".gr-dd").querySelector("[data-who-open]").setAttribute("aria-expanded", "false"); pop.remove(); pop = null; } };
    document.addEventListener("mousedown", e => { if (pop && !e.target.closest(".gr-dd")) close(); });
    document.addEventListener("keydown", e => { if (pop && e.key === "Escape") close(); });
    box.addEventListener("change", e => {
      const cb = e.target.closest("[data-who]"); if (!cb) return;
      const it = cb.closest("[data-it]"), x = g.items.find(y => y.id === it.dataset.it), id = String(cb.dataset.who);
      x.people = cb.checked ? [...new Set([...(x.people || []).map(String), id])] : (x.people || []).map(String).filter(p => p !== id);
      it.querySelector("[data-who-open] span").textContent = whoText(x); changed();
    });
    box.addEventListener("click", e => {
      const openB = e.target.closest("[data-who-open]"), del = e.target.closest("[data-del-it]");
      if (openB) {
        const was = pop && pop.closest(".gr-dd") === openB.closest(".gr-dd"); close(); if (was) return;
        const x = g.items.find(y => y.id === openB.closest("[data-it]").dataset.it);
        pop = document.createElement("div"); pop.className = "gr-dd-pop"; pop.setAttribute("role", "listbox"); pop.setAttribute("aria-multiselectable", "true");
        pop.innerHTML = P.map(p => `<label class="gr-dd-opt"><input type="checkbox" data-who="${esc(p.id)}"${(x.people || []).map(String).includes(String(p.id)) ? " checked" : ""}><span>${esc(p.name || p.email)}</span></label>`).join("");
        openB.after(pop); openB.setAttribute("aria-expanded", "true");
        return;
      }
      if (del) { g.items = g.items.filter(y => y.id !== del.dataset.delIt); changed(); draw(); }
    });
    $("#gr-add").onclick = () => {
      const last = g.items[g.items.length - 1];
      const x = { id: uid(), kind: last ? kindOf(last) : "lecture", day: 0, start: last ? last.start : "", end: last ? last.end : "", where: last ? last.where : "", people: last ? (last.people || []).slice() : [] };
      g.items.push(x); changed(); draw();
      const sel = document.querySelector(`[data-it="${x.id}"] [data-k="day"]`); if (sel) sel.focus();
    };
    $("#gr-del").onclick = async () => {
      if (!await confirmBox(`Delete ${g.name || "this group"}?`, "Its activities go from the course page, and its students aren't in it any more.", "Delete")) return;
      st.data.groups = st.data.groups.filter(y => y !== g); changed(); go({ page: "offering", c, t });
    };
  }

  if (st.data && st.data.groups.some(x => x.id === r.g)) draw(); else load();
}
