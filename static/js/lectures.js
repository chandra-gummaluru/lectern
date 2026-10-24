/* Lectures: an offering's weeks and the lectures in them, made and changed here; the course page
   (Lectures and This week) shows them. It looks and works like the Gradebook's Evaluations: each week
   is a group card with its lectures as sub-cards, and you drag a lecture to another place or another
   week, and a week (or a divider) to another place in the term.

     #/<course>/<term>/lectures                  every week, each with its lectures
     #/<course>/<term>/lectures/<week>           a week: its name, dates and topic, and its lectures
     #/<course>/<term>/lectures/<week>/<lecture> a lecture: its type, label, title, when, description, files and links

   Kept in the offering's private files, <course>/<term>/lectures.json (the hub reads it; nothing else of
   the private files reaches students):

     { "format": "lectern-lectures/1",
       "weeks": [ { "id", "label": "Week 1", "start": "2026-09-07", "end": "2026-09-11", "topic",
                    "cards": [ { "id", "kind": "lecture", "label": "Lecture 01", "title", "description",
                                 "date": "Sep 9, 2026, 10:00", "files": [ { "label", "url" } ] } ] },
                  { "id", "isBreak": true, "text": "Reading Week" } ] }

   An offering without one starts from its course page's weeks (course.json), and becomes a lectures.json
   with the first change. Changes save by themselves. Instructors change it; TAs see it. */

import { richText } from "./richtext.js";
import { whenField } from "./when.js";

const KINDS = [["lecture", "Lecture"], ["tutorial", "Tutorial"], ["lab", "Lab"], ["other", "Other"]];
const KIND_COLOR = { lecture: "#3b7dd8", tutorial: "#2e9b6a", lab: "#8a5cd1", other: "#8b8f96" };
const WEEK_COLOR = "#c99a06";
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

// From a course page's weeks (course.json's schedule sections), the first time.
function fromCoursePage(page) {
  const weeks = [];
  ((page && page.sections) || []).filter(s => s && s.type === "schedule" && !s.hidden).forEach(s => (s.weeks || []).forEach(w => {
    if (!w) return;
    if (w.isBreak) { weeks.push({ id: uid(), isBreak: true, text: w.text || "" }); return; }
    weeks.push({ id: uid(), label: w.label || "", start: w.start || "", end: w.end || "", topic: w.topic || "",
      cards: (w.cards || []).map(c => ({ id: uid(), kind: kindOf(c), label: c.label || "", title: c.title || "", description: c.description || "",
        ...(c.date ? { date: c.date } : {}), files: (c.files || []).filter(f => f && String(f.url || "").trim()).map(f => ({ label: f.label || "", url: f.url })) })) });
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
  const here = () => { const x = ctx.route(); return x.page === "lectures" && x.c === c && x.t === t && (x.o || "") === (r.o || ""); };
  const st = (lecturesPage.state = lecturesPage.state && lecturesPage.state.key === key ? lecturesPage.state : { key, data: null, sha: undefined, saving: null, dirty: false });

  async function load() {
    pageHTML(`<div class="lt-in"><div class="lt-loading" style="min-height:200px">Reading the lectures…</div></div>`);
    try {
      const f = await Store.readFile(repo, path);
      if (f) { st.data = JSON.parse(f.text); st.sha = f.sha; }
      else {
        const pg = await Store.readText(area(Store.PUB), `${c}/${t}/course.json`).catch(() => null);
        let page = null; try { page = pg ? JSON.parse(pg).page : null; } catch (_) {}
        st.data = fromCoursePage(page); st.sha = null;
      }
      if (!Array.isArray(st.data.weeks)) st.data.weeks = [];
    } catch (e) { if (here()) pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't read the lectures. ${esc(e.message)}</p></div>`); return; }
    if (here()) draw();
  }

  // Saving: a moment after each change, one save at a time; a change made meanwhile is saved after it.
  let timer = 0;
  function changed() {
    st.dirty = true; status("Saving…");
    clearTimeout(timer); timer = setTimeout(save, 500);
  }
  async function save() {
    if (st.saving) { st.again = true; return; }
    st.saving = (async () => {
      try {
        st.dirty = false;
        st.sha = await Store.writeText(repo, path, JSON.stringify(st.data, null, 1) + "\n", "Lectures", st.sha);
        status("Saved");
      } catch (e) {
        st.dirty = true;
        status(e.conflict ? "Not saved: changed elsewhere" : "Not saved", true);
        toast(e.conflict ? "The lectures were changed somewhere else (another window, or someone on the team). Reload this page to see them; your last change wasn't saved." : `Couldn't save the lectures. ${e.message}`);
      } finally { st.saving = null; if (st.again) { st.again = false; save(); } }
    })();
  }
  function status(text, bad) { const el = $("#lw-status"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }

  const weeks = () => st.data.weeks;
  const weekById = id => weeks().find(w => w.id === id);
  const realWeeks = () => weeks().filter(w => !w.isBreak);
  const allCards = () => new Map(weeks().flatMap(w => (w.cards || []).map(x => [x.id, x])));
  const weekLine = w => { const n = (w.cards || []).length; return [rangeText(w.start, w.end) || "No dates yet", w.topic, `${n} lecture${n === 1 ? "" : "s"}`].filter(Boolean).join(" · "); };
  const titleOf = x => x.title || x.label || "Untitled";
  const nameOf = x => (x.title && x.label ? `${x.label}: ${x.title}` : titleOf(x));
  const lecWhen = x => [x.title ? x.label : (new RegExp(`^${kindName(kindOf(x))}\\b`, "i").test(x.label || "") ? "" : kindName(kindOf(x))), whenText(x.date) || "no date yet"].filter(Boolean).join(", ");
  const lecMore = x => { const n = (x.files || []).length; return n ? `${n} file${n === 1 ? "" : "s"} or link${n === 1 ? "" : "s"}.` : "No files yet: the course page says Coming soon."; };
  const status$ = () => (edit ? `<span class="lx-status" id="lw-status">${st.dirty || st.saving ? "Saving…" : ""}</span>` : "");
  const taNote = () => (edit ? "" : `<p class="lt-note lx-note">You can look at the lectures; the instructors change them.</p>`);
  const toWeek = w => go({ page: "lectures", c, t, w: w.id });
  const toLec = (w, x) => go({ page: "lectures", c, t, w: w.id, l: x.id });

  function draw() {
    const w = r.w && weekById(r.w), x = w && r.l && (w.cards || []).find(y => y.id === r.l);
    if (r.l && x) return drawLecture(w, x);
    if (r.w && w) return drawWeek(w);
    return drawList();
  }

  // One lecture as a sub-card, inside its week.
  const lecRow = (w, x) => `<div class="lx-row sub" style="--c:${KIND_COLOR[kindOf(x)]}" data-lec="${esc(x.id)}" data-w="${esc(w.id)}" role="button" tabindex="0"${edit ? ' draggable="true"' : ""}>
      <div class="lx-main"><div class="lx-top"><h3>${esc(titleOf(x))}</h3></div>
        <p class="lx-when">${esc(lecWhen(x))}</p><p>${esc(lecMore(x))}</p></div>
      ${edit ? `<div class="lx-side"><button type="button" class="lx-btn sm" data-dup="${esc(x.id)}" data-w="${esc(w.id)}" title="A copy of it, right after it">${COPY}Duplicate</button></div>` : ""}</div>`;
  const subsHTML = w => `<div class="lx-subs" data-subs="${esc(w.id)}">${(w.cards || []).map(x => lecRow(w, x)).join("")}<p class="lx-none">No lectures this week.${edit ? " Add one, or drag one here." : ""}</p></div>`;

  // ── Every week ──
  function drawList() {
    renderPath([...steps, { label: "Lectures" }]);
    const list = weeks();
    pageHTML(`<div class="lt-in"><div class="lx">
      <div class="lx-head"><h1>Lectures</h1><span class="spacer"></span>${status$()}
        ${edit ? `<button type="button" class="lx-btn" data-add-break title="A line between weeks, like Reading Week">Add a Divider</button><button type="button" class="lx-btn main" data-add-week>${ICON.plus}Add a Week</button>` : ""}</div>
      ${taNote()}
      ${list.length ? `<div class="lx-list" data-units>${list.map(w => (w.isBreak ? breakHTML(w) : weekHTML(w))).join("")}</div>` : `<div class="lx-empty">No weeks yet.${edit ? " Add the term's first week." : ""}</div>`}
    </div></div>`);
    wire($(".lx"));
    if (!edit) return;
    $("[data-add-week]").onclick = addWeek;
    $("[data-add-break]").onclick = () => { weeks().push({ id: uid(), isBreak: true, text: "Reading Week" }); changed(); draw(); };
  }
  const weekHTML = w => `<div class="lx-group" style="--c:${WEEK_COLOR}" data-unit="${esc(w.id)}"${edit ? ' draggable="true"' : ""}>
      <div class="lx-row grp" data-week="${esc(w.id)}" role="button" tabindex="0">
        <div class="lx-main"><div class="lx-top"><h3>${esc(w.label || "Week")}</h3></div><p>${esc(weekLine(w))}</p></div></div>
      ${subsHTML(w)}
      ${edit ? `<div class="lx-foot"><button type="button" class="lx-add" data-add-lec="${esc(w.id)}">${ICON.plus}Add a Lecture</button></div>` : `<div class="lx-foot"></div>`}
    </div>`;
  const breakHTML = w => `<div class="lx-break" data-unit="${esc(w.id)}"${edit ? ' draggable="true"' : ""}>${edit
    ? `<input type="text" data-break-text="${esc(w.id)}" value="${esc(w.text || "")}" placeholder="e.g. Reading Week" aria-label="Divider"><button type="button" class="lx-ic quiet" data-del-break="${esc(w.id)}" title="Delete this divider" aria-label="Delete this divider">${ICON.trash}</button>`
    : `<b>${esc(w.text || "")}</b>`}</div>`;

  // Clicks, keys and dragging on a list of weeks (or one week's lectures).
  function wire(root) {
    const open = el => { if (el.dataset.lec) toLec(weekById(el.dataset.w), allCards().get(el.dataset.lec)); else if (el.dataset.week) toWeek(weekById(el.dataset.week)); };
    root.querySelectorAll("[data-lec], [data-week]").forEach(el => {
      el.onclick = e => { if (e.target.closest("button, input")) return; e.stopPropagation(); open(el); };
      el.onkeydown = e => { if ((e.key === "Enter" || e.key === " ") && e.target === el) { e.preventDefault(); open(el); } };
    });
    if (!edit) return;
    root.querySelectorAll("[data-add-lec]").forEach(b => { b.onclick = () => addLecture(weekById(b.dataset.addLec)); });
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
    const x = { id: uid(), kind, label: nextLabel(weeks(), kind, w), title: "", description: "", files: [] };
    (w.cards = w.cards || []).push(x); changed();
    toLec(w, x);
  }
  function duplicate(w, x) {
    const y = { ...JSON.parse(JSON.stringify(x)), id: uid(), label: nextLabel(weeks(), kindOf(x), w) };
    w.cards.splice(w.cards.indexOf(x) + 1, 0, y); changed(); toLec(w, y);
  }

  // ── A week ──
  const weekSteps = w => [...steps, { label: "Lectures", go: () => go({ page: "lectures", c, t }) }, { label: w.label || "Week" }];
  function drawWeek(w) {
    renderPath(weekSteps(w));
    const dis = edit ? "" : " disabled";
    pageHTML(`<div class="lt-in"><div class="lx ed">
      ${taNote()}
      <div class="lx-editor" style="--c:${WEEK_COLOR}">
        <div class="lx-ed-head"><h2 id="lw-h">${esc(w.label || "Week")}</h2>
          <span class="lx-acts">${status$()}${edit ? `<button type="button" class="lx-ic" id="lw-del" title="Delete this week" aria-label="Delete this week">${ICON.trash}</button>` : ""}</span></div>
        <div class="lx-grid week">
          <label class="lx-f">Name<input type="text" id="lw-label" value="${esc(w.label)}" placeholder="e.g. Week 4"${dis}></label>
          <div class="lx-f">Starts<div id="lw-start-f"></div></div>
          <div class="lx-f">Ends<div id="lw-end-f"></div></div>
        </div>
        <p class="lx-help">Its class days, e.g. Monday to Friday. On the course page, This week runs to the Sunday after.</p>
        <div class="lx-grid one"><label class="lx-f">Topic<input type="text" id="lw-topic" value="${esc(w.topic)}" placeholder="What this week covers"${dis}></label></div>
        <h3 class="lx-sec">Lectures</h3>
        <p class="lx-help">Its lectures, tutorials and labs, in order.${edit ? " Drag one to move it; on the list of weeks, drag it to another week." : ""}</p>
        ${subsHTML(w)}
        ${edit ? `<div class="lx-adds">${KINDS.map(([k, n]) => `<button type="button" class="lx-add" data-add-kind="${k}">${ICON.plus}${k === "other" ? "Something Else" : `Add a ${n}`}</button>`).join("")}</div>` : ""}
      </div>
    </div></div>`);
    const root = $(".lx");
    wire(root);
    let endF = null;
    whenField($("#lw-start-f"), { date: w.start, withTime: false, id: "lw-start", label: "Starts", empty: "Choose a date", disabled: !edit,
      onChange: ({ date }) => { w.start = date; if (w.start && (!w.end || w.end < w.start)) { w.end = addDays(w.start, 4); endF.set({ date: w.end }); } changed(); } });
    endF = whenField($("#lw-end-f"), { date: w.end, withTime: false, id: "lw-end", label: "Ends", empty: "Choose a date", disabled: !edit, onChange: ({ date }) => { w.end = date; changed(); } });
    if (!edit) return;
    const bind = (id, k, after) => { const el = $(id); el.oninput = el.onchange = () => { w[k] = el.value.trim(); if (after) after(); changed(); }; };
    let shown = w.label || "Week";
    bind("#lw-label", "label", () => { if ((w.label || "Week") === shown) return; shown = w.label || "Week"; $("#lw-h").textContent = shown; renderPath(weekSteps(w)); });
    bind("#lw-topic", "topic");
    root.querySelectorAll("[data-add-kind]").forEach(b => { b.onclick = () => addLecture(w, b.dataset.addKind); });
    $("#lw-del").onclick = async () => {
      const n = (w.cards || []).length;
      if (!await confirmBox("Delete this week?", `${esc(w.label || "This week")}${n ? ` and its ${n} lecture${n === 1 ? "" : "s"}` : ""} go${n ? "" : "es"} from the course page.`, "Delete")) return;
      st.data.weeks = weeks().filter(x => x !== w); changed(); go({ page: "lectures", c, t });
    };
  }

  // ── A lecture ──
  const lecSteps = (w, x) => [...steps, { label: "Lectures", go: () => go({ page: "lectures", c, t }) }, { label: w.label || "Week", go: () => toWeek(w) }, { label: titleOf(x) }];
  const namedHTML = x => `Shown as <b>${esc(nameOf(x))}</b>.${x.label && /\d/.test(x.label) ? ` Add another ${esc(kindName(kindOf(x)).toLowerCase())} and it's numbered after this one.` : ""}`;
  function drawLecture(w, x) {
    renderPath(lecSteps(w, x));
    const dis = edit ? "" : " disabled", when = readStamp(x.date), k = kindOf(x);
    const files = x.files || [];
    pageHTML(`<div class="lt-in"><div class="lx ed">
      ${taNote()}
      <div class="lx-editor" id="lw-ed" style="--c:${KIND_COLOR[k]}">
        <div class="lx-ed-head"><h2 id="lw-h">${esc(titleOf(x))}</h2>
          <span class="lx-acts">${status$()}${edit ? `<button type="button" class="lx-ic" id="lw-del" title="Delete this lecture" aria-label="Delete this lecture">${ICON.trash}</button>` : ""}</span></div>
        <div class="lx-grid">
          <div class="lx-f">Type<span class="lx-seg" role="group" aria-label="Type">${KINDS.map(([v, n]) => `<button type="button" data-kind="${v}" aria-pressed="${v === k}"${dis}>${n}</button>`).join("")}</span></div>
          <label class="lx-f">Label<input type="text" id="lw-label" value="${esc(x.label)}" placeholder="e.g. Lecture 07"${dis}></label>
          <label class="lx-f">Title<input type="text" id="lw-title" value="${esc(x.title)}" placeholder="e.g. Latches and flip-flops"${dis}></label>
        </div>
        <p class="lx-help" id="lw-named">${namedHTML(x)}</p>
        <div class="lx-grid when">
          <label class="lx-f">Week<select id="lw-week"${dis}>${realWeeks().map(y => `<option value="${esc(y.id)}"${y === w ? " selected" : ""}>${esc([y.label || "Week", rangeText(y.start, y.end)].filter(Boolean).join(" · "))}</option>`).join("")}</select></label>
          <div class="lx-f">When<div id="lw-when-f"></div></div>
        </div>
        <p class="lx-help">The date and time are optional: with a date, This week shows it on its day.</p>
        <h3 class="lx-sec">Description</h3>
        <div id="lw-desc"></div>
        <h3 class="lx-sec">Files and Links</h3>
        <p class="lx-help">Each one is a button students click on the course page, with this lecture. With none, it says Coming soon.</p>
        <div id="lw-files">${files.map((f, i) => `<div class="lx-frow"><input type="text" data-fl="${i}" value="${esc(f.label)}" placeholder="Button text, e.g. Slides" aria-label="Button text"${dis}><input type="url" data-fu="${i}" value="${esc(f.url)}" placeholder="https://…" aria-label="Link"${dis}>${edit ? `<button type="button" class="lx-ic quiet" data-fdel="${i}" aria-label="Remove it">${ICON.trash}</button>` : ""}</div>`).join("") || (edit ? "" : `<p class="lx-help">None.</p>`)}</div>
        ${edit ? `<div class="lx-fbtns"><button type="button" class="lx-btn" id="lw-up">${ICON.plus}Upload a File</button><input type="file" id="lw-file" hidden><button type="button" class="lx-btn" id="lw-link">${ICON.plus}Add a Link</button></div>` : ""}
      </div>
    </div></div>`);
    whenField($("#lw-when-f"), { date: when.date, time: when.time, id: "lw-when", label: "When", empty: "Choose a date", timeLabel: "Starts At", near: w.start, disabled: !edit,
      onChange: ({ date, time }) => { if (date) x.date = writeStamp(date, time); else delete x.date; changed(); } });
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
      if (!x.label || new RegExp(`^${kindName(was)}\\b`, "i").test(x.label)) { x.label = nextLabel(weeks().map(y => (y === w ? { ...y, cards: y.cards.filter(z => z !== x) } : y)), now, w); $("#lw-label").value = x.label; }
      document.querySelectorAll("[data-kind]").forEach(y => y.setAttribute("aria-pressed", y === b));
      $("#lw-ed").style.setProperty("--c", KIND_COLOR[now]);
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
      if (!await confirmBox("Delete this lecture?", `${esc(titleOf(x))} goes from the course page, with its files and links (uploaded files stay in the course's files).`, "Delete")) return;
      w.cards = w.cards.filter(z => z !== x); changed(); toWeek(w);
    };
  }

  if (st.data) draw(); else load();
}

/** Is a save still to happen (leaving the page)? */
export const lecturesUnsaved = () => !!(lecturesPage.state && (lecturesPage.state.dirty || lecturesPage.state.saving));
