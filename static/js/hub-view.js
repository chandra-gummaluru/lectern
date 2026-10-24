/* The course hub's look, shared: the hub (hub.js) draws each tab with it, and so does the Course Page
   Builder, so the page you edit is the page students see.

     HubView.draw(D, tab, arg, opts)   one tab's HTML. D = { data: { <tab>: … }, pages }: the hub's API
                                       answer (server/hub.py), or HubView.fromPage's. arg: #week/<i>.
     HubView.fromPage(page, year)      the same tab data, made from the builder's page in the browser,
                                       with each item's place in the page (_p) so the builder can edit it.
     HubView.currentWeek(weeks, now)   which week is "this week"

   With opts.edit, things that can be edited carry the builder's data-act / data-path hooks: lectures,
   weeks, dividers and announcements open for editing; weeks and lectures can be dragged; + Add buttons. */
(() => {
"use strict";

let D = null, EDIT = false;

// ── Text ─────────────────────────────────────────────────────────────
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// A link from the page: http(s) and mailto only; a relative one is a file beside the course page.
function href(u) {
  u = String(u || "").trim();
  if (!u) return "";
  const sp = u.match(/^https:\/\/([\w-]+)\.sharepoint\.com\/:\w:\/[gr]\/personal\/([^/]+)\/([A-Za-z0-9_-]+)/);
  if (sp) return `https://${sp[1]}.sharepoint.com/personal/${sp[2]}/_layouts/15/download.aspx?share=${sp[3]}`;
  if (/^(https?:|mailto:)/i.test(u)) return u;
  if (/^[a-z][a-z0-9+.-]*:/i.test(u) || u.startsWith("//")) return "";   // javascript: and the like
  try { return new URL(u, D.pages || location.href).href; } catch (_) { return ""; }
}

// The course page's shorthand: **bold**, *italic*, ~~strike~~, ==highlight==, `code`, [text](link), emails.
function rich(s) {
  const kept = [], keep = h => `\u0000${kept.push(h) - 1}\u0000`;
  let t = esc(s).replace(/`([^`]+)`/g, (_, c) => keep(`<code>${c}</code>`));
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) => {
    const h = href(url.replace(/&amp;/g, "&"));
    return h ? keep(`<a href="${esc(h)}"${h.startsWith("mailto:") ? "" : ' target="_blank" rel="noopener"'}>${txt}</a>`) : m;
  });
  t = t.replace(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, m => keep(`<a href="mailto:${m}">${m}</a>`));
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/~~([^~]+)~~/g, "<del>$1</del>").replace(/==([^=]+)==/g, "<mark>$1</mark>");
  return t.replace(/\u0000(\d+)\u0000/g, (_, i) => kept[i]);
}
// Blank line = new paragraph, "- " bullets, "1. " numbered, "### " heading, ``` code ```.
function markdown(src) {
  const out = []; let list = null, para = [], fence = null;
  const fp = () => { if (para.length) { out.push(`<p>${rich(para.join(" "))}</p>`); para = []; } };
  const fl = () => { if (list) { out.push(`<${list.tag}>${list.items.map(x => `<li>${rich(x)}</li>`).join("")}</${list.tag}>`); list = null; } };
  String(src || "").split("\n").forEach(raw => {
    const line = raw.trim(); let m;
    if (fence) { if (/^```/.test(line)) { out.push(`<pre>${esc(fence.join("\n"))}</pre>`); fence = null; } else fence.push(raw.replace(/\s+$/, "")); return; }
    if (/^```/.test(line)) { fp(); fl(); fence = []; return; }
    if (!line) { fp(); fl(); }
    else if ((m = line.match(/^[-*•]\s+(.*)$/))) { fp(); if (!list || list.tag !== "ul") { fl(); list = { tag: "ul", items: [] }; } list.items.push(m[1]); }
    else if ((m = line.match(/^\d+[.)]\s+(.*)$/))) { fp(); if (!list || list.tag !== "ol") { fl(); list = { tag: "ol", items: [] }; } list.items.push(m[1]); }
    else if ((m = line.match(/^#{1,6}\s+(.*)$/))) { fp(); fl(); out.push(`<h5>${rich(m[1])}</h5>`); }
    else { fl(); para.push(line); }
  });
  fp(); fl(); if (fence) out.push(`<pre>${esc(fence.join("\n"))}</pre>`);
  return `<div class="hb-md">${out.join("")}</div>`;
}

// ── Dates ────────────────────────────────────────────────────────────
const fromIso = s => { const m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(s || ""); return m ? new Date(+m[1], m[2] - 1, +m[3]) : null; };
const isoDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (s, n) => { const d = fromIso(s); if (!d) return ""; d.setDate(d.getDate() + n); return isoDate(d); };
const mondayOf = s => { const d = fromIso(s); if (!d) return ""; d.setDate(d.getDate() - (d.getDay() + 6) % 7); return isoDate(d); };
const today = () => isoDate(new Date());
// A week runs Monday to Sunday (its own dates are its class days), or to the day before the next one starts.
const weekEnd = (w, next) => { const e = addDays(mondayOf(w.end || w.start), 6); return next && next.start <= e ? addDays(next.start, -1) : e; };
const fmt = (s, o) => { const d = fromIso(s); return d ? d.toLocaleDateString("en-CA", o) : ""; };
const DAY = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const DAY3 = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const hhmm = (a, b) => (a ? (b ? `${a}–${b}` : a) : "");
// "Oct 18, 2026, 15:42" (a lecture's or an announcement's date) → its ISO day, or "".
function stampDay(t) {
  const m = /([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})/.exec(t || "");
  if (!m) return "";
  const d = new Date(`${m[1]} ${m[2]}, ${m[3]}`);
  return isNaN(d) ? "" : isoDate(d);
}
const annTime = a => { const t = Date.parse(String(a.date || "").replace(/\bp\.m\./i, "PM").replace(/\ba\.m\./i, "AM")); return isNaN(t) ? (a.at || 0) : t; };
// Older pages give a week's dates only as text ("Sept 8 – 12"): read them, in the term's year.
const MON = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
function weekRange(w, year) {
  if (/^\d{4}-\d\d-\d\d$/.test(w.start || "")) return [w.start, /^\d{4}-\d\d-\d\d$/.test(w.end || "") && w.end >= w.start ? w.end : w.start];
  const m = /([a-z]{3})[a-z]*\.?\s*(\d{1,2})(?:\s*[-–—]\s*(?:([a-z]{3})[a-z]*\.?\s*)?(\d{1,2}))?/i.exec(w.dates || "");
  if (!m || !year || !(m[1].toLowerCase() in MON)) return ["", ""];
  const sm = MON[m[1].toLowerCase()], em = m[3] && m[3].toLowerCase() in MON ? MON[m[3].toLowerCase()] : sm;
  return [isoDate(new Date(year, sm, +m[2])), isoDate(new Date(year + (em < sm ? 1 : 0), em, +(m[4] || m[2])))];
}

// ── Icons ────────────────────────────────────────────────────────────
const svg = p => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const LOCK = svg('<rect x="4.5" y="11" width="15" height="9.5" rx="2"/><path d="M8 11V7.5a4 4 0 0 1 8 0V11"/>');
const PREV = svg('<path d="m15 18-6-6 6-6"/>'), NEXT = svg('<path d="m9 18 6-6-6-6"/>');
const TRASH = svg('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>');
const GRIP = '<svg class="hbe-grip" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/></svg>';

// ── Editing hooks (the builder) ──────────────────────────────────────
const opens = (p, title) => (EDIT && p ? ` data-act="open" data-path="${esc(p)}" role="button" tabindex="0" title="${esc(title)}"` : "");
const edCls = p => (EDIT && p ? " hb-ed" : "");

// ── Pieces ───────────────────────────────────────────────────────────
const data = id => (D.data || {})[id] || null;
const fileLinks = fs => (fs || []).map(f => [f, href(f.url)]).filter(x => x[1])
  .map(([f, h]) => `<a class="hb-file" href="${esc(h)}" target="_blank" rel="noopener">${esc(f.label || "Download")}</a>`).join("");
const fmtW = n => String(Math.round(Number(n || 0) * 100) / 100);

function lectureCard(c, drag) {
  const files = fileLinks(c.files);
  const when = c.date ? esc(String(c.date).replace(/, \d{4}/, "")) : "";
  const dr = EDIT && drag ? ` draggable="true" data-ldrag="${esc(drag.week)}" data-lj="${drag.j}"` : "";
  return `<article class="hb-card${edCls(c._p)}${EDIT && !c.title ? " hb-untitled" : ""}"${opens(c._p, "Edit this lecture: its title, description, files and links")}${dr}><div class="hb-card-top"><span>${esc(c.label)}</span><span>${when}</span></div>
    <h3>${esc(c.title || (EDIT ? "Untitled" : c.label) || "Untitled")}</h3>${c.description ? `<p>${rich(c.description)}</p>` : ""}
    ${files ? `<div class="hb-files">${files}</div>` : `<div class="hb-soon">Coming soon</div>`}</article>`;
}
function evalWhen(e) {
  const d = fromIso(e.date); if (!d) return "";
  return `${e.type === "test" ? "" : "Due "}${d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" })}${e.time ? `, ${e.time}` : ""}`;
}
function evalCard(e) {
  const ev = data("evaluations"), files = fileLinks(ev && ev.files[e.id]), p = EDIT ? `evalFiles.${e.id}` : "";
  return `<article class="hb-card${e.type === "test" ? " test" : ""}${edCls(p)}"${opens(p, "Add files and links for this evaluation")}><div class="hb-card-top"><span>${e.type === "test" ? "Test" : "Due"}</span><span>${esc(evalWhen(e).replace(/^Due /, ""))}</span></div>
    <h3>${esc(e.name)}</h3>${files ? `<div class="hb-files">${files}</div>` : ""}</article>`;
}
function annHTML(a, meta) {
  return `<article class="hb-ann${edCls(a._p)}"${opens(a._p, "Edit this announcement")}><p class="hb-ann-meta">${esc([meta, a.date].filter(Boolean).join(" · "))}</p>${a.title ? `<h3>${esc(a.title)}</h3>` : EDIT ? "<h3>Untitled</h3>" : ""}${markdown(a.body)}</article>`;
}
function tableHTML(cols, rows, foot) {
  return `<div class="hb-tw"><table class="hb-t"><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${rich(c)}</td>`).join("")}</tr>`).join("")}</tbody>${foot && foot.some(x => x) ? `<tfoot><tr>${foot.map(c => `<td>${rich(c)}</td>`).join("")}</tr></tfoot>` : ""}</table></div>`;
}
const blocksHTML = bs => (bs || []).map(b => `<div class="hb-block">${b.heading ? `<h4>${esc(b.heading)}</h4>` : ""}${b.table ? tableHTML(b.table.columns, b.table.rows, b.table.footer) : markdown(b.body)}</div>`).join("");

// Meeting times and office hours (Overview's meetings sections), every one.
const KIND = { lecture: "Lecture", tutorial: "Tutorial", lab: "Lab", office: "Office hours", other: "" };
const meetingName = m => (m.kind === "other" || !KIND[m.kind] ? m.label || "Meeting" : KIND[m.kind]);
const meetingSub = m => (m.kind !== "other" && KIND[m.kind] ? m.label : "");
const meetingsTable = items => tableHTML(["What", "When", "Where", "Who"], items.slice().sort((a, b) => (a.day || 9) - (b.day || 9) || String(a.start).localeCompare(b.start))
  .map(m => [[meetingName(m), meetingSub(m)].filter(Boolean).join(" "), `${DAY[m.day] || ""} ${hhmm(m.start, m.end)}`.trim(), m.where, m.who]), null);
function meetings() {
  const o = data("overview"); if (!o) return [];
  return o.sections.filter(s => s.type === "meetings").flatMap(s => s.items || []).filter(m => m.day);
}

// The week to show as this one: the week we're in; between weeks (a reading week, the weekend after
// one), the next one; before the term, the first. → { k: its place among the dated weeks, note, dated }
function currentWeek(cal, now) {
  const dated = cal.filter(w => !w.isBreak && w.start);
  let k = 0, note = "";
  dated.forEach((w, j) => { if (mondayOf(w.start) <= now) k = j; });
  if (now < mondayOf(dated[0].start)) note = `The term starts ${fmt(dated[0].start, { weekday: "long", month: "long", day: "numeric" })}. Here's the first week.`;
  else if (dated[k + 1] && now > weekEnd(dated[k], dated[k + 1])) {
    const gap = cal.find(b => b.isBreak && b.i > dated[k].i && b.i < dated[k + 1].i);
    k++;
    note = gap && now < mondayOf(dated[k].start) ? `${gap.label || "A break"}: no classes this week. Here's what's coming up.` : "";
  }
  return { k, note, dated };
}

// ── Tabs ─────────────────────────────────────────────────────────────
const DRAW = {
  overview() {
    const o = data("overview");
    let h = `<h2 class="hb-h2">Overview</h2>${o.description ? `<p class="hb-desc">${rich(o.description)}</p>` : ""}`;
    o.sections.forEach(s => {
      h += `<h3 class="hb-h3">${esc(s.title)}</h3>`;
      if (s.type === "meetings") h += (s.items || []).length ? meetingsTable(s.items) : `<p class="hb-empty">No times yet.</p>`;
      else if (s.type === "table") h += tableHTML(s.columns, s.rows, s.footer);
      else if (s.type === "sessions") h += tableHTML(s.headers, s.groups.flatMap(g => g.slots.map((x, i) => [i ? "" : g.name, x.a, x.b, i ? "" : g.extra])), null);
      h += blocksHTML(s.blocks);
    });
    return h;
  },

  week(arg) {
    const cal = (data("week").weeks || []), dated = cal.filter(w => !w.isBreak && w.start);
    if (!dated.length) return `<h2 class="hb-h2">This week</h2><p class="hb-empty">The term's weeks don't have dates yet.${EDIT ? " Give them dates on the Lectures tab (open a week)." : ""}</p>`;
    const now = today();
    let k = arg == null || arg === "" ? -1 : dated.findIndex(w => w.i === Number(arg)), note = "";
    if (k < 0) ({ k, note } = currentWeek(cal, now));
    const w = dated[k], mon = mondayOf(w.start), next = dated[k + 1];
    const last = weekEnd(w, next);
    const inWeek = d => d && d >= mon && d <= last;

    const L = data("lectures"), lw = L ? L.weeks.find(x => x.i === w.i) : null;
    const E = data("evaluations"), evs = E ? (E.evals || []).filter(e => inWeek(e.date)).sort((a, b) => `${a.date}${a.time}`.localeCompare(`${b.date}${b.time}`)) : [];
    const A = data("announcements"), anns = A ? A.items.filter(a => a.wi === w.i).sort((a, b) => annTime(b) - annTime(a)) : [];
    const ms = meetings();

    // The days: meetings (every week, on their day), evaluations and dated lectures.
    const days = [];
    for (let d = mon; d <= last; d = addDays(d, 1)) {
      const dow = (fromIso(d).getDay() + 6) % 7 + 1, items = [];
      ms.filter(m => m.day === dow).forEach(m => items.push({ t: m.start, h: `<div class="hb-ev"><span class="tm">${esc(hhmm(m.start, m.end))}</span><span class="k">${esc(meetingName(m))}${meetingSub(m) ? ` ${esc(meetingSub(m))}` : ""}</span>${esc(m.who)}${m.where ? ` <span class="wh">${m.who ? "· " : ""}${esc(m.where)}</span>` : ""}</div>` }));
      evs.filter(e => e.date === d).forEach(e => items.push({ t: e.time || "23:59", h: `<div class="hb-ev due"><span class="tm">${esc(e.time || "")}</span><span class="k">${e.type === "test" ? "Test" : "Due"}</span>${esc(e.name)}</div>` }));
      (lw ? lw.cards : []).filter(c => stampDay(c.date) === d).forEach(c => items.push({ t: (/(\d\d:\d\d)/.exec(c.date) || [])[1] || "", h: `<div class="hb-ev"><span class="tm">${esc((/(\d\d:\d\d)/.exec(c.date) || [])[1] || "")}</span><span class="k">${esc(c.label)}</span>${esc(c.title)}</div>` }));
      if (!items.length && dow > 5) continue;
      items.sort((a, b) => String(a.t).localeCompare(String(b.t)));
      days.push(`<li${d === now ? ' class="today"' : ""}><div class="dd">${DAY3[dow]}<b>${fromIso(d).getDate()}</b></div><div>${items.map(x => x.h).join("") || '<span class="hb-nothing">—</span>'}</div></li>`);
    }

    let left = "";
    if (A) {
      left += `<h3 class="hb-h3">Announcements</h3>`;
      if (anns.length) left += anns.map(a => annHTML(a, "")).join("");
      else {
        const latest = A.items.filter(a => a.wi < w.i).sort((a, b) => annTime(b) - annTime(a))[0];
        left += latest ? annHTML(latest, `Latest · ${latest.week}`) : `<p class="hb-nothing">None this week.</p>`;
      }
    }
    if (lw) {
      left += `<h3 class="hb-h3">Lectures</h3>`;
      left += lw.cards.length || lw.noClass ? `<div class="hb-grid">${lw.cards.map(c => lectureCard(c)).join("")}${lw.noClass ? `<div class="hb-card nocl">No class${lw.noClass > 1 ? ` (${lw.noClass} hours)` : ""}</div>` : ""}</div>` : `<p class="hb-nothing">No lectures this week.</p>`;
      if (lw.deadlines.length) left += `<div class="hb-pills" style="margin-top:12px">${lw.deadlines.map(d => `<span class="hb-pill">${esc(d)}</span>`).join("")}</div>`;
    }
    if (E) left += `<h3 class="hb-h3">Evaluations</h3>${evs.length ? `<div class="hb-grid">${evs.map(evalCard).join("")}</div>` : `<p class="hb-nothing">Nothing due this week.</p>`}`;

    const prev = dated[k - 1];
    return `<div class="hb-weeknav">
        <button type="button" class="hb-btn" data-week="${prev ? prev.i : ""}" aria-label="Previous week"${prev ? "" : " disabled"}>${PREV}</button>
        <div class="grow"><h2 class="hb-h2">${esc(w.label)}${lw && lw.topic ? `: ${esc(lw.topic)}` : ""}</h2><span class="d">${esc(`${fmt(mon, { month: "short", day: "numeric" })} – ${fmt(last, { month: "short", day: "numeric" })}`)}${mon <= now && now <= last ? " · this week" : ""}</span></div>
        <button type="button" class="hb-btn" data-week="${next ? next.i : ""}" aria-label="Next week"${next ? "" : " disabled"}>${NEXT}</button>
      </div>${note ? `<p class="hb-note">${esc(note)}</p>` : ""}
      <div class="hb-cols"><div>${left || '<p class="hb-nothing">Nothing to show for this week.</p>'}</div>
        <div><h3 class="hb-h3">Day by day</h3><ul class="hb-days">${days.join("")}</ul></div></div>`;
  },

  lectures() {
    const L = data("lectures"), E = data("evaluations"), now = today();
    const head = `<h2 class="hb-h2">Lectures</h2><p class="hb-lede">Every week's lectures and their files, in order.</p>`;
    const adds = list => (EDIT ? `<div class="hbe-adds"><button type="button" class="hbe-add" data-act="add" data-path="${esc(list)}" data-kind="week">+ Add Week</button><button type="button" class="hbe-add" data-act="add" data-path="${esc(list)}" data-kind="break">+ Add Section Divider</button></div>` : "");
    if (!L.weeks.length) return head + (EDIT && L.lists && L.lists.length ? adds(L.lists[0]) : `<p class="hb-empty">No lectures yet.</p>`);
    const cw = L.weeks.some(w => !w.isBreak && w.start) ? currentWeek(L.weeks, now) : null, cur = cw ? cw.dated[cw.k].i : -1;
    return head + L.weeks.map((w, j) => {
      const drag = EDIT && w._list ? ` draggable="true" data-dl="${esc(w._list)}" data-di="${w._j}"` : "";
      const tail = w._last ? adds(w._list) : "";
      if (w.isBreak) {
        if (!EDIT) return `<div class="hb-break">${esc(w.label)}</div>`;
        return `<div class="hb-break hbe-break"${drag} title="Drag to move it">${GRIP}<span class="ed" data-bind="${esc(w._p)}.text" data-ph="Section divider, e.g. Reading Week" contenteditable="plaintext-only">${esc(w.label)}</span><button type="button" class="hbe-x" data-act="del" data-path="${esc(w._list)}" data-i="${w._j}" data-noun="break" title="Delete this divider" aria-label="Delete this divider">${TRASH}</button></div>${tail}`;
      }
      const nx = L.weeks.slice(j + 1).find(x => !x.isBreak && x.start);
      const end = w.start ? (nx ? addDays(mondayOf(nx.start), -1) : addDays(mondayOf(w.start), 6)) : "";
      const evs = E && w.start ? (E.evals || []).filter(e => e.date && e.date >= mondayOf(w.start) && e.date <= end) : [];
      const pills = [...evs.map(e => `<span class="hb-pill${e.type === "test" ? " dk" : ""}">${esc(String(e.name).split(":")[0])}</span>`), ...w.deadlines.map(d => `<span class="hb-pill">${esc(d)}</span>`)].join("");
      const name = EDIT ? `<button type="button" class="hbe-wname" data-act="open" data-path="${esc(w._p)}" title="Edit this week: its dates, topic, hours, deadlines and announcements">${esc(w.label || "Week")}</button>` : esc(w.label);
      const cards = w.cards.map((c, k) => lectureCard(c, { week: w._p, j: k })).join("");
      const add = EDIT ? `<div class="hbe-adds sm"><button type="button" class="hbe-add" data-act="lec-add" data-path="${esc(w._p)}" data-lfree="${esc(w._p)}" title="Add a lecture at the end of this week (or drop a lecture here to move it to the end)">+ Add Lecture</button></div>` : "";
      return `<section class="hb-week${w.i === cur ? " now" : ""}" id="wk-${w.i}"${drag}><div class="hb-week-h">${EDIT ? GRIP : ""}<h3${w.i === cur ? ` data-now="${mondayOf(w.start) <= now ? "This week" : "Up next"}"` : ""}>${name}</h3>${w.dates ? `<span class="d">${esc(w.dates)}</span>` : EDIT ? `<span class="d">No dates</span>` : ""}${pills ? `<div class="hb-pills">${pills}</div>` : ""}${w.topic ? `<span class="t">${rich(w.topic)}</span>` : ""}</div>
        ${w.cards.length || w.noClass ? `<div class="hb-grid">${cards}${w.noClass ? `<div class="hb-card nocl">No class</div>` : ""}</div>` : `<p class="hb-nothing">No lectures this week.</p>`}${add}</section>${tail}`;
    }).join("");
  },

  evaluations() {
    const E = data("evaluations");
    if (!E.units.length) return `<h2 class="hb-h2">Evaluations</h2><p class="hb-empty">The marking scheme will appear here.${EDIT ? " It comes from the gradebook: add evaluations there." : ""}</p>`;
    const files = e => fileLinks(E.files[e.id]);
    const note = e => [...(e.notes || []), e.accom && e.accom.standard && e.accom.approval ? "This applies only if you request it and it's approved." : ""].filter(Boolean).join(" ");
    const edit = e => (EDIT ? `<button type="button" class="hbe-mini" data-act="open" data-path="evalFiles.${esc(e.id)}" title="Files and links for ${esc(e.name)}">${(E.files[e.id] || []).length ? "Edit files" : "+ Files"}</button>` : "");
    const cell = e => `${esc(note(e))}${files(e) ? `<div class="hb-files">${files(e)}</div>` : ""}${edit(e)}`;
    const rows = [], total = E.units.reduce((t, u) => t + Number(u.weight || 0), 0);
    E.units.forEach(u => {
      if (u.kind === "group") {
        rows.push(`<tr><td>${esc(u.name)}</td><td>${fmtW(u.weight)}%</td><td></td><td>${esc(`The best ${u.keep} of ${u.count} count, ${fmtW(u.weight / Math.max(1, u.keep))}% each.`)}</td></tr>`);
        u.members.forEach(m => rows.push(`<tr class="sub"><td>${esc(m.name)}</td><td></td><td class="nw">${esc(evalWhen(m))}</td><td>${cell(m)}</td></tr>`));
      } else rows.push(`<tr><td>${esc(u.name)}</td><td>${fmtW(u.weight)}%</td><td class="nw">${esc(evalWhen(u))}</td><td>${cell(u)}</td></tr>`);
    });
    const makeups = (E.evals || []).filter(e => e.makeupFor);
    return `<h2 class="hb-h2">Evaluations</h2><p class="hb-lede">Every evaluation, its weight and when it is. Together they make up your course grade.</p>
      <div class="hb-tw"><table class="hb-t"><thead><tr><th>Evaluation</th><th>Weight</th><th>When</th><th>Notes</th></tr></thead><tbody>${rows.join("")}</tbody>
      <tfoot><tr><td>Total</td><td>${fmtW(total)}%</td><td></td><td></td></tr></tfoot></table></div>
      ${makeups.length ? `<h3 class="hb-h3">Makeups</h3><div class="hb-grid">${makeups.map(evalCard).join("")}</div>` : ""}`;
  },

  announcements() {
    const items = data("announcements").items.slice().sort((a, b) => annTime(b) - annTime(a));
    return `<h2 class="hb-h2">Announcements</h2><p class="hb-lede">Newest first.</p>${items.length ? items.map(a => annHTML(a, a.week)).join("") : '<p class="hb-empty">No announcements yet.</p>'}`;
  },

  policies() {
    const P = data("policies"), kinds = [];
    P.rules.forEach(x => { let k = kinds.find(y => y.title === x.title); if (!k) kinds.push(k = { title: x.title, items: [] }); k.items.push(x.text); });
    const body = kinds.map(k => `<div class="hb-block"><h4>${esc(k.title)}</h4>${markdown(k.items.length === 1 ? k.items[0] : k.items.map(t => `- ${t}`).join("\n"))}</div>`).join("")
      + P.sections.map(s => blocksHTML(s.blocks)).join("");
    return `<h2 class="hb-h2">Policies</h2><p class="hb-lede">${esc((P.sections[0] && P.sections[0].caption) || "Course rules, and what to do if you miss work")}</p>${body ? `<div class="hb-panel">${body}</div>` : '<p class="hb-empty">No policies yet.</p>'}`;
  },

  accommodations() {
    return `<h2 class="hb-h2">My accommodations</h2><p class="hb-lede">Your accommodation requests and what was decided.</p><div class="hb-panel"><p class="hb-empty">Requests you make will show here.</p></div>`;
  },
};

function draw(d, tab, arg, opts = {}) {
  D = d; EDIT = !!opts.edit;
  try { return DRAW[tab](arg); } finally { EDIT = false; }
}

// ── The tabs' data, from the builder's page (as server/hub.py makes it, plus where each thing is) ──
const str = x => (typeof x === "string" ? x : "");
const arr = x => (Array.isArray(x) ? x : []);
const filesOf = fs => arr(fs).filter(f => f && str(f.url).trim()).map(f => ({ label: str(f.label), url: str(f.url) }));
function fromPage(page, year) {
  const secs = arr(page.sections).map((s, si) => [s, si]).filter(([s]) => s && !s.hidden);
  const scheme = page.scheme || {}, weeks = [], anns = [], lists = [];
  secs.forEach(([s, si]) => {
    if (s.type !== "schedule") return;
    const list = `sections.${si}.weeks`; lists.push(list);
    const ws = arr(s.weeks);
    ws.forEach((w, wi) => {
      const p = `${list}.${wi}`, base = { i: weeks.length, _p: p, _list: list, _j: wi, _last: wi === ws.length - 1 };
      if (w.isBreak) { weeks.push({ ...base, isBreak: true, label: str(w.text) || str(w.label), cards: [], deadlines: [] }); return; }
      const [start, end] = weekRange(w, year);
      const wk = { ...base, isBreak: false, label: str(w.label), dates: str(w.dates), start, end, topic: str(w.topic),
        deadlines: arr(w.deadlines).filter(d => str(d).trim()), noClass: arr(w.off).length,
        cards: arr(w.cards).map((c, k) => ({ label: str(c.label), title: str(c.title), description: str(c.description), date: str(c.date), hours: c.hours || 1, files: filesOf(c.files), _p: `${p}.cards.${k}` })) };
      weeks.push(wk);
      arr(w.announcements).forEach((a, k) => {
        if (str(a.title).trim() || str(a.body).trim()) anns.push({ title: str(a.title), body: str(a.body), date: str(a.date), at: a.at || 0, week: wk.label, wi: wk.i, _p: `${p}.announcements.${k}` });
      });
    });
  });
  const pol = secs.filter(([s]) => s.type === "policies").map(([s]) => s), rules = [];
  pol.forEach(s => arr(scheme.policies).forEach(x => { const show = s.show || {}; if (x.id in show ? show[x.id] : x.show) rules.push({ title: x.title, text: x.text }); }));
  const ef = page.evalFiles || {};
  return {
    overview: { description: str(page.description), sections: secs.filter(([s]) => s.type === "meetings").map(([s]) => ({ type: "meetings", title: str(s.title), items: arr(s.items).map(m => ({ ...m, day: Number(m.day) || 0 })).filter(m => m.day), blocks: [] })) },
    lectures: { weeks, lists },
    announcements: { items: anns },
    evaluations: { units: arr(scheme.units), evals: arr(scheme.evals), files: Object.fromEntries(Object.entries(ef).map(([k, v]) => [k, filesOf(v)])) },
    policies: { sections: pol.map(s => ({ title: str(s.title), caption: str(s.caption), blocks: arr(s.blocks).filter(b => !b.hidden) })), rules },
    week: { weeks: weeks.map(w => ({ i: w.i, label: w.label, dates: w.dates || "", start: w.start || "", end: w.end || "", isBreak: w.isBreak })) },
    accommodations: {},
  };
}

const TABS = [["overview", "Overview"], ["week", "This week"], ["lectures", "Lectures"], ["evaluations", "Evaluations"], ["announcements", "Announcements"], ["policies", "Policies"], ["accommodations", "My accommodations"]];

window.HubView = { draw, fromPage, currentWeek, today, esc, rich, markdown, meetingsTable, TABS, LOCK };
})();
