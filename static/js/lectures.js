/* Lectures: an offering's weeks and the lectures in them, made and changed here (like Evaluations and
   its groups); the course page (Lectures and This week) shows them.

     #/<course>/<term>/lectures                  every week, each with its lectures
     #/<course>/<term>/lectures/<week>           a week: its name, dates and topic
     #/<course>/<term>/lectures/<week>/<lecture> a lecture: its type, title, description, date, files and links

   Kept in the offering's private files, <course>/<term>/lectures.json (the hub reads it; nothing else of
   the private files reaches students):

     { "format": "lectern-lectures/1",
       "weeks": [ { "id", "label": "Week 1", "start": "2026-09-07", "end": "2026-09-11", "topic",
                    "cards": [ { "id", "kind": "lecture", "label": "Lecture 01", "title", "description",
                                 "date": "Sep 9, 2026, 10:00", "files": [ { "label", "url" } ] } ] },
                  { "id", "isBreak": true, "text": "Reading Week" } ] }

   An offering without one starts from its course page's weeks (course.json), and becomes a lectures.json
   with the first change. Changes save by themselves. Instructors change it; TAs see it. */

const KINDS = [["lecture", "Lecture"], ["tutorial", "Tutorial"], ["lab", "Lab"], ["other", "Other"]];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"];
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
// A lecture's date: "Sep 9, 2026, 10:00" (the course page's form) ↔ { date: "2026-09-09", time: "10:00" }.
const MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function readStamp(t) {
  const m = /([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})(?:,?\s+(\d{1,2}):(\d\d))?/.exec(t || "");
  if (!m) return { date: "", time: "" };
  const d = new Date(`${m[1]} ${m[2]}, ${m[3]}`);
  return isNaN(d) ? { date: "", time: "" } : { date: isoDate(d), time: m[4] ? `${m[4].padStart(2, "0")}:${m[5]}` : "" };
}
const writeStamp = (date, time) => { const d = fromIso(date); return d ? `${MON3[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}${time ? `, ${time}` : ""}` : ""; };
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
  const dateLine = w => [rangeText(w.start, w.end) || "No dates", w.topic].filter(Boolean).join(" · ");
  const lecLine = x => [new RegExp(`^${kindName(kindOf(x))}\\b`, "i").test(x.label || "") ? "" : kindName(kindOf(x)), x.date ? x.date.replace(/, \d{4}/, "") : "", (x.files || []).length ? `${x.files.length} file${x.files.length === 1 ? "" : "s"}` : "No files yet"].filter(Boolean).join(" · ");

  function draw() {
    const w = r.w && weekById(r.w), x = w && r.l && (w.cards || []).find(y => y.id === r.l);
    if (r.l && x) return drawLecture(w, x);
    if (r.w && w) return drawWeek(w);
    return drawList();
  }

  // ── Every week ──
  function drawList() {
    renderPath([...steps, { label: "Lectures" }]);
    const list = weeks();
    pageHTML(`<div class="lt-in lt-lw">
      <div class="lt-off-head"><div><h1>Lectures</h1><p class="lt-lede">The weeks of the term and the lectures in each. The course page shows them in Lectures and This week.</p></div>
        <div class="lt-off-acts">${edit ? `<span class="lw-status" id="lw-status"></span><button type="button" class="lt-btn" data-add-break>Add a Divider</button><button type="button" class="lt-btn primary" data-add-week>${ICON.plus}Add a Week</button>` : ""}</div></div>
      ${edit ? "" : `<p class="lt-note">As a TA you can look at the lectures; the instructors change them.</p>`}
      <div class="lw-list">${list.length ? list.map((w, i) => w.isBreak ? breakHTML(w, i) : weekHTML(w, i)).join("") : `<p class="lt-hint">No weeks yet.${edit ? " Add the first one." : ""}</p>`}</div>
    </div>`);
    const root = $(".lt-lw");
    root.querySelectorAll("[data-week]").forEach(b => { b.onclick = e => { if (e.target.closest("[data-lec], [data-add-lec], [data-move]")) return; go({ page: "lectures", c, t, w: b.dataset.week }); }; });
    root.querySelectorAll("[data-lec]").forEach(b => { b.onclick = e => { e.stopPropagation(); go({ page: "lectures", c, t, w: b.dataset.w, l: b.dataset.lec }); }; });
    if (!edit) return;
    root.querySelector("[data-add-week]").onclick = addWeek;
    root.querySelector("[data-add-break]").onclick = () => { weeks().push({ id: uid(), isBreak: true, text: "Reading Week" }); changed(); draw(); };
    root.querySelectorAll("[data-add-lec]").forEach(b => { b.onclick = e => { e.stopPropagation(); addLecture(weekById(b.dataset.addLec)); }; });
    root.querySelectorAll("[data-move]").forEach(b => { b.onclick = e => { e.stopPropagation(); move(Number(b.dataset.i), Number(b.dataset.move)); }; });
    root.querySelectorAll("[data-break-text]").forEach(inp => { inp.oninput = () => { weekById(inp.dataset.breakText).text = inp.value; changed(); }; });
    root.querySelectorAll("[data-del-break]").forEach(b => { b.onclick = () => { st.data.weeks = weeks().filter(w => w.id !== b.dataset.delBreak); changed(); draw(); }; });
  }
  const moveBtns = i => edit ? `<span class="lw-move"><button type="button" class="lt-btn lw-ic" data-move="-1" data-i="${i}" title="Move up" aria-label="Move up"${i ? "" : " disabled"}>${ICON.up}</button><button type="button" class="lt-btn lw-ic" data-move="1" data-i="${i}" title="Move down" aria-label="Move down"${i < weeks().length - 1 ? "" : " disabled"}>${ICON.down}</button></span>` : "";
  const weekHTML = (w, i) => `<section class="lw-week" data-week="${esc(w.id)}" role="button" tabindex="0" title="Open ${esc(w.label || "this week")}">
      <div class="lw-week-h"><div class="grow"><h2>${esc(w.label || "Week")}</h2><p>${esc(dateLine(w))}</p></div>${moveBtns(i)}</div>
      ${(w.cards || []).map(x => `<div class="lw-lec" data-lec="${esc(x.id)}" data-w="${esc(w.id)}" role="button" tabindex="0"><div class="grow"><h3>${esc(x.title || x.label || "Untitled")}</h3><p>${esc([x.title ? x.label : "", lecLine(x)].filter(Boolean).join(" · "))}</p></div></div>`).join("")}
      ${edit ? `<button type="button" class="lt-btn add lw-add" data-add-lec="${esc(w.id)}">${ICON.plus}Add a Lecture</button>` : ""}
    </section>`;
  const breakHTML = (w, i) => `<div class="lw-break">${edit ? `<input type="text" data-break-text="${esc(w.id)}" value="${esc(w.text || "")}" placeholder="e.g. Reading Week" aria-label="Divider">${moveBtns(i)}<button type="button" class="lt-btn lt-trash lw-ic" data-del-break="${esc(w.id)}" title="Delete this divider" aria-label="Delete this divider">${ICON.trash}</button>` : `<b>${esc(w.text || "")}</b>`}</div>`;

  function move(i, d) {
    const a = weeks(), j = i + d; if (j < 0 || j >= a.length) return;
    [a[i], a[j]] = [a[j], a[i]]; changed(); draw();
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
    go({ page: "lectures", c, t, w: w.id });
  }
  function addLecture(w, kind = "lecture") {
    const x = { id: uid(), kind, label: nextLabel(weeks(), kind, w), title: "", description: "", files: [] };
    (w.cards = w.cards || []).push(x); changed();
    go({ page: "lectures", c, t, w: w.id, l: x.id });
  }

  // ── A week ──
  function drawWeek(w) {
    renderPath([...steps, { label: "Lectures", go: () => go({ page: "lectures", c, t }) }, { label: w.label || "Week" }]);
    const dis = edit ? "" : " disabled";
    pageHTML(`<div class="lt-in lt-lw lw-page">
      <div class="lt-off-head"><h1>${esc(w.label || "Week")}</h1><div class="lt-off-acts">${edit ? `<span class="lw-status" id="lw-status"></span><button type="button" class="lt-btn lt-trash" id="lw-del" title="Delete this week" aria-label="Delete this week">${ICON.trash}</button>` : ""}</div></div>
      <div class="lw-card lt-form">
        <div class="lw-two"><label>Name<input type="text" id="lw-label" value="${esc(w.label)}" placeholder="e.g. Week 4"${dis}></label>
          <label>Topic<input type="text" id="lw-topic" value="${esc(w.topic)}" placeholder="What this week covers"${dis}></label></div>
        <div class="lw-two"><label>Starts<input type="date" id="lw-start" value="${esc(w.start)}"${dis}></label>
          <label>Ends<input type="date" id="lw-end" value="${esc(w.end)}"${dis}><small>Its class days, e.g. Monday to Friday. This week runs to the Sunday after.</small></label></div>
      </div>
      <h2 class="lw-h2">Lectures</h2>
      <div class="lw-week lw-week-in">${(w.cards || []).map((x, k) => `<div class="lw-lec" data-lec="${esc(x.id)}" role="button" tabindex="0"><div class="grow"><h3>${esc(x.title || x.label || "Untitled")}</h3><p>${esc([x.title ? x.label : "", lecLine(x)].filter(Boolean).join(" · "))}</p></div>${edit ? `<span class="lw-move"><button type="button" class="lt-btn lw-ic" data-lmove="-1" data-k="${k}" aria-label="Move up"${k ? "" : " disabled"}>${ICON.up}</button><button type="button" class="lt-btn lw-ic" data-lmove="1" data-k="${k}" aria-label="Move down"${k < w.cards.length - 1 ? "" : " disabled"}>${ICON.down}</button></span>` : ""}</div>`).join("") || `<p class="lt-hint">No lectures this week.</p>`}
        ${edit ? `<div class="lw-adds">${KINDS.map(([k, n]) => `<button type="button" class="lt-btn add" data-add-kind="${k}">${ICON.plus}${k === "other" ? "Something Else" : `Add a ${n}`}</button>`).join("")}</div>` : ""}</div>
    </div>`);
    const root = $(".lw-page");
    root.querySelectorAll("[data-lec]").forEach(b => { b.onclick = e => { if (e.target.closest("[data-lmove]")) return; go({ page: "lectures", c, t, w: w.id, l: b.dataset.lec }); }; });
    if (!edit) return;
    const bind = (id, k, after) => { const el = $(id); el.oninput = el.onchange = () => { w[k] = el.value.trim(); if (after) after(); changed(); }; };
    let shown = w.label || "Week";
    bind("#lw-label", "label", () => { if ((w.label || "Week") === shown) return; shown = w.label || "Week"; root.querySelector("h1").textContent = shown; renderPath([...steps, { label: "Lectures", go: () => go({ page: "lectures", c, t }) }, { label: w.label || "Week" }]); });
    bind("#lw-topic", "topic");
    bind("#lw-start", "start", () => { if (w.start && (!w.end || w.end < w.start)) { w.end = addDays(w.start, 4); $("#lw-end").value = w.end; } });
    bind("#lw-end", "end");
    root.querySelectorAll("[data-add-kind]").forEach(b => { b.onclick = () => addLecture(w, b.dataset.addKind); });
    root.querySelectorAll("[data-lmove]").forEach(b => { b.onclick = e => { e.stopPropagation(); const k = Number(b.dataset.k), j = k + Number(b.dataset.lmove); [w.cards[k], w.cards[j]] = [w.cards[j], w.cards[k]]; changed(); drawWeek(w); }; });
    $("#lw-del").onclick = async () => {
      if (!await confirmBox("Delete this week?", `${esc(w.label || "This week")} and its ${(w.cards || []).length} lecture${(w.cards || []).length === 1 ? "" : "s"} go${(w.cards || []).length === 1 ? "es" : ""} from the course page.`, "Delete")) return;
      st.data.weeks = weeks().filter(x => x !== w); changed(); go({ page: "lectures", c, t });
    };
  }

  // ── A lecture ──
  function drawLecture(w, x) {
    renderPath([...steps, { label: "Lectures", go: () => go({ page: "lectures", c, t }) }, { label: w.label || "Week", go: () => go({ page: "lectures", c, t, w: w.id }) }, { label: x.title || x.label || "Untitled" }]);
    const dis = edit ? "" : " disabled", when = readStamp(x.date), k = kindOf(x);
    const files = x.files || [];
    pageHTML(`<div class="lt-in lt-lw lw-page">
      <div class="lt-off-head"><h1 id="lw-h">${esc(x.title || x.label || "Untitled")}</h1><div class="lt-off-acts">${edit ? `<span class="lw-status" id="lw-status"></span><button type="button" class="lt-btn" id="lw-dup">Duplicate</button><button type="button" class="lt-btn lt-trash" id="lw-del" title="Delete this lecture" aria-label="Delete this lecture">${ICON.trash}</button>` : ""}</div></div>
      <div class="lw-card lt-form">
        <div class="lw-two"><label>Type<select id="lw-kind"${dis}>${KINDS.map(([v, n]) => `<option value="${v}"${v === k ? " selected" : ""}>${n}</option>`).join("")}</select></label>
          <label>Label<input type="text" id="lw-label" value="${esc(x.label)}" placeholder="e.g. Lecture 07"${dis}></label></div>
        <label>Title<input type="text" id="lw-title" value="${esc(x.title)}" placeholder="e.g. Latches and flip-flops"${dis}></label>
        <label>Description<textarea id="lw-desc" rows="3" placeholder="A sentence or two"${dis}>${esc(x.description)}</textarea></label>
        <div class="lw-two"><label>Date<input type="date" id="lw-date" value="${esc(when.date)}"${dis}><small>Optional. With a date, This week shows it on its day.</small></label>
          <label>Time<input type="time" id="lw-time" value="${esc(when.time)}"${dis}></label></div>
        <label>Week<select id="lw-week"${dis}>${realWeeks().map(y => `<option value="${esc(y.id)}"${y === w ? " selected" : ""}>${esc([y.label || "Week", rangeText(y.start, y.end)].filter(Boolean).join(" · "))}</option>`).join("")}</select></label>
      </div>
      <h2 class="lw-h2">Files and Links</h2>
      <div class="lw-card"><p class="lt-part-text lw-help">Each one is a button students click on the course page. With none, it says Coming soon.</p>
        <div id="lw-files">${files.map((f, i) => `<div class="lw-file"><input type="text" data-fl="${i}" value="${esc(f.label)}" placeholder="Button text, e.g. Slides" aria-label="Button text"${dis}><input type="url" data-fu="${i}" value="${esc(f.url)}" placeholder="https://…" aria-label="Link"${dis}>${edit ? `<button type="button" class="lt-btn lt-trash lw-ic" data-fdel="${i}" aria-label="Remove it">${ICON.trash}</button>` : ""}</div>`).join("") || (edit ? "" : `<p class="lt-hint">None.</p>`)}</div>
        ${edit ? `<div class="lw-adds"><button type="button" class="lt-btn" id="lw-up">${ICON.plus}Upload a File</button><input type="file" id="lw-file" hidden><button type="button" class="lt-btn" id="lw-link">${ICON.plus}Add a Link</button></div>` : ""}</div>
    </div>`);
    if (!edit) return;
    let shown = x.title || x.label || "Untitled";
    const head = () => { const now = x.title || x.label || "Untitled"; if (now === shown) return; shown = now; $("#lw-h").textContent = now; renderPath([...steps, { label: "Lectures", go: () => go({ page: "lectures", c, t }) }, { label: w.label || "Week", go: () => go({ page: "lectures", c, t, w: w.id }) }, { label: x.title || x.label || "Untitled" }]); };
    const bind = (id, fn) => { const el = $(id); el.oninput = el.onchange = () => { fn(el.value); changed(); }; };
    bind("#lw-label", v => { x.label = v.trim(); head(); });
    bind("#lw-title", v => { x.title = v.trim(); head(); });
    bind("#lw-desc", v => { x.description = v.trim(); });
    const stamp = () => { const d = $("#lw-date").value, tm = $("#lw-time").value; if (d) x.date = writeStamp(d, tm); else delete x.date; };
    bind("#lw-date", stamp); bind("#lw-time", stamp);
    $("#lw-kind").onchange = () => {   // a new type: the label follows, if it was the usual one
      const was = kindOf(x), now = $("#lw-kind").value;
      x.kind = now;
      if (!x.label || new RegExp(`^${kindName(was)}\\b`, "i").test(x.label)) { x.label = nextLabel(weeks().map(y => (y === w ? { ...y, cards: y.cards.filter(z => z !== x) } : y)), now, w); $("#lw-label").value = x.label; head(); }
      changed();
    };
    $("#lw-week").onchange = () => {
      const to = weekById($("#lw-week").value); if (!to || to === w) return;
      w.cards = w.cards.filter(z => z !== x); (to.cards = to.cards || []).push(x); changed();
      go({ page: "lectures", c, t, w: to.id, l: x.id }); toast(`Moved to ${to.label || "another week"}.`);
    };
    const filesBox = $("#lw-files");
    filesBox.oninput = e => {
      const i = e.target.dataset.fl ?? e.target.dataset.fu; if (i == null) return;
      x.files[+i][e.target.dataset.fl != null ? "label" : "url"] = e.target.value.trim(); changed();
    };
    filesBox.querySelectorAll("[data-fdel]").forEach(b => { b.onclick = () => { x.files.splice(+b.dataset.fdel, 1); changed(); drawLecture(w, x); }; });
    $("#lw-link").onclick = () => { (x.files = x.files || []).push({ label: x.files.length ? "" : "Slides", url: "" }); changed(); drawLecture(w, x); const u = $$("[data-fu]").pop(); if (u) u.focus(); };
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
    $("#lw-dup").onclick = () => {
      const y = { ...JSON.parse(JSON.stringify(x)), id: uid(), label: nextLabel(weeks(), kindOf(x), w) };
      w.cards.splice(w.cards.indexOf(x) + 1, 0, y); changed(); go({ page: "lectures", c, t, w: w.id, l: y.id });
    };
    $("#lw-del").onclick = async () => {
      if (!await confirmBox("Delete this lecture?", `${esc(x.title || x.label || "It")} goes from the course page, with its files and links (uploaded files stay in the course's files).`, "Delete")) return;
      w.cards = w.cards.filter(z => z !== x); changed(); go({ page: "lectures", c, t, w: w.id });
    };
  }
  const $$ = s => [...document.querySelectorAll(s)];

  if (st.data) draw(); else load();
}

/** Is a save still to happen (leaving the page)? */
export const lecturesUnsaved = () => !!(lecturesPage.state && (lecturesPage.state.dirty || lecturesPage.state.saving));
