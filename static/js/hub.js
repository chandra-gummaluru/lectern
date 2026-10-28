/* The course page (/c/<handle>/<course>/<term>/): one simple page for students, like Lectern's own.

   One call to the hub's API (server/hub.py) brings back the course, who's looking, each part (and
   whether this viewer may open it) and the content of the parts they may open. The rest is drawing.
   The page opens on a home with the latest announcement, the weeks, and the evaluations; each one
   opens its own page, with a path back, as in Lectern:

     #                    home
     #announcements       every announcement, newest first
     #activities          the weeks
     #week/<i>            one week: its activities (with their files), what's due, its announcements
     #evaluations         every evaluation and its weight
     #evaluation/<id>     one evaluation (or group): when, its weight, files, accommodations
     #about, #accommodations

   Older addresses still work (#lectures, #evaluations/<id>, #week). About and My accommodations are
   drawn by hub-view.js, which the Course Page Builder uses too. */
(() => {
"use strict";

const root = document.getElementById("hb");
const $ = id => document.getElementById(id);
let D = null;

const { esc, LOCK, markdown, currentWeek, today } = window.HubView;
const tab = id => (D.tabs || []).find(t => t.id === id);
const data = id => (D.data || {})[id] || null;
const open = id => { const t = tab(id); return !!(t && t.open); };
// For the teaching team: a part that visitors who aren't signed in don't see (it's marked with a lock).
const hidden = id => { const t = tab(id); return !!(t && D.viewer.staff && t.visibility === "signed-in"); };

// ── Small things ─────────────────────────────────────────────────────
const svg = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const CHEV = svg('<path d="m9 6 6 6-6 6"/>');
const KIND_ICON = {
  lecture: svg('<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8"/>'),
  tutorial: svg('<path d="M4 5h11a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3v-3H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M19 9h1a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-1v3l-3-3h-3"/>'),
  lab: svg('<path d="M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7.5 15h9"/>'),
  other: svg('<circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="8.5"/>'),
};
const EV_ICON = {
  assignment: svg('<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h4"/>'),
  test: svg('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="m9 13 2 2 4-4"/>'),
  project: svg('<path d="m12 3 8.5 4.5L12 12 3.5 7.5z"/><path d="m3.5 12 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5"/>'),
  lab: KIND_ICON.lab, other: KIND_ICON.other,
  group: svg('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
};
const KIND_NAME = { lecture: "Lecture", tutorial: "Tutorial", lab: "Lab", other: "Other" };
const EV_NAME = { assignment: "Assignment", test: "Test", project: "Project", lab: "Lab", other: "Other" };
const kindOf = c => (KIND_NAME[c.kind] ? c.kind : (Object.keys(KIND_NAME).find(k => String(c.label || "").toLowerCase().startsWith(k)) || "lecture"));
const evType = e => (EV_NAME[e.type] ? e.type : "assignment");
const fmtW = n => String(Math.round(Number(n || 0) * 100) / 100);
const fromIso = s => { const m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(s || ""); return m ? new Date(+m[1], m[2] - 1, +m[3]) : null; };
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (s, n) => { const d = fromIso(s); if (!d) return ""; d.setDate(d.getDate() + n); return iso(d); };
const mondayOf = s => { const d = fromIso(s); if (!d) return ""; d.setDate(d.getDate() - (d.getDay() + 6) % 7); return iso(d); };
const day = (s, year) => { const d = fromIso(s); return d ? d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric", ...(year ? { year: "numeric" } : {}) }) : ""; };
// An evaluation's when: "Due Fri, Oct 2 at 23:59", a test's "Wed, Oct 28 at 18:10".
// An assignment: released, then due; a test, a lab or another: its date.
const isDue = e => evType(e) === "assignment" || e.type === "project";
const evWhen1 = e => [isDue(e) && e.release ? `Released ${day(e.release)}${e.releaseTime ? ` at ${e.releaseTime}` : ""}` : "", e.date ? `${isDue(e) ? "Due " : ""}${day(e.date)}${e.time ? ` at ${e.time}` : ""}` : ""].filter(Boolean).join(" · ");
// (The teaching team also sees the dates some sections have of their own; a student gets their section's.)
const evWhen = e => { const own = evWhen1(e), D = (e.dates || []).filter(d => d.date); if (!D.length) return own;
  const G = ((data("about") || {}).groups) || [], gn = ids => ids.map(id => (G.find(x => x.id === id) || {}).name).filter(Boolean).join(", ") || "Some sections";
  return [own && `${own} (everyone else)`, ...D.map(d => `${gn(d.groups)}: ${day(d.date)}${d.time ? ` at ${d.time}` : ""}`)].filter(Boolean).join(" · "); };
// An activity's or announcement's stamp ("Oct 18, 2026, 15:42") → "Sun, Oct 18 at 15:42".
function stampText(t) {
  const m = /([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})/.exec(t || ""); if (!m) return String(t || "");
  const d = new Date(`${m[1]} ${m[2]}, ${m[3]}`); if (isNaN(d)) return String(t || "");
  const tm = (/(\d{1,2}:\d\d)/.exec(t) || [])[1];
  return `${day(iso(d))}${tm ? ` at ${tm}` : ""}`;
}
const datesOf = c => (Array.isArray(c.dates) && c.dates.filter(Boolean).length ? c.dates.filter(Boolean) : c.date ? [c.date] : []);
function href(u) {
  u = String(u || "").trim(); if (!u) return "";
  if (/^(https?:|mailto:)/i.test(u)) return u;
  if (/^[a-z][a-z0-9+.-]*:/i.test(u) || u.startsWith("//")) return "";
  try { return new URL(u, D.pages || location.href).href; } catch (_) { return ""; }
}
const filesHTML = fs => { const L = (fs || []).map(f => [f, href(f.url)]).filter(x => x[1]); return L.length ? `<div class="hs-files">${L.map(([f, h]) => `<a class="hs-file" href="${esc(h)}" target="_blank" rel="noopener">${esc(f.label || "Download")}</a>`).join("")}</div>` : ""; };
const annTime = a => { const t = Date.parse(String(a.date || "")); return isNaN(t) ? a.at || 0 : t; };

// The weeks (with their place in the term), this week, and what's dated in a week.
const weeks = () => ((data("lectures") || {}).weeks || []);
const realWeeks = () => weeks().filter(w => !w.isBreak);
const weekNum = w => { const m = /(\d+)/.exec(w.label || ""); return m ? m[1] : String(realWeeks().indexOf(w) + 1); };
function thisWeek() {
  const cal = weeks().filter(w => !w.isBreak && w.start);
  if (!cal.length) return null;
  const cw = currentWeek(weeks().map(w => ({ ...w })), today());
  return cw && cw.dated[cw.k] ? cw.dated[cw.k].i : null;
}
function weekSpan(w) {
  if (!w.start) return null;
  const R = realWeeks(), nx = R.slice(R.indexOf(w) + 1).find(y => y.start);
  return [mondayOf(w.start), nx ? addDays(mondayOf(nx.start), -1) : addDays(mondayOf(w.end || w.start), 6)];
}
const allEvals = () => { const E = data("evaluations"); return E ? E.evals || [] : []; };
const evalsIn = w => { const s = weekSpan(w); return s ? allEvals().filter(e => e.date && e.date >= s[0] && e.date <= s[1]).sort((a, b) => `${a.date}${a.time}`.localeCompare(`${b.date}${b.time}`)) : []; };
const annsIn = w => ((data("announcements") || {}).items || []).filter(a => a.wi === w.i).sort((a, b) => annTime(b) - annTime(a));

// ── Pieces ───────────────────────────────────────────────────────────
const DAY3 = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const head = (title, sub) => `<header class="hs-head"><h1>${esc(title)}</h1>${sub ? `<p>${sub}</p>` : ""}</header>`;
const path = steps => `<nav class="hs-path" aria-label="Where you are"><a href="#">Home</a>${steps.map(([l, h]) => `<span aria-hidden="true">›</span>${h ? `<a href="${h}">${esc(l)}</a>` : `<b>${esc(l)}</b>`}`).join("")}</nav>`;
const secHead = (title, h, extra = "") => `<a class="hs-sec-h" href="${h}"><h2>${esc(title)}</h2>${extra}${CHEV}</a>`;
function lockedSec(id, title) {
  return `<section class="hs-sec"><div class="hs-sec-h hs-off"><h2>${esc(title)}</h2>${LOCK}</div><div class="hs-locked"><span>For people in the course.</span><a class="hb-btn" href="${esc(D.signIn || D.lectern)}">Sign in</a></div></section>`;
}
function lockedPage(id, title) {
  return `${path([[title]])}<div class="hb-locked">${LOCK}<h2>${esc(title)}</h2><p>${id === "accommodations" ? "Sign in to ask for accommodations and follow your requests." : "This part of the course page is for people in the course. Sign in to see it."}</p>
    <a class="hb-btn primary" href="${esc(D.signIn || D.lectern)}">Sign in</a></div>`;
}
const annsOn = key => ((data("announcements") || {}).items || []).filter(a => a.on === key).sort((x, y) => annTime(y) - annTime(x));
// For the teaching team: what's only for some sections says which.
const groupTag = ids => { if (!(ids || []).length || !D.viewer.staff) return ""; const G = ((data("about") || {}).groups) || [], n = ids.map(id => (G.find(x => x.id === id) || {}).name).filter(Boolean); return `<span class="hs-tag hs-gtag" title="Only their students see this">${esc(n.length ? n.join(", ") : "Some groups")} only</span>`; };
// New: an announcement a signed-in student hasn't seen yet. Shown in full, it's seen (told to the server a
// moment later; it stays marked New on this page until they leave it).
let SEEN0 = null; const shownNew = new Set();
const seenSet = () => SEEN0 || (SEEN0 = new Set((D.viewer && D.viewer.seen) || []));
const isNew = a => !!(D.viewer && D.viewer.role === "student" && a.id && !seenSet().has(a.id));
const note = a => { if (isNew(a)) shownNew.add(a.id); return ""; };
const unread = () => ((data("announcements") || {}).items || []).filter(isNew).length;
function markSeen() {
  const SEEN = seenSet(), ids = [...shownNew].filter(id => !SEEN.has(id)); shownNew.clear();
  if (!ids.length) return;
  setTimeout(() => { ids.forEach(id => SEEN.add(id)); paintBadge(); fetch(`${root.dataset.api}/seen`, { method: "POST", credentials: "same-origin", headers: { "X-Lectern": "1", "Content-Type": "application/json" }, body: JSON.stringify({ ids }) }).catch(() => {}); }, 1500);
}
const MEGAPHONE = svg('<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>');
// An announcement, as an activity's card is: its icon, ANNOUNCEMENT (and its sections), its title and date, its message.
const annGo = a => (a.id ? ` data-go="#announcement/${encodeURIComponent(a.id)}" role="link" tabindex="0" title="Open it: its discussion too"` : "");
const annCard = a => `<article class="hs-card hs-ann hs-act hd-row${isNew(a) ? " hs-new" : ""}${a.id ? " wk-go" : ""}"${note(a)}${annGo(a)}><span class="hs-ic">${MEGAPHONE}</span><div class="hs-act-b hd-main"><div class="hd"><p class="hs-kick">${isNew(a) ? `<span class="hs-newtag">New</span>` : ""}Announcement${groupTag(a.groups)}</p>${a.title ? `<h3>${esc(a.title)}</h3>` : ""}<p class="hs-when">${esc(stampText(a.date))}</p></div><div class="hs-body">${markdown(a.body)}</div></div></article>`;
// Discussions (discuss.js): a link to one from an activity's or an announcement's row, with how many posts it
// has (signed-in people only: they're for the people in the course); and the discussion itself, at the
// bottom of an item's page.
const CHAT = svg('<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>');
const dcLink = (t, href) => (D.viewer.signedIn && !dcOff(t) ? `<a class="hs-file dc-link" href="${href}">${CHAT}Discussion<span class="dc-link-n" data-dcn="${esc(t)}"></span></a>` : "");
// An item's buttons in one row: its files and links, then its Discussion (as the files' buttons are).
const withDc = (files, link, soon) => { const f = filesHTML(files); return f ? (link ? f.replace(/<\/div>$/, `${link}</div>`) : f) : `${soon ? `<p class="hs-soon">Files coming soon</p>` : ""}${link ? `<div class="hs-files">${link}</div>` : ""}`; };
// Discussion is on unless Lectern turned it off for the item (Allow Discussion unticked).
const REDO = svg('<path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/>');
const HEART = svg('<path d="M12 21s-7.5-4.4-7.5-10.2A4.3 4.3 0 0 1 12 8.1a4.3 4.3 0 0 1 7.5 2.7C19.5 16.6 12 21 12 21z"/>');
const dcOff = t => (D.closed || []).includes(t);
const dcHere = t => (dcOff(t) ? "" : `<section class="dc" data-dc="${esc(t)}"></section>`);
let DCN = null, DCN_AT = 0;
function discussions(m) {
  m.querySelectorAll("[data-dc]").forEach(el => import("/static/js/discuss.js").then(x => x.mount(el, { api: root.dataset.api, target: el.dataset.dc, signIn: D.signIn || D.lectern,
    ...(el.dataset.post ? { post: +el.dataset.post, onPost: p => { const b = m.querySelector(".hs-path b"); if (b) b.textContent = p ? p.title || "Post" : "Post"; if (p && p.title) document.title = p.title; } } : {}) })).catch(e => console.error(e)));
  const spans = m.querySelectorAll("[data-dcn]"); if (!spans.length || !D.viewer.signedIn) return;
  const fill = () => spans.forEach(sp => { const n = (DCN || {})[sp.dataset.dcn] || 0; sp.textContent = n ? ` · ${n}` : ""; });
  if (DCN && Date.now() - DCN_AT < 30000) return fill();
  fetch(`${root.dataset.api}/discussion/counts`, { credentials: "same-origin" }).then(r => r.ok ? r.json() : { counts: {} }).then(d => { DCN = d.counts || {}; DCN_AT = Date.now(); fill(); }).catch(() => {});
}
const findActivity = id => { for (const w of weeks()) for (const c of w.cards || []) if (String(c.id) === String(id)) return { w, c }; return null; };
// An announcement as a row in a card's group (a week's page, Announcements): as an activity's row is.
const annItem = a => `<div class="wk-item${isNew(a) ? " wk-new" : ""}${a.id ? " wk-go" : ""}"${note(a)}${annGo(a)}><span class="hs-ic">${MEGAPHONE}</span><div class="wk-b"><p class="hs-kick">${isNew(a) ? `<span class="hs-newtag">New</span>` : ""}Announcement${groupTag(a.groups)}</p><h3>${esc(a.title || "Announcement")}</h3><p class="wk-when">${esc(stampText(a.date))}</p><div class="hs-body">${markdown(a.body)}</div></div>${a.id ? CHEV : ""}</div>`;
// An evaluation as a row in a card's group (a week's page, a group's): it opens the evaluation's page.
const evItem = e => `<a class="wk-item wk-link" href="#evaluation/${encodeURIComponent(e.id)}"><span class="hs-ic">${EV_ICON[evType(e)]}</span><div class="wk-b"><p class="hs-kick">${esc(e.name)}</p><h3>${esc(e.title || e.name)}</h3>${evWhen(e) ? `<p class="wk-when">${esc(evWhen(e))}</p>` : ""}</div>${CHEV}</a>`;
function weekRow(w, now) {
  if (w.isBreak) return `<p class="hs-break">${esc(w.label || "Break")}</p>`;
  const bits = [w.dates, w.topic].filter(Boolean).map(esc).join(" · ");
  return `<a class="hs-row hs-wk${w.i === now ? " now" : ""}" href="#week/${w.i}"><span class="hs-num${w.i === now ? " on" : ""}" title="${w.i === now ? "This week" : ""}">${esc(weekNum(w))}</span><span class="hs-t"><b>${esc(w.label || "Week")}</b>${bits ? `<small>${bits}</small>` : ""}</span>${CHEV}</a>`;
}
// A week, opened: its row, then its activities and what's due, inside it (as a week is in Lectern).
function weekOpen(w, now) {
  const evs = open("evaluations") ? evalsIn(w) : [];
  const body = (w.cards.length ? w.cards.map(activityCard).join("") : `<p class="hs-empty">${w.noClass ? "No class this week." : "No activities this week."}</p>`) + evs.map(e => evRow(e)).join("");
  return `<div class="hs-group hs-wkopen">${weekRow(w, now).replace('class="hs-row hs-wk', 'class="hs-row hs-wk hs-grp')}<div class="hs-stack">${body}</div></div>`;
}
const weekList = () => { const now = thisWeek(); return `<div class="hs-list">${weeks().map(w => weekRow(w, now)).join("")}</div>`; };
function evRow(e, weight) {
  const t = evType(e);
  return `<a class="hs-row hs-ev" href="#evaluation/${encodeURIComponent(e.id)}"><span class="hs-ic">${EV_ICON[t]}</span><span class="hs-t"><small class="hs-kick">${esc(e.name)}</small><b>${esc(e.title || e.name)}</b>${evWhen(e) ? `<small>${esc(evWhen(e))}</small>` : ""}</span>${weight != null ? `<span class="hs-w">${fmtW(weight)}%</span>` : ""}${CHEV}</a>`;
}
// An announcement about an activity, under it: its date, title and message.
const annMini = a => `<div class="hs-mini"><p class="hs-kick">Announcement · ${esc(stampText(a.date))}</p>${a.title ? `<b>${esc(a.title)}</b>` : ""}<div class="hs-body">${markdown(a.body)}</div></div>`;
function activityCard(c) {
  const k = kindOf(c), D_ = datesOf(c).map(stampText).join(" · ");
  const anns = c.id ? annsOn(`act:${c.id}`) : [];
  return `<article class="hs-card hs-act hd-row${c.id ? " wk-go" : ""}"${c.id ? ` data-go="#activity/${encodeURIComponent(c.id)}" role="link" tabindex="0" title="Open it: its discussion too"` : ""}><span class="hs-ic">${KIND_ICON[k]}</span><div class="hs-act-b hd-main"><div class="hd"><p class="hs-kick">${esc(KIND_NAME[k])}${groupTag(c.groups)}</p><h3>${esc(c.title || c.label || "Untitled")}</h3>${D_ ? `<p class="hs-when">${esc(D_)}</p>` : ""}</div>${c.description ? `<div class="hs-body">${markdown(c.description)}</div>` : ""}${filesHTML(c.files) || `<p class="hs-soon">Files coming soon</p>`}${anns.length ? `<div class="hs-on">${anns.map(annMini).join("")}</div>` : ""}</div></article>`;
}
// Request Accommodation: when the gradebook says students can ask (until its deadline, if there is one).
function requestHTML(e) {
  const a = e.accom, E = data("evaluations"); if (!a || !(a.approval || a.alternate)) return "";
  const by = a.by ? new Date(`${a.by}T${a.byTime || "23:59"}`) : null, rq = E && E.request;
  if (by && !isNaN(by) && by < new Date()) return `<p class="hs-note">The deadline for accommodation requests has passed.</p>`;
    const when = by && !isNaN(by) ? `<span class="hs-by">Request by ${esc(day(a.by))}, ${esc(a.byTime || "23:59")}</span>` : "";
  // Signed in: the request is made here, on the course page. Not signed in: sign in first.
  const btn = D.viewer.signedIn ? `<a class="hb-btn" href="#request/${encodeURIComponent(e.id)}">Request Accommodation</a>`
    : `<a class="hb-btn" href="${esc(D.signIn || D.lectern)}">Sign in to Request an Accommodation</a>`;
  return `<div class="hs-req">${btn}${when}</div>`;
}
// Every evaluation (a group with its own inside it), each opening its page; the weight on the right.
function evalList() {
    const U = (data("evaluations").units || []);
    const rows = U.map(u => (u.kind === "group"
      ? `<div class="hs-group"><a class="hs-row hs-ev hs-grp" href="#evaluation/${encodeURIComponent(u.id)}"><span class="hs-ic">${EV_ICON.group}</span><span class="hs-t"><small class="hs-kick">Group</small><b>${esc(u.name)}</b><small>The best ${u.keep} of ${u.count} count, ${fmtW(u.weight / Math.max(1, u.keep))}% each</small></span><span class="hs-w">${fmtW(u.weight)}%</span>${CHEV}</a>
          <div class="hs-list">${(u.members || []).map(m => evRow(m)).join("")}</div></div>`
      : evRow(u, u.weight))).join("");
  return U.length ? `<div class="hs-list">${rows}</div>` : `<p class="hs-empty">The marking scheme will appear here.</p>`;
}
const unitOf = id => { const E = data("evaluations"); if (!E) return null; for (const u of E.units || []) { if (u.id === id) return { u }; if (u.kind === "group") { const m = (u.members || []).find(x => x.id === id); if (m) return { u: m, group: u }; } } const e = allEvals().find(x => x.id === id); return e ? { u: e } : null; };

// A row that opens a page of the course page (Evaluations, About the Course…), locked when it isn't open.
const linkRow = (id, t, sub, tb) => `<a class="hs-row hs-link" href="#${id}"><span class="hs-t"><b>${esc(t)}</b><small>${esc(sub)}</small></span>${!open(tb || id) || hidden(tb || id) ? `<span class="hs-lock" title="${open(tb || id) ? "Visitors who aren't signed in don't see this" : "Sign in to see this"}">${LOCK}</span>` : ""}${CHEV}</a>`;
// ── Requesting an accommodation ──────────────────────────────────────
// Signed in, so the course page knows who's asking (the email they signed in with); to be sure it's them,
// they give their identifier and name too, which must match the class list exactly (server/accommodations.py).
const ReqForm = (() => {
  let ev = null, info = null, rt = null, keep = {};
  const api = (method, body) => fetch(`${root.dataset.api}/accommodation${method === "GET" ? `?e=${encodeURIComponent(ev.id)}` : ""}`, {
    method, credentials: "same-origin", headers: method === "GET" ? {} : { "X-Lectern": "1", "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  }).then(r => r.json().catch(() => ({})).then(d => { if (!r.ok) { const x = new Error(d.error || "Something went wrong. Try again in a moment."); x.code = d.code; x.status = r.status; throw x; } return d; }),
    e => { if (e.status) throw e; throw new Error("Couldn't reach the course page. Check your connection and try again."); });
  const box = () => $("rq-box");
  // Names as they're written: a capital at the start of each part ("jeremy o'neil-smith" → "Jeremy O'Neil-Smith").
  const capital = v => v.replace(/(^|[\s\-'’])(\p{Ll})/gu, (m, a, b) => a + b.toUpperCase());
  function start(u) {
    ev = u; info = null; rt = null; keep = {};
    if (!D.viewer.signedIn) { box().innerHTML = `<div class="hs-card"><p>Sign in to request an accommodation.</p><a class="hb-btn" href="${esc(D.signIn || D.lectern)}">Sign in</a></div>`; return; }
    api("GET").then(d => { info = d; form(); }, e => { box().innerHTML = `<div class="hs-card rq-card"><p>${esc(e.message)}</p><div class="rq-acts"><a class="hb-btn" href="#evaluation/${encodeURIComponent(ev.id)}">Back to ${esc(ev.name)}</a></div></div>`; });
  }
  function form(err) {
    const s = info.standard, W = info.waiting || [], k = keep, dl = info.deadline;
    // One request of a kind at a time: one waiting for a decision (or the standard one, approved) can't be asked for again.
    const stdNo = W.includes("standard") ? "You've asked for it: it's waiting for a decision." : info.approvedStandard ? "You've asked for it, and it's been approved." : "";
    const altNo = W.includes("alternate") ? "You've asked for one: it's waiting for a decision." : "";
    const canStd = !!(s && s.approval) && !stdNo, alt = !!info.alternate && !altNo;
    const byEl = document.getElementById("rq-by");   // the deadline, under the title
    if (byEl) { byEl.hidden = !dl || !dl.date; byEl.innerHTML = dl && dl.date ? `Requests close ${esc(dl.text)}, or when the marks are out if that's sooner` : ""; }
    if (dl && dl.passed) { box().innerHTML = `<div class="hs-card rq-card"><p>${dl.marks ? `Requests for ${esc(ev.name)} closed when its marks came out.` : `The deadline to request an accommodation for ${esc(ev.name)} has passed (${esc(dl.text)}).`} If you still need one, contact your instructor.</p></div>`; return; }
    if (!canStd && !alt && (stdNo || altNo)) { box().innerHTML = sentHTML("You've Asked Already", `Your request for ${esc(ev.name)} is waiting for a decision. You'll get an email when it's decided.`, ""); return; }
    const kind = k.kind || (canStd && !alt ? "standard" : !canStd && alt ? "alternate" : "");
    // Each choice as Lectern's ticks are: the radio, its name, and a line under it.
    const opt = (v, t, sub, on, off) => `<label class="rq-choice${off ? " off" : ""}"><input type="radio" name="kind" class="rq-opt" data-kind="${v}" value="${v}"${on && !off ? " checked" : ""}${off ? " disabled" : ""}><b>${esc(t)}</b><span>${esc(sub)}</span></label>`;
    const staff = D.viewer.role !== "student";
    box().innerHTML = `<form class="hs-card rq-card" id="rq-form" novalidate>
      ${staff ? `<p class="rq-note">This is what a student sees. Only students signed in to the course page can send one.</p>` : ""}
      <h2 class="hs-h2">Confirm It's You</h2>
      <p class="rq-help">For security purposes, please provide us with the following information.</p>
      <div class="rq-grid">
        <label class="rq-f">${esc(String(info.idLabel || "Student Number").replace(/\b\w/g, c => c.toUpperCase()))}<input type="text" name="id" autocomplete="off" spellcheck="false" value="${esc(k.id || "")}"></label>
        <label class="rq-f">First Name<input type="text" name="first" autocomplete="given-name" spellcheck="false" value="${esc(k.first || "")}"></label>
        <label class="rq-f">Last Name<input type="text" name="last" autocomplete="family-name" spellcheck="false" value="${esc(k.last || "")}"></label>
      </div>
      <h2 class="hs-h2 rq-h2">What You Need</h2>
      <p class="rq-help">Choose one of the following accommodations.</p>
      <div class="rq-opts" role="radiogroup" aria-label="What you need">
        ${opt("standard", "The Standard Accommodation", canStd ? s.text : stdNo || (s ? `It applies without a request: ${s.text}` : "Not available for this evaluation."), kind === "standard", !canStd)}
        ${opt("alternate", "An Alternate Accommodation", alt ? "Something other than the standard accommodation: say what you need." : altNo || "Not available for this evaluation.", kind === "alternate", !alt)}
      </div>
      <div class="rq-more" id="rq-more"${kind === "alternate" ? "" : " hidden"}><div id="rq-rt"></div>
        <small class="rq-help">To share a document (a doctor's note, say), add a link to it. Files and pictures can't be attached.</small></div>
      <p class="rq-err" id="rq-err" role="alert">${esc(err || "")}</p>
      <div class="rq-acts"><span class="sp"></span><a class="hb-btn" href="#evaluation/${encodeURIComponent(ev.id)}">Cancel</a><button type="submit" class="hb-btn primary"${staff ? " disabled" : ""}>Send Request</button></div>
    </form>`;
    const f = $("rq-form");
    ["first", "last"].forEach(n => { const el = f[n]; el.addEventListener("input", () => { const p = el.selectionStart, v = capital(el.value); if (v !== el.value) { el.value = v; el.setSelectionRange(p, p); } }); });
    let chosen = kind;
    f.querySelectorAll(".rq-opt").forEach(b => { b.onchange = () => {
      chosen = b.dataset.kind;
      $("rq-more").hidden = chosen !== "alternate";
      if (chosen === "alternate" && rt) rt.el.focus();
    }; });
    import("/static/js/richtext.js").then(m => {
      rt = m.richText($("rq-rt"), { value: k.details || "", placeholder: "e.g. Writing it on a different day, because…", label: "What you need" });
    }).catch(() => { $("rq-rt").innerHTML = `<textarea class="rq-ta" maxlength="4000">${esc(k.details || "")}</textarea>`; rt = { get: () => $("rq-rt").querySelector("textarea").value, el: $("rq-rt").querySelector("textarea") }; });
    if (!err) f.id.focus();
    f.onsubmit = ev2 => {
      ev2.preventDefault();
      const d = { e: ev.id, id: f.id.value.trim(), first: capital(f.first.value.trim()), last: capital(f.last.value.trim()), kind: chosen, details: chosen === "alternate" && rt ? rt.get().trim() : "" };
      keep = { ...d };
      const say = t => { $("rq-err").textContent = t; };
      if (!d.id || !d.first || !d.last) return say(`Fill in your ${info.idLabel.toLowerCase()}, first name and last name.`);
      if (!d.kind) return say("Choose what you're asking for.");
      if (d.kind === "alternate" && !d.details) { say("Say what you need."); if (rt) rt.el.focus(); return; }
      const b = f.querySelector("button[type=submit]"); b.disabled = true; b.textContent = "Sending…";
      api("POST", d).then(done, e => form(e.message));
    };
  }
  function done(res) {
    keep = { id: keep.id, first: keep.first, last: keep.last };
    box().innerHTML = sentHTML("Request Sent", `Your instructor will review it, and you'll get an email at <b>${esc(res.email)}</b> when it's approved or rejected.${res.emailed ? " We've emailed you a copy." : ""}`, res.id);
  }
  function sentHTML(title, text, ref) {
    return `<div class="rq-sent"><span class="rq-sent-ic" aria-hidden="true">${svg('<path d="M5 12.5l4.5 4.5L19 7.5"/>')}</span><div class="rq-sent-b"><b>${title}</b><p>${text}</p>${ref ? `<small>Reference ${esc(ref)}</small>` : ""}</div></div>
      <div class="rq-acts"><span class="sp"></span><a class="hb-btn" href="#accommodations">See My Requests</a><a class="hb-btn" href="#evaluation/${encodeURIComponent(ev.id)}">Back to ${esc(ev.name)}</a></div>`;
  }
  return { start };
})();

// ── Requesting a remark ──────────────────────────────────────────────
// Signed in, and their mark is out: they say what should be looked at again and why; a code emailed to them
// confirms it (as an accommodation request's does); decided in Lectern's Remark Requests.
const RemarkForm = (() => {
  let ev = null, info = null, rt = null, keep = {};
  const api = (method, body) => fetch(`${root.dataset.api}/remark${method === "GET" ? `?e=${encodeURIComponent(ev.id)}` : ""}`, {
    method, credentials: "same-origin", headers: method === "GET" ? {} : { "X-Lectern": "1", "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  }).then(r => r.json().catch(() => ({})).then(d => { if (!r.ok) { const x = new Error(d.error || "Something went wrong. Try again in a moment."); x.code = d.code; throw x; } return d; }),
    e => { if (e.code !== undefined) throw e; throw new Error("Couldn't reach the course page. Check your connection and try again."); });
  const box = () => $("rq-box");
  const back = () => `<a class="hb-btn" href="#evaluation/${encodeURIComponent(ev.id)}">Back to ${esc(ev.name)}</a>`;
  function start(u) {
    ev = u; info = null; rt = null; keep = {};
    if (!D.viewer.signedIn) { box().innerHTML = `<div class="hs-card"><p>Sign in to request a remark.</p><a class="hb-btn" href="${esc(D.signIn || D.lectern)}">Sign in</a></div>`; return; }
    api("GET").then(d => { info = d; form(); }, e => { box().innerHTML = `<div class="hs-card rq-card"><p>${esc(e.message)}</p><div class="rq-acts">${back()}</div></div>`; });
  }
  function form(err) {
    const by = document.getElementById("rq-by"), dl = info.deadline;
    if (by) { by.hidden = !dl; by.textContent = dl ? `Requests close ${dl.text}` : ""; }
    const stop = info.closed ? `The deadline to request a remark for ${ev.name} has passed (${dl ? dl.text : ""}).`
      : info.notYet ? `Remark requests for ${ev.name} open ${info.from ? info.from.text : "later"}.`
      : !info.released || !info.marked ? `You can ask once your mark for ${ev.name} is out.` : "";
    if (info.waiting) { box().innerHTML = sentHTML("You've Asked Already", `Your remark request for ${esc(ev.name)} is waiting for a decision. You'll get an email when it's decided.`, ""); return; }
    if (stop) { box().innerHTML = `<div class="hs-card rq-card"><p>${esc(stop)}</p><div class="rq-acts">${back()}</div></div>`; return; }
    const staff = D.viewer.role !== "student";
    box().innerHTML = `<form class="hs-card rq-card" id="rq-form" novalidate>
      ${staff ? `<p class="rq-note">This is what a student sees. Only students signed in to the course page can send one.</p>` : ""}
      <h2 class="hs-h2">Confirm It's You</h2>
      <p class="rq-help">For security purposes, please provide us with the following information.</p>
      <div class="rq-grid">
        <label class="rq-f">${esc(String(info.idLabel || "Student Number").replace(/\b\w/g, c => c.toUpperCase()))}<input type="text" name="id" autocomplete="off" spellcheck="false" value="${esc(keep.id || "")}"></label>
        <label class="rq-f">First Name<input type="text" name="first" autocomplete="given-name" spellcheck="false" value="${esc(keep.first || "")}"></label>
        <label class="rq-f">Last Name<input type="text" name="last" autocomplete="family-name" spellcheck="false" value="${esc(keep.last || "")}"></label>
      </div>
      <h2 class="hs-h2 rq-h2">What Should Be Remarked</h2>
      <p class="rq-help">Say which questions or parts, and why you think they should be looked at again.</p>
      <div class="rq-more"><div id="rq-rt"></div><small class="rq-help">To share a document, add a link to it. Files and pictures can't be attached.</small></div>
      <p class="rq-err" id="rq-err" role="alert">${esc(err || "")}</p>
      <div class="rq-acts"><span class="sp"></span><a class="hb-btn" href="#evaluation/${encodeURIComponent(ev.id)}">Cancel</a><button type="submit" class="hb-btn primary"${staff ? " disabled" : ""}>Send Request</button></div>
    </form>`;
    const f = $("rq-form");
    const cap = v => v.replace(/(^|[\s\-'’])(\p{Ll})/gu, (m0, a, b) => a + b.toUpperCase());
    ["first", "last"].forEach(n => { const el = f[n]; el.addEventListener("input", () => { const p = el.selectionStart, v = cap(el.value); if (v !== el.value) { el.value = v; el.setSelectionRange(p, p); } }); });
    import("/static/js/richtext.js").then(m => { rt = m.richText($("rq-rt"), { value: keep.details || "", placeholder: "e.g. Question 2(b): my answer is the same as the solution's, but it lost 2 marks…", label: "What should be remarked" }); });
    if (!err) f.id.focus();
    f.onsubmit = e2 => {
      e2.preventDefault();
      const d = { e: ev.id, id: f.id.value.trim(), first: cap(f.first.value.trim()), last: cap(f.last.value.trim()), details: rt ? rt.get().trim() : "" };
      keep = { ...d };
      if (!d.id || !d.first || !d.last) { $("rq-err").textContent = `Fill in your ${String(info.idLabel || "student number").toLowerCase()}, first name and last name.`; return; }
      if (!d.details) { $("rq-err").textContent = "Say what should be remarked, and why."; if (rt) rt.el.focus(); return; }
      const b = f.querySelector("button[type=submit]"); b.disabled = true; b.textContent = "Sending…";
      api("POST", d).then(done, e => form(e.message));
    };
  }
  function done(res) {
    keep = { id: keep.id, first: keep.first, last: keep.last };
    box().innerHTML = sentHTML("Request Sent", `Your instructor will review it, and you'll get an email at <b>${esc(res.email)}</b> when it's decided.${res.emailed ? " We've emailed you a copy." : ""}`, res.id);
  }
  function sentHTML(title, text, ref) {
    return `<div class="rq-sent"><span class="rq-sent-ic" aria-hidden="true">${svg('<path d="M5 12.5l4.5 4.5L19 7.5"/>')}</span><div class="rq-sent-b"><b>${title}</b><p>${text}</p>${ref ? `<small>Reference ${esc(ref)}</small>` : ""}</div></div>
      <div class="rq-acts"><span class="sp"></span><a class="hb-btn" href="#accommodations">See My Requests</a>${back()}</div>`;
  }
  return { start };
})();

// ── One evaluation, as one card (as the gradebook's editor and a student's page have it) ──
// Its dates (a signed-in student's section's; everyone's otherwise), its grading (worth, and their mark),
// what happens if it's missed (the gradebook's two choices, the chosen one marked, and where its weight goes),
// its files and its announcements. Request Accommodation sits at the top, where the editor's buttons are.
function evalCard(u, group, E) {
  const t = evType(u), files = filesHTML((E.files || {})[u.id] || u.files), A = annsOn(`eval:${u.id}`);
  const at = (d, tm) => (d ? `${day(d, true)}${tm ? ` at ${tm}` : ""}` : "To be announced");
  const due = isDue(u), me = D.viewer && D.viewer.role === "student";
  const sec = title => `<h2 class="ec-sec">${esc(title)}</h2>`;
  // Dates: one row each (the course's, and each section's own), Released and Due (or its Date).
  const PIN = svg('<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>');
  const rows = [{ who: (u.dates || []).length ? "All other sections" : me ? "" : "Everyone", date: u.date, time: u.time, release: u.release, releaseTime: u.releaseTime, where: u.where, map: u.map, address: u.address },
    ...(u.dates || []).map(d => ({ who: (d.names || []).join(", ") || "Some sections", ...d }))];
  if ((u.dates || []).length) rows.push(rows.shift());   // the sections' own first, then everyone else's
  // Its facts, together in one area (no boxes): when (each section's, if they differ), what it's worth, its points.
  const tile = (k, v, sub = "", cls = "") => `<div class="ec-fact${cls}"><small>${esc(k)}</small><b>${esc(v)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</div>`;
  // Its dates, a row each: whose (a section's icon and name, or everyone), then when (released, and due or its date).
  const CAL = svg('<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>');
  const OPEN = svg('<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>');
  const ALL = svg('<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><circle cx="17" cy="9" r="2.6"/><path d="M16.5 14.6c2.6.2 4.5 2.2 4.5 5.4"/>');
  const whoIc = r => (r.kinds && r.kinds.length ? KIND_ICON[r.kinds[0]] || KIND_ICON.other : ALL);
  const dates = `<div class="ec-when">${rows.map(r => `<div class="ec-wrow">
      ${r.who ? `<span class="ec-wwho"><span class="hs-ic sm">${whoIc(r)}</span>${esc(r.who)}</span>` : ""}
      <span class="ec-wat">${due && r.release ? `<span class="ec-wd"><span class="hs-ic sm">${OPEN}</span><small>Released</small>${esc(at(r.release, r.releaseTime))}</span>` : ""}<span class="ec-wd"><span class="hs-ic sm">${CAL}</span>${due ? "<small>Due</small>" : ""}${esc(at(r.date, r.time))}</span>${r.where ? `<span class="ec-wd"><span class="hs-ic sm">${PIN}</span>${r.map ? `<a href="${esc(r.map)}" target="_blank" rel="noopener" title="${esc(r.address || "On the map")}">${esc(r.where)}</a>` : esc(r.where)}</span>` : ""}</span></div>`).join("")}</div>`;
  // Grading: what it's worth, and its points (theirs, once it's marked).
  const m = (D.viewer.marks || {})[u.id], total = u.total;
  const ST = { missed: "Not submitted", aiv: "Academic integrity issue", excused: "Excused", deferred: "Deferred" };
  // Grading, as the dates are: one row of what it's worth, out of how many points, and their mark.
  const outOf = total ? fmtW(total) : "—";
  const mark = m && m.status ? ST[m.status] : m && m.pts != null ? `${fmtW(m.pts)} / ${total ? fmtW(total) : "?"}${total ? ` (${fmtW(Math.round(m.pts / total * 1000) / 10)}%)` : ""}` : me ? "Not marked yet" : "Sign in to see it";
  const worthV = group ? `${fmtW(group.weight / Math.max(1, group.keep))}%` : u.weight != null ? `${fmtW(u.weight)}%` : "—";
  const PCT = svg('<path d="M19 5 5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>');
  const PTS = svg('<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>');
  const MARK = svg('<circle cx="12" cy="12" r="8.5"/><path d="m8.2 12.3 2.6 2.6 5-5.2"/>');
  const fact = (ic, k, v, cls = "") => `<span class="ec-wd${cls}"><span class="hs-ic sm">${ic}</span><small>${esc(k)}</small>${esc(v)}</span>`;
  // Their mark, big (as the gradebook shows a student's): the percent, with its points under it.
  const marked = m && m.pts != null, pc = marked && total ? Math.round(m.pts / total * 1000) / 10 : null;
  const big = m && m.status ? `<b class="ec-mk-st">${esc(ST[m.status])}</b>` : marked ? `<b>${pc != null ? `${fmtW(pc)}%` : fmtW(m.pts)}</b><small>${fmtW(m.pts)} / ${total ? fmtW(total) : "?"}</small>` : `<b class="ec-mk-none">—</b><small>${me ? "Not marked yet" : "Sign in to see your mark"}</small>`;
  const grading = `<div class="ec-grading"><div class="ec-mk">${big}</div></div>`;
  // Under its title: what it's worth and out of how many points, in words.
  const subline = [worthV !== "—" ? `Worth ${worthV} of your grade` : "", total ? `${fmtW(total)} points` : "", group ? `in ${group.name}, where the best ${group.keep} of ${group.count} count` : ""].filter(Boolean).join(" · ");
  // If you miss it: the gradebook's choice (as its editor shows it, not to be changed here).
  const w = fmtW(u.weight), mi = u.missed;
  const opt = (on, ttl, sub) => `<p class="ec-p ec-pol">${esc(sub)}</p>`;
  const policy = !group && mi ? `<div>${mi.mode === "reweight" && (mi.parts || []).length ? "" : opt(true, "", `If you miss it, it counts as zero: the ${w}% stays, with a mark of 0.`)}</div>
    ${mi.mode === "reweight" && (mi.parts || []).length ? `<div class="ec-rw"><p class="ec-rw-h">If you miss it, its ${w}% goes to…</p>${mi.parts.map(x => {
      const it = unitOf(x.id), ic = EV_ICON[it ? evType(it.u) : "assignment"];
      return `<div class="ec-rw-row"><span class="hs-ic sm">${ic}</span><b>${esc(x.name)}</b><span class="sp"></span>${x.kind === "shift" && x.was != null ? `<s>${fmtW(x.was)}%</s><span class="ec-arrow">→</span><b>${fmtW(x.was + x.pct)}%</b>` : `<b>${fmtW(x.pct)}%</b>`}</div>`; }).join("")}
      ${mi.zero > 0 ? `<div class="ec-rw-row ec-zero"><span class="sp"></span>${fmtW(mi.zero)}% counts as zero</div>` : ""}</div>` : ""}` : (u.notes || []).map(n => `<p class="ec-p">${esc(n)}</p>`).join("");
  // Accommodations: the standard one (if it must be asked for), and until when.
  const a = u.accom || {}, by = a.by ? `${day(a.by, true)}, ${a.byTime || "23:59"}, or when the marks are out if that's sooner` : "";
  // Accommodations: one row, as the dates are: what can be asked for and until when, and the button to ask.
  const HAND = HEART;
  const asks = [a.standard && a.approval ? (policy && mi ? "The policy above applies only if you request it and it's approved." : `The standard accommodation (${String(a.standard).replace(/\.\s*$/, "")}) applies only if you request it and it's approved.`) : "", a.alternate ? (a.standard && a.approval ? "You can also ask for something else." : "You can ask for an alternate accommodation.") : ""].filter(Boolean).join(" ");
  const acc = (a.standard && a.approval) || a.alternate ? `<div class="ec-accrow"><span class="hs-ic sm">${HAND}</span><div class="ec-acct"><b>Accommodations</b><span>${esc(asks)}</span>${by ? `<small>Requests close ${esc(by)}.</small>` : ""}</div>@@REQ@@</div>` : "";
  const req = requestBtn(u);
  // Remarks: once their mark is out, a student can ask for it to be looked at again (while requests are open).
  const rk = u.remark, rkBy = rk && rk.by ? new Date(`${rk.by}T${rk.byTime || "23:59"}`) : null, rkFrom = rk && rk.from ? new Date(`${rk.from}T${rk.fromTime || "00:00"}`) : null;
  const rkBtn = !rk ? "" : !D.viewer.signedIn ? `<a class="hb-btn" href="${esc(D.signIn || D.lectern)}">Sign in to Request a Remark</a>`
    : rkBy && !isNaN(rkBy) && rkBy < new Date() ? `<button type="button" class="hb-btn" disabled>Requests Closed</button>`
    : me && m && !(rkFrom && rkFrom > new Date()) ? `<a class="hb-btn" href="#remark/${encodeURIComponent(u.id)}">Request Remark</a>` : "";
  const rkText = !rk ? "" : me && !m ? "Once your mark is out, you can ask for it to be looked at again." : rkFrom && rkFrom > new Date() ? `You can ask for your mark to be looked at again from ${rk.from ? `${day(rk.from, true)}${rk.fromTime ? `, ${rk.fromTime}` : ""}` : ""}.` : "You can ask for your mark to be looked at again.";
  const rmk = rk ? `<div class="ec-accrow"><span class="hs-ic sm">${REDO}</span><div class="ec-acct"><b>Remarks</b><span>${esc(rkText)}</span>${rk.by ? `<small>Requests close ${esc(`${day(rk.by, true)}, ${rk.byTime || "23:59"}`)}.</small>` : ""}</div>${rkBtn ? `<span class="ec-accbtn">${rkBtn}</span>` : ""}</div>` : "";
  return `${path([["Evaluations", "#evaluations"], ...(group ? [[group.name, `#evaluation/${encodeURIComponent(group.id)}`]] : []), [u.name]])}
    <article class="ec-card">
      <header class="ec-head"><span class="hs-ic ec-ic">${EV_ICON[t]}</span><div class="ec-tt"><p class="hs-kick">${esc(u.name)}</p><h1>${esc(u.title || u.name)}</h1>${subline ? `<p class="ec-subline">${esc(subline)}</p>` : ""}</div>${grading}</header>
      <div class="ec-part">${dates}</div>
      ${policy ? `<div class="ec-part">${policy}</div>` : ""}
      ${acc ? `<div class="ec-part">${acc.replace("@@REQ@@", req ? `<span class="ec-accbtn">${req}</span>` : "")}</div>` : req ? `<div class="ec-part ec-req">${req}</div>` : ""}
      ${rmk ? `<div class="ec-part">${rmk}</div>` : ""}
      ${files ? `${sec("Files and Links")}${files}` : ""}
      ${A.length ? `${sec("Announcements")}<div class="hs-stack">${A.map(annCard).join("")}</div>` : ""}
      ${dcHere(`eval:${u.id}`)}
    </article>`;
}
// Request Accommodation, at the top of an evaluation's card: when students can ask (until its deadline).
function requestBtn(e) {
  const a = e.accom; if (!a || !(a.approval || a.alternate)) return "";
  if (e.released || (D.viewer.marks || {})[e.id]) return `<button type="button" class="hb-btn" disabled>Requests Closed</button>`;   // its marks are out
  const by = a.by ? new Date(`${a.by}T${a.byTime || "23:59"}`) : null;
  if (by && !isNaN(by) && by < new Date()) return `<button type="button" class="hb-btn" disabled>Requests Closed</button>`;
  return D.viewer.signedIn ? `<a class="hb-btn" href="#request/${encodeURIComponent(e.id)}">Request Accommodation</a>` : `<a class="hb-btn" href="${esc(D.signIn || D.lectern)}">Sign in to Request an Accommodation</a>`;
}

// ── Pages ────────────────────────────────────────────────────────────
const PAGES = {
  home() {
    const c = D.course, a = data("about"), out = [];
    const shown = new Set();   // what has a See all link already (it isn't listed again below)
    // The newest announcement in full, then this week opened (the first week, before the term starts).
    if (open("announcements")) {
      const items = (data("announcements").items || []).slice().sort((x, y) => annTime(y) - annTime(x));
      if (items.length) { out.push(`<section class="hs-sec">${annCard(items[0])}<div class="hs-list hs-after">${linkRow("announcements", "All Announcements", unread() > (isNew(items[0]) ? 1 : 0) ? `${unread() - (isNew(items[0]) ? 1 : 0)} more new · ${items.length} in all, newest first.` : `${items.length} announcement${items.length === 1 ? "" : "s"}, newest first.`)}</div></section>`); shown.add("announcements"); }
    }
    if (open("lectures")) {
      const now = thisWeek(), w = realWeeks().find(x => x.i === now) || realWeeks()[0];
      if (w) { out.push(`<section class="hs-sec">${weekOpen(w, now)}<div class="hs-list hs-after">${linkRow("activities", "All Weeks", "The term, week by week: lectures, tutorials and labs, with their files.", "lectures")}</div></section>`); shown.add("activities"); }
    }
    // Then everything else, each a page of its own.
    const more = [
      ["announcements", "Announcements", "News for the class, newest first."],
      ["activities", "Activities", "The term, week by week: lectures, tutorials and labs, with their files.", "lectures"],
      ["evaluations", "Evaluations", "Every evaluation, its weight and when it is."],
      ["about", "About the Course", "The teaching team, class times and office hours, and the course's rules."],
      ["accommodations", "My Requests", "Your accommodation and remark requests, and what was decided."],
    ].filter(([id, , , t]) => tab(t || id) && !shown.has(id));
    if (more.length) out.push(`<section class="hs-sec"><div class="hs-list">${more.map(([id, t, s, tb]) => linkRow(id, t, s, tb)).join("")}</div></section>`);
    document.title = [c.code, c.title].filter(Boolean).join(": ") || "Course page";
    return out.join("");
  },
  announcements() {
    if (!open("announcements")) return lockedPage("announcements", "Announcements");
    const items = (data("announcements").items || []).slice().sort((a, b) => annTime(b) - annTime(a));
    // The title, then each announcement a card of its own, newest first.
    return `${path([["Announcements"]])}${head("Announcements", "News for the class, newest first.")}
      ${items.length ? `<div class="hs-cards">${items.map(annItem).join("")}</div>` : `<p class="hs-empty">No announcements yet.</p>`}`;
  },
  activities() {
    if (!open("lectures")) return lockedPage("lectures", "Activities");
    // The title, then the term's weeks, a card each.
    const now = thisWeek();
    const rows = weeks().map(w => w.isBreak ? `<div class="wk-item wk-break">${esc(w.label || "Break")}</div>`
      : `<a class="wk-item wk-link hs-wk${w.i === now ? " wk-now" : ""}" href="#week/${w.i}"><span class="hs-num${w.i === now ? " on" : ""}"${w.i === now ? ' title="This week"' : ""}>${esc(weekNum(w))}</span><div class="wk-b"><p class="hs-kick">${esc(w.label || "Week")}</p><h3>${esc(w.topic || w.label || "Week")}</h3>${w.dates ? `<p class="wk-when">${esc(w.dates)}</p>` : ""}</div>${CHEV}</a>`).join("");
    return `${path([["Activities"]])}${head("Activities", "The term, week by week: open a week for its lectures, tutorials and labs, their files, and what's due.")}
      ${rows ? `<div class="hs-cards">${rows}</div>` : `<p class="hs-empty">The weeks will appear here.</p>`}`;
  },
  week(arg) {
    if (!open("lectures")) return lockedPage("lectures", "Activities");
    const w = weeks().find(x => String(x.i) === String(arg) && !x.isBreak);
    if (!w) return PAGES.activities();
    const now = thisWeek() === w.i, R = realWeeks(), k = R.indexOf(w), prev = R[k - 1], next = R[k + 1];
    const evs = open("evaluations") ? evalsIn(w) : [], anns = open("announcements") ? annsIn(w) : [];
    const sub = [w.dates, w.topic].filter(Boolean).map(esc).join(" · ") + (now ? ` <span class="hs-tag">This week</span>` : "");
    // One card, as an evaluation's page is: the week at the top, then its activities, what's due, and its
    // announcements, each a row (no cards inside the card).
    const item = (ic, kick, title, when, rest = "", go = "") => `<div class="wk-item${go ? " wk-go" : ""}"${go ? ` data-go="${go}" role="link" tabindex="0" title="Open it: its discussion too"` : ""}><span class="hs-ic">${ic}</span><div class="wk-b"><p class="hs-kick">${kick}</p><h3>${esc(title)}</h3>${when ? `<p class="wk-when">${esc(when)}</p>` : ""}${rest}</div>${go ? CHEV : ""}</div>`;
    const acts = w.cards.map(c => { const k = kindOf(c), anns = c.id ? annsOn(`act:${c.id}`) : [];
      return item(KIND_ICON[k], `${esc(KIND_NAME[k])}${groupTag(c.groups)}`, c.title || c.label || "Untitled", datesOf(c).map(stampText).join(" · "),
        `${c.description ? `<div class="hs-body">${markdown(c.description)}</div>` : ""}${filesHTML(c.files) || `<p class="hs-soon">Files coming soon</p>`}${anns.length ? `<div class="hs-on">${anns.map(annMini).join("")}</div>` : ""}`, c.id ? `#activity/${encodeURIComponent(c.id)}` : ""); }).join("");
    const due = evs.map(evItem).join("");
    const an = anns.map(annItem).join("");
    return `<div class="wk-top">${path([["Activities", "#activities"], [w.label || "Week"]])}<nav class="wk-pn" aria-label="Other weeks">${prev ? `<a class="hb-btn" href="#week/${prev.i}" title="${esc(prev.label || "Previous week")}">${svg('<path d="m15 6-6 6 6 6"/>')}Previous</a>` : `<span class="hb-btn wk-off" aria-disabled="true">${svg('<path d="m15 6-6 6 6 6"/>')}Previous</span>`}${next ? `<a class="hb-btn" href="#week/${next.i}" title="${esc(next.label || "Next week")}">Next${svg('<path d="m9 6 6 6-6 6"/>')}</a>` : `<span class="hb-btn wk-off" aria-disabled="true">Next${svg('<path d="m9 6 6 6-6 6"/>')}</span>`}</nav></div>
      <article class="ec-card wk-card">
        <header class="ec-head"><span class="hs-num${now ? " on" : ""}"${now ? ' title="This week"' : ""}>${esc(weekNum(w))}</span><div class="ec-tt"><p class="hs-kick">${esc(w.label || "Week")}</p><h1>${esc(w.topic || w.label || "Week")}</h1>${w.dates ? `<p class="ec-subline">${esc(w.dates)}</p>` : ""}</div></header>
        ${[acts, due, an].filter(Boolean).map(x => `<div class="wk-group"><div class="wk-list">${x}</div></div>`).join("") || `<p class="hs-empty">${w.noClass ? "No class this week." : "No activities this week."}</p>`}
      </article>
`;
  },
  evaluations() {
    if (!open("evaluations")) return lockedPage("evaluations", "Evaluations");
    // The title, then each evaluation a card with its weight: a group a tinted card with its own inside it,
    // and a makeup a dashed card under the evaluation it's for.
    const U = data("evaluations").units || [], MK = allEvals().filter(x => x.makeupFor);
    const W = w => (w != null ? `<span class="wk-w">${fmtW(w)}%</span>` : "");
    const row = (e, w, sub, mk) => `<a class="wk-item wk-link hs-ev${sub ? " wk-sub" : ""}${mk ? " mk" : ""}" href="#evaluation/${encodeURIComponent(e.id)}"><span class="hs-ic">${EV_ICON[e.kind === "group" ? "group" : evType(e)]}</span><div class="wk-b"><p class="hs-kick">${esc(e.kind === "group" ? "Group" : mk ? `Makeup for ${mk.name}` : e.name)}</p><h3>${esc(e.kind === "group" ? e.name : e.title || e.name)}</h3>${e.kind === "group" ? `<p class="wk-when">The best ${e.keep} of ${e.count} count, ${fmtW(e.weight / Math.max(1, e.keep))}% each</p>` : evWhen(e) ? `<p class="wk-when">${esc(evWhen(e))}</p>` : ""}</div>${W(w)}${CHEV}</a>`;
    const one = (e, w, sub) => row(e, w, sub) + MK.filter(x => x.makeupFor === e.id).map(x => row(x, null, sub, e)).join("");
    const rows = U.map(u => u.kind === "group" ? `<div class="hs-gcard">${row(u, u.weight)}<div class="hs-cards">${(u.members || []).map(m => one(m, null, true)).join("")}</div></div>` : one(u, u.weight)).join("");
    return `${path([["Evaluations"]])}${head("Evaluations", "Every evaluation, its weight and when it is. Together they make up your course grade.")}
      ${rows ? `<div class="hs-cards">${rows}</div>` : `<p class="hs-empty">The marking scheme will appear here.</p>`}`;
  },
  evaluation(arg) {
    if (!open("evaluations")) return lockedPage("evaluations", "Evaluations");
    const f = unitOf(arg); if (!f) return PAGES.evaluations();
    if (UPD && (UPD.items || []).some(x => x.kind === "mark" && x.eval === f.u.id)) setTimeout(() => seenUpd(`eval:${f.u.id}`), 0);   // its mark isn't new any more
    const { u, group } = f, E = data("evaluations");
    if (u.kind === "group") {
      return `${path([["Evaluations", "#evaluations"], [u.name]])}
        <article class="ec-card wk-card">
          <header class="ec-head"><span class="hs-ic ec-ic">${EV_ICON.group}</span><div class="ec-tt"><p class="hs-kick">Group</p><h1>${esc(u.name)}</h1><p class="ec-subline">Worth ${fmtW(u.weight)}% of your grade: the best ${u.keep} of ${u.count} count, ${fmtW(u.weight / Math.max(1, u.keep))}% each.</p></div></header>
          ${(u.members || []).length ? `<div class="wk-group"><div class="wk-list">${u.members.map(evItem).join("")}</div></div>` : ""}
        </article>`;
    }
    return evalCard(u, group, E);
  },
  // One activity (#activity/<id>): its card, and its discussion.
  activity(arg) {
    if (!open("lectures")) return lockedPage("lectures", "Activities");
    const f = findActivity(arg); if (!f) return PAGES.activities();
    const { w, c } = f, k = kindOf(c), anns = c.id ? annsOn(`act:${c.id}`) : [], when = datesOf(c).map(stampText).join(" · ");
    return `${path([["Activities", "#activities"], [w.label || "Week", `#week/${w.i}`], [c.title || c.label || "Activity"]])}
      <article class="ec-card wk-card">
        <header class="ec-head"><span class="hs-ic ec-ic">${KIND_ICON[k]}</span><div class="ec-tt"><p class="hs-kick">${esc(KIND_NAME[k])}${groupTag(c.groups)}</p><h1>${esc(c.title || c.label || "Untitled")}</h1>${when ? `<p class="ec-subline">${esc(when)}</p>` : ""}</div></header>
        ${c.description ? `<div class="hs-body ec-body">${markdown(c.description)}</div>` : ""}${filesHTML(c.files)}
        ${anns.length ? `<div class="wk-group"><div class="wk-list">${anns.map(annItem).join("")}</div></div>` : ""}
        ${dcHere(`act:${c.id}`)}
      </article>`;
  },
  // One post of a discussion (#post/<target>/<id>), on its own page: the way to it is the item it's on.
  post(arg) {
    const t = String(arg || ""), id = decodeURIComponent(location.hash.slice(1)).split("/")[2], [k, x] = [t.slice(0, t.indexOf(":")), t.slice(t.indexOf(":") + 1)];
    let way = null;
    if (k === "eval" && open("evaluations")) { const f = unitOf(x); if (f) way = [["Evaluations", "#evaluations"], [f.u.title || f.u.name || "Evaluation", `#evaluation/${encodeURIComponent(f.u.id)}`]]; }
    if (k === "act" && open("lectures")) { const f = findActivity(x); if (f) way = [["Activities", "#activities"], [f.w.label || "Week", `#week/${f.w.i}`], [f.c.title || f.c.label || "Activity", `#activity/${encodeURIComponent(f.c.id)}`]]; }
    if (k === "ann" && open("announcements")) { const a = ((data("announcements") || {}).items || []).find(y => String(y.id) === x); if (a) way = [["Announcements", "#announcements"], [a.title || "Announcement", `#announcement/${encodeURIComponent(a.id)}`]]; }
    if (!way || !/^\d+$/.test(id || "")) return PAGES.home();
    if (dcOff(t)) return PAGES[{ eval: "evaluation", act: "activity", ann: "announcement" }[k]](x);   // discussion's off: the item itself
    return `${path([...way, ["Post"]])}
      <article class="ec-card dc-page"><section class="dc" data-dc="${esc(t)}" data-post="${esc(id)}"></section></article>`;
  },
  // One announcement (#announcement/<id>): it, and its discussion.
  announcement(arg) {
    if (!open("announcements")) return lockedPage("announcements", "Announcements");
    const a = ((data("announcements") || {}).items || []).find(x => String(x.id) === String(arg)); if (!a) return PAGES.announcements();
    note(a);
    return `${path([["Announcements", "#announcements"], [a.title || "Announcement"]])}
      <article class="ec-card wk-card">
        <header class="ec-head"><span class="hs-ic ec-ic">${MEGAPHONE}</span><div class="ec-tt"><p class="hs-kick">${isNew(a) ? `<span class="hs-newtag">New</span>` : ""}Announcement${groupTag(a.groups)}</p><h1>${esc(a.title || "Announcement")}</h1><p class="ec-subline">${esc(stampText(a.date))}</p></div></header>
        <div class="hs-body ec-body">${markdown(a.body)}</div>
        ${dcHere(`ann:${a.id}`)}
      </article>`;
  },
  // (Its description is in the header already.)
  about() {
    if (!open("about")) return lockedPage("about", "About the Course");
    const a = data("about"), G = a.groups, T = a.team || [];
    // The rest (the course page's own sections, the rules) as it was drawn; without sections, the team's times too.
    const rest = HubView.draw({ ...D, data: { ...D.data, about: { ...a, description: "", ...(G ? { team: [], groups: null, rules: [] } : {}) } } }, "about").replace(/<h2 class="hb-h2">About the course<\/h2>/, "");
    if (!G) return `${path([["About the Course"]])}${head("About the Course", "")}${rest}`;
    const mine = D.viewer && D.viewer.role === "student";
    // One card, as a week's page is: each section and each person a row (their kind's icon, or their initials),
    // with their times as lines of icons: the days, the hours, and where.
    const CAL = svg('<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>');
    const CLOCK = svg('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>');
    const PIN = svg('<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>');
    const MAIL = svg('<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>');
    const fact = (ic, html) => `<span class="ec-wd"><span class="hs-ic sm">${ic}</span>${html}</span>`;
    const timesHTML = I => { const L = [];   // the days that share a time and a place, together
      I.slice().sort((x, y) => (x.day || 9) - (y.day || 9)).forEach(x => { const k = `${x.start}|${x.end}|${x.where || ""}`, l = L.find(y => y.k === k); if (l) l.days.push(DAY3[x.day]); else L.push({ k, days: [DAY3[x.day]].filter(Boolean), x }); });
      return `<div class="ab-times">${L.map(l => `<div class="ab-time">${fact(CAL, esc(l.days.join(", ")))}${l.x.start ? fact(CLOCK, esc([l.x.start, l.x.end].filter(Boolean).join("–"))) : ""}${l.x.where ? fact(PIN, l.x.map ? `<a href="${esc(l.x.map)}" target="_blank" rel="noopener" title="${esc(l.x.address || "On the map")}">${esc(l.x.where)}</a>` : esc(l.x.where)) : ""}</div>`).join("")}</div>`; };
    const SEC = { lecture: "Lecture Section", tutorial: "Tutorial Section", lab: "Lab Section" };
    const item = (ic, kick, title, rest) => `<div class="wk-item">${ic}<div class="wk-b"><p class="hs-kick">${kick}</p><h3>${esc(title)}</h3>${rest}</div></div>`;
    const secs = G.slice().sort((x, y) => (["lecture", "tutorial", "lab"].indexOf(x.kind) - ["lecture", "tutorial", "lab"].indexOf(y.kind)) || String(x.name).localeCompare(String(y.name), undefined, { numeric: true }))
      .map(g => item(`<span class="hs-ic">${KIND_ICON[g.kind] || KIND_ICON.other}</span>`, esc(SEC[g.kind] || "Section"), g.name || "Section",
        `${(g.who || []).length ? `<p class="ab-who">${esc(g.who.join(", "))}</p>` : ""}${(g.items || []).length ? timesHTML(g.items) : ""}`)).join("");
    const ROLE = { coordinator: "Coordinator", instructor: "Instructor", ta: "TA", staff: "Staff" };
    const ini = n => String(n || "").split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join("").toUpperCase();
    const people = T.map(p => { const oh = (p.times || []).filter(x => x.kind === "office" && x.day);
      return item(`<span class="hs-av ab-av" aria-hidden="true">${esc(ini(p.name))}</span>`, esc(ROLE[p.role] || ""), p.name,
        `<div class="ab-times">${p.email ? `<div class="ab-time">${fact(MAIL, `<a href="mailto:${esc(p.email)}">${esc(p.email)}</a>`)}${p.office ? fact(PIN, esc(p.office)) : ""}</div>` : ""}</div>
        ${oh.length ? `<p class="ab-oh">Office Hours</p>${timesHTML(oh)}` : ""}`); }).join("");
    // The course's rules (the gradebook's), a row each.
    const RULE = svg('<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.9 7.5-9.5V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>');
    const rules = (a.rules || []).filter(r => r.title || r.text).map(r => item(`<span class="hs-ic">${RULE}</span>`, "Policy", r.title || "Policy", r.text ? `<div class="hs-body">${markdown(r.text)}</div>` : "")).join("");
    const c = D.course;
    // The title, then each section, each person and each policy a card of its own.
    return `${path([["About the Course"]])}${head("About the Course", esc([c.term, c.school].filter(Boolean).join(" · ")))}
      <div class="ab-page">${[secs, people, rules].filter(Boolean).map(x => `<div class="hs-cards">${x}</div>`).join("")}</div>
      ${rest.replace(/\s/g, "") ? `<div class="ab-rest">${rest}</div>` : ""}`;
  },
  // Requesting an accommodation for one evaluation (#request/<id>): drawn once what can be asked for is in.
  request(arg) {
    if (!open("evaluations")) return lockedPage("evaluations", "Evaluations");
    const f = unitOf(arg); if (!f || f.u.kind === "group") return PAGES.evaluations();
    const { u, group } = f;
    setTimeout(() => ReqForm.start(u), 0);
    return `${path([["Evaluations", "#evaluations"], ...(group ? [[group.name, `#evaluation/${encodeURIComponent(group.id)}`]] : []), [u.name, `#evaluation/${encodeURIComponent(u.id)}`], ["Request an Accommodation"]])}
      <article class="ec-card rq-page">
        <header class="ec-head"><span class="hs-ic ec-ic">${HEART}</span><div class="ec-tt"><p class="hs-kick">Accommodation Request${u.title && u.title !== u.name ? ` / ${esc(u.name)}` : ""}</p><h1>${esc(u.title || u.name)}</h1><p class="ec-subline" id="rq-by" hidden></p></div></header>
        <div id="rq-box"><p class="hs-empty">Loading…</p></div>
      </article>`;
  },
  // Requesting a remark for one evaluation (#remark/<id>): what should be looked at again, and why.
  remark(arg) {
    if (!open("evaluations")) return lockedPage("evaluations", "Evaluations");
    const f = unitOf(arg); if (!f || f.u.kind === "group") return PAGES.evaluations();
    const { u, group } = f;
    setTimeout(() => RemarkForm.start(u), 0);
    return `${path([["Evaluations", "#evaluations"], ...(group ? [[group.name, `#evaluation/${encodeURIComponent(group.id)}`]] : []), [u.name, `#evaluation/${encodeURIComponent(u.id)}`], ["Request a Remark"]])}
      <article class="ec-card rq-page">
        <header class="ec-head"><span class="hs-ic ec-ic">${REDO}</span><div class="ec-tt"><p class="hs-kick">Remark Request${u.title && u.title !== u.name ? ` / ${esc(u.name)}` : ""}</p><h1>${esc(u.title || u.name)}</h1><p class="ec-subline" id="rq-by" hidden></p></div></header>
        <div id="rq-box"><p class="hs-empty">Loading…</p></div>
      </article>`;
  },
  // The student's requests (accommodations.py), a card each as the other lists are: its state's icon, the
  // evaluation, what was asked for, when, what was decided, and the note that came with it.
  accommodations() {
    if (!open("accommodations")) return lockedPage("accommodations", "My Requests");
    setTimeout(myRequests, 0);
    setTimeout(() => seenUpd("requests"), 0);
    return `${path([["My Requests"]])}${head("My Requests", "Your accommodation and remark requests, and what was decided.")}<div id="ma-box"><p class="hs-empty">Loading…</p></div>`;
  },
};

const REQ_IC = {
  approved: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="m7.8 12.3 2.8 2.8 5.6-6"/></svg>',
  rejected: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="m8.8 8.8 6.4 6.4M15.2 8.8l-6.4 6.4"/></svg>',
  pending: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M9.6 9.3a2.5 2.5 0 0 1 4.8 1c0 1.7-2.4 2.2-2.4 3.6"/><path d="M12 17h.01" stroke-width="2.8"/></svg>',
};
const REQ_WORD = { approved: "Approved", rejected: "Rejected", pending: "Waiting for a decision" };
function myRequests() {
  const box = document.getElementById("ma-box"); if (!box) return;
  const when = iso => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" }); };
  fetch(`${root.dataset.api}/accommodations`, { credentials: "same-origin" }).then(r => r.json().then(d => (r.ok ? d : Promise.reject(new Error(d.error || "Your requests couldn't be loaded. Try again in a moment.")))))
    .then(d => {
      const R = d.requests || [];
      box.innerHTML = R.length ? `<div class="hs-cards">${R.map(r => { const st = REQ_IC[r.status] ? r.status : "pending";
        const line = [`Requested ${when(r.submitted)}`, st === "pending" ? REQ_WORD.pending : `${REQ_WORD[st]} ${when(r.decided)}${r.decidedBy ? ` by ${r.decidedBy}` : ""}`].filter(Boolean).join(" · ");
        return `<div class="wk-item wk-go ma-req st-${st}" data-go="#evaluation/${encodeURIComponent(r.eval)}" role="link" tabindex="0" title="Open ${esc(r.evalName || "the evaluation")}">
          <span class="hs-ic ma-ic" title="${esc(REQ_WORD[st])}" aria-label="${esc(REQ_WORD[st])}">${REQ_IC[st]}</span>
          <div class="wk-b"><p class="hs-kick">${r.type === "remark" ? "Remark Request" : "Accommodation Request"} / ${esc(r.evalName || "Evaluation")}</p><h3>${r.type === "remark" ? "Remark" : r.kind === "standard" ? "Standard Accommodation" : "Alternate Accommodation"}</h3><p class="wk-when">${esc(line)}</p>
            ${r.kind === "standard" && r.type !== "remark" ? (r.standard ? `<div class="hs-body"><p>${esc(r.standard)}</p></div>` : "") : r.details ? `<div class="hs-body">${markdown(r.details)}</div>` : ""}
            ${r.note ? `<div class="ma-note"><b>${esc(r.decidedBy || "Your instructor")}</b>${markdown(r.note)}</div>` : ""}</div>${CHEV}</div>`; }).join("")}</div>`
        : `<p class="hs-empty">No requests yet. Ask from an evaluation's page, with Request Accommodation or Request Remark.</p>`;
    }, e => { box.innerHTML = `<p class="hs-empty">${esc(e.message)}</p>`; });
}

// ── What's new (replies to discussions they're in; requests decided): a count on the account button ──
let UPD = null;
function updates() {
  if (!D || !D.viewer.signedIn || D.viewer.preview) return;
  fetch(`${root.dataset.api}/updates`, { credentials: "same-origin" }).then(r => (r.ok ? r.json() : null)).then(d => {
    UPD = d; paintBadge();
  }).catch(() => {});
}
// The count: the server's (replies, decisions, marks) and the announcements they haven't seen yet.
function newAnns() { return ((data("announcements") || {}).items || []).filter(isNew); }
function paintBadge() {
  const b = $("hb-acct"); if (!b) return;
  const old = b.querySelector(".hb-badge"); if (old) old.remove();
  const n = ((UPD && UPD.count) || 0) + newAnns().length;
  if (n) b.insertAdjacentHTML("beforeend", `<span class="hb-badge" title="${n} new" aria-label="${n} new">${n > 99 ? "99+" : n}</span>`);
}
// Something's been looked at (a discussion opened, My Requests): it's not new any more.
function seenUpd(what) {
  if (!D || !D.viewer.signedIn || D.viewer.preview) return;
  fetch(`${root.dataset.api}/updates/seen`, { method: "POST", credentials: "same-origin", headers: { "X-Lectern": "1", "Content-Type": "application/json" }, body: JSON.stringify({ what }) }).then(updates).catch(() => {});
}
window.HubSeen = seenUpd;

// ── The page ─────────────────────────────────────────────────────────
function route() {
  let [id, arg] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (id === "lectures") id = "activities";
  if (id === "evaluations" && arg) id = "evaluation";
  if (id === "week" && !arg) { id = ""; }
  return { id: PAGES[id] && id !== "home" ? id : "home", arg };
}

document.addEventListener("click", e => { const g = e.target.closest("[data-go]"); if (!g || e.target.closest("a, button") || (getSelection && String(getSelection()).length)) return; location.hash = g.dataset.go; });
document.addEventListener("keydown", e => { const g = e.target.closest && e.target.closest("[data-go]"); if (g && e.target === g && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); location.hash = g.dataset.go; } });
function draw() {
  const { id, arg } = route(), m = $("hb-main");
  try { m.innerHTML = PAGES[id](arg); markSeen(); discussions(m); }
  catch (e) { console.error(e); m.innerHTML = `<p class="hb-empty">Something went wrong showing this part of the page.</p>`; }
  if (id !== "home") { const h = m.querySelector(".hs-head h1, .hb-h2, .hb-locked h2"); document.title = `${h ? h.textContent : "Course page"} · ${D.course.code || D.course.title}`; }
}

function header() {
  const c = D.course, v = D.viewer;
  $("hb-sub").textContent = [c.term, c.school].filter(Boolean).join(" · ");
  const t = $("hb-title");
  t.innerHTML = `<a href="#">${esc([c.code, c.title].filter(Boolean).join(": ") || "Course page")}</a>`;
  t.title = t.textContent;
  // The course's description, in the header under the term and school.
  const a = data("about"), hin = document.querySelector(".hb-head-in");
  if (a && a.description && hin && !$("hb-desc")) hin.insertAdjacentHTML("afterend", `<div class="hb-desc-h" id="hb-desc">${markdown(a.description)}</div>`);
  const ROLE = { owner: "Instructor", instructor: "Instructor", ta: "TA", staff: "Staff", student: "Student" };
  // Who's signed in, as Lectern's bar has it: a button with their name that opens a menu (or Sign in).
  // Students sign in to this course page (its own sign-in: email and a code); the teaching team is signed in to Lectern.
  const USER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/></svg>';
  const DOWN = '<svg class="hb-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
  const who = $("hb-who");
  if (!v.signedIn) { who.innerHTML = `<a class="hb-acct" href="${esc(D.signIn || D.lectern)}">${USER}<span>Sign in</span></a>`; }
  else {
    who.innerHTML = `<div class="hb-acct-wrap"><button type="button" class="hb-acct" id="hb-acct" aria-haspopup="menu" aria-expanded="false">${USER}<span>${esc(v.name)}</span>${DOWN}</button></div>`;
    const btn = $("hb-acct"); let menu = null;
    const close = () => { if (menu) { menu.remove(); menu = null; btn.setAttribute("aria-expanded", "false"); } };
    btn.onclick = e => {
      e.stopPropagation(); if (menu) return close();
      menu = document.createElement("div"); menu.className = "hb-menu"; menu.setAttribute("role", "menu");
      const U = [...newAnns().map(a => ({ kind: "ann", a })), ...((UPD && UPD.items) || [])].slice(0, 12);
      const item = x => x.kind === "ann" ? `<a role="menuitem" class="hb-upd" href="#announcement/${encodeURIComponent(x.a.id)}"><b>New announcement</b><span>${esc(x.a.title || "Announcement")}</span></a>`
        : x.kind === "reply" ? `<a role="menuitem" class="hb-upd" href="#post/${encodeURIComponent(x.target)}/${x.post}"><b>${x.n} new repl${x.n === 1 ? "y" : "ies"}</b><span>${esc(x.title || "Your post")}</span></a>`
        : x.kind === "mark" ? `<a role="menuitem" class="hb-upd" href="#evaluation/${encodeURIComponent(x.eval)}"><b>Your mark is out</b><span>${esc(x.name)}</span></a>`
        : `<a role="menuitem" class="hb-upd" href="#accommodations"><b>${x.type === "remark" ? "Remark" : "Accommodation"} request ${esc(x.status)}</b><span>${esc(x.evalName)}</span></a>`;
      menu.innerHTML = `${U.length ? `${U.map(item).join("")}<hr>` : ""}
        <p>Signed in as <b>${esc(v.name)}</b>${v.role ? `<br><span>${esc(ROLE[v.role] || v.role)}</span>` : ""}</p><hr>
        ${v.staff ? `<a role="menuitem" href="${esc(D.lectern)}">Edit in Lectern</a><a role="menuitem" href="${esc(location.pathname + "?as=public" + location.hash)}">See it as a visitor</a>` : ""}
        ${v.role === "student" ? `<button type="button" role="menuitem" id="hb-out">Sign out</button>` : ""}`;
      btn.after(menu); btn.setAttribute("aria-expanded", "true");
      menu.querySelectorAll(".hb-upd").forEach(a => { a.onclick = () => close(); });
      const out = $("hb-out");
      if (out) out.onclick = async () => { out.disabled = true; await fetch(`${root.dataset.api}/sign-out`, { method: "POST", credentials: "same-origin", headers: { "X-Lectern": "1" } }).catch(() => {}); location.reload(); };
    };
    document.addEventListener("click", e => { if (menu && !menu.contains(e.target)) close(); });
    updates();
    document.addEventListener("keydown", e => { if (menu && e.key === "Escape") { close(); btn.focus(); } });
  }
  const bar = $("hb-staff");
  if (v.staff) {
    const base = location.pathname;
    bar.innerHTML = `<div class="hb-staff-in">${v.preview
      ? `<span class="grow">You're seeing this page as a visitor who isn't signed in.</span><a href="${esc(base + location.hash)}">Back to your view</a>`
      : `<span class="grow">You're on the teaching team. Parts marked ${LOCK.replace("<svg", '<svg style="width:12px;height:12px;vertical-align:-1px"')} are hidden from visitors who aren't signed in.</span><a href="${esc(base + "?as=public" + location.hash)}">See it as a visitor</a><a href="${esc(D.lectern)}">Edit in Lectern</a>`}</div>`;
    bar.hidden = false;
  }
  const nav = $("hb-tabs"); if (nav) nav.hidden = true;   // no tabs: the home page and its paths
}

async function load() {
  const as = new URLSearchParams(location.search).get("as");
  try {
    const r = await fetch(root.dataset.api + (as ? `?as=${encodeURIComponent(as)}` : ""), { credentials: "same-origin" });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "This course page couldn't be loaded.");
    D = j;
  } catch (e) {
    $("hb-main").innerHTML = `<p class="hb-empty">${esc(e.message || "This course page couldn't be loaded.")}</p>`;
    return;
  }
  header();
  draw();
  addEventListener("hashchange", () => { scrollTo({ top: 0 }); draw(); });
}
load();
})();
