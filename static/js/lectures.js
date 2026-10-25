/* Activities: an offering's weeks and the activities in them (lectures, tutorials, labs and other ones), made and
   changed here; the course page (Activities and This week) shows them. An activity can go with one of the
   gradebook's evaluations (e.g. a lab with its lab report). (The file and its addresses keep the older name:
   lectures.json, #/<course>/<term>/lectures or /activities.) It looks and works like the Gradebook's Evaluations: each week
   is a group card with its activities as sub-cards, and you drag an activity to another place or another
   week, and a week (or a divider) to another place in the term.

     #/<course>/<term>/activities                   every week, each with its activities
     #/<course>/<term>/activities/<week>            a week: its name, dates and topic, and its activities
     #/<course>/<term>/activities/<week>/<activity> an activity: its type, label, title, when, evaluation, description, files

   Kept in the offering's private files, <course>/<term>/lectures.json (the hub reads it; nothing else of
   the private files reaches students):

     { "format": "lectern-lectures/1",
       "weeks": [ { "id", "label": "Week 1", "start": "2026-09-07", "end": "2026-09-11", "topic",
                    "cards": [ { "id", "kind": "lecture", "label": "Lecture 01", "title", "description",
                                 "date": "Sep 9, 2026, 10:00", "files": [ { "label", "url" } ], "eval": "<evaluation id>"? } ] },
                  { "id", "isBreak": true, "text": "Reading Week" } ] }

   An offering without one starts from its course page's weeks (course.json), and becomes a lectures.json
   with the first change. Changes save by themselves. Instructors change it; TAs see it. */

import { richText } from "./richtext.js";
import { whenField } from "./when.js";
import { pickMany } from "./pick.js";
// An activity's activity groups (only their students see it; none: everyone). (Older ones had one, "group".)
export const groupsOf = x => (Array.isArray(x.groups) ? x.groups.map(String) : x.group ? [String(x.group)] : []);

const KINDS = [["lecture", "Lecture"], ["tutorial", "Tutorial"], ["lab", "Lab"], ["other", "Other"]];
const KIND_COLOR = { lecture: "#c99a06", tutorial: "#c99a06", lab: "#c99a06", other: "#c99a06" };   // one colour: types show by their icons
const ic = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
// Each type's icon: a lecture's board, a tutorial's conversation, a lab's flask, and a dot for the rest.
export const KIND_ICON = {
  lecture: ic('<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8"/>'),
  tutorial: ic('<path d="M4 5h11a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3v-3H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M19 9h1a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-1v3l-3-3h-3"/>'),
  lab: ic('<path d="M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7.5 15h9"/>'),
  other: ic('<circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="8.5"/>'),
};
const WEEK_COLOR = "#c99a06";
// An evaluation's icon and name, as the Gradebook's Evaluations has them.
const EV_TYPES = { assignment: "Assignment", test: "Test", project: "Project", lab: "Lab", other: "Other" };
const EV_ICON = {
  assignment: ic('<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h4"/>'),
  test: ic('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="m9 13 2 2 4-4"/>'),
  project: ic('<path d="m12 3 8.5 4.5L12 12 3.5 7.5z"/><path d="m3.5 12 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5"/>'),
  lab: ic('<path d="M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7.5 15h9"/>'),
  other: ic('<circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="8.5"/>'),
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"];
const DAYS3 = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const COPY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>';
const uid = () => Math.random().toString(36).slice(2, 10);
const fromIso = s => { const m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(s || ""); return m ? new Date(+m[1], m[2] - 1, +m[3]) : null; };
const isoDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (s, n) => { const d = fromIso(s); if (!d) return ""; d.setDate(d.getDate() + n); return isoDate(d); };
export function rangeText(start, end) {
  const a = fromIso(start), b = fromIso(end) || a;
  if (!a) return "";
  const A = `${MONTHS[a.getMonth()]} ${a.getDate()}`;
  if (+a === +b) return A;
  return a.getMonth() === b.getMonth() ? `${A} – ${b.getDate()}` : `${A} – ${MONTHS[b.getMonth()]} ${b.getDate()}`;
}
// A date: "Sep 9, 2026, 10:00" (the course page's form) ↔ { date: "2026-09-09", time: "10:00" }.
const MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function readStamp(t) {
  const m = /([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})(?:,?\s+(\d{1,2}):(\d\d))?/.exec(t || "");
  if (!m) return { date: "", time: "" };
  const d = new Date(`${m[1]} ${m[2]}, ${m[3]}`);
  return isNaN(d) ? { date: "", time: "" } : { date: isoDate(d), time: m[4] ? `${m[4].padStart(2, "0")}:${m[5]}` : "" };
}
export const writeStamp = (date, time) => { const d = fromIso(date); return d ? `${MON3[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}${time ? `, ${time}` : ""}` : ""; };
// "Wed, Sep 9 at 10:00", as Evaluations says when one is due.
export function whenText(stamp, year = false) {
  const { date, time } = readStamp(stamp), d = fromIso(date);
  return d ? `${DAYS3[d.getDay()]}, ${MON3[d.getMonth()]} ${d.getDate()}${year ? `, ${d.getFullYear()}` : ""}${time ? ` at ${time}` : ""}` : "";
}
// An activity's dates: one or more (e.g. a lab held on three days). "dates" when there are several; "date" is the first.
export const datesOf = c => (Array.isArray(c.dates) && c.dates.filter(Boolean).length ? c.dates.filter(Boolean) : c.date ? [c.date] : []);
function setDates(c, list) {
  const L = list.filter(Boolean);
  if (L.length) c.date = L[0]; else delete c.date;
  if (L.length > 1) c.dates = L; else delete c.dates;
}
const datesText = c => { const D = datesOf(c).map(s => [readStamp(s), s]).sort((a, b) => (a[0].date + a[0].time).localeCompare(b[0].date + b[0].time)).map(x => x[1]); return D.length > 1 ? D.map(s => whenText(s)).join(" · ") : whenText(D[0], true); };
const kindOf = c => c.kind || (KINDS.find(([, n]) => String(c.label || "").toLowerCase().startsWith(n.toLowerCase())) || ["lecture"])[0];
const kindName = k => (KINDS.find(x => x[0] === k) || KINDS[0])[1];

// "Lecture 07" → "Lecture 08"; the next of a kind is numbered after the last one of that kind before it.
function nextLabel(weeks, kind, beforeWeek = null) {
  const name = kindName(kind);
  if (kind === "other") return "";
  let last = null;
  for (const w of weeks) { if (w.isBreak) continue; for (const c of w.cards || []) if (kindOf(c) === kind) last = c; if (w === beforeWeek) break; }
  const m = last && /^(.*?)(\d+)(\D*)$/.exec(last.label || "");
  return m ? m[1] + String(Number(m[2]) + 1).padStart(m[2].length, "0") + m[3] : `${name} ${kind === "lecture" ? "01" : "1"}`;
}

// Lectures, tutorials and labs are named by their type, numbered in course order (Lecture 01, Tutorial 1…);
// only Other has a label of its own. An older label that isn't the usual one moves into the title.
function renumber(weeks) {
  const n = {};
  for (const w of weeks) { if (w.isBreak) continue; for (const x of w.cards || []) {
    const k = kindOf(x); x.kind = k; if (k === "other") continue;
    const name = kindName(k), lab = String(x.label || "").trim();
    // A label that's one of the types' own (Lecture 01, Tutorial 2…, e.g. from before a change of type) isn't kept;
    // and a title that a change of type once grew ("Tutorial 1: Lecture 01: Prologue") loses those.
    const AUTO = /^(lecture|tutorial|lab)\s*\d*$/i;
    if (lab && !AUTO.test(lab)) { const t = String(x.title || "").trim(); x.title = t ? `${lab}: ${t}` : lab; }
    if (x.title) x.title = String(x.title).replace(/^(\s*(lecture|tutorial|lab)\s*\d+\s*:\s*)+/i, "").trim() || x.title;
    n[k] = (n[k] || 0) + 1; x.label = `${name} ${k === "lecture" ? String(n[k]).padStart(2, "0") : n[k]}`;
  } }
}

// From a course page's weeks (course.json's schedule sections), the first time.
function fromCoursePage(page) {
  const weeks = [];
  ((page && page.sections) || []).filter(s => s && s.type === "schedule" && !s.hidden).forEach(s => (s.weeks || []).forEach(w => {
    if (!w) return;
    if (w.isBreak) { weeks.push({ id: uid(), isBreak: true, text: w.text || "" }); return; }
    weeks.push({ id: uid(), label: w.label || "", start: w.start || "", end: w.end || "", topic: w.topic || "",
      cards: (w.cards || []).map(c => ({ id: uid(), kind: kindOf(c), label: c.label || "", title: c.title || "", description: c.description || "",
        ...(c.date ? { date: c.date } : {}), ...(Array.isArray(c.dates) && c.dates.length > 1 ? { dates: c.dates.slice() } : {}), files: (c.files || []).filter(f => f && String(f.url || "").trim()).map(f => ({ label: f.label || "", url: f.url })) })) });
  }));
  return { format: "lectern-lectures/1", weeks };
}

// Dragging, as in Evaluations: the card itself becomes an empty dashed slot that moves through the list
// (the others slide out of its way); dropping keeps the order, cancelling puts everything back.
function slide(box, move, skip) {
  const kids = [...box.children], before = new Map(kids.map(k => [k, k.getBoundingClientRect().top]));
  move();
  kids.forEach(k => {
    if (k === skip || !k.isConnected) return;
    const dy = before.get(k) - k.getBoundingClientRect().top; if (!dy) return;
    k.style.transition = "none"; k.style.transform = `translateY(${dy}px)`;
    requestAnimationFrame(() => { k.style.transition = "transform .18s ease"; k.style.transform = ""; });
  });
}

export function lecturesPage(ctx, r) {
  const { $, esc, pageHTML, toast, confirmBox, go, Store, area, canEdit, ICON, renderPath, steps, uploadPublic } = ctx;
  const { c, t } = r;
  const path = `${c}/${t}/lectures.json`, repo = area(Store.PRIV);
  const key = `${r.o || ""}/${c}/${t}`;
  const edit = canEdit(c, t);
  // An instructor (ctx.myGroups: the activity groups they run an activity of) adds and changes only those
  // groups' activities; the weeks, and everyone's activities, are the coordinators'.
  const lim = edit ? null : new Set();   // (filled once the groups are read)
  const mayCard = x => edit || !!(lim && x && groupsOf(x).length && groupsOf(x).every(g => lim.has(g)));
  const mine = () => { if (lim) { lim.clear(); (st.groups || []).forEach(g => { if ((g.items || []).some(x => (x.people || []).map(String).includes(String(ctx.me)))) lim.add(g.id); }); } };
  // (Instructors add theirs to the course's weeks, once a coordinator has set them up here.)
  const mayAdd = () => edit || !!(lim && lim.size && st.sha !== null);
  const here = () => { const x = ctx.route(); return x.page === "lectures" && x.c === c && x.t === t && (x.o || "") === (r.o || ""); };
  const st = (lecturesPage.state = lecturesPage.state && lecturesPage.state.key === key ? lecturesPage.state : { key, data: null, sha: undefined, saving: null, dirty: false });
  if (st.groups) mine();

  async function load() {
    pageHTML(`<div class="lt-in"><div class="lt-loading" style="min-height:200px">Reading the activities…</div></div>`);
    // The evaluations and groups first: the page may be drawn again (by another view of it) as soon as there are weeks.
    try { st.evals = ctx.evaluations ? await ctx.evaluations() : []; } catch (_) { st.evals = []; }
    try { st.groups = ctx.groups ? await ctx.groups() : []; } catch (_) { st.groups = []; }
    mine();
    try {
      const f = await Store.readFile(repo, path);
      if (f) { st.data = JSON.parse(f.text); st.sha = f.sha; }
      else {
        const pg = await Store.readText(area(Store.PUB), `${c}/${t}/course.json`).catch(() => null);
        let page = null; try { page = pg ? JSON.parse(pg).page : null; } catch (_) {}
        st.data = fromCoursePage(page); st.sha = null;
      }
      if (!Array.isArray(st.data.weeks)) st.data.weeks = [];
    } catch (e) { if (here()) pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't read the activities. ${esc(e.message)}</p></div>`); return; }
    if (here()) draw();
  }

  // Saving: a moment after each change, one save at a time; a change made meanwhile is saved after it.
  let timer = 0;
  function changed() {
    renumber(weeks());
    st.dirty = true; status("Saving…");
    clearTimeout(timer); timer = setTimeout(save, 500);
  }
  async function save() {
    if (st.saving) { st.again = true; return; }
    st.saving = (async () => {
      try {
        st.dirty = false;
        st.sha = await Store.writeText(repo, path, JSON.stringify(st.data, null, 1) + "\n", "Activities", st.sha);
        status("Saved");
      } catch (e) {
        st.dirty = true;
        status(e.conflict ? "Not saved: changed elsewhere" : "Not saved", true);
        toast(e.conflict ? "The activities were changed somewhere else (another window, or someone on the team). Reload this page to see them; your last change wasn't saved." : `Couldn't save the activities. ${e.message}`);
      } finally { st.saving = null; if (st.again) { st.again = false; save(); } }
    })();
  }
  function status(text, bad) { const el = $("#lw-status"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }

  const weeks = () => st.data.weeks;
  const weekById = id => weeks().find(w => w.id === id);
  const realWeeks = () => weeks().filter(w => !w.isBreak);
  const allCards = () => new Map(weeks().flatMap(w => (w.cards || []).map(x => [x.id, x])));
  const weekLine = w => { const n = (w.cards || []).length; return [rangeText(w.start, w.end) || "No dates yet", w.topic, `${n} activit${n === 1 ? "y" : "ies"}`].filter(Boolean).join(" · "); };
  const titleOf = x => x.title || x.label || "Untitled";
  const nameOf = x => (x.title && x.label ? `${x.label}: ${x.title}` : titleOf(x));
  const PAPERCLIP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21 11-8.6 8.6a5 5 0 0 1-7-7L14 4a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4L15.5 7"/></svg>';
  const kindLabel = x => x.label || kindName(kindOf(x));   // above the title, e.g. LECTURE 07
  // Under the title: when it is (if it has a date) and its files; nothing about what it doesn't have.
  // Under the title: when it is, as Announcements says it (if it has a date); its description; then what goes with it.
  const plain = t => String(t || "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[*_`#>]+/g, "").replace(/^\s*([-+]|\d+[.)])\s+/gm, "").replace(/\s+/g, " ").trim();
  const lecMeta = x => { const n = (x.files || []).length; return [n ? `<span class="lx-files">${PAPERCLIP}${n} file${n === 1 ? "" : "s"}</span>` : ""].filter(Boolean).join('<span class="lx-sep">·</span>'); };
  const status$ = () => (mayAdd() ? `<span class="lx-status" id="lw-status">${st.dirty || st.saving ? "Saving…" : ""}</span>` : "");
  const taNote = () => (edit ? "" : lim && lim.size && st.sha === null ? `<p class="lt-note lx-note">You can add activities for your activity groups once a coordinator has set up the weeks here.</p>` : mayAdd() ? `<p class="lt-note lx-note">You can add and change the activities for your activity groups (${esc([...lim].map(groupName).filter(Boolean).join(", "))}); the coordinators change the weeks and everyone's.</p>` : `<p class="lt-note lx-note">You can look at the activities; the coordinators change them.</p>`);
  const toWeek = w => go({ page: "lectures", c, t, w: w.id });
  const toLec = (w, x) => go({ page: "lectures", c, t, w: w.id, l: x.id });

  function draw() {
    renumber(weeks());
    const w = r.w && weekById(r.w), x = w && r.l && (w.cards || []).find(y => y.id === r.l);
    if (r.l && x) return drawLecture(w, x);
    if (r.w && w) return drawWeek(w);
    return drawList();
  }

  // One lecture as a sub-card, inside its week.
  const lecRow = (w, x) => `<div class="lx-row sub lx-lec" style="--c:${KIND_COLOR[kindOf(x)]}" data-lec="${esc(x.id)}" data-w="${esc(w.id)}" role="button" tabindex="0"${edit ? ' draggable="true"' : ""}>
      <span class="lx-kicon" title="${esc(kindName(kindOf(x)))}">${KIND_ICON[kindOf(x)]}</span>
      <div class="lx-main"><p class="lx-kind">${esc(kindName(kindOf(x)))}${groupsOf(x).map(groupName).filter(Boolean).length ? ` · ${esc(groupsOf(x).map(groupName).filter(Boolean).join(", "))}` : ""}</p><h3>${esc(titleOf(x))}</h3>${datesText(x) ? `<p class="lx-when">${esc(datesText(x))}</p>` : ""}${plain(x.description) ? `<p class="lx-clip">${esc(plain(x.description))}</p>` : ""}${lecMeta(x) ? `<p class="lx-meta">${lecMeta(x)}</p>` : ""}</div></div>`;
  // An activity for one activity group (e.g. LEC0101) is only for its students; without one, it's everyone's.
  const groupName = id => (id && ((st.groups || []).find(g => g.id === id) || {}).name) || "";
  const mondayOf = s => { const d = fromIso(s); if (!d) return ""; d.setDate(d.getDate() - (d.getDay() + 6) % 7); return isoDate(d); };
  const weekEvals = w => {
    if (!w.start) return [];
    const R = realWeeks(), nx = R.slice(R.indexOf(w) + 1).find(y => y.start);
    const from = mondayOf(w.start), to = nx ? addDays(mondayOf(nx.start), -1) : addDays(mondayOf(w.end || w.start), 6);
    return (st.evals || []).filter(e => e.date && e.date >= from && e.date <= to).sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || "")));
  };
  const evWhen = e => { const d = fromIso(e.date); if (!d) return ""; const day = `${DAYS3[d.getDay()]}, ${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}, ${d.getFullYear()}`; return `${e.type === "test" ? "" : "Due "}${day}${e.time ? ` at ${e.time}` : ""}`; };
  // An evaluation dated this week (from the gradebook): it opens in the Evaluations.
  const evRow = e => `<div class="lx-row sub lx-lec lx-ev" data-ev="${esc(e.id)}" role="button" tabindex="0" title="Open ${esc(e.name)} in the Evaluations">
      <span class="lx-kicon" title="${esc(EV_TYPES[e.type] || "Assignment")}">${EV_ICON[e.type] || EV_ICON.assignment}</span>
      <div class="lx-main"><p class="lx-kind">${esc(EV_TYPES[e.type] || "Assignment")}${e.short ? ` / ${esc(e.short)}` : ""}</p><h3>${esc(e.name)}</h3><p class="lx-when">${esc(evWhen(e))}</p></div></div>`;
  const evsHTML = w => { const E = weekEvals(w); return E.length ? `<div class="lx-evs">${E.map(evRow).join("")}</div>` : ""; };
  const subsHTML = w => `<div class="lx-subs" data-subs="${esc(w.id)}">${(w.cards || []).map(x => lecRow(w, x)).join("")}<p class="lx-none">No activities this week.${edit ? " Open the week to add one, or drag one here." : ""}</p></div>`;

  // ── Every week ──
  function drawList() {
    renderPath([...steps, { label: "Activities" }]);
    const list = weeks();
    pageHTML(`<div class="lt-in"><div class="lx">
      <div class="lx-head"><h1>Activities</h1><span class="spacer"></span>${status$()}
        ${edit ? `<button type="button" class="lx-btn add" data-add-week>${ICON.plus}Add a Week</button>` : ""}</div>
      ${taNote()}
      ${list.length ? `<div class="lx-list" data-units>${list.map(w => (w.isBreak ? breakHTML(w) : weekHTML(w))).join("")}</div>` : `<div class="lx-empty">No weeks yet.${edit ? " Add the term's first week." : ""}</div>`}
    </div></div>`);
    wire($(".lx"));
    if (!edit) return;
    $("[data-add-week]").onclick = addWeek;
  }
  // A week's number, for the circle beside it: the number in its name ("Week 4"), else its place among the weeks.
  const weekNum = w => { const m = /(\d+)/.exec(w.label || ""); return m ? m[1] : String(realWeeks().indexOf(w) + 1); };
  const weekHTML = w => `<div class="lx-group" style="--c:${WEEK_COLOR}" data-unit="${esc(w.id)}"${edit ? ' draggable="true"' : ""}>
      <div class="lx-row grp" data-week="${esc(w.id)}" role="button" tabindex="0">
        <span class="lx-wnum" aria-hidden="true">${esc(weekNum(w))}</span>
        <div class="lx-main"><div class="lx-top"><h3>${esc(w.label || "Week")}</h3></div><p>${esc(weekLine(w))}</p></div></div>
      ${subsHTML(w)}${evsHTML(w)}
      <div class="lx-foot"></div>
    </div>`;
  const breakHTML = w => `<div class="lx-break" data-unit="${esc(w.id)}"${edit ? ' draggable="true"' : ""}>${edit
    ? `<input type="text" data-break-text="${esc(w.id)}" value="${esc(w.text || "")}" placeholder="e.g. Reading Week" aria-label="Divider"><button type="button" class="lx-ic quiet" data-del-break="${esc(w.id)}" title="Delete this divider" aria-label="Delete this divider">${ICON.trash}</button>`
    : `<b>${esc(w.text || "")}</b>`}</div>`;

  // Clicks, keys and dragging on a list of weeks (or one week's lectures).
  function wire(root) {
    const open = el => { if (el.dataset.lec) toLec(weekById(el.dataset.w), allCards().get(el.dataset.lec)); else if (el.dataset.week) toWeek(weekById(el.dataset.week)); };
    root.querySelectorAll("[data-ev]").forEach(el => {
      const open = () => ctx.openEval && ctx.openEval(el.dataset.ev);
      el.onclick = e => { e.stopPropagation(); open(); };
      el.onkeydown = e => { if ((e.key === "Enter" || e.key === " ") && e.target === el) { e.preventDefault(); open(); } };
    });
    root.querySelectorAll("[data-lec], [data-week]").forEach(el => {
      el.onclick = e => { if (e.target.closest("button, input")) return; e.stopPropagation(); open(el); };
      el.onkeydown = e => { if ((e.key === "Enter" || e.key === " ") && e.target === el) { e.preventDefault(); open(el); } };
    });
    if (!edit) return;
    root.querySelectorAll("[data-dup]").forEach(b => { b.onclick = e => { e.stopPropagation(); duplicate(weekById(b.dataset.w), allCards().get(b.dataset.dup)); }; });
    root.querySelectorAll("[data-break-text]").forEach(inp => { inp.oninput = () => { weekById(inp.dataset.breakText).text = inp.value; changed(); }; });
    root.querySelectorAll("[data-del-break]").forEach(b => { b.onclick = () => { st.data.weeks = weeks().filter(w => w.id !== b.dataset.delBreak); changed(); draw(); }; });
    dragging(root);
  }

  function dragging(root) {
    let d = null;   // { kind: "lec" | "unit", el, dropped }
    root.addEventListener("dragstart", e => {
      if (e.target.closest && e.target.closest("input, button")) { e.preventDefault(); return; }
      const lec = e.target.closest && e.target.closest("[data-lec][draggable]"), unit = !lec && e.target.closest && e.target.closest("[data-units] > [data-unit]");
      if (!lec && !unit) return;
      d = { kind: lec ? "lec" : "unit", el: lec || unit, dropped: false };
      e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", d.el.dataset.lec || d.el.dataset.unit);
      requestAnimationFrame(() => d && d.el.classList.add("dragging"));
      e.stopPropagation();
    });
    root.addEventListener("dragover", e => {
      if (!d) return;
      if (d.kind === "unit") {
        const over = e.target.closest && e.target.closest("[data-units] > [data-unit]");
        if (!over) return;
        e.preventDefault(); e.dataTransfer.dropEffect = "move";
        if (over === d.el) return;
        const rc = over.getBoundingClientRect(), ref = e.clientY > rc.top + rc.height / 2 ? over.nextElementSibling : over;
        if (ref === d.el || d.el.nextElementSibling === ref) return;
        slide(over.parentNode, () => over.parentNode.insertBefore(d.el, ref), d.el);
        return;
      }
      // A lecture: over another lecture (before or after it), or anywhere on a week (at its end).
      const group = e.target.closest && e.target.closest("[data-unit], .lx-editor");
      const subs = group && group.querySelector("[data-subs]");
      if (!subs) return;
      e.preventDefault(); e.dataTransfer.dropEffect = "move";
      const over = e.target.closest("[data-lec]");
      if (over === d.el) return;
      let ref;
      if (over && over.parentNode === subs) { const rc = over.getBoundingClientRect(); ref = e.clientY > rc.top + rc.height / 2 ? over.nextElementSibling : over; }
      else if (d.el.parentNode === subs) return;   // on its own week, not on a lecture: it stays where it is
      else ref = subs.querySelector(".lx-none");
      if (d.el.parentNode === subs && (ref === d.el || d.el.nextElementSibling === ref)) return;
      slide(subs, () => subs.insertBefore(d.el, ref), d.el);
      d.el.dataset.w = subs.dataset.subs;
    });
    root.addEventListener("drop", e => {
      if (!d) return;
      e.preventDefault(); d.dropped = true;
      if (d.kind === "unit") {
        const ids = [...root.querySelectorAll("[data-units] > [data-unit]")].map(x => x.dataset.unit);
        const by = new Map(weeks().map(w => [w.id, w]));
        st.data.weeks = [...ids.map(id => by.get(id)).filter(Boolean), ...weeks().filter(w => !ids.includes(w.id))];
      } else {
        const cards = allCards();
        root.querySelectorAll("[data-subs]").forEach(s => { const w = weekById(s.dataset.subs); if (w) w.cards = [...s.querySelectorAll("[data-lec]")].map(x => cards.get(x.dataset.lec)).filter(Boolean); });
      }
      changed();
    });
    root.addEventListener("dragend", () => {
      if (!d) return;
      const was = d; d = null;
      was.el.classList.remove("dragging");
      if (here()) draw();   // dropped: each week's count as it is now; cancelled: back to how it was
    });
  }

  function addWeek() {
    const real = realWeeks(), prev = real[real.length - 1];
    const m = prev && /^(.*?)(\d+)(\D*)$/.exec(prev.label || "");
    const label = m ? m[1] + String(Number(m[2]) + 1).padStart(m[2].length, "0") + m[3] : `Week ${real.length + 1}`;
    const dated = [...weeks()].reverse().find(w => !w.isBreak && w.start);
    let start = "", end = "";
    if (dated) { const gap = weeks().slice(weeks().indexOf(dated) + 1).filter(w => !w.isBreak).length + 1; start = addDays(dated.start, 7 * gap); end = addDays(dated.end || dated.start, 7 * gap); }
    const w = { id: uid(), label, start, end, topic: "", cards: [] };
    weeks().push(w); changed();
    toWeek(w);
  }
  function addLecture(w, kind = "lecture") {
    const x = { id: uid(), kind, label: nextLabel(weeks(), kind, w), title: "", description: "", files: [], ...(edit ? {} : { groups: [...lim].slice(0, 1) }) };
    (w.cards = w.cards || []).push(x); changed();
    toLec(w, x);
  }
  function duplicate(w, x) {
    const y = { ...JSON.parse(JSON.stringify(x)), id: uid(), label: nextLabel(weeks(), kindOf(x), w) };
    w.cards.splice(w.cards.indexOf(x) + 1, 0, y); changed(); toLec(w, y);
  }

  // ── A week ──
  const weekSteps = w => [...steps, { label: "Activities", go: () => go({ page: "lectures", c, t }) }, { label: w.label || "Week" }];
  function drawWeek(w) {
    renderPath(weekSteps(w));
    const dis = edit ? "" : " disabled";
    pageHTML(`<div class="lt-in"><div class="lx ed">
      ${taNote()}
      <div class="lx-editor" style="--c:${WEEK_COLOR}">
        <div class="lx-ed-head"><span class="lx-wnum" id="lw-wnum" aria-hidden="true">${esc(weekNum(w))}</span><h2 id="lw-h">${esc(w.label || "Week")}</h2>
          <span class="lx-acts">${status$()}${edit ? `<button type="button" class="lx-ic" id="lw-del" title="Delete this week" aria-label="Delete this week">${ICON.trash}</button>` : ""}</span></div>
        <div class="lx-grid week">
          <label class="lx-f">Name<input type="text" id="lw-label" value="${esc(w.label)}" placeholder="e.g. Week 4"${dis}></label>
          <div class="lx-f">Starts<div id="lw-start-f"></div></div>
          <div class="lx-f">Ends<div id="lw-end-f"></div></div>
        </div>
        <p class="lx-help">Its class days, e.g. Monday to Friday. On the course page, This week runs to the Sunday after.</p>
        <div class="lx-grid one"><label class="lx-f">Topic<input type="text" id="lw-topic" value="${esc(w.topic)}" placeholder="What this week covers"${dis}></label></div>
        <h3 class="lx-sec">Activities</h3>
        <p class="lx-help">Its activities, in order.${edit ? " Drag one to move it; on the list of weeks, drag it to another week." : ""}</p>
        ${subsHTML(w)}${evsHTML(w)}
        ${mayAdd() ? `<div class="lx-adds"><button type="button" class="lx-btn add" data-add-activity>${ICON.plus}Add an Activity</button></div>` : ""}
      </div>
    </div></div>`);
    const root = $(".lx");
    wire(root);
    let endF = null;
    whenField($("#lw-start-f"), { date: w.start, withTime: false, id: "lw-start", label: "Starts", empty: "Choose a date", disabled: !edit,
      onChange: ({ date }) => { w.start = date; if (w.start && (!w.end || w.end < w.start)) { w.end = addDays(w.start, 4); endF.set({ date: w.end }); } changed(); } });
    endF = whenField($("#lw-end-f"), { date: w.end, withTime: false, id: "lw-end", label: "Ends", empty: "Choose a date", disabled: !edit, onChange: ({ date }) => { w.end = date; changed(); } });
    root.querySelectorAll("[data-add-activity]").forEach(b => { b.onclick = () => { const last = (w.cards || []).filter(mayCard).at(-1); addLecture(w, last ? kindOf(last) : "lecture"); }; });
    if (!edit) return;
    const bind = (id, k, after) => { const el = $(id); el.oninput = el.onchange = () => { w[k] = el.value.trim(); if (after) after(); changed(); }; };
    let shown = w.label || "Week";
    bind("#lw-label", "label", () => { if ((w.label || "Week") === shown) return; shown = w.label || "Week"; $("#lw-h").textContent = shown; $("#lw-wnum").textContent = weekNum(w); renderPath(weekSteps(w)); });
    bind("#lw-topic", "topic");
    $("#lw-del").onclick = async () => {
      const n = (w.cards || []).length;
      if (!await confirmBox("Delete this week?", `${esc(w.label || "This week")}${n ? ` and its ${n} activit${n === 1 ? "y" : "ies"}` : ""} go${n ? "" : "es"} from the course page.`, "Delete")) return;
      st.data.weeks = weeks().filter(x => x !== w); changed(); go({ page: "lectures", c, t });
    };
  }

  // ── A lecture ──
  const lecSteps = (w, x) => [...steps, { label: "Activities", go: () => go({ page: "lectures", c, t }) }, { label: w.label || "Week", go: () => toWeek(w) }, { label: titleOf(x) }];
  const namedHTML = x => `Shown as <b>${esc(nameOf(x))}</b>.${kindOf(x) === "other" ? "" : ` ${esc(kindName(kindOf(x)))}s are numbered in course order.`}`;
  function drawLecture(w, x) {
    renderPath(lecSteps(w, x));
    const edit = mayCard(x);   // (here: may this one be changed)
    const dis = edit ? "" : " disabled", k = kindOf(x);
    const files = x.files || [];
    pageHTML(`<div class="lt-in"><div class="lx ed">
      ${taNote()}
      <div class="lx-editor" id="lw-ed" style="--c:${KIND_COLOR[k]}">
        <div class="lx-ed-head"><span class="lx-kicon big" id="lw-kicon">${KIND_ICON[k]}</span><h2 id="lw-h">${esc(titleOf(x))}</h2>
          <span class="lx-acts">${status$()}${edit ? `<button type="button" class="lx-ic" id="lw-del" title="Delete this activity" aria-label="Delete this activity">${ICON.trash}</button>` : ""}</span></div>
        <div class="lx-grid">
          <div class="lx-f">Type<span class="lx-seg" role="group" aria-label="Type">${KINDS.map(([v, n]) => `<button type="button" data-kind="${v}" aria-pressed="${v === k}"${dis}>${n}</button>`).join("")}</span></div>
          <label class="lx-f">Label<input type="text" id="lw-label" value="${esc(x.label)}" placeholder="e.g. Midterm review"${k === "other" ? dis : ' disabled title="Only Other has a label of its own; the rest are named by their type, in order"'}></label>
          <label class="lx-f">Title<input type="text" id="lw-title" value="${esc(x.title)}" placeholder="e.g. Latches and flip-flops"${dis}></label>
        </div>
        <p class="lx-help" id="lw-named">${namedHTML(x)}</p>
        <div class="lx-grid when">
          <label class="lx-f">Week<select id="lw-week"${dis}>${realWeeks().map(y => `<option value="${esc(y.id)}"${y === w ? " selected" : ""}>${esc([y.label || "Week", rangeText(y.start, y.end)].filter(Boolean).join(" · "))}</option>`).join("")}</select></label>
          <div class="lx-f">When<div id="lw-whens" class="lx-whens"></div></div>
        </div>

        <div class="lx-grid one"><div class="lx-f">For<div id="lw-groups"></div></div></div>
        <h3 class="lx-sec">Description</h3>
        <div id="lw-desc"></div>
        <h3 class="lx-sec">Files and Links</h3>
        <p class="lx-help">Each one is a button students click on the course page, with this activity. With none, it says Coming soon.</p>
        <div id="lw-files">${files.map((f, i) => `<div class="lx-frow"><input type="text" data-fl="${i}" value="${esc(f.label)}" placeholder="Button text, e.g. Slides" aria-label="Button text"${dis}><input type="url" data-fu="${i}" value="${esc(f.url)}" placeholder="https://…" aria-label="Link"${dis}>${edit ? `<button type="button" class="lx-ic quiet" data-fdel="${i}" aria-label="Remove it">${ICON.trash}</button>` : ""}</div>`).join("") || (edit ? "" : `<p class="lx-help">None.</p>`)}</div>
        ${edit ? `<div class="lx-fbtns"><button type="button" class="lx-btn add" id="lw-up">${ICON.plus}Upload a File</button><input type="file" id="lw-file" hidden><button type="button" class="lx-btn add" id="lw-link">${ICON.plus}Add a Link</button></div>` : ""}
      </div>
    </div></div>`);
    // Its dates: a field for each (at least one), and another one added with Add a Date; only days in its week
    // (its Monday to the day before the next week's, or that Sunday).
    const weekSpan = w => { if (!w.start) return {}; const R = realWeeks(), nx = R.slice(R.indexOf(w) + 1).find(y => y.start); return { min: mondayOf(w.start), max: nx ? addDays(mondayOf(nx.start), -1) : addDays(mondayOf(w.end || w.start), 6) }; };
    // Its dates: a field for each (at least one), and another one added with Add a Date.
    let W = datesOf(x).slice(); if (!W.length) W = [""];
    const whens = () => {
      const host = $("#lw-whens");
      host.innerHTML = W.map((_, i) => `<div class="lx-when-row"><div data-wi="${i}"></div>${edit && W.length > 1 ? `<button type="button" class="lx-ic quiet" data-wdel="${i}" title="Remove this date" aria-label="Remove this date">${ICON.trash}</button>` : ""}</div>`).join("")
        + (edit && W.some(Boolean) ? `<button type="button" class="lx-btn add sm" id="lw-when-add">${ICON.plus}Add a Date</button>` : "");
      W.forEach((s, i) => { const v = readStamp(s);
        whenField(host.querySelector(`[data-wi="${i}"]`), { date: v.date, time: v.time, id: i ? `lw-when-${i}` : "lw-when", label: i ? `Date ${i + 1}` : "When", empty: "Choose a date", timeLabel: "Starts At", near: (readStamp(W[0]).date || w.start), ...weekSpan(w), disabled: !edit,
          onChange: ({ date, time }) => { W[i] = date ? writeStamp(date, time) : ""; setDates(x, W); changed(); if (!date && W.length > 1) { W.splice(i, 1); whens(); } else if (!$("#lw-when-add") && date) whens(); } }); });
      host.querySelectorAll("[data-wdel]").forEach(b => { b.onclick = () => { W.splice(+b.dataset.wdel, 1); if (!W.length) W = [""]; setDates(x, W); changed(); whens(); }; });
      const add = $("#lw-when-add"); if (add) add.onclick = () => { W.push(""); whens(); const f = host.querySelector(`[data-wi="${W.length - 1}"] button`); if (f) f.click(); };
    };
    whens();
    // For: its activity groups (none: everyone). An instructor picks among theirs (at least one).
    const G = (st.groups || []).filter(g => canEdit(c, t) || !edit || lim.has(g.id)).slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    pickMany($("#lw-groups"), { options: G.map(g => [g.id, g.name || "Untitled group"]), value: groupsOf(x), empty: canEdit(c, t) || !edit ? "Everyone in the course" : "Pick your groups", label: "For", id: "lw-group", disabled: !edit,
      onChange: v => { delete x.group; if (v.length) x.groups = v; else delete x.groups; changed(); } });
    richText($("#lw-desc"), { value: x.description, placeholder: "A sentence or two about it", label: "Description", disabled: !edit, onChange: v => { x.description = v; changed(); } });
    if (!edit) return;
    let shown = titleOf(x);
    const head = () => { $("#lw-named").innerHTML = namedHTML(x); const now = titleOf(x); if (now === shown) return; shown = now; $("#lw-h").textContent = now; renderPath(lecSteps(w, x)); };
    const bind = (id, fn) => { const el = $(id); el.oninput = el.onchange = () => { fn(el.value); changed(); }; };
    bind("#lw-label", v => { x.label = v.trim(); head(); });
    bind("#lw-title", v => { x.title = v.trim(); head(); });
    document.querySelectorAll("[data-kind]").forEach(b => { b.onclick = () => {   // a new type: the label follows, if it was the usual one
      const was = kindOf(x), now = b.dataset.kind; if (now === was) return;
      x.kind = now;
      if (now === "other") x.label = ""; else renumber(weeks());
      const lab = $("#lw-label"); lab.value = x.label || ""; lab.disabled = now !== "other"; lab.title = now === "other" ? "" : "Only Other has a label of its own; the rest are named by their type, in order";
      document.querySelectorAll("[data-kind]").forEach(y => y.setAttribute("aria-pressed", y === b));
      $("#lw-ed").style.setProperty("--c", KIND_COLOR[now]); $("#lw-kicon").innerHTML = KIND_ICON[now];
      head(); changed();
    }; });

    $("#lw-week").onchange = () => {
      const to = weekById($("#lw-week").value); if (!to || to === w) return;
      w.cards = w.cards.filter(z => z !== x); (to.cards = to.cards || []).push(x); changed();
      toLec(to, x); toast(`Moved to ${to.label || "another week"}.`);
    };
    const filesBox = $("#lw-files");
    filesBox.oninput = e => {
      const i = e.target.dataset.fl ?? e.target.dataset.fu; if (i == null) return;
      x.files[+i][e.target.dataset.fl != null ? "label" : "url"] = e.target.value.trim(); changed();
    };
    filesBox.querySelectorAll("[data-fdel]").forEach(b => { b.onclick = () => { x.files.splice(+b.dataset.fdel, 1); changed(); drawLecture(w, x); }; });
    $("#lw-link").onclick = () => { (x.files = x.files || []).push({ label: x.files.length ? "" : "Slides", url: "" }); changed(); drawLecture(w, x); const u = [...document.querySelectorAll("[data-fu]")].pop(); if (u) u.focus(); };
    const up = $("#lw-up"), inp = $("#lw-file");
    up.onclick = () => inp.click();
    inp.onchange = async () => {
      const file = inp.files && inp.files[0]; inp.value = ""; if (!file) return;
      up.disabled = true; up.textContent = `Uploading ${file.name}…`;
      try {
        const url = await uploadPublic(file, "lectures");
        (x.files = x.files || []).push({ label: file.name.replace(/\.[^.]+$/, ""), url }); changed();
        toast(`Uploaded ${file.name}.`);
      } catch (e) { toast(e.message || `Couldn't upload ${file.name}.`); }
      if (here()) drawLecture(w, x);
    };
    $("#lw-del").onclick = async () => {
      if (!await confirmBox("Delete this activity?", `${esc(titleOf(x))} goes from the course page, with its files and links (uploaded files stay in the course's files).`, "Delete")) return;
      w.cards = w.cards.filter(z => z !== x); changed(); toWeek(w);
    };
  }

  if (st.data) { draw(); if (ctx.evaluations) ctx.evaluations().then(e => { const was = JSON.stringify(st.evals || []); st.evals = e; if (JSON.stringify(e) !== was && here()) draw(); }).catch(() => {}); }   // (an evaluation added or moved meanwhile)
  else load();
}

/** Is a save still to happen (leaving the page)? */
export const lecturesUnsaved = () => !!(lecturesPage.state && (lecturesPage.state.dirty || lecturesPage.state.saving));
