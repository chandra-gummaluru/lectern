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
  try { return new URL(u, (D && D.pages) || location.href).href; } catch (_) { return ""; }
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
const CHEV = svg('<path d="m6 9 6 6 6-6"/>').replace("<svg", '<svg class="hb-chev"');
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
    <h3>${esc(c.title || (EDIT ? "Untitled" : c.label) || "Untitled")}</h3>${c.description ? `<div class="hb-card-desc">${markdown(c.description)}</div>` : ""}
    ${files ? `<div class="hb-files">${files}</div>` : `<div class="hb-soon">Coming soon</div>`}</article>`;
}
function evalWhen(e) {
  const d = fromIso(e.date); if (!d) return "";
  return `${e.type === "test" ? "" : "Due "}${d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" })}${e.time ? `, ${e.time}` : ""}`;
}
function evalCard(e) {
  const ev = data("evaluations"), files = fileLinks(ev && ev.files[e.id]), p = "";
  return `<article class="hb-card${e.type === "test" ? " test" : ""}${edCls(p)}"${opens(p, "Add files and links for this evaluation")}><div class="hb-card-top"><span>${e.type === "test" ? "Test" : "Due"}</span><span>${esc(evalWhen(e).replace(/^Due /, ""))}</span></div>
    <h3>${esc(e.name)}</h3>${files ? `<div class="hb-files">${files}</div>` : ""}</article>`;
}
function annHTML(a, meta) {
  return `<article class="hb-ann${edCls(a._p)}"${opens(a._p, "Edit this announcement")}><p class="hb-ann-meta">${esc([meta, a.date].filter(Boolean).join(" · "))}</p>${a.title ? `<h3>${esc(a.title)}</h3>` : EDIT ? "<h3>Untitled</h3>" : ""}${markdown(a.body)}</article>`;
}
// The Announcements tab: each one with its day beside it, on a line down the page.
// One announcement on the Announcements tab: its date and time, its title, and (open) its message. The newest is
// open; the others open with a click.
function feedHTML(a, open) {
  const d = fromIso(stampDay(a.date)), tm = (/(\d{1,2}:\d\d)/.exec(a.date || "") || [])[1] || "";
  const when = d ? `${d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric", year: "numeric" })}${tm ? ` · ${tm}` : ""}` : a.date || "";
  return `<details class="hb-ann hb-ann-x"${open ? " open" : ""}><summary>${when ? `<p class="hb-ann-meta">${esc(when)}</p>` : ""}<h3>${esc(a.title || "Announcement")}</h3>${CHEV}</summary><div class="hb-ann-b">${markdown(a.body)}</div></details>`;
}
const initials = n => String(n || "").split(/[\s,]+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase() || "·";
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
  const o = data("about"); if (!o) return [];
  const team = (o.team || []).flatMap(p => (p.times || []).map(x => ({ kind: x.kind, label: x.section, day: x.day, start: x.start, end: x.end, where: x.where, who: p.name })));
  return [...team, ...o.sections.filter(s => s.type === "meetings").flatMap(s => s.items || [])].filter(m => m.day);
}

// The teaching team's activities (Lectern → Teaching Team → each person), by group: each group (a lecture
// section, a tutorial, a lab…) with its times and who runs it; then office hours; then how to reach each person.
const ROLE = { instructor: "Instructor", ta: "TA", staff: "Staff" };
const when = x => [DAY3[x.day] || "", hhmm(x.start, x.end)].filter(Boolean).join(" ");
function teamHTML(team) {
  if (!team || !team.length) return "";
  const secs = new Map();
  team.forEach(p => (p.times || []).forEach(x => {
    if (x.kind === "office" || !x.day) return;
    const key = `${x.kind}|${x.section || ""}`;
    if (!secs.has(key)) secs.set(key, { kind: x.kind, section: x.section, times: [], who: [] });
    const s = secs.get(key);
    if (!s.times.some(y => y.day === x.day && y.start === x.start && y.where === x.where)) s.times.push(x);
    if (!s.who.includes(p.name)) s.who.push(p.name);
  }));
  const order = { lecture: 0, tutorial: 1, lab: 2, other: 3 };
  const cards = [...secs.values()].sort((a, b) => order[a.kind] - order[b.kind] || String(a.section).localeCompare(String(b.section)))
    .map(s => `<article class="hb-card hb-sec"><div class="hb-card-top"><span>${esc(KIND[s.kind] || "Other")}</span></div><h3>${esc(s.section || KIND[s.kind] || "Section")}</h3>
      ${s.times.sort((a, b) => a.day - b.day || String(a.start).localeCompare(b.start)).map(x => `<p class="hb-sec-t">${esc(when(x))}${x.where ? ` <span>· ${esc(x.where)}</span>` : ""}</p>`).join("")}
      <p class="hb-sec-who">${esc(s.who.join(", "))}</p></article>`).join("");
  const oh = team.flatMap(p => (p.times || []).filter(x => x.kind === "office" && x.day).map(x => ({ who: p.name, day: x.day, when: `${DAY[x.day]} ${hhmm(x.start, x.end)}`.trim(), where: x.where, start: x.start })))
    .sort((a, b) => a.day - b.day || String(a.start).localeCompare(String(b.start)));
  const people = team.map(p => `<article class="hb-person"><span class="hb-av" aria-hidden="true">${esc(initials(p.name))}</span><div><h4>${esc(p.name)}</h4><p class="hb-person-r">${esc(ROLE[p.role] || "")}${p.office ? ` · ${esc(p.office)}` : ""}</p>${p.email ? `<a href="mailto:${esc(p.email)}">${esc(p.email)}</a>` : ""}</div></article>`).join("");
  return `${cards ? `<h3 class="hb-h3">Activities</h3><div class="hb-grid">${cards}</div>` : ""}
    ${oh.length ? `<h3 class="hb-h3">Office Hours</h3><ul class="hb-rows">${oh.map(x => `<li><b>${esc(x.when)}</b><span>${esc(x.who)}</span><span class="hb-rows-w">${esc(x.where || "")}</span></li>`).join("")}</ul>` : ""}
    <h3 class="hb-h3">Teaching Team</h3><div class="hb-people">${people}</div>`;
}

// The week to show as this one: the week we're in; between weeks (a reading week, the weekend after
// one), the next one; before the term, the first. → { k: its place among the dated weeks, note, dated }
function currentWeek(cal, now) {
  const dated = cal.filter(w => !w.isBreak && w.start);
  let k = 0, note = "";
  dated.forEach((w, j) => { if (mondayOf(w.start) <= now) k = j; });
  if (now >= mondayOf(dated[0].start) && dated[k + 1] && now > weekEnd(dated[k], dated[k + 1])) {   // (before the term: the first week, no note)
    const gap = cal.find(b => b.isBreak && b.i > dated[k].i && b.i < dated[k + 1].i);
    k++;
    note = gap && now < mondayOf(dated[k].start) ? `${gap.label || "A break"}: no classes this week. Here's what's coming up.` : "";
  }
  return { k, note, dated };
}

// ── Tabs ─────────────────────────────────────────────────────────────
const DRAW = {
  about() {
    const a = data("about");
    let h = `<h2 class="hb-h2">About the course</h2>${a.description ? `<div class="hb-desc">${markdown(a.description)}</div>` : ""}${teamHTML(a.team)}`;
    (a.sections || []).forEach(s => {
      if (s.title) h += `<h3 class="hb-h3">${esc(s.title)}</h3>`;
      if (s.type === "meetings") h += (s.items || []).length ? meetingsTable(s.items) : "";
      else if (s.type === "table") h += tableHTML(s.columns, s.rows, s.footer);
      else if (s.type === "sessions") h += tableHTML(s.headers, s.groups.flatMap(g => g.slots.map((x, i) => [i ? "" : g.name, x.a, x.b, i ? "" : g.extra])), null);
      h += blocksHTML(s.blocks);
    });
    const kinds = [];
    (a.rules || []).forEach(x => { let k = kinds.find(y => y.title === x.title); if (!k) kinds.push(k = { title: x.title, items: [] }); k.items.push(x.text); });
    const pol = kinds.map(k => `<article class="hb-pol"><h4>${esc(k.title)}</h4>${markdown(k.items.length === 1 ? k.items[0] : k.items.map(t => `- ${t}`).join("\n"))}</article>`).join("") + blocksHTML(a.policies);
    if (pol) h += `<h3 class="hb-h3">Policies</h3><div class="hb-pols">${pol}</div>`;
    return h;
  },

  week(arg) {
    const cal = (data("week").weeks || []), dated = cal.filter(w => !w.isBreak && w.start);
    if (!dated.length) return `<h2 class="hb-h2">This week</h2><p class="hb-empty">The term's weeks don't have dates yet.${EDIT ? " Give them dates on the Lectures tab (open a week)." : ""}</p>`;
    const now = today();
    const { k, note } = currentWeek(cal, now);   // always the week we're in (or, between weeks, the next)
    const w = dated[k], mon = mondayOf(w.start), next = dated[k + 1];
    const last = weekEnd(w, next);
    const inWeek = d => d && d >= mon && d <= last;

    const L = data("lectures"), lw = L ? L.weeks.find(x => x.i === w.i) : null;
    const E = data("evaluations"), evs = E ? (E.evals || []).filter(e => inWeek(e.date)).sort((a, b) => `${a.date}${a.time}`.localeCompare(`${b.date}${b.time}`)) : [];
    const A = data("announcements"), anns = A ? A.items.filter(a => a.wi === w.i).sort((a, b) => annTime(b) - annTime(a)) : [];
    const ms = meetings().filter(m => m.start);

    // The days: meetings (every week, on their day), evaluations and dated lectures.
    const days = [];
    for (let d = mon; d <= addDays(mon, 6); d = addDays(d, 1)) {   // Monday to Sunday
      const dow = (fromIso(d).getDay() + 6) % 7 + 1, items = [];
      // Each thing: its time (start, and end below), what it is, and one quiet detail (where, or its label).
      const tm = (a, b) => `<span class="tm">${a ? `<b>${esc(a)}</b>${b ? `<small>${esc(b)}</small>` : ""}` : "<b>·</b>"}</span>`;
      ms.filter(m => m.day === dow).forEach(m => items.push({ t: m.start, h: `<div class="hb-ev">${tm(m.start, m.end)}<span class="what"><b>${esc(meetingName(m))}${meetingSub(m) ? ` <span class="sec">${esc(meetingSub(m))}</span>` : ""}</b>${m.where ? `<small>${esc(m.where)}</small>` : ""}</span></div>` }));
      evs.filter(e => e.date === d).forEach(e => items.push({ t: e.time || "23:59", h: `<div class="hb-ev due">${tm(e.time, "")}<span class="what"><b>${esc(e.name)}</b><span class="hb-tag${e.type === "test" ? " dk" : ""}">${e.type === "test" ? "Test" : "Due"}</span></span></div>` }));
      (lw ? lw.cards : []).filter(c => stampDay(c.date) === d).forEach(c => { const at = (/(\d\d:\d\d)/.exec(c.date) || [])[1] || ""; items.push({ t: at, h: `<div class="hb-ev">${tm(at, "")}<span class="what"><b>${esc(c.title || c.label)}</b>${c.title && c.label ? `<small>${esc(c.label)}</small>` : ""}</span></div>` }); });
      items.sort((a, b) => String(a.t).localeCompare(String(b.t)));
      if (!items.length) continue;   // only the days that have something on them
      days.push(`<li class="${d === now ? "today" : ""}"><span class="hb-tl-dot"></span><p class="hb-tl-d">${d === now ? `<i>Today</i>` : ""}${esc(DAY3[dow])} · ${esc(fmt(d, { month: "short", day: "numeric" }))}</p><div class="hb-day-items">${items.map(x => x.h).join("")}</div></li>`);
    }

    // Only what there is: a part with nothing in it this week isn't shown (no empty headings).
    let main = "";
    const latest = A && !anns.length ? A.items.filter(a => a.wi < w.i).sort((a, b) => annTime(b) - annTime(a))[0] : null;
    if (anns.length || latest) main += `<h3 class="hb-h3">Announcements</h3>${anns.length ? anns.map(a => annHTML(a, "")).join("") : annHTML(latest, `Latest · ${latest.week}`)}`;
    if (lw && (lw.cards.length || lw.noClass)) main += `<h3 class="hb-h3">Lectures</h3><div class="hb-grid">${lw.cards.map(c => lectureCard(c)).join("")}${lw.noClass ? `<div class="hb-card nocl">No class${lw.noClass > 1 ? ` (${lw.noClass} hours)` : ""}</div>` : ""}</div>`;

    // One column, so it reads the same whatever the week has: the days that have something on them (side by side),
    // then the week's announcements, then its lectures. A part with nothing in it isn't shown.
    const daysHTML = days.length ? `<h3 class="hb-h3">Day by day</h3><div class="hb-tl hb-dtl"><ol>${days.join("")}</ol></div>` : "";
    return `<div class="hb-weeknav">
        <div class="grow"><p class="hb-eyebrow">This week · ${esc(`${fmt(mon, { month: "short", day: "numeric" })} – ${fmt(last, { month: "short", day: "numeric" })}`)}</p><h2 class="hb-h2">${esc(w.label)}${lw && lw.topic ? `: ${esc(lw.topic)}` : ""}</h2></div>
      </div>${note ? `<p class="hb-note">${esc(note)}</p>` : ""}
      ${daysHTML + main || '<p class="hb-nothing hb-nothing-wk">Nothing on this week: no classes, deadlines or announcements.</p>'}`;
  },

  lectures() {
    const L = data("lectures"), E = data("evaluations"), now = today();
    const head = `<h2 class="hb-h2">Lectures</h2><p class="hb-lede">Every week of the term, its lectures and their files.</p>`;
    const adds = list => (EDIT ? `<div class="hbe-adds"><button type="button" class="hbe-add" data-act="add" data-path="${esc(list)}" data-kind="week">+ Add Week</button><button type="button" class="hbe-add" data-act="add" data-path="${esc(list)}" data-kind="break">+ Add Section Divider</button></div>` : "");
    if (!L.weeks.length) return head + (EDIT && L.lists && L.lists.length ? adds(L.lists[0]) : `<p class="hb-empty">No lectures yet.</p>`);
    const cw = L.weeks.some(w => !w.isBreak && w.start) ? currentWeek(L.weeks, now) : null, cur = cw ? cw.dated[cw.k].i : -1;
    return head + `<div class="hb-term">` + L.weeks.map((w, j) => {
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
      return `<section class="hb-week${w.i === cur ? " now" : ""}" id="wk-${w.i}"${drag}><div class="hb-week-h">${EDIT ? GRIP : ""}${w.i === cur ? `<span class="hb-now">This week</span>` : ""}<h3 title="${esc(w.label || "")}">${name}</h3>${w.dates ? `<span class="d">${esc(w.dates)}</span>` : EDIT ? `<span class="d">No dates</span>` : ""}${w.topic ? `<span class="t">${rich(w.topic)}</span>` : ""}${pills ? `<div class="hb-pills">${pills}</div>` : ""}</div>
        <div class="hb-week-b">${w.cards.length || w.noClass ? `<div class="hb-grid">${cards}${w.noClass ? `<div class="hb-card nocl">No class</div>` : ""}</div>` : `<p class="hb-nothing">No lectures this week.</p>`}${add}</div></section>${tail}`;
    }).join("") + `</div>`;
  },

  evaluations() {
    const E = data("evaluations");
    if (!E.units.length) return `<h2 class="hb-h2">Evaluations</h2><p class="hb-empty">The marking scheme will appear here.${EDIT ? " It comes from the gradebook: add evaluations there." : ""}</p>`;
    const files = e => fileLinks(E.files[e.id]);
    const note = e => [...(e.notes || []), e.accom && e.accom.standard && e.accom.approval ? "This applies only if you request it and it's approved." : ""].filter(Boolean).join(" ");
    const edit = () => "";
    // Request Accommodation: when the gradebook says students can ask (until its deadline, if there is one).
    const request = e => {
      const a = e.accom; if (!a || !(a.approval || a.alternate)) return "";
      const by = a.by ? new Date(`${a.by}T${a.byTime || "23:59"}`) : null, rq = E.request;
      if (by && !isNaN(by) && by < new Date()) return `<div class="hb-req-off">The deadline for accommodation requests has passed.</div>`;
      const when = by && !isNaN(by) ? `<span class="hb-req-by">Request by ${esc(by.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" }))}, ${esc(a.byTime || "23:59")}</span>` : "";
      const url = rq && rq.url ? `${rq.url}?${new URLSearchParams({ r: rq.r, o: rq.o, e: e.id })}` : "";
      return `<div class="hb-req">${url ? `<a class="hb-btn hb-req-btn" href="${esc(url)}" target="_blank" rel="noopener">Request Accommodation</a>` : `<span class="hb-btn hb-req-btn">Request Accommodation</span>`}${when}</div>`;
    };
    const extras = e => `${note(e) ? `<p class="hb-eval-n">${esc(note(e))}</p>` : ""}${files(e) ? `<div class="hb-files">${files(e)}</div>` : ""}${request(e)}${edit(e)}`;
    // A marking scheme, as a syllabus has it: one list, each evaluation a row (its name and when, its weight on the
    // right); a group's row opens to show its parts.
    const when = e => esc(evalWhen(e).replace(/^Due /, ""));
    const one = u => `<li class="hb-eval${u.type === "test" ? " test" : ""}"><div class="hb-eval-m"><h3>${esc(u.name)}</h3>${evalWhen(u) ? `<p class="hb-eval-d">${u.type === "test" ? "" : "Due "}${when(u)}</p>` : ""}${extras(u)}</div><div class="hb-eval-w">${fmtW(u.weight)}%</div></li>`;
    const group = u => `<li class="hb-eval grp"><details><summary><div class="hb-eval-m"><h3>${esc(u.name)}</h3><p class="hb-eval-d">${esc(`Best ${u.keep} of ${u.count}, ${fmtW(u.weight / Math.max(1, u.keep))}% each`)}</p></div><div class="hb-eval-w">${fmtW(u.weight)}%</div>${CHEV}</summary>
        <ul class="hb-eval-subs">${u.members.map(m => `<li><div><b>${esc(m.name)}</b>${evalWhen(m) ? `<span>${when(m)}</span>` : ""}</div>${extras(m)}</li>`).join("")}</ul></details></li>`;
    return `<h2 class="hb-h2">Evaluations</h2><p class="hb-lede">Every evaluation, its weight and when it is. Together they make up your course grade.</p>
      <ol class="hb-scheme">${E.units.map(u => (u.kind === "group" ? group(u) : one(u))).join("")}</ol>`;
  },

  announcements() {
    const items = data("announcements").items.slice().sort((a, b) => annTime(b) - annTime(a));
    const head = `<h2 class="hb-h2">Announcements</h2><p class="hb-lede">News for the class, newest first.</p>`;
    if (!items.length) return head + '<p class="hb-empty">No announcements yet.</p>';
    // By week, as on the Lectures tab: the week on the left, its announcements beside it (each with its date).
    const cal = (data("week") || {}).weeks || [], groups = [];
    items.forEach(a => {
      const key = a.wi >= 0 ? a.wi : `w:${a.week || ""}`;
      let g = groups.find(x => x.key === key);
      if (!g) groups.push(g = { key, wi: a.wi, label: a.week || "Announcements", items: [] });
      g.items.push(a);
    });
    let first = true;
    return head + `<div class="hb-term hb-anns">${groups.map((g, k) => {
      const wk = cal.find(w => w.i === g.wi);
      return `<section class="hb-week${k === 0 ? " now" : ""}"><div class="hb-week-h"><h3 title="${esc(g.label)}">${esc(g.label)}</h3>${wk && wk.dates ? `<span class="d">${esc(wk.dates)}</span>` : ""}</div>
        <div class="hb-week-b hb-ann-list">${g.items.map(a => { const h = feedHTML(a, first); first = false; return h; }).join("")}</div></section>`;
    }).join("")}</div>`;
  },

  accommodations() {
    return `<h2 class="hb-h2">My accommodations</h2><p class="hb-lede">Your accommodation requests and what was decided.</p><div class="hb-panel hb-soft"><p class="hb-empty">Requests you make will show here.</p></div>`;
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
// Each evaluation's files: the gradebook's (Evaluations → its page), then any the course page itself had (older pages).
function evalFilesOf(scheme, ef) {
  const out = {};
  arr(scheme.evals).forEach(e => { const fs = filesOf(e.files); if (fs.length) out[e.id] = fs; });
  Object.entries(ef || {}).forEach(([k, v]) => { const have = new Set((out[k] || []).map(f => f.url)); const more = filesOf(v).filter(f => !have.has(f.url)); if (more.length) out[k] = [...(out[k] || []), ...more]; });
  return out;
}
// The Lectures part's weeks (lectures.json), as the course page shows them.
const MONTHS_ = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"];
function rangeText(a, b) {
  const x = fromIso(a), y = fromIso(b) || x; if (!x) return "";
  const A = `${MONTHS_[x.getMonth()]} ${x.getDate()}`;
  return +x === +y ? A : x.getMonth() === y.getMonth() ? `${A} – ${y.getDate()}` : `${A} – ${MONTHS_[y.getMonth()]} ${y.getDate()}`;
}
function partWeeks(lectures, year) {
  return arr(lectures.weeks).filter(w => w && typeof w === "object").map((w, i) => {
    if (w.isBreak) return { i, isBreak: true, label: str(w.text), cards: [], deadlines: [] };
    const [start, end] = weekRange(w, year);
    return { i, isBreak: false, label: str(w.label), dates: str(w.dates) || rangeText(start, end), start, end, topic: str(w.topic), deadlines: [], noClass: 0,
      cards: arr(w.cards).map(c => ({ kind: str(c.kind), label: str(c.label), title: str(c.title), description: str(c.description), date: str(c.date), files: filesOf(c.files) })) };
  });
}
// The week a day is in (the last week whose Monday is on or before it).
const weekOfDay = (day, weeks) => { let f = null; weeks.forEach(w => { if (!w.isBreak && w.start && mondayOf(w.start) <= day) f = w; }); return f; };
// About: the offering's description (about.json, else the page's own), the teaching team, and the gradebook's
// course rules that its Settings show on the course page.
function aboutOf(a, scheme, team, page) {
  return { description: str(a && typeof a.description === "string" ? a.description : page.description), team, sections: [], policies: [],
    rules: arr(scheme.policies).filter(x => x && x.show).map(x => ({ title: x.title, text: x.text })) };
}
function fromPage(page, year, lectures, extra) {
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
  if (lectures && Array.isArray(lectures.weeks)) {   // the Lectures part's weeks; the announcements go to the week of their date
    const part = partWeeks(lectures, year);
    weeks.length = 0; weeks.push(...part); lists.length = 0;
    anns.forEach(a => { const d = stampDay(a.date), w = (d && weekOfDay(d, weeks)) || weeks.find(x => !x.isBreak && x.label === a.week); a.wi = w ? w.i : -1; if (w) a.week = w.label; });
  }
  if (extra && Array.isArray(extra.announcements)) {   // the Announcements part's: each in the week of its date
    anns.length = 0;
    extra.announcements.filter(a => a && (str(a.title).trim() || str(a.body).trim())).forEach(a => {
      const d = stampDay(a.date), w = d && weekOfDay(d, weeks);
      anns.push({ title: str(a.title), body: str(a.body), date: str(a.date), at: a.at || 0, week: w ? w.label : "", wi: w ? w.i : -1 });
    });
  }
  const ef = page.evalFiles || {};
  return {
    about: aboutOf(extra && extra.about, scheme, arr(extra && extra.team), page),
    lectures: { weeks, lists },
    announcements: { items: anns },
    evaluations: { units: arr(scheme.units), evals: arr(scheme.evals), files: evalFilesOf(scheme, ef),
      request: scheme.requests && scheme.requests.url ? { url: scheme.requests.url, r: scheme.requests.repo, o: scheme.requests.offering } : null },
    week: { weeks: weeks.map(w => ({ i: w.i, label: w.label, dates: w.dates || "", start: w.start || "", end: w.end || "", isBreak: w.isBreak })) },
    accommodations: {},
  };
}

const TABS = [["week", "This week"], ["announcements", "Announcements"], ["lectures", "Activities"], ["evaluations", "Evaluations"], ["about", "About"], ["accommodations", "My accommodations"]];

window.HubView = { draw, fromPage, currentWeek, today, esc, rich, markdown, meetingsTable, TABS, LOCK };
})();
