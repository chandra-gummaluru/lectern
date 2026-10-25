/* Announcements: written here, and the course page shows each one in the week its date falls in
   (Announcements, and This week). It looks and works like the Gradebook's Evaluations: a list of long
   cards, newest first, and each one's page.

     #/<course>/<term>/announcements          every announcement, newest first
     #/<course>/<term>/announcements/<id>     one: its title, date and time, and message

   Kept in the offering's private files, <course>/<term>/announcements.json:

     { "format": "lectern-announcements/1",
       "items": [ { "id", "title", "date": "Oct 24, 2026, 13:48", "at": 1792860000000, "body": "Markdown" } ] }

   An offering without one starts from its course page's announcements (course.json), and becomes an
   announcements.json with the first change. Changes save by themselves. Instructors write them; TAs see them. */

import { readStamp, writeStamp, whenText, COPY } from "./lectures.js";
import { whenField } from "./when.js";
import { richText } from "./richtext.js";
import { pickMany, pickOne } from "./pick.js";
import { SECTION_ICON, SECTION_NAME, sectionKind, sortSections, runsSection } from "./groups.js";
import { KIND_ICON, EV_ICON, EV_TYPES } from "./lectures.js";
// Its sections (only their students see it; none: everyone). (Older ones had one, "group".)
const groupsOf = x => (Array.isArray(x.groups) ? x.groups.map(String) : x.group ? [String(x.group)] : []);

const COLOR = "#c99a06";
const uid = () => Math.random().toString(36).slice(2, 10);
const MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = n => String(n).padStart(2, "0");
const stampOf = d => `${MON3[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
const timeOf = a => { const t = Date.parse(String(a.date || "")); return isNaN(t) ? a.at || 0 : t; };
// A line of the message, for the list: without its Markdown.
const plain = s => String(s || "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[*_`#>]+/g, "").replace(/^\s*[-+]\s+/gm, "").replace(/\s+/g, " ").trim();

function fromCoursePage(page) {
  const items = [];
  ((page && page.sections) || []).filter(s => s && s.type === "schedule").forEach(s => (s.weeks || []).forEach(w => (w && w.announcements || []).forEach(a => {
    if (a && ((a.title || "").trim() || (a.body || "").trim())) items.push({ id: uid(), title: a.title || "", date: a.date || "", at: a.at || 0, body: a.body || "" });
  })));
  return { format: "lectern-announcements/1", items };
}

export function announcementsPage(ctx, r) {
  const { $, esc, pageHTML, toast, confirmBox, go, Store, area, canEdit, ICON, renderPath, steps, markdown } = ctx;
  const { c, t } = r, path = `${c}/${t}/announcements.json`, repo = area(Store.PRIV), edit = canEdit(c, t);
  // An instructor writes only for their sections (the ones they run): one for one of
  // those groups, or about one of those groups' activities. Everyone's, and other groups', are the coordinators'.
  const lim = () => { const L = new Set(); if (!edit) (st.groups || []).forEach(g => { if (runsSection(g, ctx.me)) L.add(g.id); }); return L; };
  const forOf = x => { const on = String(x.on || ""); if (on.startsWith("act:")) { const a = (st.acts || []).find(y => `act:${y.id}` === on); return a ? a.groups || [] : []; } return groupsOf(x); };
  const mayAnn = x => { if (edit) return true; const L = lim(), G = forOf(x); return G.length > 0 && G.every(g => L.has(g)); };
  // (Instructors write theirs into the course's announcements, once a coordinator has started them.)
  const mayAdd = () => edit || (lim().size > 0 && st.sha !== null);
  const key = `${r.o || ""}/${c}/${t}`;
  const here = () => { const x = ctx.route(); return x.page === "announcements" && x.c === c && x.t === t; };
  const st = (announcementsPage.state = announcementsPage.state && announcementsPage.state.key === key ? announcementsPage.state : { key, data: null, sha: undefined });

  async function load() {
    pageHTML(`<div class="lt-in"><div class="lt-loading" style="min-height:200px">Reading the announcements…</div></div>`);
    try {
      // What one can be about, and who it's for, first: the page may be drawn again as soon as there's data.
      const [G, A, E] = await Promise.all([ctx.groups ? ctx.groups().catch(() => []) : [], ctx.activities ? ctx.activities().catch(() => []) : [], ctx.evaluations ? ctx.evaluations().catch(() => []) : []]);
      st.groups = G; st.acts = A; st.evals = E;
      const f = await Store.readFile(repo, path);
      if (f) { st.data = JSON.parse(f.text); st.sha = f.sha; }
      else {
        const pg = await Store.readText(area(Store.PUB), `${c}/${t}/course.json`).catch(() => null);
        let page = null; try { page = pg ? JSON.parse(pg).page : null; } catch (_) {}
        st.data = fromCoursePage(page); st.sha = null;
      }
      if (!Array.isArray(st.data.items)) st.data.items = [];
    } catch (e) { if (here()) pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't read the announcements. ${esc(e.message)}</p></div>`); return; }
    if (here()) draw();
  }

  // Saving: a moment after each change, one save at a time, kept with the offering's announcements (not this
  // drawing of the page: opening another announcement mustn't start a second save beside the first).
  function changed() { status("Saving…"); clearTimeout(st.timer); st.timer = setTimeout(save, 500); }
  async function save() {
    if (st.saving) { st.again = true; return; }
    st.saving = (async () => {
      try { st.sha = await Store.writeText(repo, path, JSON.stringify(st.data, null, 1) + "\n", "Announcements", st.sha); status("Saved"); }
      catch (e) { status("Not saved", true); toast(e.conflict ? "The announcements were changed somewhere else. Reload this page to see them; your last change wasn't saved." : `Couldn't save. ${e.message}`); }
      finally { st.saving = null; if (st.again) { st.again = false; save(); } }
    })();
  }
  function status(text, bad) { const el = $("#an-status"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }
  const status$ = () => (mayAdd() ? `<span class="lx-status" id="an-status"></span>` : "");
  const taNote = (x = null) => (!edit && !x && lim().size && st.sha === null ? `<p class="lt-note lx-note">You can write announcements for your sections once a coordinator has written the course's first one here.</p>` : (edit || (x ? mayAnn(x) : mayAdd()) ? (edit || x ? "" : `<p class="lt-note lx-note">You can write announcements for your activity groups; the coordinators write everyone's.</p>`) : `<p class="lt-note lx-note">You can read ${x ? "this announcement" : "the announcements"}; ${x ? "it's someone else's" : "the coordinators and instructors write them"}.</p>`));
  const whenOf = x => whenText(x.date, true) || "No date yet";

  function draw() {
    const a = r.a && st.data.items.find(x => x.id === r.a);
    return a ? drawOne(a) : drawList();
  }

  function drawList() {
    renderPath([...steps, { label: "Announcements" }]);
    const list = st.data.items.slice().sort((x, y) => timeOf(y) - timeOf(x));
    pageHTML(`<div class="lt-in"><div class="lx">
      <div class="lx-head"><h1>Announcements</h1><span class="spacer"></span>${status$()}${mayAdd() ? `<button type="button" class="lx-btn add" id="an-new">${ICON.plus}New Announcement</button>` : ""}</div>
      ${taNote()}
      ${list.length ? `<div class="lx-list">${list.map(x => `<div class="lx-row" style="--c:${COLOR}" data-an="${esc(x.id)}" role="button" tabindex="0">
          <div class="lx-main"><div class="lx-top"><h3>${esc(x.title || "Untitled")}</h3></div>
            <p class="lx-when">${esc(whenOf(x))}</p>${plain(x.body) ? `<p class="lx-clip">${esc(plain(x.body))}</p>` : ""}</div></div>`).join("")}</div>`
        : `<div class="lx-empty">No announcements yet.${edit ? " Write the first one: the course page shows it in the week of its date." : ""}</div>`}
    </div></div>`);
    document.querySelectorAll("[data-an]").forEach(b => {
      const open = () => go({ page: "announcements", c, t, a: b.dataset.an });
      b.onclick = e => { if (e.target.closest("a, button")) return; open(); };
      b.onkeydown = e => { if ((e.key === "Enter" || e.key === " ") && e.target === b) { e.preventDefault(); open(); } };
    });
    if (!mayAdd()) return;
    document.querySelectorAll("[data-dup]").forEach(b => { b.onclick = e => {
      e.stopPropagation();
      const x = st.data.items.find(y => y.id === b.dataset.dup); if (!x) return;
      const y = { ...x, id: uid(), title: x.title ? `${x.title} (copy)` : "", date: stampOf(new Date()), at: Date.now() };
      st.data.items.push(y); changed(); go({ page: "announcements", c, t, a: y.id });
    }; });
    $("#an-new").onclick = () => {
      const x = { id: uid(), title: "", date: stampOf(new Date()), at: Date.now(), body: "", ...(edit ? {} : { groups: [...lim()].slice(0, 1) }) };
      st.data.items.push(x); changed(); go({ page: "announcements", c, t, a: x.id });
    };
  }

  function drawOne(x) {
    const crumbs = () => renderPath([...steps, { label: "Announcements", go: () => go({ page: "announcements", c, t }) }, { label: x.title || "New announcement" }]);
    crumbs();
    const edit = mayAnn(x), L = lim();   // (here: may this one be changed)
    const when = readStamp(x.date), dis = edit ? "" : " disabled";
    pageHTML(`<div class="lt-in"><div class="lx ed">
      ${taNote(x)}
      <div class="lx-editor" style="--c:${COLOR}">
        <div class="lx-ed-head"><h2 id="an-h">${esc(x.title || "New announcement")}</h2>
          <span class="lx-acts">${status$()}${edit ? `<button type="button" class="lx-ic" id="an-del" title="Delete this announcement" aria-label="Delete this announcement">${ICON.trash}</button>` : ""}</span></div>
        <h3 class="lx-sec lx-first">General</h3>
        <div class="lx-grid one"><label class="lx-f">Title<input type="text" id="an-title" value="${esc(x.title)}" placeholder="e.g. Midterm rooms posted"${dis}></label></div>
        <div class="lx-grid two an-row">
          <div class="lx-f">About<div id="an-on-f"></div></div>
          <div class="lx-f">For<div id="an-groups"></div></div>
        </div>
        <h3 class="lx-sec">Date</h3>
        <div class="lx-grid two"><div class="lx-f">When<div id="an-when-f"></div></div></div>
        <p class="lx-help">The course page shows it in the week this date is in (Announcements, and This week), newest first.</p>
        <h3 class="lx-sec">Message</h3>
        <div id="an-body"></div>
      </div>
    </div></div>`);
    whenField($("#an-when-f"), { date: when.date, time: when.time, id: "an-when", label: "When", empty: "Choose a date", timeLabel: "At", disabled: !edit,
      onChange: ({ date, time }) => { x.date = date ? writeStamp(date, time) : ""; changed(); } });
    richText($("#an-body"), { value: x.body, placeholder: "Write it here.", label: "Message", disabled: !edit, onChange: v => { x.body = v; changed(); } });
    // Who it's for: everyone, or sections (several, if need be); about an activity, the activity's own students.
    const forSel = () => {
      const act = String(x.on || "").startsWith("act:") ? (st.acts || []).find(a => `act:${a.id}` === x.on) : null;
      const G = (st.groups || []).slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })), gname = id => ((G.find(g => g.id === id) || {}).name || "");
      const host = $("#an-groups");
      if (act) {
        pickMany(host, { options: [], value: [], empty: (act.groups || []).length ? `${act.groups.map(gname).filter(Boolean).join(", ")}, as its activity is` : "Everyone, as its activity is", id: "an-group", disabled: true });
      } else {
        pickMany(host, { options: G.filter(g => canEdit(c, t) || !edit || L.has(g.id)).map(g => ({ value: g.id, label: g.name || "Untitled section", kick: SECTION_NAME[sectionKind(g)], icon: SECTION_ICON[sectionKind(g)] })), value: groupsOf(x), id: "an-group", label: "For", allowEmpty: canEdit(c, t), emptyHint: "Every student sees it",
          empty: canEdit(c, t) || !edit ? "Everyone in the course" : "Pick your sections", disabled: !edit,
          onChange: v => { delete x.group; if (v.length) x.groups = v; else delete x.groups; changed(); } });
      }
    };
    forSel();
    // What it's about: an activity (under its week) or an evaluation, each with its icon, or nothing in particular.
    const KN = { lecture: "Lecture", tutorial: "Tutorial", lab: "Lab", other: "Other" };
    const aboutOpts = [
      ...(st.acts || []).filter(a => canEdit(c, t) || !edit || ((a.groups || []).length && a.groups.every(g => L.has(g))) || x.on === `act:${a.id}`)
        .map(a => ({ value: `act:${a.id}`, label: a.name, kick: KN[a.kind] || "Activity", icon: KIND_ICON[a.kind] || KIND_ICON.other, group: a.week })),
      ...(st.evals || []).map(e => ({ value: `eval:${e.id}`, label: e.title || e.name, kick: e.title ? e.name : EV_TYPES[e.type] || "Evaluation", icon: EV_ICON[e.type] || EV_ICON.assignment, group: "Evaluations" })),
    ];
    pickOne($("#an-on-f"), { options: aboutOpts, value: x.on || "", empty: "Nothing in particular", emptyHint: "A general announcement", search: "Search activities and evaluations", id: "an-on", label: "About",
      disabled: !edit, onChange: v => onChange(v) });
    if (!edit) return;
    const onChange = val => { if (val) x.on = val; else delete x.on; if (String(x.on || "").startsWith("act:")) { delete x.group; delete x.groups; } else if (!canEdit(c, t) && !groupsOf(x).length) x.groups = [...L].slice(0, 1); forSel(); changed(); };
    let shown = x.title || "New announcement";
    const head = () => { const now = x.title || "New announcement"; if (now === shown) return; shown = now; $("#an-h").textContent = now; crumbs(); };
    $("#an-title").oninput = $("#an-title").onchange = e => { x.title = e.target.value.trim(); head(); changed(); };
    $("#an-del").onclick = async () => {
      if (!await confirmBox("Delete this announcement?", "It goes from the course page.", "Delete")) return;
      st.data.items = st.data.items.filter(y => y !== x); changed(); go({ page: "announcements", c, t });
    };
  }

  if (st.data) draw(); else load();
}
