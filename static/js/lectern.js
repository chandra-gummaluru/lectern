/* ============================================================
   Lectern — the shell: splash and sign-in, Home, a course
   offering's page, your account, the pinned path, and opening the builders.

   Routes (in the address, so Back and reload work):
     #/                    Home: every course offering
     #/csc258/f26          one offering: its course page, grades and exams
     #/csc258/f26/course   the Course Page Builder on csc258/f26/course.json (public repo)
     #/csc258/f26/grades   the Grade Builder on csc258/f26/grades.json (private repo)
     #/csc258/f26/lectures   the weeks and their lectures (lectures.js), shown on the course page
     #/csc258/f26/announcements   announcements (announcements.js), each in its week on the course page
     #/csc258/f26/team/12    a teaching team member: their sections, times and office hours (team.js)
     #/csc258/f26/exams/midterm   the Exam Builder on csc258/f26/midterm/exam.json (private repo)
     #/~ana/csc258/f26/…   the same, for an offering in someone else's files that you're on the teaching team of
     #/account             your account: password, two-factor sign-in, sessions
   Everything is kept on Lectern's server, in your account's two areas: "pub" (course pages, published
   at /p/<handle>/…) and "priv" (grades, exams). See store.js and server/store.py.
   ============================================================ */
import * as Auth from "./auth.js";
import * as Store from "./store.js";
import { accountPage } from "./account.js";
import { lecturesPage, lecturesUnsaved } from "./lectures.js";
import { teamMemberPage } from "./team.js";
import { announcementsPage } from "./announcements.js";
import { studentsCard } from "./students.js";
import { groupsCard, groupPage, readGroups, groupIdsFor, GROUP_ICON } from "./groups.js";
import { richText } from "./richtext.js";

const Lectern = window.Lectern;
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const slugOK = s => /^[\w.-]+$/.test(s) && !/^[._]/.test(s);
const termName = t => { const m = /^([wsf])(\d{2})$/i.exec(t); return m ? `${{ w: "Winter", s: "Summer", f: "Fall" }[m[1].toLowerCase()]} 20${m[2]}` : t; };
const termKey = t => { const m = /^([wsf])(\d{2})$/i.exec(t); return m ? Number(m[2]) * 10 + { w: 1, s: 2, f: 3 }[m[1].toLowerCase()] : -1; };
const termOrder = (a, b) => termKey(b) - termKey(a) || a.localeCompare(b);   // newest first: f26 > s26 > w26 > f25
const isTerm = t => /^[wsf]\d{2}$/i.test(t);
const encPath = p => p.split("/").map(encodeURIComponent).join("/");

const svgI = (d, w = 2) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICON = {
  plus: svgI('<path d="M12 5v14M5 12h14"/>'),
  up: svgI('<path d="m18 15-6-6-6 6"/>'),
  down: svgI('<path d="m6 9 6 6 6-6"/>'),
  lectures: svgI('<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>'),
  out: svgI('<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>'),
  folder: svgI('<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.5h7.5A2.5 2.5 0 0 1 21 10v7.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/>', 1.8),
  page: svgI('<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 9h18M8 13h3M8 16h6"/>', 1.8),
  grades: svgI('<path d="M4 20V4M4 20h16"/><path d="m8 15 3.5-4 3 2.5L20 7"/>', 1.8),
  exam: svgI('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>', 1.8),
  doc: svgI('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>', 1.8),
  lock: svgI('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>', 1.8),
  globe: svgI('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>', 1.8),
  trash: svgI('<path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>', 1.8),
  evals: svgI('<path d="M9 6h11M9 12h11M9 18h11"/><path d="m3.5 6 1.2 1.2L7 5M3.5 12l1.2 1.2L7 11M3.5 18l1.2 1.2L7 17"/>', 1.8),
  gear: svgI('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>', 1.6),
  warn: svgI('<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>'),
  team: svgI('<circle cx="9" cy="8" r="3.2"/><path d="M3 19.5c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><circle cx="17" cy="9" r="2.6"/><path d="M16.5 14.1c2.6.2 4.5 2.1 4.5 4.9"/>', 1.8),
  mail: svgI('<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m3.5 7 8.5 6 8.5-6"/>', 1.8),
  accom: svgI('<path d="M12 3 4.5 6v5.5c0 4.6 3.1 8.2 7.5 9.5 4.4-1.3 7.5-4.9 7.5-9.5V6z"/><path d="m8.8 12 2.2 2.2 4.2-4.4"/>', 1.8),
  user: svgI('<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>', 1.8),
};
const TOOLS = {
  course: { title: "Course Page", file: "course.json", repo: "pub" },
  grades: { title: "Gradebook", file: "grades.json", repo: "priv" },
  exams: { title: "Exams", file: "exam.json", repo: "priv" },
};

// ── State ────────────────────────────────────────────────────────────
const S = {
  user: null,          // { id, email, name, handle, twoFactor, recoveryLeft, site }
  shared: [],          // offerings in others' files you're on the team of: { owner (handle), ownerName, offering, role }
  offerings: null,     // "c/t" → { c, t, page, grades, exams: [] }
  listing: null, listError: null,
  route: { page: "home" },
  ready: false,
};
const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (_) { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} },
};

// Whose files an offering is in: "" for your own, else the owner's handle (a teaching team you're on).
// Pages inside an offering take it from the route, so links within one stay in the same owner's files.
const curOwner = () => (S.route && S.route.o) || "";
const pagesBase = () => (S.user ? S.user.site.slice(0, -(S.user.handle.length + 1)) : "");
const siteURL = (o = curOwner()) => (S.user ? (o ? `${pagesBase()}${o}/` : S.user.site) : "");
// The course page itself (the hub, server/hub.py), at Lectern's own address.
const hubURL = (c, t, o = curOwner()) => `${location.origin}/c/${encodeURIComponent(o || (S.user && S.user.handle) || "")}/${encPath(`${c}/${t}`)}/`;
const liveURL = (c, t, o = curOwner()) => { const s = siteURL(o); return s ? `${s}${encPath(`${c}/${t}/info.html`)}` : ""; };
const okey = (c, t, o = curOwner()) => `${o}|${c}/${t}`;
const offering = (c, t, o = curOwner()) => (S.offerings && S.offerings.get(okey(c, t, o))) || { c, t, o, page: false, grades: false, exams: [] };
// Your role in an offering: owner (your own), instructor or ta.
const roleIn = (c, t, o = curOwner()) => !o ? "owner" : ((S.shared.find(x => x.owner === o && x.offering === `${c}/${t}`) || {}).role || "");
const canEdit = (c, t, o) => ["owner", "coordinator"].includes(roleIn(c, t, o));   // everything (instructors: their groups' activities and announcements)
const area = (which, o = curOwner()) => (o ? `${o}.${which}` : which);
const ROLE_NAME = { owner: "Owner", coordinator: "Coordinator", instructor: "Instructor", ta: "TA", staff: "Staff" };
const A_ROLE = { coordinator: "a coordinator", instructor: "an instructor", ta: "a TA", staff: "staff" };
const ownerName = o => ((S.shared.find(x => x.owner === o) || {}).ownerName || o);

// ── Messages and windows ─────────────────────────────────────────────
function toast(msg) {
  const root = $("#lt-toast-root");
  if (!root.classList.contains("lt-toasts")) root.className = "lt-toasts";
  const el = document.createElement("div");
  el.className = "lt-toast"; el.textContent = msg;
  root.append(el);
  setTimeout(() => el.remove(), 4200);
}
function modal(html, onReady, { sticky = false } = {}) {   // sticky: Escape and the backdrop don't close it
  const bg = document.createElement("div");
  bg.className = "lt-modal-bg";
  bg.innerHTML = `<div class="lt-modal" role="dialog" aria-modal="true">${html}</div>`;
  $("#lt-modal-root").append(bg);
  const m = bg.firstElementChild;
  const close = () => { bg.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = e => { if (e.key === "Escape") { e.stopPropagation(); if (!sticky) close(); } };
  document.addEventListener("keydown", onKey, true);
  bg.addEventListener("mousedown", e => { if (e.target === bg && !sticky) close(); });
  onReady(m, close);
  const first = m.querySelector("input, select, .primary");
  if (first) first.focus();
  return close;
}
function confirmBox(title, text, yes, no = "Cancel") {
  return new Promise(res => modal(`<h2>${esc(title)}</h2><p>${text}</p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>${esc(no)}</button><button type="button" class="lt-btn primary" data-yes>${esc(yes)}</button></div>`, (m, close) => {
    m.querySelector("[data-no]").onclick = () => { close(); res(false); };
    m.querySelector("[data-yes]").onclick = () => { close(); res(true); };
  }));
}

// ── Splash ───────────────────────────────────────────────────────────
function showSplash(msg = "", isError = false) {
  document.documentElement.classList.remove("lt-has-session");
  document.body.className = "lt-on-splash";
  $("#app").hidden = true; $("#splash").hidden = false;
  document.title = $("title").dataset.splash || document.title;
  const st = $("#splash-status");
  st.className = `sp-hint${isError ? " is-error" : ""}`;
  st.textContent = msg || "";
}

// ── Starting a session ───────────────────────────────────────────────
function showApp() {
  document.documentElement.classList.remove("lt-has-session");
  $("#splash").hidden = true; $("#app").hidden = false;
}

async function start(user, how, team, note) {
  S.user = user;
  S.ready = true;
  if (note) setTimeout(() => toast(note), 300);
  showApp();
  renderBar();
  connectAll();
  listAll();
  // A new account on a teaching team: straight to that offering. Any other new account: to its page,
  // to turn on two-factor sign-in.
  if (team) {
    const [c, t] = team.offering.split("/");
    const isNew = Date.now() / 1000 - (user.created || 0) < 300;
    toast(`You're on the teaching team for ${c.toUpperCase()} ${t}.${isNew ? " When you have a moment, turn on two-factor sign-in (Your account)." : ""}`);
    await listed();
    return go({ page: "offering", c, t, o: team.owner });
  }
  if (how === "invite") { toast(`Welcome to Lectern, ${user.name.split(" ")[0]}. Next: turn on two-factor sign-in.`); return go({ page: "account" }); }
  route();
}
function signOut() {
  Auth.signOut().finally(() => { try { sessionStorage.clear(); } catch (_) {} location.replace("/"); });
}
// Your session ended mid-work (too long idle, or signed out elsewhere): sign in again, in a window,
// so nothing unsaved is lost; the call that noticed is then made again (auth.js, scope.js).
Auth.setReauth(() => Auth.reauthWindow(modal, S.user ? S.user.email : "", signOut)());
Lectern.reauth = Auth.reauth;

// ── Listing every course offering ────────────────────────────────────
function listAll() {
  const map = new Map();
  const add = (c, t, what, owner = "") => {
    if ([c, t].some(x => x.startsWith(".") || x.startsWith("_"))) return;
    if (owner && !S.shared.some(x => x.owner === owner && x.offering === `${c}/${t}`)) return;
    const k = okey(c, t, owner), o = map.get(k) || { c, t, o: owner, page: false, grades: false, exams: [] };
    if (what.page) o.page = true;
    if (what.grades) o.grades = true;
    if (what.exams) what.exams.forEach(e => { if (!o.exams.includes(e)) o.exams.push(e); });
    if (what.folder) o.folder = true;
    map.set(k, o);
  };
  S.listing = (async () => {
    // The teams you're on (their offerings are in their owners' files), then every owner's files you can see.
    try { S.shared = (await Auth.api("/api/teams/mine")).shared; } catch (_) {}
    const owners = ["", ...new Set(S.shared.map(x => x.owner))];
    await Promise.all(owners.map(async owner => {
      const [pv, pb] = await Promise.all([Store.tree(area(Store.PRIV, owner)), Store.tree(area(Store.PUB, owner))]);
      pb.forEach(x => {
        const p = x.path.split("/");
        if (x.type === "tree" && p.length === 2) add(p[0], p[1], { folder: true }, owner);
        if (x.type === "blob" && p.length === 3 && (p[2] === "course.json" || p[2] === "info.html")) add(p[0], p[1], { page: true }, owner);
      });
      pv.forEach(x => {
        const p = x.path.split("/");
        if (x.type === "tree" && p.length === 2) add(p[0], p[1], { folder: true }, owner);
        if (x.type === "blob" && p.length === 3 && p[2] === "grades.json") add(p[0], p[1], { grades: true }, owner);
        if (x.type === "blob" && p.length === 4 && p[3] === "exam.json") add(p[0], p[1], { exams: [p[2]] }, owner);
      });
    }));
    // A shared offering is there even before it has files.
    S.shared.forEach(x => { const [c, t] = x.offering.split("/"); add(c, t, {}, x.owner); });
    // A folder that has nothing yet counts only if it's named like a term (f26, w27, s26).
    for (const [k, o] of map) if (!o.o && !o.page && !o.grades && !o.exams.length && !isTerm(o.t)) map.delete(k);
    map.forEach(o => o.exams.sort());
    S.offerings = map; S.listError = null;
    return map;
  })().catch(e => { S.listError = e; throw e; });
  // Pages that show the list draw again when it arrives (not a builder, and not your account page, which doesn't use it).
  const redraw = () => { if (["home", "offering", "accom", "lectures", "team", "groups", "announcements"].includes(S.route.page)) renderPage(); };
  S.listing.then(redraw, redraw);
  return S.listing;
}
const listed = () => (S.listing || listAll()).catch(() => null);

// ── Routes ───────────────────────────────────────────────────────────
function parseHash() {
  let p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  let o = "";
  if (p[0] && /^~[a-z0-9-]+$/.test(p[0])) { o = p[0].slice(1); p = p.slice(1); }   // someone else's offering (a team you're on)
  if (S.user && o === S.user.handle) o = "";
  if (p.length >= 2 && slugOK(p[0]) && slugOK(p[1])) {
    const [c, t, tool, e] = p;
    if (tool === "course") return { page: "tool", tool, c, t, o };
    // The gradebook's three parts: Evaluations, the Gradebook (grades and students) and the course's Settings
    const part = { evaluations: "evals", gradebook: "book", grades: "book", settings: "settings" }[tool];
    if (part) return { page: "tool", tool: "grades", part, c, t, o };
    if (tool === "exams" && e && slugOK(e)) return { page: "tool", tool, c, t, e, o };
    if (tool === "accommodations") return { page: "accom", c, t, o };
    if (tool === "lectures" || tool === "activities") return { page: "lectures", c, t, o, w: e || "", l: p[4] || "" };
    if (tool === "team" && e) return { page: "team", c, t, o, p: e };
    if (tool === "groups" && e) return { page: "groups", c, t, o, g: e };
    if (tool === "announcements") return { page: "announcements", c, t, o, a: e || "" };
    return { page: "offering", c, t, o };
  }
  if (p.length === 1 && p[0] === "account") return { page: "account" };
  return { page: "home" };
}
const PARTS = { evals: { slug: "evaluations", title: "Evaluations" }, book: { slug: "gradebook", title: "Gradebook" }, settings: { slug: "settings", title: "Gradebook" } };
const partOf = view => view === "evals" ? "evals" : view === "settings" ? "settings" : "book";
const hashFor = r => {
  if (r.page === "home") return "#/";
  if (r.page === "account") return "#/account";
  const at = `#/${r.o ? `~${r.o}/` : ""}${r.c}/${r.t}`;
  return r.page === "offering" ? at : r.page === "accom" ? `${at}/accommodations` : r.page === "team" ? `${at}/team/${encodeURIComponent(r.p)}` : r.page === "groups" ? `${at}/groups/${encodeURIComponent(r.g)}` : r.page === "announcements" ? `${at}/announcements${r.a ? `/${encodeURIComponent(r.a)}` : ""}` : r.page === "lectures" ? `${at}/activities${r.w ? `/${encodeURIComponent(r.w)}${r.l ? `/${encodeURIComponent(r.l)}` : ""}` : ""}` : r.tool === "exams" ? `${at}/exams/${r.e}`
    : r.tool === "grades" ? `${at}/${PARTS[r.part || "book"].slug}` : `${at}/${r.tool}`;
};
const routeKey = r => hashFor(r);
let pendingOpen = null;      // options for the next open (copy from, title), set by a button just before it navigates
function go(r, opts = null) {
  // Within an offering, links stay in the same owner's files unless they say otherwise.
  if (r.c && r.o === undefined) r = { ...r, o: curOwner() };
  pendingOpen = opts;
  const h = hashFor(r);
  if (location.hash === h) route(); else location.hash = h;
}
const scrolls = {};
let seq = 0;
async function route() {
  if (!S.ready) return;
  scrolls[routeKey(S.route)] = window.scrollY;
  const r = parseHash(), my = ++seq, prevTool = S.route.page === "tool";
  S.route = r;
  closeMenu();
  if (r.page === "tool") return openTool(r, my);
  // Coming back from a builder: what's in the repositories may have changed (a save made a new file).
  if (prevTool) listAll();
  showPageChrome();
  renderPage();
  window.scrollTo(0, scrolls[routeKey(r)] || 0);
}
window.addEventListener("hashchange", () => {
  if (/^#(invite|join|reset)=/.test(location.hash)) return location.reload();   // an invitation or reset link, pasted into this tab
  stamp(); route();
});

// ── Back and Forward ─────────────────────────────────────────────────
// Every page is a step in the browser's history: Lectern's own pages (by their address) and the pages
// inside a builder (a week, a student, the marking guide…), which have the same address, so each step
// also carries where the builder was (lt). Back/Forward (and the browser's own) go through them.
const H = { at: 0, top: 0, applying: false };
let pendingWhere = null;     // where a builder should go once it's open, after Back/Forward to its address
function stamp() {           // a step we just arrived at by address gets its number
  const st = history.state || {};
  if (st.i == null) { H.at += 1; H.top = H.at; history.replaceState({ ...st, i: H.at }, ""); }
  else H.at = st.i;
  drawNav();
}
window.addEventListener("popstate", e => {
  const st = e.state || {};
  if (st.i != null) H.at = st.i;
  drawNav();
  if (!st.lt) return;
  // Same address (inside a builder): put the builder back where it was. Otherwise route() opens the
  // builder first, then this is applied.
  if (S.route.page === "tool" && hashFor(S.route) === location.hash && Lectern.tools[S.route.tool] && Lectern.active === S.route.tool) applyWhere(Lectern.tools[S.route.tool], st.lt);
  else pendingWhere = st.lt;
});
function applyWhere(t, lt) {
  if (!t.api.goto) return;
  H.applying = true;
  try { t.api.goto(lt); } finally { setTimeout(() => { H.applying = false; }, 50); }
}
// Inside a builder: when its page changes, that's a new step (unless we're going Back/Forward to it).
function noteWhere(t) {
  if (!t.api.where || H.applying) return;
  const lt = t.api.where(), st = history.state || {};
  const url = S.route.page === "tool" ? hashFor(S.route) : location.hash;
  if (!st.lt) { history.replaceState({ ...st, lt }, "", url); return; }
  if (JSON.stringify(st.lt) === JSON.stringify(lt)) return;
  H.at += 1; H.top = H.at;
  history.pushState({ i: H.at, lt }, "", url);
  drawNav();
}
function navButtons() {
  return `<span class="lt-nav"><button type="button" data-nav="-1" title="Back to the page you were on" aria-label="Back">${svgI('<path d="M15 18l-6-6 6-6"/>')}</button><button type="button" data-nav="1" title="Forward" aria-label="Forward">${svgI('<path d="M9 18l6-6-6-6"/>')}</button></span>`;
}
function drawNav() {
  document.querySelectorAll('[data-nav="-1"]').forEach(b => { b.disabled = H.at <= 1; });
  document.querySelectorAll('[data-nav="1"]').forEach(b => { b.disabled = H.at >= H.top; });
}
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-nav]");
  if (!b || b.disabled) return;
  e.preventDefault(); e.stopPropagation();
  b.dataset.nav === "-1" ? history.back() : history.forward();
}, true);
$("#lt-home").insertAdjacentHTML("afterend", navButtons());
stamp();

// ── Top bar and path (on Lectern's own pages) ────────────────────────
function showPageChrome() {
  pendingWhere = null;
  Lectern.show(null);
  document.body.className = "lt-on-app lt-on-page";
  $("#lt-bar").hidden = false; $("#lt-page").hidden = false;
  syncBarHeight();
}
function syncBarHeight() { document.documentElement.style.setProperty("--lt-tb", `${$("#lt-bar").offsetHeight}px`); }
new ResizeObserver(() => { if (!$("#lt-bar").hidden) syncBarHeight(); }).observe($("#lt-bar"));

function unsavedTools() {
  return Object.entries(Lectern.tools).filter(([, t]) => t.api && t.api.state().unsaved && t.api.state().path).map(([name, t]) => ({ name, path: t.api.state().path }));
}
function routeForPath(tool, path, part, o) {
  const p = path.split("/");
  if (o === undefined) o = (Lectern.tools[tool] && Lectern.tools[tool].owner) || "";
  return tool === "exams" ? { page: "tool", tool, c: p[0], t: p[1], e: p[2], o } : tool === "grades" ? { page: "tool", tool, part: part || "book", c: p[0], t: p[1], o } : { page: "tool", tool, c: p[0], t: p[1], o };
}
function renderBar() {
  const st = $("#lt-status");
  const un = unsavedTools();
  st.innerHTML = `${un.length ? `<button type="button" class="lt-pill" id="lt-unsaved" title="${esc(un.map(u => u.path).join("\n"))}">${ICON.warn}${un.length === 1 ? `<span>Not saved<span class="lt-pill-x">: ${esc(un[0].path.split("/").slice(0, un[0].name === "exams" ? 3 : 2).join("/"))} ${esc(TOOLS[un[0].name].title.toLowerCase())}</span></span>` : `${un.length} not saved`}</button>` : ""}`;
  const u = $("#lt-unsaved");
  if (u) u.onclick = () => go(routeForPath(un[0].name, un[0].path));
  const a = $("#lt-acct");
  const who = S.user ? `${ICON.user}<span>${esc(S.user.name || S.user.email)}</span>` : "";
  a.innerHTML = who ? who + CHEV : "";
  a.hidden = !who;
  if (saving) st.innerHTML = `<span class="lt-saving">${esc(savingText)}</span>`;
  if (menuEl) drawMenuSave();
}
const CHEV = '<svg class="lt-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
$("#lt-home").onclick = () => go({ page: "home" });

// ── Save: one button saves every course page, gradebook and exam with changes ──
const SAVE_WHAT = { course: "course page", grades: "gradebook", exams: "exam" };
function saveLabel(u) {
  const p = u.path.split("/");
  return u.name === "exams" ? `${p[0]}/${p[1]} ${p[2]}` : `${p[0]}/${p[1]} ${SAVE_WHAT[u.name]}`;
}
let saving = false, savingText = "";
// Save lives in the account menu; while saving, the progress shows in the bar's status.
function setSaving(t) { savingText = t; renderBar(); }
async function saveAll() {
  const un = unsavedTools().filter(u => Lectern.tools[u.name].api.save);
  if (saving || !un.length) return;
  saving = true;
  const where = "elsewhere (another tab, or another computer)";
  const done = [], failed = [];
  try {
    for (let k = 0; k < un.length; k++) {
      const u = un[k], api = Lectern.tools[u.name].api;
      setSaving(un.length > 1 ? `Saving ${k + 1} of ${un.length}…` : "Saving…");
      const p = u.path.split("/"), what = u.name === "exams" ? `${p[2]} exam` : SAVE_WHAT[u.name];
      const msg = `Update ${p[0]} ${p[1]} ${what}`;
      const t = Lectern.tools[u.name], ta = roleIn(p[0], p[1], t.owner || "") === "ta";
      // A TA saves marks only: not exams or the course page, and only the marks in a gradebook (the server
      // keeps everything else as it was, so say so first if they changed anything else).
      if (["staff", "instructor"].includes(roleIn(p[0], p[1], t.owner || ""))) { failed.push({ u, error: "Your role can look at this, but not change it: ask a coordinator." }); continue; }
      if (ta && u.name !== "grades") { failed.push({ u, error: "As a TA you can't save changes here: ask an instructor." }); continue; }
      if (ta && t.taBase && t.taBase !== noMarks(api.book())
          && !await confirmBox("Only marks are saved", "As a TA, only your marks are saved. Your other changes here (evaluations, students or settings) will be undone. Save the marks?", "Save the marks", "Cancel")) {
        failed.push({ u, error: "Not saved." }); continue;
      }
      let r;
      try { r = await api.save(msg); } catch (e) { r = { error: e.message }; }
      if (r.conflict) {
        const yes = await confirmBox("Changed elsewhere", `<code>${esc(u.path)}</code> changed ${where} since you opened it. Replace that version with yours? (Or skip it, and open it again to see the other changes.)`, "Replace it with mine", "Skip it");
        if (yes) { try { r = await api.save(msg, true); } catch (e) { r = { error: e.message }; } }
        else { failed.push({ u, error: "Skipped: it changed elsewhere." }); continue; }
      }
      if (r.ok && ta) await reopenAfterTA(t, u.path);   // show what was kept: the gradebook as saved
      if (r.ok) done.push(u); else failed.push({ u, error: r.error || "Couldn't save." });
      if (r.ok && u.name === "grades" && !ta) await syncScheme(p[0], p[1], t.owner || "").catch(e => console.warn("[Lectern] marking scheme:", e));
    }
  } finally {
    saving = false; savingText = ""; renderBar();
  }
  if (failed.length) modal(`<h2>${done.length ? "Some changes weren't saved" : "Not saved"}</h2>
    ${done.length ? `<p>Saved ${esc(done.map(saveLabel).join(", "))}.</p>` : ""}
    <ul class="lt-fails">${failed.map(f => `<li><b>${esc(saveLabel(f.u))}</b>: ${esc(f.error)}</li>`).join("")}</ul>
    <div class="lt-modal-acts"><button type="button" class="lt-btn primary" data-ok>OK</button></div>`, (m, close) => { m.querySelector("[data-ok]").onclick = close; });
  else if (done.length) toast(`Saved ${done.map(saveLabel).join(", ")}.`);
  if (done.length) {   // new files: Home and the course offering's page show them
    await listAll().catch(() => null);
    const r = S.route; if (r.page === "tool" && Lectern.tools[r.tool]) toolPath(Lectern.tools[r.tool]);
  }
}
Lectern.saveAll = saveAll;

// A TA's gradebook: what it was when opened (tidied by the builder), apart from marks, to tell whether a
// TA changed anything else; and after a save, open it again from the server so it shows what was kept.
const noMarks = b => { try { const x = JSON.parse(JSON.stringify(b)); delete x.marks; return JSON.stringify(x); } catch (_) { return ""; } };
async function reopenAfterTA(t, path) {
  const where = t.api.where ? t.api.where() : null;
  try {
    await t.api.open(path.split("/").slice(0, 2).join("/"), true);
    t.taBase = noMarks(t.api.book());
    if (where && t.api.goto) t.api.goto(where);
  } catch (e) { console.warn("[Lectern] reopen:", e); }
}

// ── Deleting takes two clicks: the first turns the button red ("Delete?"), the second deletes. ──
// For every delete button in Lectern and its builders (not the course offering's, which asks you to type its name).
const DELETES = 'button.trash, button.ic.trash, button.c.x[data-act="del"], button[data-act="del"], button[data-act="delcol"], button[data-act="tdel"], button[data-act="pol-fdel"], button[data-act="pol-bdel"], button[data-act="fld-del"], button[data-ed="delete"], button[data-ed="gdelete"], button[data-ed="sremove"], button[data-act="evdel"], button[data-act="grpdel"]';
let armed = null, armTimer = 0;
const disarm = () => { if (armed) { armed.classList.remove("lt-armed"); armed.removeAttribute("data-armed"); } armed = null; clearTimeout(armTimer); };
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest(DELETES);
  if (!b || b.disabled || b.id === "lt-del-off") { if (armed && !(e.target.closest && e.target.closest("[data-armed]"))) disarm(); return; }
  if (b === armed) { disarm(); return; }   // the second click: let it through
  e.preventDefault(); e.stopImmediatePropagation(); e.stopPropagation();
  disarm(); armed = b; b.classList.add("lt-armed"); b.setAttribute("data-armed", "1");
  armTimer = setTimeout(disarm, 3500);
}, true);
document.addEventListener("keydown", e => { if (e.key === "Escape") disarm(); }, true);   // a builder's own Save button (e.g. an announcement's) saves the same way
// Ctrl+S (⌘S) is the same Save, in a builder too.
window.addEventListener("keydown", e => {
  if (!((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "s")) return;
  if (!document.body.classList.contains("lt-on-app")) return;
  e.preventDefault(); e.stopImmediatePropagation(); e.stopPropagation();
  saveAll();
}, true);

// The account menu: who's signed in, Save, your account, sign out.
let menuEl = null;
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; $("#lt-acct").setAttribute("aria-expanded", "false"); } }
$("#lt-acct").onclick = e => {
  e.stopPropagation();
  if (menuEl) return closeMenu();
  menuEl = document.createElement("div");
  menuEl.className = "lt-menu"; menuEl.setAttribute("role", "menu");
  menuEl.innerHTML = `<p>Signed in as <b>${esc(S.user && (S.user.name || S.user.email))}</b><br><span class="lt-menu-sub">${esc(S.user && S.user.email)}</span></p><hr>
       <button type="button" role="menuitem" data-m="save" class="lt-menu-save"></button><hr>
       <button type="button" role="menuitem" data-m="account">Your account</button>
       <button type="button" role="menuitem" data-m="out">Sign out</button>`;
  $("#lt-acct").after(menuEl);
  drawMenuSave();
  $("#lt-acct").setAttribute("aria-expanded", "true");
  menuEl.onclick = async ev => {
    const m = ev.target.closest("[data-m]"); if (!m || m.disabled) return;
    closeMenu();
    if (m.dataset.m === "save") saveAll();
    if (m.dataset.m === "account") go({ page: "account" });
    if (m.dataset.m === "out") {
      const un = unsavedTools();
      if (un.length && !await confirmBox("Not saved", `${esc(un.map(saveLabel).join(", "))} ${un.length === 1 ? "has" : "have"} changes that aren't saved. Sign out and lose them?`, "Sign out", "Cancel")) return;
      Lectern.leaving = true;
      signOut();
    }
  };
};
// The menu's Save: what it would save, or that everything is saved.
function drawMenuSave() {
  const b = menuEl && menuEl.querySelector('[data-m="save"]'); if (!b) return;
  const un = unsavedTools();
  b.disabled = saving || !un.length;
  b.innerHTML = `<span>${saving ? esc(savingText || "Saving…") : un.length ? "Save" : "Everything is saved"}</span><kbd>${/Mac|iP/.test(navigator.platform) ? "⌘S" : "Ctrl+S"}</kbd>`;
  b.title = un.length ? `Save ${un.map(saveLabel).join(", ")}` : "";
}
document.addEventListener("click", e => { if (menuEl && !menuEl.contains(e.target)) closeMenu(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeMenu(); });

// The path strip: always there, e.g. Home › csc258 / f26 › Gradebook › Students › Castillo, Maya.
function renderPath(steps) {
  const nav = $("#lt-path");
  requestAnimationFrame(() => { nav.scrollLeft = nav.scrollWidth; nav.classList.toggle("scrolled", nav.scrollLeft > 0); });
  if (!nav.dataset.fade) { nav.dataset.fade = "1"; nav.addEventListener("scroll", () => nav.classList.toggle("scrolled", nav.scrollLeft > 0), { passive: true }); }
  nav.innerHTML = steps.map((s, k) => {
    const last = k === steps.length - 1;
    const inner = esc(s.label);
    const el = !last && s.go ? `<button type="button" class="lt-step" data-k="${k}" title="${inner}">${inner}</button>` : `<span class="lt-step${last ? " cur" : ""}"${last ? ' aria-current="page"' : ""} title="${inner}">${inner}</span>`;
    return el + (last ? "" : '<span class="lt-sep" aria-hidden="true">›</span>');
  }).join("");
  nav.querySelectorAll("button[data-k]").forEach(b => { b.onclick = () => steps[Number(b.dataset.k)].go(); });
  nav.scrollLeft = nav.scrollWidth;   // on a narrow screen, the end of the path is what shows
  const tail = steps.slice(1).map(s => s.label);
  document.title = tail.length ? `${tail.slice(-2).join(" · ")} · Lectern` : "Lectern";
}
// The path starts at the repository (Home: all its courses).
const HOME_STEP = { label: "Home", go: () => go({ page: "home" }) };
const offeringLabel = (c, t, o = curOwner()) => `${c} / ${t}${o ? ` (${ownerName(o)})` : ""}`;
const offeringStep = (c, t) => ({ label: offeringLabel(c, t), go: () => go({ page: "offering", c, t }) });

// ── Lectern's own pages ──────────────────────────────────────────────
function pageHTML(html) { $("#lt-page").innerHTML = html; }
function renderPage() {
  renderBar();
  const r = S.route;
  if (r.page === "home") { renderPath([{ label: HOME_STEP.label }]); return homePage(); }
  if (r.page === "offering") { renderPath([HOME_STEP, { label: offeringLabel(r.c, r.t) }]); return offeringPage(r.c, r.t); }
  if (r.page === "accom") { renderPath([HOME_STEP, offeringStep(r.c, r.t), { label: "Accommodations" }]); return accomPage(r.c, r.t); }
  if (r.page === "lectures") return lecturesPage({ $, esc, pageHTML, toast, confirmBox, go, Store, area, canEdit, ICON, renderPath, route: () => S.route,
    steps: [HOME_STEP, offeringStep(r.c, r.t)], uploadPublic: Lectern.uploadPublic,
    // The gradebook's evaluations: each week shows the ones dated in it, and opens one in the Evaluations.
    evaluations: async () => { const b = await getBook(r.c, r.t).catch(() => null); return b ? (b.evals || []).map(e => ({ id: e.id, name: e.name || e.label || "Evaluation", type: e.type || "assignment", short: e.short || "", date: e.date || "", time: e.time || "" })) : []; },
    openEval: id => go({ page: "tool", tool: "grades", part: "evals", c: r.c, t: r.t }, { where: { view: "evals", evalEd: id, groupEd: "", student: "", stAcc: "", stFrom: "" } }),
    groups: () => readGroups(Store, area(Store.PRIV), r.c, r.t).then(x => x.data.groups), me: S.user.id }, r);
  if (r.page === "announcements") return announcementsPage({ $, esc, pageHTML, toast, confirmBox, go, Store, area, canEdit, ICON, renderPath, route: () => S.route,
    steps: [HOME_STEP, offeringStep(r.c, r.t)], markdown: s => window.HubView.markdown(s), me: S.user.id,
    // What an announcement can be about (an activity, an evaluation), and the groups it can be for.
    groups: () => readGroups(Store, area(Store.PRIV), r.c, r.t).then(x => x.data.groups),
    evaluations: async () => { const b = await getBook(r.c, r.t).catch(() => null); return b ? (b.evals || []).map(e => ({ id: e.id, name: e.name || e.label || "Evaluation" })) : []; },
    activities: async () => { const t = await readPriv(`${r.c}/${r.t}/lectures.json`).catch(() => null); let d = null; try { d = t ? JSON.parse(t) : null; } catch (_) {}
      return ((d && d.weeks) || []).filter(w => !w.isBreak).flatMap(w => (w.cards || []).map(x => ({ id: x.id, week: w.label || "Week", name: x.title || x.label || "Untitled", groups: Array.isArray(x.groups) ? x.groups.map(String) : x.group ? [String(x.group)] : [] }))); } }, r);
  if (r.page === "team") return teamMemberPage({ $, esc, pageHTML, toast, go, Store, area, canEdit, ICON, renderPath, route: () => S.route, ROLE_NAME,
    steps: [HOME_STEP, offeringStep(r.c, r.t)], api: Auth.api, owner: () => curOwner() || S.user.handle,
    groups: () => readGroups(Store, area(Store.PRIV), r.c, r.t).then(x => x.data.groups) }, r);
  if (r.page === "groups") return groupPage({ $, esc, pageHTML, toast, confirmBox, go, Store, repo: area(Store.PRIV), canEdit, ICON, renderPath, route: () => S.route,
    steps: [HOME_STEP, offeringStep(r.c, r.t)], team: () => teamPeople(r.c, r.t), students: () => getBook(r.c, r.t).then(b => (b && b.students) || []) }, r);
  const ctx = { S, pageHTML, modal, toast, setUser: u => { S.user = u; renderBar(); } };
  if (r.page === "account") { renderPath([HOME_STEP, { label: "Your Account" }]); return accountPage(ctx); }
}

function sourceBar() {
  return `<div class="lt-src">${ICON.globe}<div><b>Your course pages are public at <a href="${esc(siteURL())}" target="_blank" rel="noopener"><code>${esc(siteURL())}</code></a></b>
      <span>Grades, exams and accommodation requests are private: only you see them.</span></div></div>`;
}

let homeFilter = (() => { try { return JSON.parse(localStorage.getItem("lectern.home.filter")) || {}; } catch (_) { return {}; } })();
function homePage() {
  const all = S.offerings ? [...S.offerings.values()].sort((a, b) => termOrder(a.t, b.t) || a.c.localeCompare(b.c)) : null;
  const terms = all ? [...new Set(all.map(o => o.t))].sort(termOrder) : [], courses = all ? [...new Set(all.map(o => o.c))].sort() : [];
  if (homeFilter.t && !terms.includes(homeFilter.t)) homeFilter.t = "";
  if (homeFilter.c && !courses.includes(homeFilter.c)) homeFilter.c = "";
  const offs = all ? all.filter(o => (!homeFilter.t || o.t === homeFilter.t) && (!homeFilter.c || o.c === homeFilter.c)) : null;
  const n = all ? all.length : 0;
  const sel = (k, label, opts, name) => `<select class="lt-filter" data-f="${k}" aria-label="${label}"><option value="">${label}</option>${opts.map(v => `<option value="${esc(v)}"${homeFilter[k] === v ? " selected" : ""}>${esc(name(v))}</option>`).join("")}</select>`;
  pageHTML(`<div class="lt-in">
    <h1>Your Courses</h1>
    <p class="lt-lede">Each course offering is a course in one term, like <code>csc258/f26</code>. It has a course page for students, its evaluations and a gradebook, and a teaching team. Offerings you're on someone else's team for are here too.</p>
    ${sourceBar()}
    <div class="lt-sec"><h2>Course Offerings</h2>${all && n ? `<div class="lt-filters">${sel("t", "All Terms", terms, t => `${termName(t)} (${t})`)}${sel("c", "All Courses", courses, c => c.toUpperCase())}</div>` : ""}
      <button type="button" class="lt-btn add" id="lt-new"${all ? "" : " disabled"}>${ICON.plus}New Course Offering</button></div>
    <div id="lt-list"></div>
  </div>`);
  $("#lt-new").onclick = newOfferingDialog;
  $("#lt-page").querySelectorAll(".lt-filter").forEach(x => { x.onchange = () => { homeFilter[x.dataset.f] = x.value; try { localStorage.setItem("lectern.home.filter", JSON.stringify(homeFilter)); } catch (_) {} homePage(); }; });
  const list = $("#lt-list");
  if (S.listError) { list.innerHTML = `<p class="lt-note err">Couldn't read your courses. ${esc(S.listError.message)} <button type="button" class="lt-link" id="lt-retry">Try again</button></p>`; $("#lt-retry").onclick = () => { listAll(); }; return; }
  if (!offs) { list.innerHTML = `<div class="lt-grid">${'<div class="lt-card ghost"><div class="lt-strip">&nbsp;</div><div style="padding-top:22px"><div class="lt-ghost-bar" style="width:45%;height:22px"></div><div class="lt-ghost-bar" style="width:70%"></div><div class="lt-ghost-bar" style="width:55%"></div></div></div>'.repeat(3)}</div>`; return; }
  if (!offs.length) { list.innerHTML = n ? `<p class="lt-note">No course offerings match. <button type="button" class="lt-link" id="lt-unfilter">Show them all</button></p>` : `<button type="button" class="lt-card new" id="lt-new2">${ICON.plus}<span>New Course Offering</span><small>A new term of a course, or a new course</small></button>`;
    const u = $("#lt-unfilter"); if (u) u.onclick = () => { homeFilter = {}; try { localStorage.removeItem("lectern.home.filter"); } catch (_) {} homePage(); };
    const n2 = $("#lt-new2"); if (n2) n2.onclick = newOfferingDialog;
    return; }
  // The three most recent as cards; the rest as a list.
  const live = o => (o.page ? liveURL(o.c, o.t, o.o) : "");
  const team = o => (o.o ? `${esc(ownerName(o.o))}'s · ${ROLE_NAME[roleIn(o.c, o.t, o.o)] || ""}` : "");
  const cards = offs.slice(0, 3), rest = offs.slice(3);
  list.innerHTML = `<div class="lt-grid">${cards.map((o, k) => `<div class="lt-card go" role="link" tabindex="0" data-k="${k}" aria-label="Open ${esc(o.c)} ${esc(o.t)}">
      <div class="lt-strip"><span>${esc(o.c)}/${esc(o.t)}</span>${o.o ? `<span class="r" title="On ${esc(ownerName(o.o))}'s teaching team">${team(o)}</span>` : ""}</div>
      <div class="lt-body">
        <div><h3 class="lt-title">${esc(o.c.toUpperCase())}</h3>
        <p class="lt-sub">${esc(termName(o.t))}</p></div>
        <span class="lt-term" aria-hidden="true">${esc(o.t)}</span>
      </div>
      <div class="lt-foot">${live(o) ? `<span>Published</span><a href="${esc(live(o))}" target="_blank" rel="noopener" data-chip>Live page ${ICON.out}</a>` : `<span>No course page yet</span>`}</div>
    </div>`).join("")}</div>${rest.length ? `
    <div class="lt-olist">${rest.map((o, j) => `<div class="lt-orow go" role="link" tabindex="0" data-k="${j + 3}" aria-label="Open ${esc(o.c)} ${esc(o.t)}">
      <span class="lt-orow-t">${esc(o.t)}</span><b>${esc(o.c.toUpperCase())}</b><span class="lt-orow-n">${esc(termName(o.t))}${o.o ? ` · ${team(o)}` : ""}</span>
      <span class="lt-orow-r">${live(o) ? `<a href="${esc(live(o))}" target="_blank" rel="noopener" data-chip>Live page ${ICON.out}</a>` : ""}</span>
    </div>`).join("")}</div>` : ""}`;
  list.querySelectorAll("[data-k]").forEach(el => {
    const o = offs[Number(el.dataset.k)];
    const open = e => { if (e.target.closest("[data-chip]")) return; go({ page: "offering", c: o.c, t: o.t, o: o.o }); };
    el.addEventListener("click", open);
    el.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(e); } });
  });
}
function newOfferingDialog() {
  const now = new Date(), y = now.getFullYear() % 100, mo = now.getMonth();
  const season = mo >= 8 ? "f" : mo >= 4 ? "s" : "w";
  modal(`<h2>New Course Offering</h2><p>A course in one term, in its own folder, e.g. <code>csc258/f26</code>.</p>
    <div class="lt-form">
      <label>Course<input type="text" id="no-c" placeholder="csc258" spellcheck="false" autocomplete="off"><small>Lower case, as in the folder name.</small></label>
      <label>Title<input type="text" id="no-title" placeholder="e.g. Computer Organization" autocomplete="off"><small>On the course page, with the course code, term and ${esc(INSTITUTION())}.</small></label>
      <div class="two">
        <label>Term<select id="no-s"><option value="f">Fall</option><option value="w">Winter</option><option value="s">Summer</option></select></label>
        <label>Year<input type="text" id="no-y" value="20${String(y).padStart(2, "0")}" inputmode="numeric" autocomplete="off"></label>
      </div>
    </div>
    <p class="lt-err" id="no-err"></p>
    <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn primary" data-ok>Continue</button></div>`, (m, close) => {
    m.querySelector("#no-s").value = season;
    m.querySelector("[data-no]").onclick = close;
    const ok = async () => {
      const c = m.querySelector("#no-c").value.trim().toLowerCase().replace(/\s+/g, "");
      const yy = /^(?:20)?(\d{2})$/.exec(m.querySelector("#no-y").value.trim());
      const title = m.querySelector("#no-title").value.trim();
      const err = m.querySelector("#no-err");
      if (!slugOK(c)) { err.textContent = "Enter the course as letters and numbers, e.g. csc258."; return; }
      if (!title) { err.textContent = "Enter the course's title, e.g. Computer Organization."; return m.querySelector("#no-title").focus(); }
      if (!yy) { err.textContent = "Enter the year, e.g. 2026."; return; }
      const t = `${m.querySelector("#no-s").value}${yy[1]}`;
      const path = `${c}/${t}/about.json`, repo = area(Store.PRIV, "");
      m.querySelector("[data-ok]").disabled = true;
      try {   // its folder starts with its title (about.json): an offering that's there already keeps its own
        if (!await Store.readFile(repo, path)) await Store.writeText(repo, path, JSON.stringify({ format: "lectern-about/2", title, description: "" }, null, 1) + "\n", `New course offering ${c} ${t}`, null);
      } catch (e) { err.textContent = `Couldn't make it. ${e.message}`; m.querySelector("[data-ok]").disabled = false; return; }
      close();
      aboutCache.delete(`/${c}/${t}`);
      await listAll().catch(() => null);
      go({ page: "offering", c, t, o: "" });
    };
    m.querySelector("[data-ok]").onclick = ok;
    m.querySelectorAll("input").forEach(i => i.addEventListener("keydown", e => { if (e.key === "Enter") ok(); }));
  });
}

// The offering's title and description (about.json in its private files): the title is asked for when it's
// made, and both are changed on its page, under its code. An older offering without one starts from its
// course page's (course.json), and has one from the first change.
const aboutCache = new Map();   // "<owner>/<c>/<t>" → { data, sha }
async function readAbout(c, t, o = curOwner()) {
  const k = `${o}/${c}/${t}`;
  if (aboutCache.has(k)) return aboutCache.get(k);
  const f = await Store.readFile(area(Store.PRIV, o), `${c}/${t}/about.json`);
  let data = null; try { data = f ? JSON.parse(f.text) : null; } catch (_) {}
  if (!data || typeof data !== "object") {
    let page = null; try { page = JSON.parse(await Store.readText(area(Store.PUB, o), `${c}/${t}/course.json`) || "null"); page = page && page.page; } catch (_) {}
    data = { format: "lectern-about/2", title: (page && page.title) || "", description: (page && page.description) || "" };
  }
  const v = { data: { format: "lectern-about/2", title: String(data.title || ""), description: String(data.description || "") }, sha: f ? f.sha : null };
  aboutCache.set(k, v);
  return v;
}
let aboutTimer = 0, aboutSaving = null, aboutAgain = null;
function saveAboutSoon(c, t, o, v) {
  const el = $("#lt-about-st"); if (el) { el.textContent = "Saving…"; el.classList.remove("bad"); }
  clearTimeout(aboutTimer);
  aboutTimer = setTimeout(async function save() {
    if (aboutSaving) { aboutAgain = save; return; }
    aboutSaving = (async () => {
      const st = () => $("#lt-about-st");
      try {
        v.sha = await Store.writeText(area(Store.PRIV, o), `${c}/${t}/about.json`, JSON.stringify(v.data, null, 1) + "\n", "Title and description", v.sha);
        if (st()) st().textContent = "Saved";
      } catch (e) {
        if (st()) { st().textContent = "Not saved"; st().classList.add("bad"); }
        toast(e.conflict ? "The title or description changed somewhere else. Reload to see it; your last change wasn't saved." : `Couldn't save. ${e.message}`);
      } finally { aboutSaving = null; if (aboutAgain) { const f = aboutAgain; aboutAgain = null; f(); } }
    })();
  }, 600);
}
const INSTITUTION = () => ($(".sp-inst") && $(".sp-inst").textContent.trim()) || "";

function offeringPage(c, t) {
  const o = offering(c, t), loading = !S.offerings && !S.listError;
  const role = roleIn(c, t), edit = role === "owner" || role === "coordinator", ta = role === "ta", own = !curOwner();
  const book = path => ` data-part="${path}"${!o.grades && loading ? " disabled" : ""}`;
  pageHTML(`<div class="lt-in">
    <div class="lt-off-head">
      <div class="lt-off-id"><h1 class="lt-off-h1"><span>${esc(c.toUpperCase())}</span><span id="lt-h1-title"></span></h1>
        <p class="lt-term-line">${esc(termName(t))}</p>
        ${!own ? `<p class="lt-team-line">${esc(ownerName(curOwner()))}'s course offering · you're ${A_ROLE[role] || "a coordinator"}</p>` : ""}</div>
      <div class="lt-off-acts"><a class="lt-btn primary" id="lt-view-page" href="${esc(hubURL(c, t))}" target="_blank" rel="noopener" title="The course page, as students see it">${ICON.page}View Course Page</a>${edit ? `<button type="button" class="lt-btn lt-trash" id="lt-del-off" title="Delete this course offering…" aria-label="Delete this course offering">${ICON.trash}</button>` : ""}</div>
    </div>
    <div class="lt-about" id="lt-about"></div>
    ${loading ? `<p class="lt-note">Checking what it has…</p>` : ""}
    ${S.listError ? `<p class="lt-note err">Couldn't read your courses. ${esc(S.listError.message)}</p>` : ""}
    ${role === "staff" ? `<p class="lt-note">As staff you decide accommodation requests (any activity group's), and can look at everything else here, but not change it.</p>` : ""}
    ${role === "instructor" ? `<p class="lt-note">As an instructor you add and change the activities and announcements for your activity groups (the ones you run an activity of). Everything else is the coordinators'.</p>` : ""}
    ${ta ? `<p class="lt-note">As a TA you can enter marks in the gradebook for every student, and look at the evaluations and exams. Changes to anything else are for the coordinators: Lectern won't save them.</p>` : ""}
    <div class="lt-three lt-off-parts">
      <section class="lt-part lt-wide">
        <div class="lt-part-head">${ICON.mail}<h2>Announcements</h2></div>
        <p class="lt-part-text">News for the class. Each one goes in the week of its date on the course page.</p>
        <div class="lt-part-acts"><button type="button" class="lt-btn${edit ? " primary" : ""}" id="lt-anns">${edit ? "Open Announcements" : "See Announcements"}</button></div>
      </section>
      <section class="lt-part">
        <div class="lt-part-head">${ICON.lectures}<h2>Activities</h2></div>
        <p class="lt-part-text">The weeks of the term and each week's activities (lectures, tutorials, labs), with their files and links.</p>
        <div class="lt-part-acts"><button type="button" class="lt-btn${edit ? " primary" : ""}" id="lt-lectures">${edit ? "Open Activities" : "See Activities"}</button></div>
      </section>
      <section class="lt-part">
        <div class="lt-part-head">${ICON.evals}<h2>Evaluations</h2></div>
        <p class="lt-part-text">${o.grades ? `The assignments, tests and exams: weights, dates, files, and what happens if one is missed.${edit ? " Build each one's exam or handout from here." : ""}` : "No evaluations for this term yet."}</p>
        <div id="lt-loose"></div>
        <div class="lt-part-acts">${o.grades || edit ? `<button type="button" class="lt-btn${edit ? " primary" : ""}"${book("evals")}>${o.grades ? (edit ? "Open Evaluations" : "See Evaluations") : "Add Evaluations"}</button>` : ""}</div>
      </section>
      <section class="lt-part">
        <div class="lt-part-head">${ICON.grades}<h2>Gradebook</h2></div>
        <p class="lt-part-text">${o.grades ? (edit ? `Enter marks, see every student's grade, and give a student their own policy (an accommodation). Its Settings button has the grade ranges, rounding and course rules.` : "Enter marks, and see every student's grade.") : "No gradebook for this term yet: it starts with the evaluations, or the students."}</p>
        <div class="lt-part-acts">${o.grades || edit ? `<button type="button" class="lt-btn${o.grades ? " primary" : ""}"${book("book")}>${o.grades ? "Open Gradebook" : "Start a Gradebook"}</button>` : ""}</div>
      </section>
      ${edit || role === "staff" ? `<section class="lt-part lt-wide">
        <div class="lt-part-head">${ICON.accom}<h2>Accommodations</h2></div>
        <p class="lt-part-text" id="lt-accom-sum">Requests students make with the course page's Request Accommodation buttons. Approve or reject each one; the student gets an email.</p>
        <div class="lt-part-acts"><button type="button" class="lt-btn" id="lt-accom"${!o.grades && loading ? " disabled" : ""}>Open Accommodations</button></div>
      </section>` : ""}
      <section class="lt-part lt-wide lt-team" id="lt-team">
        <div class="lt-part-head">${ICON.team}<h2>Teaching Team</h2></div>
        <div class="lt-team-body"><p class="lt-part-text">Loading…</p></div>
      </section>
      <section class="lt-part lt-wide lt-team" id="lt-groups">
        <div class="lt-part-head">${GROUP_ICON}<h2>Activity Groups</h2></div>
        <div class="lt-team-body"><p class="lt-part-text">Loading…</p></div>
      </section>
      <section class="lt-part lt-wide lt-team" id="lt-students">
        <div class="lt-part-head">${ICON.user}<h2>Students</h2></div>
        <div class="lt-team-body"><p class="lt-part-text">Loading…</p></div>
      </section>
    </div>
  </div>`);
  $("#lt-lectures").onclick = () => go({ page: "lectures", c, t });
  $("#lt-anns").onclick = () => go({ page: "announcements", c, t });
  const acc = $("#lt-accom");
  if (acc) acc.onclick = () => go({ page: "accom", c, t });
  if (acc && o.grades) readAccom(c, t).then(d => {
    const el = $("#lt-accom-sum"), n = d ? d.requests.filter(x => x.status === "pending").length : 0;
    if (!el || !n || S.route.page !== "offering" || S.route.c !== c || S.route.t !== t) return;
    el.innerHTML = `<b>${n} request${n === 1 ? "" : "s"} waiting</b> for a decision. Approve or reject each one; the student gets an email.`;
    $("#lt-accom").classList.add("primary");
  }).catch(() => {});
  $("#lt-page").querySelectorAll("[data-part]").forEach(b => { b.onclick = () => go({ page: "tool", tool: "grades", part: b.dataset.part, c, t }); });
  const del = $("#lt-del-off"); if (del) del.onclick = () => deleteOfferingDialog(c, t);
  aboutPart(c, t, edit);
  teamPart(c, t);
  groupsPart(c, t);
  studentsPart(c, t);
  // Exams and handouts that no evaluation builds (made before they were linked): still reachable here.
  if (o.exams.length) docLinks(c, t).then(links => {
    const linked = new Set(Object.values(links).map(d => d.folder)), loose = o.exams.filter(e => !linked.has(e)), el = $("#lt-loose");
    if (!el || !loose.length || S.route.page !== "offering" || S.route.c !== c || S.route.t !== t) return;
    el.innerHTML = `<p class="lt-part-text lt-loose-h">Not linked to an evaluation:</p><ul class="lt-rows">${loose.map(e => `<li><button type="button" class="row" data-exam="${esc(e)}">${ICON.doc}${esc(e)}</button></li>`).join("")}</ul>`;
    el.querySelectorAll("[data-exam]").forEach(b => { b.onclick = () => go({ page: "tool", tool: "exams", c, t, e: b.dataset.exam }); });
  }).catch(() => {});
}

// Under the code: the title and the description, changed right there (they save by themselves).
async function aboutPart(c, t, edit) {
  const o = curOwner(), box = $("#lt-about");
  const here = () => S.route.page === "offering" && S.route.c === c && S.route.t === t && curOwner() === o && document.body.contains(box);
  let v;
  try { v = await readAbout(c, t, o); } catch (e) { if (here()) box.innerHTML = `<p class="lt-note err">Couldn't read the title and description. ${esc(e.message)}</p>`; return; }
  if (!here()) return;
  const d = v.data;
  if (!edit) {
    if (d.title) $("#lt-h1-title").innerHTML = `<span class="lt-h1-colon">:</span> ${esc(d.title)}`;
    $(".lt-off-h1").title = $(".lt-off-h1").textContent;
    box.innerHTML = d.description ? `<div class="lt-about-desc">${window.HubView.markdown(d.description)}</div>` : "";
    return;
  }
  $("#lt-h1-title").innerHTML = `<span class="lt-h1-colon">:</span> <span class="lt-h1-in" id="lt-title" contenteditable="plaintext-only" role="textbox" aria-label="The course's title" data-ph="Add the course's title" spellcheck="true">${esc(d.title)}</span>`;
  box.innerHTML = `<div class="lt-about-desc" id="lt-desc"></div>
    <span class="lt-about-st" id="lt-about-st" aria-live="polite"></span>`;
  const ti = $("#lt-title"), tEmpty = () => ti.classList.toggle("empty", !ti.textContent.trim());
  tEmpty();
  const full = () => { $(".lt-off-h1").title = d.title ? `${c.toUpperCase()}: ${d.title}` : ""; };
  full();
  ti.oninput = () => { d.title = ti.textContent.replace(/\s+/g, " ").trim(); tEmpty(); full(); saveAboutSoon(c, t, o, v); };
  ti.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); ti.blur(); } };
  ti.onpaste = e => { e.preventDefault(); document.execCommand("insertText", false, (e.clipboardData.getData("text/plain") || "").replace(/\s+/g, " ")); };
  richText($("#lt-desc"), { value: d.description, quiet: true, label: "The course's description", placeholder: "Add a description: what the course is about, in a few sentences. Students see it on the course page's About tab.",
    onChange: md => { d.description = md; saveAboutSoon(c, t, o, v); } });
}

// ── The teaching team: who else works on this offering, as instructor or TA ──
// Instructors add people by email (someone without an account gets an invitation that makes one),
// change roles and remove people; anyone can leave. The server enforces what each role may do.
// ── Students: the class list (students.js): the gradebook's students, who can sign in to the course page ──
function gradebookOf(c, t, o = curOwner()) {
  const g = Lectern.tools.grades;
  return g && g.api && g.api.state().path === `${c}/${t}/grades.json` && (g.owner || "") === o ? g : null;
}
function studentsPart(c, t) {
  const box = $("#lt-students .lt-team-body"), o = curOwner(), owner = o || S.user.handle;
  return studentsCard({ box, esc, toast, modal, confirmBox, Store, area: a => area(a, o), api: Auth.api, owner, lead: canEdit(c, t), ICON, termName,
    // The activity groups (a student is in one or more), and the ones a class list names (made if they're new).
    groups: () => readGroups(Store, area(Store.PRIV, o), c, t).then(x => x.data.groups),
    groupIds: names => groupIdsFor(Store, area(Store.PRIV, o), c, t, names),
    groupsChanged: () => groupsPart(c, t),
    // A student's own page, in the gradebook (their marks, accommodations, notes; dropping or deleting them).
    openStudent: num => go({ page: "tool", tool: "grades", part: "book", c, t }, { where: { view: "students", student: num, stFrom: "grades", stAcc: "", evalEd: "", groupEd: "" } }),
    here: () => S.route.page === "offering" && S.route.c === c && S.route.t === t && curOwner() === o && document.body.contains(box),
    gradebook: () => gradebookOf(c, t, o),
    // The file changed: an open gradebook reads it again when it next shows; a new one is on Home.
    changedBook: made => { const g = gradebookOf(c, t, o); if (g) g.stale = true; if (made) listAll().catch(() => null); } }, c, t);
}

// ── Activity groups (groups.js): the course's sections, their weekly activities and who runs them ──
const teamPeople = (c, t) => Auth.api(`/api/teams/${encodeURIComponent(curOwner() || S.user.handle)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`).then(d => d.people.map(p => ({ id: String(p.id), name: p.name || p.email, email: p.email })));
function groupsPart(c, t) {
  const box = $("#lt-groups .lt-team-body"), o = curOwner();
  return groupsCard({ box, esc, toast, modal, go, Store, repo: area(Store.PRIV, o), lead: canEdit(c, t), ICON,
    here: () => S.route.page === "offering" && S.route.c === c && S.route.t === t && curOwner() === o && document.body.contains(box),
    students: () => getBook(c, t).then(b => (b && b.students) || []) }, c, t);
}

async function teamPart(c, t) {
  const box = $("#lt-team .lt-team-body"), o = curOwner(), owner = o || S.user.handle;
  const here = () => S.route.page === "offering" && S.route.c === c && S.route.t === t && curOwner() === o && document.body.contains(box);
  const base = `/api/teams/${encodeURIComponent(owner)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`;
  let d;
  try { d = await Auth.api(base); } catch (e) { if (here()) box.innerHTML = `<p class="lt-note err">${esc(e.message)}</p>`; return; }
  if (!here()) return;
  const lead = d.you === "owner" || d.you === "coordinator";
  // Coordinator, instructor, TA or staff: a switch, like Lectern's other choices.
  const roleSeg = (cur, attrs, label, small = true) => `<span class="lt-seg${small ? " lt-seg-sm" : ""}" role="radiogroup" aria-label="${esc(label)}">${[["coordinator", "Coordinator"], ["instructor", "Instructor"], ["ta", "TA"], ["staff", "Staff"]].map(([v, n]) =>
    `<button type="button" role="radio" ${attrs} data-v="${v}" aria-checked="${cur === v}" aria-pressed="${cur === v}">${n}</button>`).join("")}</span>`;
  const roleSel = p => roleSeg(p.role, `data-role="${p.id}"`, `Role for ${p.email}`);
  box.innerHTML = `<div class="lt-st-head"><p class="lt-part-text">${lead ? "Coordinators do everything here (the team too). Instructors add and change their activity groups' activities and announcements. TAs enter marks for every student. Staff decide accommodation requests." : "The people who work on this offering."}</p>${lead ? `<div class="lt-st-acts"><button type="button" class="lt-btn add" id="lt-team-new">${ICON.plus}Add a Team Member</button></div>` : ""}</div>
    <div class="lt-olist lt-team-list">${d.people.map(p => `<div class="lt-orow lt-user">
        <button type="button" class="lt-user-who lt-user-open" data-person="${p.id}" title="Their activities (lectures, tutorials, labs, office hours) and contact details, for the course page"><b>${esc(p.name || p.email)}${p.id === d.me ? " (you)" : ""}</b><span>${esc(p.email)}</span></button>
        <span class="lt-orow-r">${p.role === "owner" ? `<span class="lt-tag lt-owner">Owner</span>`
          : lead && p.id !== d.me ? `${roleSel(p)}<button type="button" class="lt-link lt-del" data-remove="${p.id}">Remove</button>`
          : `<span class="lt-tag${p.role === "ta" || p.role === "staff" ? " dim" : ""}">${ROLE_NAME[p.role]}</span>${p.id === d.me ? `<button type="button" class="lt-link lt-del" data-remove="${p.id}">Leave</button>` : ""}`}</span>
      </div>`).join("")}
      ${d.invites.map(i => `<div class="lt-orow lt-user"><div class="lt-user-who"><b>${esc(i.email)}</b><span>Invited as ${A_ROLE[i.role] || "an instructor"}: waiting for them to accept</span></div>
        <span class="lt-orow-r"><button type="button" class="lt-link" data-uninvite="${esc(i.id)}">Cancel</button></span></div>`).join("")}</div>
    ${lead ? `<div id="lt-team-msg"></div>` : ""}`;
  const again = () => teamPart(c, t);
  const call = async (what, body) => { try { await Auth.api(`${base}/${what}`, body); return true; } catch (e) { toast(e.message); again(); return false; } };
  box.querySelectorAll("button[data-role]").forEach(b => {
    b.onclick = async () => {
      if (b.getAttribute("aria-pressed") === "true") return;
      b.parentElement.querySelectorAll("button").forEach(x => { const on = x === b; x.setAttribute("aria-pressed", on); x.setAttribute("aria-checked", on); });
      if (await call("role", { user: Number(b.dataset.role), role: b.dataset.v })) toast(`Now ${A_ROLE[b.dataset.v]}.`);
    };
  });
  box.querySelectorAll("[data-person]").forEach(b => { b.onclick = () => go({ page: "team", c, t, p: b.dataset.person }); });
  box.querySelectorAll("[data-remove]").forEach(b => {
    b.onclick = async () => {
      const me = Number(b.dataset.remove) === d.me;
      if (!await confirmBox(me ? "Leave this team?" : "Remove them from the team?", me ? `You won't see ${esc(c)}/${esc(t)} any more, unless someone adds you again.` : "They won't see this offering any more. You can add them again.", me ? "Leave" : "Remove")) return;
      if (!await call("remove", { user: Number(b.dataset.remove) })) return;
      if (me) { toast(`You left ${c}/${t}.`); await listAll().catch(() => null); return go({ page: "home" }); }
      again();
    };
  });
  box.querySelectorAll("[data-uninvite]").forEach(b => { b.onclick = async () => { if (await call("uninvite", { id: b.dataset.uninvite })) again(); }; });
  // Adding someone: their email and role, in a window; they get an invitation to accept.
  const add = $("#lt-team-new");
  if (add) add.onclick = () => modal(`<h2>Add a Team Member</h2><p>They get an email with a link to join this offering's teaching team. They join once they accept it (signing in, or making an account).</p>
      <div class="lt-form">
        <label>Email<input type="email" id="tm-new-email" placeholder="name@utoronto.ca" autocomplete="off" spellcheck="false"></label>
        <div><span class="lt-field-l">Role</span>${roleSeg("ta", 'data-newrole=""', "Role", false)}<small class="lt-role-help" id="tm-new-help"></small></div>
      </div>
      <p class="lt-err" id="tm-new-err"></p>
      <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn primary" data-ok>Send the Invitation</button></div>`, (m, close) => {
    let newRole = "ta";
    const HELP = { coordinator: "Does everything here, the team too.", instructor: "Adds and changes the activities and announcements for the activity groups they run an activity of (set on a group's page).", ta: "Enters marks for every student, and sees the gradebook and exams.", staff: "Decides accommodation requests from any activity group; changes nothing else." };
    const help = () => { m.querySelector("#tm-new-help").textContent = HELP[newRole]; };
    help();
    m.querySelectorAll("button[data-newrole]").forEach(b => { b.onclick = () => { newRole = b.dataset.v; m.querySelectorAll("button[data-newrole]").forEach(x => { const on = x === b; x.setAttribute("aria-pressed", on); x.setAttribute("aria-checked", on); }); help(); }; });
    m.querySelector("[data-no]").onclick = close;
    const ok = m.querySelector("[data-ok]"), err = m.querySelector("#tm-new-err"), em = m.querySelector("#tm-new-email");
    const send = async () => {
      const email = em.value.trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { err.textContent = "Enter their email address."; return em.focus(); }
      ok.disabled = true; err.textContent = "";
      try {
        const r = await Auth.api(`${base}/add`, { email, role: newRole });
        close();
        await again();
        const msg = $("#lt-team-msg"); if (!msg) return;
        if (r.emailed) { toast(`Invitation emailed to ${email}. They join once they accept it.`); return; }
        msg.innerHTML = `<p class="lt-note">The server can't send email, so send them this link: they join once they open it (and sign in, or make an account). Only to them: it works for whoever has it.
          <span class="lt-linkbox"><input type="text" readonly value="${esc(r.link)}"><button type="button" class="lt-btn" data-copy>Copy</button></span></p>`;
        const cp = msg.querySelector("[data-copy]"); if (cp) cp.onclick = async () => { try { await navigator.clipboard.writeText(r.link); toast("Copied."); } catch (_) { msg.querySelector("input").select(); } };
      } catch (x) { err.textContent = x.message; ok.disabled = false; }
    };
    ok.onclick = send;
    em.addEventListener("keydown", e => { if (e.key === "Enter") send(); });
  });
}
function deleteOfferingDialog(c, t) {
  const o = offering(c, t), name = `${c}/${t}`;
  const open = unsavedTools().filter(u => u.path.startsWith(`${name}/`));
  if (open.length) return confirmBox("Not saved", `<code>${esc(open[0].path)}</code> has changes that aren't saved. Save or discard them before deleting <code>${esc(name)}</code>.`, "OK", "Cancel");
  const what = [o.page && "its course page and files", o.grades && "its gradebook", o.exams.length && `${o.exams.length} exam${o.exams.length === 1 ? "" : "s"}`].filter(Boolean);
  modal(`<h2>Delete ${esc(name)}?</h2>
    <p>This deletes <code>${esc(name)}</code>${what.length ? `: ${esc(what.join(", ").replace(/, ([^,]*)$/, " and $1"))}` : ""}, and takes its course page off the web. The server keeps a copy of every version, so your Lectern admin can still get it back.</p>
    <div class="lt-form"><label><span>Type <code>${esc(name)}</code> to confirm</span><input type="text" id="del-name" autocomplete="off" spellcheck="false"></label></div>
    <p class="lt-err" id="del-err"></p>
    <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn lt-btn-danger" data-ok disabled>Delete</button></div>`, (m, close) => {
    const inp = m.querySelector("#del-name"), ok = m.querySelector("[data-ok]");
    inp.addEventListener("input", () => { ok.disabled = inp.value.trim() !== name; });
    m.querySelector("[data-no]").onclick = close;
    ok.onclick = async () => {
      ok.disabled = true; ok.textContent = "Deleting…";
      try {
        const msg = `Delete ${name}`;
        await Store.deleteFolder(area(Store.PUB), name, msg);
        await Store.deleteFolder(area(Store.PRIV), name, msg);
        close();
        toast(`Deleted ${name}.`);
        S.offerings && S.offerings.delete(okey(c, t));
        listAll();
        go({ page: "home" });
      } catch (e) { ok.disabled = false; ok.textContent = "Delete"; m.querySelector("#del-err").textContent = e.message; }
    };
  });
}

function newExamDialog(c, t) {
  const all = S.offerings ? [...S.offerings.values()].filter(o => o.o === curOwner()).sort((a, b) => termOrder(a.t, b.t) || a.c.localeCompare(b.c)).flatMap(o => o.exams.map(e => `${o.c}/${o.t}/${e}`)) : [];
  const have = offering(c, t).exams;
  modal(`<h2>New exam</h2><p>Its folder goes in <code>${esc(c)}/${esc(t)}/</code>, with the grades (private).</p>
    <div class="lt-form">
      <label>Title<input type="text" id="ne-title" placeholder="Midterm" autocomplete="off"></label>
      <label>Folder name<input type="text" id="ne-slug" placeholder="midterm" spellcheck="false" autocomplete="off"><small>Lower case, no spaces.</small></label>
      ${all.length ? `<label>Start from<select id="ne-copy"><option value="">A blank exam</option>${all.map(p => `<option value="${esc(p)}">A copy of ${esc(p)}</option>`).join("")}</select></label>` : ""}
    </div>
    <p class="lt-err" id="ne-err"></p>
    <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn primary" data-ok>Create</button></div>`, (m, close) => {
    const title = m.querySelector("#ne-title"), slug = m.querySelector("#ne-slug");
    let touched = false;
    title.addEventListener("input", () => { if (!touched) slug.value = title.value.trim().toLowerCase().replace(/[^\w.-]+/g, "-").replace(/^-+|-+$/g, ""); });
    slug.addEventListener("input", () => { touched = true; });
    m.querySelector("[data-no]").onclick = close;
    const ok = () => {
      const e = slug.value.trim(), err = m.querySelector("#ne-err");
      if (!slugOK(e)) { err.textContent = "Give the exam a folder name: letters, numbers and dashes, e.g. midterm."; return; }
      if (have.includes(e)) { err.textContent = `${c}/${t}/${e} already exists.`; return; }
      const cp = m.querySelector("#ne-copy");
      close();
      go({ page: "tool", tool: "exams", c, t, e }, { copyFrom: cp && cp.value ? cp.value : "", title: title.value.trim() });
    };
    m.querySelector("[data-ok]").onclick = ok;
    m.querySelectorAll("input").forEach(i => i.addEventListener("keydown", ev => { if (ev.key === "Enter") ok(); }));
  });
}

// ── Accommodations: requests from the course page, approved or rejected here ──
// Students' requests are in your private files, <course>/<term>/accommodations.json (the server writes
// them: students don't sign in). A decision goes through the server too, which saves it and emails the student.
async function readAccom(c, t) {
  const text = await readPriv(`${c}/${t}/accommodations.json`);
  if (!text) return { requests: [] };
  try { const d = JSON.parse(text); return { requests: Array.isArray(d.requests) ? d.requests : [] }; } catch (_) { return { requests: [], bad: true }; }
}
let serverCfg = null;
const getCfg = () => serverCfg || (serverCfg = fetch("/api/config").then(r => r.json()).catch(() => ({})));
const accomUI = { show: "pending", ev: "" };
const fmtStamp = iso => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString("en-CA", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }); };
const STATUS = { pending: "Waiting", approved: "Approved", rejected: "Rejected" };

async function accomPage(c, t) {
  pageHTML(`<div class="lt-in lt-accom">
    <h1>Accommodations</h1>
    <p class="lt-lede">Requests from the <b>Request Accommodation</b> buttons on <code>${esc(c)}/${esc(t)}</code>'s course page. Approving or rejecting one emails the student.</p>
    <div id="lt-acc"><div class="lt-loading" style="min-height:160px">Reading requests…</div></div>
  </div>`);
  const mine = () => S.route.page === "accom" && S.route.c === c && S.route.t === t;
  let data, book, cfg;
  try { [data, book, cfg] = await Promise.all([readAccom(c, t), getBook(c, t).catch(() => null), getCfg()]); }
  catch (e) { if (mine()) $("#lt-acc").innerHTML = `<p class="lt-note err">Couldn't read the requests. ${esc(e.message)}</p>`; return; }
  if (!mine()) return;
  const evals = (book && book.evals) || [];
  const asks = evals.filter(e => e.accom && ((e.accom.approval && String(e.accom.standard || "").trim()) || e.accom.alternate));
  const canDecide = true;
  const draw = () => {
    const all = data.requests.slice().sort((a, b) => String(b.submitted).localeCompare(String(a.submitted)));
    const byEv = all.filter(r => !accomUI.ev || r.eval === accomUI.ev);
    const pending = byEv.filter(r => r.status === "pending"), decided = byEv.filter(r => r.status !== "pending");
    const list = accomUI.show === "pending" ? pending : accomUI.show === "decided" ? decided : byEv;
    const evNames = [...new Map(all.map(r => [r.eval, r.evalName])).entries()];
    const notes = [
      !cfg.email ? `<p class="lt-note"><b>Emails aren't being sent:</b> the server has no SMTP settings, so students won't hear about decisions (see the README).</p>` : "",
      book && !asks.length ? `<p class="lt-note">No evaluation takes requests yet. In <button type="button" class="lt-link" data-evals>Evaluations</button>, open one and set its <b>Accommodations</b>; then save the course page so its buttons appear.</p>` : "",
      data.bad ? `<p class="lt-note err"><code>accommodations.json</code> couldn't be read.</p>` : "",
    ].join("");
    const seg = (k, label, n) => `<button type="button" data-show="${k}" aria-pressed="${accomUI.show === k}">${label}${n != null ? ` <span>${n}</span>` : ""}</button>`;
    $("#lt-acc").innerHTML = `${notes}
      <div class="lt-sec"><div class="lt-seg" role="group" aria-label="Show">${seg("pending", "Waiting", pending.length)}${seg("decided", "Decided", decided.length)}${seg("all", "All")}</div>
        <div class="lt-filters">${evNames.length > 1 ? `<select class="lt-filter" id="acc-ev" aria-label="Evaluation"><option value="">All Evaluations</option>${evNames.map(([id, n]) => `<option value="${esc(id)}"${accomUI.ev === id ? " selected" : ""}>${esc(n || id)}</option>`).join("")}</select>` : ""}
        <button type="button" class="lt-btn" id="acc-refresh">Refresh</button></div></div>
      ${list.length ? `<div class="lt-reqs">${list.map(reqCard).join("")}</div>`
        : `<p class="lt-hint">${accomUI.show === "pending" ? (all.length ? "Nothing waiting: every request has a decision." : "No requests yet.") : "None."}</p>`}`;
    $("#lt-acc").querySelectorAll("[data-show]").forEach(b => { b.onclick = () => { accomUI.show = b.dataset.show; draw(); }; });
    const f = $("#acc-ev"); if (f) f.onchange = () => { accomUI.ev = f.value; draw(); };
    $("#acc-refresh").onclick = () => accomPage(c, t);
    const ev = $("#lt-acc [data-evals]"); if (ev) ev.onclick = () => go({ page: "tool", tool: "grades", part: "evals", c, t });
    $("#lt-acc").querySelectorAll("[data-decide]").forEach(b => { b.onclick = () => decideDialog(data.requests.find(r => r.id === b.dataset.id), b.dataset.decide); });
  };
  const reqCard = r => `<article class="lt-req st-${esc(r.status)}">
      <div class="lt-req-top"><div class="lt-req-who"><b>${esc(r.first)} ${esc(r.last)}</b><span>${esc(r.student)} · <a href="mailto:${esc(r.email)}">${esc(r.email)}</a></span></div>
        <span class="lt-req-st">${esc(STATUS[r.status] || r.status)}</span></div>
      <p class="lt-req-what"><b>${esc(r.evalName)}</b> · ${r.kind === "standard" ? "Standard accommodation" : "Alternate accommodation"} · <span title="${esc(r.submitted)}">${esc(fmtStamp(r.submitted))}</span></p>
      ${r.kind === "standard" ? `<p class="lt-req-body">${esc(r.standard)}</p>` : `<blockquote class="lt-req-body">${esc(r.details)}</blockquote>`}
      ${r.status !== "pending" ? `<p class="lt-req-dec">${esc(STATUS[r.status])}${r.decidedBy ? ` by ${esc(r.decidedBy)}` : ""}${r.decided ? `, ${esc(fmtStamp(r.decided))}` : ""}.${r.note ? ` Note: “${esc(r.note)}”` : ""}</p>` : ""}
      <div class="lt-req-acts">${r.status === "pending"
        ? `<button type="button" class="lt-btn" data-decide="rejected" data-id="${esc(r.id)}"${canDecide ? "" : " disabled"}>Reject</button><button type="button" class="lt-btn primary" data-decide="approved" data-id="${esc(r.id)}"${canDecide ? "" : " disabled"}>Approve</button>`
        : `<button type="button" class="lt-link" data-decide="${r.status === "approved" ? "rejected" : "approved"}" data-id="${esc(r.id)}"${canDecide ? "" : " disabled"}>${r.status === "approved" ? "Reject it instead" : "Approve it instead"}</button>`}<span class="lt-req-ref">${esc(r.id)}</span></div>
    </article>`;
  function decideDialog(r, decision) {
    if (!r) return;
    const yes = decision === "approved";
    modal(`<h2>${yes ? "Approve" : "Reject"} this request?</h2>
      <p>${esc(r.first)} ${esc(r.last)}, ${esc(r.evalName)}: ${r.kind === "standard" ? `the standard accommodation (${esc(r.standard)})` : "an alternate accommodation"}. ${cfg.email ? `They're emailed at <b>${esc(r.email)}</b>.` : "The server has no SMTP settings, so no email is sent."}</p>
      <div class="lt-form"><label>Note to the student<textarea id="dc-note" rows="4" placeholder="${yes ? "e.g. Write it Thursday at 6 in BA 2135." : "e.g. Please come to office hours to talk about it."}">${esc(r.status === "pending" ? "" : r.note || "")}</textarea><small>Optional. It goes in the email.</small></label></div>
      <p class="lt-err" id="dc-err"></p>
      <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn ${yes ? "primary" : "lt-btn-danger"}" data-ok>${yes ? "Approve" : "Reject"}</button></div>`, (m, close) => {
      m.querySelector("[data-no]").onclick = close;
      const ok = m.querySelector("[data-ok]");
      ok.onclick = async () => {
        ok.disabled = true; ok.textContent = yes ? "Approving…" : "Rejecting…";
        try {
          const d = await Auth.api("/api/accommodations/decide", { owner: curOwner() || undefined, offering: `${c}/${t}`, id: r.id, decision, note: m.querySelector("#dc-note").value });
          Object.assign(r, d.request);
          close();
          toast(`${yes ? "Approved" : "Rejected"}. ${d.emailed ? `Emailed ${r.email}.` : "No email was sent (the server's email isn't set up)."}`);
          if (mine()) draw();
        } catch (e) { ok.disabled = false; ok.textContent = yes ? "Approve" : "Reject"; m.querySelector("#dc-err").textContent = e.message; }
      };
    });
  }
  draw();
}

// ── Cross-links: Grades → the course page, and evaluations ↔ their exams and handouts ──
const num = x => (Number.isFinite(+x) ? +x : 0);
const fmtW = n => String(Math.round(num(n) * 100) / 100);

// A file in your private files (grades, exams).
const readPriv = (path, o = curOwner()) => Store.readText(area(Store.PRIV, o), path);

// The gradebook for an offering: the Grade Builder's copy when it has that one open (so changes not yet
// saved count too), else the file in the private repository.
async function getBook(c, t) {
  const g = Lectern.tools.grades, path = `${c}/${t}/grades.json`;
  if (g && g.api && g.api.state().path === path && !g.stale) return g.api.book();
  if (!offering(c, t).grades) return null;
  const text = await readPriv(path);
  try { return text ? JSON.parse(text) : null; } catch (_) { return null; }
}

// The course page shows the gradebook's evaluations and course rules from its course.json: once the gradebook
// is saved, they go there too, so nothing waits for the course page to be saved. (An open course page with
// changes not saved yet gets them when it's shown, and saves them itself.)
async function syncScheme(c, t, o) {
  const path = `${c}/${t}/course.json`, repo = area(Store.PUB, o), cp = Lectern.tools.course;
  const open = cp && cp.api && cp.api.state().path === path && (cp.owner || "") === o;
  if (open && cp.api.state().unsaved) return;
  const f = await Store.readFile(repo, path); if (!f) return;
  const d = JSON.parse(f.text), g = Lectern.tools.grades;
  if (!d || !d.page || !g || !g.api) return;
  const sc = schemeOf(g.api.book(), `${c}/${t}/grades.json`, S.user ? { url: `${await lecternURL()}request`, repo: o || S.user.handle, offering: `${c}/${t}` } : null);
  if (JSON.stringify(d.page.scheme) === JSON.stringify(sc)) return;
  d.page.scheme = sc;
  await Store.writeText(repo, path, JSON.stringify(d, null, 1) + "\n", `Update ${c} ${t} marking scheme`, f.sha);
  if (open) cp.stale = true;   // it opens again, from the file
}

// What the course page shows from a gradebook: each evaluation and group with its weight, date and rules.
// Never students or marks: only this goes to the public page.
function schemeOf(b, from, requests = null) {
  const evals = (b.evals || []).filter(e => !e.makeupFor), groups = b.groups || [];
  const byId = id => evals.find(e => e.id === id);
  const makeups = e => (b.evals || []).filter(x => x.makeupFor === e.id);
  const notes = e => {   // what happens if it isn't submitted: makeups (each for a part of its weight) and weight moved to others
    const m = e.missed || {}, w = num(e.weight), any = id => (b.evals || []).find(x => x.id === id);
    if (m.mode !== "reweight") return [];
    const mk = (m.makeups || []).filter(x => any(x.id)), to = (m.to || []).filter(x => num(x.share) > 0 && byId(x.id) && !mk.some(y => y.id === x.id));
    const T = [...mk, ...to].reduce((t, x) => t + num(x.share), 0), k = T > 100 ? 100 / T : 1, pc = x => `${fmtW(w * num(x.share) * k / 100)}%`;
    const bits = [...mk.map(x => `the makeup ${any(x.id).name} counts for ${pc(x)}`), ...to.map(x => `${pc(x)} moves to ${byId(x.id).name}`)];
    if (!bits.length) return [];
    const rest = Math.max(0, 100 - T * k);
    return [`If it isn't submitted, ${bits.length > 1 ? `${bits.slice(0, -1).join(", ")} and ${bits[bits.length - 1]}` : bits[0]}${rest > 1e-9 ? `; ${fmtW(w * rest / 100)}% counts as zero` : ""}.`];
  };
  // Accommodations (Grades → an evaluation): the standard one, and whether students can ask, until when.
  const accom = e => {
    const a = e.accom || {}, standard = String(a.standard || "").trim(), approval = !!a.approval && !!standard, alternate = !!a.alternate;
    if (!standard && !alternate) return {};
    return { accom: { standard, approval, alternate, ...(approval || alternate) && a.by ? { by: a.by, byTime: a.byTime || "" } : {} } };
  };
  // An evaluation's files and links (Evaluations → its page): what students get for it, on the course page.
  const files = e => { const fs = (e.files || []).filter(f => f && String(f.url || "").trim()).map(f => ({ label: String(f.label || ""), url: String(f.url).trim() })); return fs.length ? { files: fs } : {}; };
  const brief = e => ({ id: e.id, name: e.name, short: e.short || "", type: ["test", "project", "lab", "other"].includes(e.type) ? e.type : "assignment", date: e.date || "", time: e.time || "", ...accom(e), ...files(e) });
  const units = [], seen = new Set();
  evals.forEach(e => {
    const g = groups.find(x => (x.members || []).includes(e.id));
    if (g) {
      if (seen.has(g.id)) return;
      seen.add(g.id);
      const mem = g.members.map(byId).filter(Boolean);
      units.push({ kind: "group", id: g.id, name: g.name, weight: num(g.weight), keep: Math.min(num(g.keep) || 1, mem.length || 1), count: mem.length, members: mem.map(m => ({ ...brief(m), notes: [] })) });
    } else units.push({ kind: "eval", ...brief(e), weight: num(e.weight), notes: notes(e) });
  });
  // The course rules (the gradebook's Settings), worded for students, each saying whether the course page shows it
  // (its Settings choose: the rules do unless turned off; rounding and grade ranges don't unless turned on).
  const P = b.policies || {}, policies = [], pc = x => `${fmtW(x)}%`, SH = P.show || {};
  const target = t => t.startsWith("g:") ? ((groups.find(g => g.id === t.slice(2)) || {}).name ? `your average on ${groups.find(g => g.id === t.slice(2)).name}` : "") : ((b.evals || []).find(e => e.id === t) || {}).name ? `your mark on ${(b.evals || []).find(e => e.id === t).name}` : "";
  const CODE = { IPR: "IPR (in progress)", SDF: "SDF (standing deferred)", INC: "INC (incomplete)", NGA: "NGA (no grade available)", GWR: "GWR (grade withheld pending review)", AII: "AII (academic integrity issue)", WDR: "WDR (withdrawn)" };
  (P.autofail || []).forEach(a => {
    const ev = a.target && !a.target.startsWith("g:") ? (b.evals || []).find(e => e.id === a.target) : null;
    const w = a.when === "missed" || a.when === "deferred" ? (ev ? `you don't submit ${ev.name}` : "") : a.target && target(a.target);
    if (!w) return;
    const cond = a.when === "missed" ? `If ${w}` : a.when === "deferred" ? `If ${ev.name} is deferred for you` : `If ${w} is below ${pc(a.below)}`;
    const res = a.effect === "code" ? `your course grade is ${CODE[a.code] || a.code}` : `your course grade is ${a.effect === "set" ? "set to" : "at most"} ${pc(a.value)}`;
    policies.push({ id: `fail:${a.id}`, kind: "autofail", title: a.effect === "code" || (a.when || "below") !== "below" ? "Course Grade Rules" : "Automatic Fail", show: SH.rules !== false, text: `${cond}, ${res}.` });
  });
  const R = P.round || {};
  if (num(R.step) > 0) policies.push({ id: "round", kind: "round", title: "Rounding", show: !!SH.round, text: R.dir === "up" ? `Course grades are rounded up to ${num(R.step) === 1 ? "a whole percent" : `a multiple of ${pc(R.step)}`}.` : R.dir === "down" ? `Course grades are rounded down to ${num(R.step) === 1 ? "a whole percent" : `a multiple of ${pc(R.step)}`}.` : `Course grades are rounded to the nearest ${num(R.step) === 1 ? "whole percent" : pc(R.step)}.` });
  (P.buckets || []).forEach(x => policies.push({ id: `range:${x.id}`, kind: "range", title: "Grade Adjustments", show: !!SH.ranges, text: `A course grade from ${pc(x.from)} to ${pc(x.to)} becomes ${pc(x.value)}.` }));
  // Every evaluation by its date for the course page, makeups too (each says what it's a makeup for).
  return { from, units, evals: (b.evals || []).map(e => ({ ...brief(e), ...(e.makeupFor ? { makeupFor: e.makeupFor } : {}) })), policies, ...(requests ? { requests } : {}) };
}

// An evaluation's file, uploaded from Evaluations: into the offering's public files (<course>/<term>/evaluations/),
// under a name not taken yet. → its public address, for the course page's button.
// For the gradebook: a TA's or instructor's activity groups (the ones they run an activity of), or null.
Lectern.myGroups = async () => {
  const r = S.route; if (!r.c || !r.t || !["ta", "instructor"].includes(roleIn(r.c, r.t))) return null;
  const G = await readGroups(Store, area(Store.PRIV), r.c, r.t);
  return new Set(G.data.groups.filter(g => (g.items || []).some(x => (x.people || []).map(String).includes(String(S.user.id)))).map(g => g.id));
};
Lectern.uploadPublic = async (file, into = "evaluations") => {
  const r = S.route; if (!r.c || !r.t) throw new Error("Open a course offering first.");
  const repo = area(Store.PUB), folder = `${r.c}/${r.t}/${into === "lectures" ? "lectures" : "evaluations"}`;
  const clean = String(file.name || "file").normalize("NFKD").replace(/[^\w.-]+/g, "-").replace(/^[-.]+|-+$/g, "") || "file";
  const dot = clean.lastIndexOf("."), base = dot > 0 ? clean.slice(0, dot) : clean, ext = dot > 0 ? clean.slice(dot) : "";
  const have = new Set((await Store.tree(repo)).map(x => x.path));
  let name = clean, k = 2;
  while (have.has(`${folder}/${name}`)) name = `${base}-${k++}${ext}`;
  await Store.upload(repo, `${folder}/${name}`, file, `Upload ${name} (evaluation file)`);
  return `${siteURL()}${encPath(`${folder}/${name}`)}`;
};

// The teaching team as the course page shows it (as server/hub.py's team_of does): each person, with their
// page's email, office, sections and times (team.json).
async function teamFor(c, t) {
  const owner = curOwner() || S.user.handle;
  const [d, raw, G] = await Promise.all([Auth.api(`/api/teams/${encodeURIComponent(owner)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`), readPriv(`${c}/${t}/team.json`).catch(() => null), readGroups(Store, area(Store.PRIV), c, t).catch(() => null)]);
  let info = {}; try { info = (JSON.parse(raw || "{}") || {}).people || {}; } catch (_) {}
  const fromGroups = id => (G ? G.data.groups.flatMap(g => g.items.filter(x => (x.people || []).includes(String(id))).map(x => ({ kind: x.kind, section: g.name, day: x.day, start: x.start, end: x.end, where: x.where }))) : null);
  return d.people.filter(p => (info[p.id] || {}).show !== false).map(p => {
    const me = info[p.id] || {};
    return { name: p.name || p.email, role: ["coordinator", "ta", "staff"].includes(p.role) ? p.role : "instructor", email: me.email || p.email, office: me.office || "",
      times: [...(fromGroups(p.id) || []), ...(me.times || []).filter(x => !G || x.kind === "office")].map(x => ({ kind: x.kind || "other", section: x.section || "", day: Number(x.day) || 0, start: x.start || "", end: x.end || "", where: x.where || "" })) };
  });
}

// Where the course page's Request Accommodation buttons go: Lectern's request form, for this course
// offering, by your handle (the server finds your gradebook from it).
const lecternURL = () => getCfg().then(c => c.app_url || `${location.origin}/`);
async function requestsFor(c, t) {
  return S.user ? { url: `${await lecternURL()}request`, repo: curOwner() || S.user.handle, offering: `${c}/${t}` } : null;
}

// Each evaluation's exam or handout in an offering: the Exam Builder's open one, and every exam.json
// that names the evaluation it's for. → { evaluation id: { folder, total, layout } }
async function docLinks(c, t) {
  const out = {}, x = Lectern.tools.exams, live = x && x.api ? x.api.state() : null;
  const add = (folder, d) => { if (d.link && !out[d.link]) out[d.link] = { folder, total: num(d.total), layout: d.layout === "handout" ? "handout" : "exam" }; };
  if (live && live.path && live.path.startsWith(`${c}/${t}/`)) add(live.path.split("/")[2], live);
  await Promise.all(offering(c, t).exams.map(async e => {
    if (live && live.path === `${c}/${t}/${e}/exam.json`) return;
    try { const j = JSON.parse(await readPriv(`${c}/${t}/${e}/exam.json`) || "null"); if (j && j.settings) add(e, { link: j.settings.link, total: j.total, layout: j.settings.layout }); } catch (_) {}
  }));
  return out;
}

// Build, from an evaluation in Grades: open its exam or handout, or start one, named after it and dated.
Lectern.build = async info => {
  const r = S.route; if (!r.c) return;
  const links = await docLinks(r.c, r.t).catch(() => ({}));
  if (links[info.id]) return go({ page: "tool", tool: "exams", c: r.c, t: r.t, e: links[info.id].folder });
  const taken = new Set(offering(r.c, r.t).exams);
  const x = Lectern.tools.exams && Lectern.tools.exams.api ? Lectern.tools.exams.api.state() : null;
  if (x && x.path && x.path.startsWith(`${r.c}/${r.t}/`)) taken.add(x.path.split("/")[2]);   // the exam open now, if it's this offering's
  const base = String(info.name || info.label || "exam").split(":")[0].trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "exam";
  let folder = base, k = 2; while (taken.has(folder)) folder = `${base}-${k++}`;
  let date = "";
  if (info.date) {
    const d = new Date(`${info.date}T${info.time || "12:00"}`);
    if (!isNaN(d)) date = d.toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric", year: "numeric" }) + (info.time ? `, ${info.time}` : "");
  }
  go({ page: "tool", tool: "exams", c: r.c, t: r.t, e: folder }, { title: info.name, date, layout: info.type === "test" ? "exam" : "handout", link: info.id, created: true });
};

// Before a builder shows: the course page gets the gradebook's scheme; the gradebook gets its linked documents.
async function crossLink(tool, r, t, opts) {
  try {
    if (tool === "course") {
      const b = await getBook(r.c, r.t).catch(() => null);
      t.api.setScheme(b ? schemeOf(b, `${r.c}/${r.t}/grades.json`, await requestsFor(r.c, r.t)) : null, { edit: v => go({ page: "tool", tool: "grades", part: v === "settings" ? "settings" : "evals", c: r.c, t: r.t }) });
      if (t.api.setTeam) t.api.setTeam(await teamFor(r.c, r.t).catch(() => null));
      if (t.api.setAbout) { aboutCache.delete(`${curOwner()}/${r.c}/${r.t}`); const a = await readAbout(r.c, r.t).catch(() => null); t.api.setAbout({ ...(a ? a.data : {}), code: r.c.toUpperCase(), term: termName(r.t), school: INSTITUTION() }); }
      if (t.api.setAnnouncements) { let a = null; try { a = JSON.parse(await readPriv(`${r.c}/${r.t}/announcements.json`) || "null"); } catch (_) {} t.api.setAnnouncements(a && Array.isArray(a.items) ? a.items : null); }
      if (t.api.setLectures) { let l = null; try { l = JSON.parse(await readPriv(`${r.c}/${r.t}/lectures.json`) || "null"); } catch (_) {} t.api.setLectures(l && Array.isArray(l.weeks) ? l : null); }
    }
    if (tool === "grades") t.api.setLinks(await docLinks(r.c, r.t));
  } catch (e) { console.warn("[Lectern] cross-link:", e); }
}

// ── The builders ─────────────────────────────────────────────────────
// Each builder talks GitHub's REST API to "lectern/pub" or "lectern/priv"; scope.js sends those calls to
// your files on Lectern's server, with your session (the token here is only a placeholder).
function connection(tool, o = curOwner()) {
  return { mode: "github", repo: Store.repoName(area(TOOLS[tool].repo === "pub" ? Store.PUB : Store.PRIV, o)), branch: "main", token: "session", site: siteURL(o) };
}
function connectAll() {
  Object.entries(Lectern.tools).forEach(([name, t]) => {
    if (!t.api) return;
    try { t.api.connect(connection(name, t.owner || "")); } catch (e) { console.error(e); }
  });
}

// Once per builder: its bar's Home button goes to Lectern's Home, the path strip
// sits under its bar, and the strip follows what the builder shows.
function fitTool(t) {
  if (t.fitted) return;
  t.fitted = true;
  const root = t.root, tb = $(".tb", root), path = $("#lt-path");
  root.addEventListener("click", e => {
    if (e.target.closest("#home-btn")) { e.preventDefault(); e.stopPropagation(); go({ page: "home" }); }
  }, true);
  // The builder's bar becomes the strip under Lectern's: the path, then its own view switch and tools.
  // (Its Home, Save and status go: Lectern's bar has them.)
  if (tb) tb.classList.add("lt-tb");
  // The builder's own --tbh (what sticks under its bar) now has the path strip under it too.
  const sync = () => {
    if (Lectern.active !== t.name) return;
    const h = (tb ? tb.offsetHeight : 0) + $("#lt-bar").offsetHeight;
    if (t.usesTbh) { const want = `${h}px`; if (root.style.getPropertyValue("--tbh") !== want) { t.tbhSet = want; root.style.setProperty("--tbh", want); } }
  };
  t.sync = sync;
  new MutationObserver(() => {
    const v = root.style.getPropertyValue("--tbh");
    if (v && v !== t.tbhSet) { t.usesTbh = true; sync(); }
  }).observe(root, { attributes: true, attributeFilter: ["style"] });
  if (tb) new ResizeObserver(sync).observe(tb);
  let raf = 0;
  new MutationObserver(recs => {
    if (Lectern.active !== t.name || recs.every(r => path.contains(r.target))) return;
    cancelAnimationFrame(raf); raf = requestAnimationFrame(() => toolPath(t));
  }).observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["aria-pressed", "hidden"] });
}

// The path inside a builder: Lectern's part (Home › csc258 / f26 › Grades), then the
// builder's own (its in-page path, or the view it's on).
function toolSteps(t) {
  const cr = [...t.root.querySelectorAll("#stage .crumbs, .stage .crumbs")].find(n => !n.closest("[hidden]"));
  if (cr) return [...cr.children].filter(n => n.matches("button, .cur")).map(n => n.matches("button") ? { label: n.textContent.trim(), go: () => n.click() } : { label: n.textContent.trim() });
  const seg = t.root.querySelector("#tb-view .seg button[aria-pressed='true']");
  return seg ? [{ label: seg.textContent.trim() }] : [];
}
function toolPath(t) {
  const st = t.api.state();
  let r = S.route;
  // The builder's own Open window may have opened another file: follow it.
  if (st.path) {
    const p = routeForPath(t.name, st.path, r.part);
    if (hashFor(p) !== hashFor(r)) { r = S.route = p; history.replaceState({ i: H.at }, "", hashFor(p)); }
  }
  // The gradebook went to a page in another of its parts (e.g. an evaluation from a grade): follow it.
  // noteWhere then makes it a step at the new address.
  if (t.name === "grades" && st.view && partOf(st.view) !== (r.part || "book")) { r = S.route = { ...r, part: partOf(st.view) }; t.api.section(r.part); }
  const steps = [HOME_STEP, offeringStep(r.c, r.t)];
  if (t.name === "exams") steps.push({ label: "Evaluations", go: () => go({ page: "tool", tool: "grades", part: "evals", c: r.c, t: r.t }) }, { label: st.title || r.e });
  const own = toolSteps(t);
  const title = t.name === "grades" ? PARTS[r.part || "book"].title : TOOLS[t.name].title;
  if (own.length && own[0].label === title) { const first = own.shift(); steps.push(own.length ? { label: title, go: first.go } : { label: title }); }
  else if (t.name !== "exams") steps.push(own.length && t.api.top ? { label: title, go: () => t.api.top() } : { label: title });
  renderPath([...steps, ...own]);
  renderBar();
  noteWhere(t);
}

async function openTool(r, my) {
  const tool = r.tool;
  const opts = pendingOpen; pendingOpen = null;
  const folder = tool === "exams" ? `${r.c}/${r.t}/${r.e}` : `${r.c}/${r.t}`;
  const target = `${folder}/${TOOLS[tool].file}`;
  let t = Lectern.tools[tool] && Lectern.tools[tool].api ? Lectern.tools[tool] : null;
  // Already showing that file: just show the builder again.
  if (!(t && t.api.state().path === target && (t.owner || "") === curOwner() && !t.stale)) {
    showPageChrome();
    renderPath([HOME_STEP, offeringStep(r.c, r.t), { label: tool === "exams" ? r.e : TOOLS[tool].title }]);
    pageHTML(`<div class="lt-loading">Opening ${esc(target)}…</div>`);
    await listed();
    if (my !== seq) return;
    try {
      if (!t) {
        $("#lt-page").hidden = true; $("#lt-bar").hidden = true;      // the builder starts visible, so it lays out right
        t = await Lectern.mount(tool, $("#lt-tools"));
        Lectern.show(null);
        $("#lt-page").hidden = false; $("#lt-bar").hidden = false;
      }
      const st = t.api.state();
      if (!(st.path === target && (t.owner || "") === curOwner()) && st.unsaved && st.path) {
        const discard = await confirmBox("Not saved", `<code>${esc(st.path)}</code> has changes that aren't saved yet. Open <code>${esc(target)}</code> instead and lose them?`, "Discard and open", "Keep editing it");
        if (my !== seq) return;
        if (!discard) return go(routeForPath(tool, st.path));
      }
      t.owner = curOwner();   // whose files it's working in (yours, or a team's owner's)
      t.api.connect(connection(tool, t.owner));
      const o = offering(r.c, r.t);
      const has = tool === "course" ? o.page : tool === "grades" ? o.grades : o.exams.includes(r.e);
      await t.api.open(folder, has, opts && opts.copyFrom, opts && opts.title, opts || {});
      t.stale = false;
      t.taBase = tool === "grades" && roleIn(r.c, r.t) === "ta" && t.api.book ? noMarks(t.api.book()) : "";
      const where = "in Lectern";
      if (!has) toast(tool === "course" ? `Started ${target}. Save to create it.` : tool === "grades" ? `New gradebook for ${r.c}/${r.t}. Save to put it ${where}.`
        : opts && opts.created ? `New ${opts.layout === "handout" ? "handout" : "exam"} for ${opts.title}, in ${folder}. Its total marks become the evaluation's out of. Save to put it ${where}.` : `New exam ${folder}. Save to put it ${where}.`);
    } catch (e) {
      if (my !== seq) return;
      $("#lt-page").hidden = false; $("#lt-bar").hidden = false;
      pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't open <code>${esc(target)}</code>. ${esc(e.message)}</p><p style="margin-top:16px"><button type="button" class="lt-btn" id="lt-back">Back to ${esc(r.c)} / ${esc(r.t)}</button></p></div>`);
      $("#lt-back").onclick = () => go({ page: "offering", c: r.c, t: r.t });
      console.error(e);
      return;
    }
    if (my !== seq) return;
  }
  await crossLink(tool, r, t, opts);
  if (my !== seq) return;
  // Show it: Lectern's bar stays; the path goes into the builder's own bar, under it.
  fitTool(t);
  $("#lt-bar").hidden = false; $("#lt-page").hidden = true;
  document.body.className = `lt-on-app lt-on-tool lt-tool-${tool}`;
  syncBarHeight();
  Lectern.show(tool);
  if (tool === "grades" && t.api.section) t.api.section(r.part || "book");
  t.sync();
  if (pendingWhere) { applyWhere(t, pendingWhere); pendingWhere = null; }
  else if (opts && opts.where) applyWhere(t, opts.where);   // e.g. a student's page, from the offering's Students card
  else if (t.api.where && !(history.state || {}).lt) history.replaceState({ ...(history.state || {}), lt: t.api.where() }, "");
  toolPath(t);
  window.scrollTo(0, scrolls[routeKey(S.route)] || 0);
}

// ── Start ────────────────────────────────────────────────────────────
$("title").dataset.splash = document.title;
(async () => {
  const onSignedIn = (user, how, team, note) => start(user, how, team, note);
  // An invitation or reset link always shows its step, even when signed in already (as someone else, maybe).
  if (/^#(invite|reset)=/.test(location.hash)) { await Auth.signOut(); showSplash(); return Auth.initSplash(onSignedIn); }
  let d = null;
  try { d = await Auth.me(); } catch (e) { showSplash(e.message, true); Auth.initSplash(onSignedIn); return; }
  // A teaching team's invitation, already signed in: accept it straight away.
  const join = /^#join=([\w-]{20,200})$/.exec(location.hash);
  if (join && d.signedIn) {
    history.replaceState(null, "", location.pathname + location.search + "#/");
    try { const j = await Auth.api("/api/teams/join", { token: join[1] }); return start(d.user, "join", { owner: j.owner, offering: j.offering }); }
    catch (e) { start(d.user); return setTimeout(() => toast(e.message), 300); }
  }
  if (d.signedIn) return start(d.user);
  showSplash();
  Auth.initSplash(onSignedIn);
})();
