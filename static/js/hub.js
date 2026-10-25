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
const evWhen = e => (e.date ? `${evType(e) === "test" ? "" : "Due "}${day(e.date)}${e.time ? ` at ${e.time}` : ""}` : "");
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
const annCard = a => `<article class="hs-card hs-ann"><p class="hs-kick">${esc(stampText(a.date))}${groupTag(a.groups)}</p>${a.title ? `<h3>${esc(a.title)}</h3>` : ""}<div class="hs-body">${markdown(a.body)}</div></article>`;
function weekRow(w, now) {
  if (w.isBreak) return `<p class="hs-break">${esc(w.label || "Break")}</p>`;
  const bits = [w.dates, w.topic].filter(Boolean).map(esc).join(" · ");
  return `<a class="hs-row hs-wk${w.i === now ? " now" : ""}" href="#week/${w.i}"><span class="hs-num">${esc(weekNum(w))}</span><span class="hs-t"><b>${esc(w.label || "Week")}</b>${bits ? `<small>${bits}</small>` : ""}</span>${w.i === now ? `<span class="hs-tag">This week</span>` : ""}${CHEV}</a>`;
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
  return `<article class="hs-card hs-act hd-row"><span class="hs-ic">${KIND_ICON[k]}</span><div class="hs-act-b hd-main"><div class="hd"><p class="hs-kick">${esc(KIND_NAME[k])}${groupTag(c.groups)}</p><h3>${esc(c.title || c.label || "Untitled")}</h3>${D_ ? `<p class="hs-when">${esc(D_)}</p>` : ""}</div>${c.description ? `<div class="hs-body">${markdown(c.description)}</div>` : ""}${filesHTML(c.files) || `<p class="hs-soon">Files coming soon</p>`}${anns.length ? `<div class="hs-on">${anns.map(annMini).join("")}</div>` : ""}</div></article>`;
}
// Request Accommodation: when the gradebook says students can ask (until its deadline, if there is one).
function requestHTML(e) {
  const a = e.accom, E = data("evaluations"); if (!a || !(a.approval || a.alternate)) return "";
  const by = a.by ? new Date(`${a.by}T${a.byTime || "23:59"}`) : null, rq = E && E.request;
  if (by && !isNaN(by) && by < new Date()) return `<p class="hs-note">The deadline for accommodation requests has passed.</p>`;
  const url = rq && rq.url ? `${rq.url}?${new URLSearchParams({ r: rq.r, o: rq.o, e: e.id })}` : "";
  const when = by && !isNaN(by) ? `<span class="hs-by">Request by ${esc(day(a.by))}, ${esc(a.byTime || "23:59")}</span>` : "";
  return `<div class="hs-req">${url ? `<a class="hb-btn" href="${esc(url)}" target="_blank" rel="noopener">Request Accommodation</a>` : `<span class="hb-btn">Request Accommodation</span>`}${when}</div>`;
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

// ── Pages ────────────────────────────────────────────────────────────
const PAGES = {
  home() {
    const c = D.course, a = data("about"), out = [];
    const shown = new Set();   // what has a See all link already (it isn't listed again below)
    // The newest announcement in full, then this week opened (the first week, before the term starts).
    if (open("announcements")) {
      const items = (data("announcements").items || []).slice().sort((x, y) => annTime(y) - annTime(x));
      if (items.length) { out.push(`<section class="hs-sec">${annCard(items[0])}<a class="hs-more" href="#announcements">See all announcements ${CHEV}</a></section>`); shown.add("announcements"); }
    }
    if (open("lectures")) {
      const now = thisWeek(), w = realWeeks().find(x => x.i === now) || realWeeks()[0];
      if (w) { out.push(`<section class="hs-sec">${weekOpen(w, now)}<a class="hs-more" href="#activities">See all weeks ${CHEV}</a></section>`); shown.add("activities"); }
    }
    // Then everything else, each a page of its own.
    const more = [
      ["announcements", "Announcements", "News for the class, newest first."],
      ["activities", "Activities", "The term, week by week: lectures, tutorials and labs, with their files.", "lectures"],
      ["evaluations", "Evaluations", "Every evaluation, its weight and when it is."],
      ["about", "About the Course", "The teaching team, class times and office hours, and the course's rules."],
      ["accommodations", "My Accommodations", "Your accommodation requests and what was decided."],
    ].filter(([id, , , t]) => tab(t || id) && !shown.has(id));
    if (more.length) out.push(`<section class="hs-sec"><div class="hs-list">${more.map(([id, t, s, tb]) => `<a class="hs-row hs-link" href="#${id}"><span class="hs-t"><b>${esc(t)}</b><small>${esc(s)}</small></span>${!open(tb || id) || hidden(tb || id) ? `<span class="hs-lock" title="${open(tb || id) ? "Visitors who aren't signed in don't see this" : "Sign in to see this"}">${LOCK}</span>` : ""}${CHEV}</a>`).join("")}</div></section>`);
    document.title = [c.code, c.title].filter(Boolean).join(": ") || "Course page";
    return out.join("");
  },
  announcements() {
    if (!open("announcements")) return lockedPage("announcements", "Announcements");
    const items = (data("announcements").items || []).slice().sort((a, b) => annTime(b) - annTime(a));
    return `${path([["Announcements"]])}${head("Announcements", "News for the class, newest first.")}${items.length ? `<div class="hs-stack">${items.map(annCard).join("")}</div>` : `<p class="hs-empty">No announcements yet.</p>`}`;
  },
  activities() {
    if (!open("lectures")) return lockedPage("lectures", "Activities");
    return `${path([["Activities"]])}${head("Activities", "The term, week by week: open a week for its lectures, tutorials and labs, their files, and what's due.")}${weeks().length ? weekList() : `<p class="hs-empty">The weeks will appear here.</p>`}`;
  },
  week(arg) {
    if (!open("lectures")) return lockedPage("lectures", "Activities");
    const w = weeks().find(x => String(x.i) === String(arg) && !x.isBreak);
    if (!w) return PAGES.activities();
    const now = thisWeek() === w.i, R = realWeeks(), k = R.indexOf(w), prev = R[k - 1], next = R[k + 1];
    const evs = open("evaluations") ? evalsIn(w) : [], anns = open("announcements") ? annsIn(w) : [];
    const sub = [w.dates, w.topic].filter(Boolean).map(esc).join(" · ") + (now ? ` <span class="hs-tag">This week</span>` : "");
    return `${path([["Activities", "#activities"], [w.label || "Week"]])}${head(w.label || "Week", sub)}
      <section class="hs-sec"><h2 class="hs-h2">Activities</h2>${w.cards.length ? `<div class="hs-stack">${w.cards.map(activityCard).join("")}</div>` : `<p class="hs-empty">${w.noClass ? "No class this week." : "No activities this week."}</p>`}</section>
      ${evs.length ? `<section class="hs-sec"><h2 class="hs-h2">Due This Week</h2><div class="hs-list">${evs.map(e => evRow(e)).join("")}</div></section>` : ""}
      ${anns.length ? `<section class="hs-sec"><h2 class="hs-h2">Announcements</h2><div class="hs-stack">${anns.map(annCard).join("")}</div></section>` : ""}
      <nav class="hs-pn">${prev ? `<a href="#week/${prev.i}">‹ ${esc(prev.label || "Previous week")}</a>` : "<span></span>"}${next ? `<a href="#week/${next.i}">${esc(next.label || "Next week")} ›</a>` : ""}</nav>`;
  },
  evaluations() {
    if (!open("evaluations")) return lockedPage("evaluations", "Evaluations");
    return `${path([["Evaluations"]])}${head("Evaluations", "Every evaluation, its weight and when it is. Together they make up your course grade.")}${evalList()}`;
  },
  evaluation(arg) {
    if (!open("evaluations")) return lockedPage("evaluations", "Evaluations");
    const f = unitOf(arg); if (!f) return PAGES.evaluations();
    const { u, group } = f, E = data("evaluations");
    if (u.kind === "group") {
      return `${path([["Evaluations", "#evaluations"], [u.name]])}<p class="hs-kick hs-kick-top">Group</p>${head(u.name, `Worth ${fmtW(u.weight)}% of your grade: the best ${u.keep} of ${u.count} count, ${fmtW(u.weight / Math.max(1, u.keep))}% each.`)}
        <div class="hs-list">${(u.members || []).map(m => evRow(m)).join("")}</div>`;
    }
    const t = evType(u), files = filesHTML((E.files || {})[u.id] || u.files);
    const worth = group ? `Counts in ${esc(group.name)}: the best ${group.keep} of ${group.count}, ${fmtW(group.weight / Math.max(1, group.keep))}% each.` : u.weight != null ? `Worth ${fmtW(u.weight)}% of your grade.` : "";
    const notes = [...(u.notes || []), u.accom && u.accom.standard && u.accom.approval ? "This applies only if you request it and it's approved." : ""].filter(Boolean);
    return `${path([["Evaluations", "#evaluations"], ...(group ? [[group.name, `#evaluation/${encodeURIComponent(group.id)}`]] : []), [u.name]])}
      <p class="hs-kick hs-kick-top"><span class="hs-ic sm">${EV_ICON[t]}</span>${esc(u.name)}</p>${head(u.title || u.name, esc(evWhen(u) || (t === "test" ? "Date to be announced" : "Due date to be announced")))}
      <div class="hs-card hs-facts">${worth ? `<p>${worth}</p>` : ""}${notes.map(n => `<p>${esc(n)}</p>`).join("")}${files}${requestHTML(u)}</div>
      ${annsOn(`eval:${u.id}`).length ? `<section class="hs-sec hs-sec-top"><h2 class="hs-h2">Announcements</h2><div class="hs-stack">${annsOn(`eval:${u.id}`).map(annCard).join("")}</div></section>` : ""}`;
  },
  // (Its description is in the header already.)
  about() { return open("about") ? `${path([["About the Course"]])}${HubView.draw({ ...D, data: { ...D.data, about: { ...data("about"), description: "" } } }, "about")}` : lockedPage("about", "About the Course"); },
  accommodations() { return open("accommodations") ? `${path([["My Accommodations"]])}${HubView.draw(D, "accommodations")}` : lockedPage("accommodations", "My Accommodations"); },
};

// ── The page ─────────────────────────────────────────────────────────
function route() {
  let [id, arg] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (id === "lectures") id = "activities";
  if (id === "evaluations" && arg) id = "evaluation";
  if (id === "week" && !arg) { id = ""; }
  return { id: PAGES[id] && id !== "home" ? id : "home", arg };
}

function draw() {
  const { id, arg } = route(), m = $("hb-main");
  try { m.innerHTML = PAGES[id](arg); }
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
      menu.innerHTML = `<p>Signed in as <b>${esc(v.name)}</b>${v.role ? `<br><span>${esc(ROLE[v.role] || v.role)}</span>` : ""}</p><hr>
        ${v.staff ? `<a role="menuitem" href="${esc(D.lectern)}">Edit in Lectern</a><a role="menuitem" href="${esc(location.pathname + "?as=public" + location.hash)}">See it as a visitor</a>` : ""}
        ${v.role === "student" ? `<button type="button" role="menuitem" id="hb-out">Sign out</button>` : ""}`;
      btn.after(menu); btn.setAttribute("aria-expanded", "true");
      const out = $("hb-out");
      if (out) out.onclick = async () => { out.disabled = true; await fetch(`${root.dataset.api}/sign-out`, { method: "POST", credentials: "same-origin", headers: { "X-Lectern": "1" } }).catch(() => {}); location.reload(); };
    };
    document.addEventListener("click", e => { if (menu && !menu.contains(e.target)) close(); });
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
