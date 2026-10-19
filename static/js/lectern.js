/* ============================================================
   Lectern — the shell: splash, sign-in / folder, Home, a course
   offering's page, the pinned path, and opening the builders.

   Routes (in the address, so Back and reload work):
     #/                    Home: every course offering
     #/csc258/f26          one offering: its course page, grades and exams
     #/csc258/f26/course   the Course Page Builder on csc258/f26/info.html (public repo)
     #/csc258/f26/grades   the Grade Builder on csc258/f26/grades.json (private repo)
     #/csc258/f26/exams/midterm   the Exam Builder on csc258/f26/midterm/exam.json (private repo)
   ============================================================ */
import * as GH from "./github.js";
import * as FS from "./folder.js";
import { makeLocalGitHub } from "./localgh.js";

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
  gh: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>',
};
const TOOLS = {
  course: { title: "Course Page", file: "info.html", repo: "pub" },
  grades: { title: "Gradebook", file: "grades.json", repo: "priv" },
  exams: { title: "Exams", file: "exam.json", repo: "priv" },
};

// ── State ────────────────────────────────────────────────────────────
const S = {
  mode: null,          // "github" | "local"
  user: null,          // GitHub: { login, avatar_url }
  priv: null, pub: null,   // GitHub: the two repositories ({ full_name, default_branch, private })
  folder: null,        // folder mode: { parent, priv, pub, site, name }
  offerings: null,     // "c/t" → { c, t, page, grades, exams: [] }
  listing: null, listError: null,
  route: { page: "home" },
  ready: false,
};
const REPOS_KEY = "lectern.repos", MODE_KEY = "lectern.mode";
// The two repositories pair up by name: <name> is public (course pages), <name>-private is private
// (grades and exams). e.g. courses-utor and courses-utor-private.
const pubFor = priv => (/-private$/i.test(priv) ? priv.replace(/-private$/i, "") : "");
const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (_) { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} },
};

const siteURL = () => (S.mode === "github" ? (S.pub ? GH.siteFor(S.pub.full_name) : "") : (S.folder && S.folder.site) || "");
const liveURL = (c, t) => { const s = siteURL(); return s ? `${s}${encPath(`${c}/${t}/info.html`)}` : ""; };
const offering = (c, t) => (S.offerings && S.offerings.get(`${c}/${t}`)) || { c, t, page: false, grades: false, exams: [] };

// ── Messages and windows ─────────────────────────────────────────────
function toast(msg) {
  const root = $("#lt-toast-root");
  if (!root.classList.contains("lt-toasts")) root.className = "lt-toasts";
  const el = document.createElement("div");
  el.className = "lt-toast"; el.textContent = msg;
  root.append(el);
  setTimeout(() => el.remove(), 4200);
}
function modal(html, onReady) {
  const bg = document.createElement("div");
  bg.className = "lt-modal-bg";
  bg.innerHTML = `<div class="lt-modal" role="dialog" aria-modal="true">${html}</div>`;
  $("#lt-modal-root").append(bg);
  const m = bg.firstElementChild;
  const close = () => { bg.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = e => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  document.addEventListener("keydown", onKey, true);
  bg.addEventListener("mousedown", e => { if (e.target === bg) close(); });
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
function showSplash(msg = "", isError = false, reopen = null) {
  document.documentElement.classList.remove("lt-has-session");
  document.body.className = "lt-on-splash";
  $("#app").hidden = true; $("#splash").hidden = false;
  document.title = $("title").dataset.splash || document.title;
  const st = $("#splash-status");
  st.className = `sp-hint${isError ? " is-error" : ""}`;
  st.innerHTML = msg ? esc(msg) : "";
  if (reopen) {
    st.className = "sp-hint";
    st.innerHTML = `Last time: the <b>${esc(reopen.name)}</b> folder. <button type="button" id="splash-reopen">Open it again</button>`;
    $("#splash-reopen").onclick = async () => { if (await FS.reconnect(reopen)) startLocal(reopen); else splashSay("The browser didn't allow access to that folder.", true); };
  }
  try { $("#splash-remember").checked = GH.remembered() || localStorage.getItem("lectern.keep") === "1"; } catch (_) {}
}
const splashSay = (msg, isError) => { const st = $("#splash-status"); st.className = `sp-hint${isError ? " is-error" : ""}`; st.textContent = msg; };

$("#splash-signin").onclick = async () => {
  const b = $("#splash-signin"); b.disabled = true;
  const keep = $("#splash-remember").checked;
  try { localStorage.setItem("lectern.keep", keep ? "1" : "0"); } catch (_) {}
  try { await GH.startSignIn(keep); }
  catch (e) { splashSay(e.message, true); b.disabled = false; }
};
$("#splash-folder").onclick = async () => {
  if (!FS.supported) return splashSay("This browser can't open folders. Use Chrome or Edge, or sign in with GitHub.", true);
  let h;
  try { h = await FS.choose(); } catch (e) { return splashSay(e.message, true); }
  if (h) startLocal(h);
};

// ── Starting a session ───────────────────────────────────────────────
function showApp() {
  document.documentElement.classList.remove("lt-has-session");
  $("#splash").hidden = true; $("#app").hidden = false;
}

async function startGitHub() {
  S.mode = "github";
  store.set(MODE_KEY, "github");
  showApp();
  pageHTML(`<div class="lt-loading">Connecting to GitHub…</div>`);
  try { S.user = await GH.user(); }
  catch (e) {
    if (e.status === 401) { GH.signOut(); return showSplash(e.message || "Please sign in again.", true); }
    return pageHTML(`<div class="lt-in"><p class="lt-note err">${esc(e.message)}</p><p style="margin-top:16px"><button type="button" class="lt-btn" onclick="location.reload()">Try again</button></p></div>`);
  }
  GH.schedule();
  GH.onToken(() => connectAll());
  const saved = store.get(REPOS_KEY);
  if (saved && saved.priv) {
    try {
      S.priv = await GH.repo(saved.priv);
      S.pub = saved.pub || pubFor(saved.priv) ? await GH.repo(saved.pub || pubFor(saved.priv)).catch(e => { if (e.status === 404) return null; throw e; }) : null;
    } catch (e) { S.priv = null; S.pub = null; }
  }
  S.ready = true;
  renderBar();
  if (!S.priv || !S.pub) return setupPage();
  listAll();
  route();
}

async function startLocal(parent) {
  let ps;
  try { ps = await FS.pairs(parent); }
  catch (_) { return showSplash("Couldn't read that folder. Try choosing it again.", true); }
  if (!ps.length) return showSplash(`No course repository in “${parent.name}”. Choose the folder that holds your clone of it and its -private twin side by side, e.g. courses-utor and courses-utor-private.`, true);
  let pair = ps[0];
  const want = store.get("lectern.folder.pair");
  if (ps.length > 1) {
    pair = ps.find(p => want && p.priv === want) || await new Promise(res => modal(`<h2>Which repository?</h2><p>This folder holds more than one course repository.</p>
      <div class="lt-form"><label>Repository<select id="lt-pair">${ps.map((p, k) => `<option value="${k}">${esc(p.pub)}</option>`).join("")}</select></label></div>
      <div class="lt-modal-acts"><button type="button" class="lt-btn primary" data-ok>Open</button></div>`, (m, close) => { m.querySelector("[data-ok]").onclick = () => { close(); res(ps[Number(m.querySelector("#lt-pair").value)]); }; }));
  }
  store.set("lectern.folder.pair", pair.priv);
  S.mode = "local";
  store.set(MODE_KEY, "local");
  S.folder = await FS.open(parent, pair);
  Lectern.local = { [`local/${pair.priv}`]: makeLocalGitHub(S.folder.priv, `local/${pair.priv}`) };
  S.ready = true;
  showApp();
  renderBar();
  connectAll();
  listAll();
  route();
}

// ── Listing every course offering ────────────────────────────────────
function listAll() {
  const map = new Map();
  const add = (c, t, what) => {
    if ([c, t].some(x => x.startsWith(".") || x.startsWith("_"))) return;
    const k = `${c}/${t}`, o = map.get(k) || { c, t, page: false, grades: false, exams: [] };
    if (what.page) o.page = true;
    if (what.grades) o.grades = true;
    if (what.exams) what.exams.forEach(e => { if (!o.exams.includes(e)) o.exams.push(e); });
    if (what.folder) o.folder = true;
    map.set(k, o);
  };
  S.listing = (async () => {
    if (S.mode === "local") await FS.list(S.folder, add);
    else {
      const [pv, pb] = await Promise.all([GH.tree(S.priv.full_name, S.priv.default_branch), GH.tree(S.pub.full_name, S.pub.default_branch)]);
      pb.forEach(x => {
        const p = x.path.split("/");
        if (x.type === "tree" && p.length === 2) add(p[0], p[1], { folder: true });
        if (x.type === "blob" && p.length === 3 && p[2] === "info.html") add(p[0], p[1], { page: true });
      });
      pv.forEach(x => {
        const p = x.path.split("/");
        if (x.type === "tree" && p.length === 2) add(p[0], p[1], { folder: true });
        if (x.type === "blob" && p.length === 3 && p[2] === "grades.json") add(p[0], p[1], { grades: true });
        if (x.type === "blob" && p.length === 4 && p[3] === "exam.json") add(p[0], p[1], { exams: [p[2]] });
      });
    }
    // A folder that has nothing yet counts only if it's named like a term (f26, w27, s26).
    for (const [k, o] of map) if (!o.page && !o.grades && !o.exams.length && !isTerm(o.t)) map.delete(k);
    map.forEach(o => o.exams.sort());
    S.offerings = map; S.listError = null;
    return map;
  })().catch(e => { S.listError = e; throw e; });
  S.listing.then(() => { if (S.route.page !== "tool") renderPage(); }, () => { if (S.route.page !== "tool") renderPage(); });
  return S.listing;
}
const listed = () => (S.listing || listAll()).catch(() => null);

// ── Routes ───────────────────────────────────────────────────────────
function parseHash() {
  const p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (p.length >= 2 && slugOK(p[0]) && slugOK(p[1])) {
    const [c, t, tool, e] = p;
    if (tool === "course") return { page: "tool", tool, c, t };
    // The gradebook's three parts: Evaluations, the Gradebook (grades and students) and the course's Settings
    const part = { evaluations: "evals", gradebook: "book", grades: "book", settings: "settings" }[tool];
    if (part) return { page: "tool", tool: "grades", part, c, t };
    if (tool === "exams" && e && slugOK(e)) return { page: "tool", tool, c, t, e };
    return { page: "offering", c, t };
  }
  return { page: "home" };
}
const PARTS = { evals: { slug: "evaluations", title: "Evaluations" }, book: { slug: "gradebook", title: "Gradebook" }, settings: { slug: "settings", title: "Settings" } };
const partOf = view => view === "evals" ? "evals" : view === "settings" ? "settings" : "book";
const hashFor = r => r.page === "home" ? "#/" : r.page === "offering" ? `#/${r.c}/${r.t}` : r.tool === "exams" ? `#/${r.c}/${r.t}/exams/${r.e}`
  : r.tool === "grades" ? `#/${r.c}/${r.t}/${PARTS[r.part || "book"].slug}` : `#/${r.c}/${r.t}/${r.tool}`;
const routeKey = r => hashFor(r);
let pendingOpen = null;      // options for the next open (copy from, title), set by a button just before it navigates
function go(r, opts = null) {
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
  if (S.mode === "github" && (!S.priv || !S.pub)) return setupPage();
  if (r.page === "tool") return openTool(r, my);
  // Coming back from a builder: what's in the repositories may have changed (a save made a new file).
  if (prevTool) listAll();
  showPageChrome();
  renderPage();
  window.scrollTo(0, scrolls[routeKey(r)] || 0);
}
window.addEventListener("hashchange", () => { stamp(); route(); });

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
function routeForPath(tool, path, part) {
  const p = path.split("/");
  return tool === "exams" ? { page: "tool", tool, c: p[0], t: p[1], e: p[2] } : tool === "grades" ? { page: "tool", tool, part: part || "book", c: p[0], t: p[1] } : { page: "tool", tool, c: p[0], t: p[1] };
}
function renderBar() {
  const st = $("#lt-status");
  const un = unsavedTools();
  st.innerHTML = `${un.length ? `<button type="button" class="lt-pill" id="lt-unsaved" title="${esc(un.map(u => u.path).join("\n"))}">${ICON.warn}${un.length === 1 ? `<span>Not saved<span class="lt-pill-x">: ${esc(un[0].path.split("/").slice(0, un[0].name === "exams" ? 3 : 2).join("/"))} ${esc(TOOLS[un[0].name].title.toLowerCase())}</span></span>` : `${un.length} not saved`}</button>` : ""}`;
  const u = $("#lt-unsaved");
  if (u) u.onclick = () => go(routeForPath(un[0].name, un[0].path));
  const a = $("#lt-acct");
  a.innerHTML = S.mode === "github" && S.user ? `${S.user.avatar_url ? `<img src="${esc(S.user.avatar_url)}&s=44" alt="">` : ICON.gh}<span>${esc(S.user.login)}</span>`
    : S.mode === "local" && S.folder ? `${ICON.folder}<span>${esc(S.folder.name)}</span>` : "";
  a.hidden = !a.innerHTML;
  const sv = $("#lt-save");
  if (!saving) {
    sv.disabled = !un.length;
    sv.title = un.length ? `Save ${un.map(saveLabel).join(", ")}` : "Everything is saved";
  }
}
$("#lt-home").onclick = () => go({ page: "home" });

// ── Save: one button saves every course page, gradebook and exam with changes ──
const SAVE_WHAT = { course: "course page", grades: "gradebook", exams: "exam" };
function saveLabel(u) {
  const p = u.path.split("/");
  return u.name === "exams" ? `${p[0]}/${p[1]} ${p[2]}` : `${p[0]}/${p[1]} ${SAVE_WHAT[u.name]}`;
}
let saving = false;
async function saveAll() {
  const un = unsavedTools().filter(u => Lectern.tools[u.name].api.save);
  if (saving || !un.length) return;
  saving = true;
  const sv = $("#lt-save"); sv.disabled = true;
  const where = S.mode === "github" ? "on GitHub" : "in your folder";
  const done = [], failed = [];
  try {
    for (let k = 0; k < un.length; k++) {
      const u = un[k], api = Lectern.tools[u.name].api;
      sv.textContent = un.length > 1 ? `Saving ${k + 1} of ${un.length}…` : "Saving…";
      const p = u.path.split("/"), what = u.name === "exams" ? `${p[2]} exam` : SAVE_WHAT[u.name];
      const msg = `Update ${p[0]} ${p[1]} ${what}`;
      let r;
      try { r = await api.save(msg); } catch (e) { r = { error: e.message }; }
      if (r.conflict) {
        const yes = await confirmBox("Changed elsewhere", `<code>${esc(u.path)}</code> changed ${where} since you opened it. Replace that version with yours? (Or skip it, and open it again to see the other changes.)`, "Replace it with mine", "Skip it");
        if (yes) { try { r = await api.save(msg, true); } catch (e) { r = { error: e.message }; } }
        else { failed.push({ u, error: "Skipped: it changed " + where + "." }); continue; }
      }
      if (r.ok) done.push(u); else failed.push({ u, error: r.error || "Couldn't save." });
    }
  } finally {
    saving = false; sv.textContent = "Save"; renderBar();
  }
  if (failed.length) modal(`<h2>${done.length ? "Some changes weren't saved" : "Not saved"}</h2>
    ${done.length ? `<p>Saved ${esc(done.map(saveLabel).join(", "))}.</p>` : ""}
    <ul class="lt-fails">${failed.map(f => `<li><b>${esc(saveLabel(f.u))}</b>: ${esc(f.error)}</li>`).join("")}</ul>
    <div class="lt-modal-acts"><button type="button" class="lt-btn primary" data-ok>OK</button></div>`, (m, close) => { m.querySelector("[data-ok]").onclick = close; });
  else if (done.length) toast(`Saved ${done.map(saveLabel).join(", ")}${S.mode === "github" ? " to GitHub" : ""}.`);
  if (done.length) {   // new files: Home and the course offering's page show them
    await listAll().catch(() => null);
    const r = S.route; if (r.page === "tool" && Lectern.tools[r.tool]) toolPath(Lectern.tools[r.tool]);
  }
}
$("#lt-save").onclick = saveAll;
Lectern.saveAll = saveAll;

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

// The account menu: who's signed in, the repositories, sign out (or the folder).
let menuEl = null;
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; $("#lt-acct").setAttribute("aria-expanded", "false"); } }
$("#lt-acct").onclick = e => {
  e.stopPropagation();
  if (menuEl) return closeMenu();
  menuEl = document.createElement("div");
  menuEl.className = "lt-menu"; menuEl.setAttribute("role", "menu");
  menuEl.innerHTML = S.mode === "github"
    ? `<p>Signed in to GitHub as <b>${esc(S.user && S.user.login)}</b>.</p><hr>
       <button type="button" role="menuitem" data-m="repos">Change repository…</button>
       <button type="button" role="menuitem" data-m="out">Sign out</button>`
    : `<p>Working from the folder <b>${esc(S.folder.name)}</b>: <b>${esc(S.folder.pair.pub)}</b>.</p><hr>
       <button type="button" role="menuitem" data-m="folder">Choose another folder…</button>
       <button type="button" role="menuitem" data-m="close">Close the folder</button>`;
  $("#lt-acct").after(menuEl);
  $("#lt-acct").setAttribute("aria-expanded", "true");
  menuEl.onclick = async ev => {
    const m = ev.target.closest("[data-m]"); if (!m) return;
    closeMenu();
    if (m.dataset.m === "repos") setupPage(true);
    if (m.dataset.m === "out") { GH.signOut(); store.set(MODE_KEY, null); location.replace("/"); }
    if (m.dataset.m === "folder") { const h = await FS.choose().catch(() => null); if (h) { store.set("lectern.folder.pair", null); location.hash = "#/"; startLocal(h); } }
    if (m.dataset.m === "close") { await FS.forget(); store.set(MODE_KEY, null); location.replace("/"); }
  };
};
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
const HOME_STEP = { get label() { return S.mode === "github" ? (S.pub ? S.pub.full_name : "Home") : S.folder ? `${S.folder.name}/${S.folder.pair.pub}` : "Home"; }, go: () => go({ page: "home" }) };
const offeringStep = (c, t) => ({ label: `${c} / ${t}`, go: () => go({ page: "offering", c, t }) });

// ── Lectern's own pages ──────────────────────────────────────────────
function pageHTML(html) { $("#lt-page").innerHTML = html; }
function renderPage() {
  renderBar();
  const r = S.route;
  if (r.page === "home") { renderPath([{ label: HOME_STEP.label }]); return homePage(); }
  if (r.page === "offering") { renderPath([HOME_STEP, { label: `${r.c} / ${r.t}` }]); return offeringPage(r.c, r.t); }
}

function sourceBar() {
  if (S.mode === "github") return `<div class="lt-src">${ICON.gh}<div><b><code>${esc(S.pub.full_name)}</code></b>
      <span>Course pages publish to <code>${esc(siteURL())}</code>.</span></div>
      <button type="button" class="lt-btn" id="lt-change">Change</button></div>`;
  return `<div class="lt-src">${ICON.folder}<div><b><code>${esc(S.folder.name)}/${esc(S.folder.pair.pub)}</code></b>
    <span>On this computer. ${S.folder.site ? `Course pages link to <code>${esc(S.folder.site)}</code>.` : "No GitHub remote, so course pages use relative links."} Commit and push with git as usual.</span></div>
    <button type="button" class="lt-btn" id="lt-change">Change</button></div>`;
}
function wireSource() {
  const b = $("#lt-change"); if (!b) return;
  b.onclick = async () => {
    if (S.mode === "github") return setupPage(true);
    const h = await FS.choose().catch(() => null);
    if (h) { store.set("lectern.folder.pair", null); startLocal(h); }
  };
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
    <p class="lt-lede">Each course offering is a course in one term, like <code>csc258/f26</code>. It has a course page for students, its evaluations and a gradebook.</p>
    ${sourceBar()}
    <div class="lt-sec"><h2>Course Offerings</h2>${all && n ? `<div class="lt-filters">${sel("t", "All Terms", terms, t => `${termName(t)} (${t})`)}${sel("c", "All Courses", courses, c => c.toUpperCase())}</div>` : ""}
      <button type="button" class="lt-btn add" id="lt-new"${all ? "" : " disabled"}>${ICON.plus}New Course Offering</button></div>
    <div id="lt-list"></div>
  </div>`);
  wireSource();
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
  const live = o => (o.page ? liveURL(o.c, o.t) : "");
  const cards = offs.slice(0, 3), rest = offs.slice(3);
  list.innerHTML = `<div class="lt-grid">${cards.map((o, k) => `<div class="lt-card go" role="link" tabindex="0" data-k="${k}" aria-label="Open ${esc(o.c)} ${esc(o.t)}">
      <div class="lt-strip"><span>${esc(o.c)}/${esc(o.t)}</span></div>
      <div class="lt-body">
        <div><h3 class="lt-title">${esc(o.c.toUpperCase())}</h3>
        <p class="lt-sub">${esc(termName(o.t))}</p></div>
        <span class="lt-term" aria-hidden="true">${esc(o.t)}</span>
      </div>
      <div class="lt-foot">${live(o) ? `<span>${S.mode === "github" ? "On GitHub Pages" : ""}</span><a href="${esc(live(o))}" target="_blank" rel="noopener" data-chip>Live page ${ICON.out}</a>` : `<span>No course page yet</span>`}</div>
    </div>`).join("")}</div>${rest.length ? `
    <div class="lt-olist">${rest.map((o, j) => `<div class="lt-orow go" role="link" tabindex="0" data-k="${j + 3}" aria-label="Open ${esc(o.c)} ${esc(o.t)}">
      <span class="lt-orow-t">${esc(o.t)}</span><b>${esc(o.c.toUpperCase())}</b><span class="lt-orow-n">${esc(termName(o.t))}</span>
      <span class="lt-orow-r">${live(o) ? `<a href="${esc(live(o))}" target="_blank" rel="noopener" data-chip>Live page ${ICON.out}</a>` : ""}</span>
    </div>`).join("")}</div>` : ""}`;
  list.querySelectorAll("[data-k]").forEach(el => {
    const o = offs[Number(el.dataset.k)];
    const open = e => { if (e.target.closest("[data-chip]")) return; go({ page: "offering", c: o.c, t: o.t }); };
    el.addEventListener("click", open);
    el.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(e); } });
  });
}
function newOfferingDialog() {
  const now = new Date(), y = now.getFullYear() % 100, mo = now.getMonth();
  const season = mo >= 8 ? "f" : mo >= 4 ? "s" : "w";
  modal(`<h2>New Course Offering</h2><p>A course in one term. Its folder, e.g. <code>csc258/f26</code>, is made when you first save its course page, gradebook or an exam.</p>
    <div class="lt-form">
      <label>Course<input type="text" id="no-c" placeholder="csc258" spellcheck="false" autocomplete="off"><small>Lower case, as in the folder name.</small></label>
      <div class="two">
        <label>Term<select id="no-s"><option value="f">Fall</option><option value="w">Winter</option><option value="s">Summer</option></select></label>
        <label>Year<input type="text" id="no-y" value="20${String(y).padStart(2, "0")}" inputmode="numeric" autocomplete="off"></label>
      </div>
    </div>
    <p class="lt-err" id="no-err"></p>
    <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn primary" data-ok>Continue</button></div>`, (m, close) => {
    m.querySelector("#no-s").value = season;
    m.querySelector("[data-no]").onclick = close;
    const ok = () => {
      const c = m.querySelector("#no-c").value.trim().toLowerCase().replace(/\s+/g, "");
      const yy = /^(?:20)?(\d{2})$/.exec(m.querySelector("#no-y").value.trim());
      const err = m.querySelector("#no-err");
      if (!slugOK(c)) { err.textContent = "Enter the course as letters and numbers, e.g. csc258."; return; }
      if (!yy) { err.textContent = "Enter the year, e.g. 2026."; return; }
      close();
      go({ page: "offering", c, t: `${m.querySelector("#no-s").value}${yy[1]}` });
    };
    m.querySelector("[data-ok]").onclick = ok;
    m.querySelectorAll("input").forEach(i => i.addEventListener("keydown", e => { if (e.key === "Enter") ok(); }));
  });
}

function offeringPage(c, t) {
  const o = offering(c, t), loading = !S.offerings && !S.listError;
  // Another term of the same course with a course page: a new page can start from a copy of the newest.
  const others = S.offerings ? [...S.offerings.values()].filter(x => x.c === c && x.t !== t && x.page).sort((a, b) => termOrder(a.t, b.t)) : [];
  const live = o.page ? liveURL(c, t) : "";
  const book = path => ` data-part="${path}"${!o.grades && loading ? " disabled" : ""}`;
  pageHTML(`<div class="lt-in">
    <div class="lt-off-head">
      <div><h1>${esc(c.toUpperCase())}</h1><p class="lt-term-line">${esc(termName(t))}</p></div>
      <div class="lt-off-acts"><button type="button" class="lt-btn" data-part="settings"${!o.grades && loading ? " disabled" : ""} title="The course's settings: student fields, and the rules for course grades (ranges, rounding, automatic fail)">${ICON.gear}Settings</button><button type="button" class="lt-btn lt-trash" id="lt-del-off" title="Delete this course offering…" aria-label="Delete this course offering">${ICON.trash}</button></div>
    </div>
    ${loading ? `<p class="lt-note">Checking what it has…</p>` : ""}
    ${S.listError ? `<p class="lt-note err">Couldn't read your repository. ${esc(S.listError.message)}</p>` : ""}
    <div class="lt-three">
      <section class="lt-part">
        <div class="lt-part-head">${ICON.page}<h2>Course Page</h2></div>
        <p class="lt-part-text">${o.page ? `What students see: the weekly schedule with lectures, files and links, deadlines and announcements.` : `No course page for this term yet.${others.length ? ` Start from <code>${esc(others[0].c)}/${esc(others[0].t)}</code>'s page (without its announcements), or from a blank page.` : ""}`}</p>
        <div class="lt-part-acts">${o.page
          ? `<button type="button" class="lt-btn primary" data-go="course">Open Course Page</button>${live ? `<a class="lt-btn" href="${esc(live)}" target="_blank" rel="noopener">Live page ${ICON.out}</a>` : ""}`
          : `${others.length ? `<button type="button" class="lt-btn primary" data-go="course" data-copy="${esc(others[0].c)}/${esc(others[0].t)}">Copy ${esc(others[0].t)}'s Page</button>` : ""}<button type="button" class="lt-btn${others.length ? "" : " primary"}" data-go="course"${loading ? " disabled" : ""}>Start a Blank Page</button>`}</div>
      </section>
      <section class="lt-part">
        <div class="lt-part-head">${ICON.evals}<h2>Evaluations</h2></div>
        <p class="lt-part-text">${o.grades ? `The assignments, tests and exams: weights, dates, and what happens if one is missed. Build each one's exam or handout from here.` : "No evaluations for this term yet."}</p>
        <div id="lt-loose"></div>
        <div class="lt-part-acts"><button type="button" class="lt-btn primary"${book("evals")}>${o.grades ? "Open Evaluations" : "Add Evaluations"}</button></div>
      </section>
      <section class="lt-part">
        <div class="lt-part-head">${ICON.grades}<h2>Gradebook</h2></div>
        <p class="lt-part-text">${o.grades ? `Enter marks, see every student's grade, and give a student their own policy (an accommodation).` : "No gradebook for this term yet: it starts with the evaluations."}</p>
        <div class="lt-part-acts"><button type="button" class="lt-btn${o.grades ? " primary" : ""}"${book("book")}>${o.grades ? "Open Gradebook" : "Start a Gradebook"}</button></div>
      </section>
    </div>
  </div>`);
  $("#lt-page").querySelectorAll("[data-go]").forEach(b => { b.onclick = () => go({ page: "tool", tool: b.dataset.go, c, t }, b.dataset.copy ? { copyFrom: b.dataset.copy } : null); });
  $("#lt-page").querySelectorAll("[data-part]").forEach(b => { b.onclick = () => go({ page: "tool", tool: "grades", part: b.dataset.part, c, t }); });
  $("#lt-del-off").onclick = () => deleteOfferingDialog(c, t);
  // Exams and handouts that no evaluation builds (made before they were linked): still reachable here.
  if (o.exams.length) docLinks(c, t).then(links => {
    const linked = new Set(Object.values(links).map(d => d.folder)), loose = o.exams.filter(e => !linked.has(e)), el = $("#lt-loose");
    if (!el || !loose.length || S.route.page !== "offering" || S.route.c !== c || S.route.t !== t) return;
    el.innerHTML = `<p class="lt-part-text lt-loose-h">Not linked to an evaluation:</p><ul class="lt-rows">${loose.map(e => `<li><button type="button" class="row" data-exam="${esc(e)}">${ICON.doc}${esc(e)}</button></li>`).join("")}</ul>`;
    el.querySelectorAll("[data-exam]").forEach(b => { b.onclick = () => go({ page: "tool", tool: "exams", c, t, e: b.dataset.exam }); });
  }).catch(() => {});
}
function deleteOfferingDialog(c, t) {
  const o = offering(c, t), name = `${c}/${t}`;
  const open = unsavedTools().filter(u => u.path.startsWith(`${name}/`));
  if (open.length) return confirmBox("Not saved", `<code>${esc(open[0].path)}</code> has changes that aren't saved. Save or discard them before deleting <code>${esc(name)}</code>.`, "OK", "Cancel");
  const what = [o.page && "its course page and files", o.grades && "its gradebook", o.exams.length && `${o.exams.length} exam${o.exams.length === 1 ? "" : "s"}`].filter(Boolean);
  modal(`<h2>Delete ${esc(name)}?</h2>
    <p>This deletes the folder <code>${esc(name)}</code>${what.length ? `: ${esc(what.join(", ").replace(/, ([^,]*)$/, " and $1"))}` : ""}. ${S.mode === "github" ? "It's one commit, so it can still be got back from the repository's history on GitHub." : "It's deleted from the folder on this computer; if you've committed it, git still has it."}</p>
    <div class="lt-form"><label><span>Type <code>${esc(name)}</code> to confirm</span><input type="text" id="del-name" autocomplete="off" spellcheck="false"></label></div>
    <p class="lt-err" id="del-err"></p>
    <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn lt-btn-danger" data-ok disabled>Delete</button></div>`, (m, close) => {
    const inp = m.querySelector("#del-name"), ok = m.querySelector("[data-ok]");
    inp.addEventListener("input", () => { ok.disabled = inp.value.trim() !== name; });
    m.querySelector("[data-no]").onclick = close;
    ok.onclick = async () => {
      ok.disabled = true; ok.textContent = "Deleting…";
      try {
        if (S.mode === "github") {
          const msg = `Delete ${name}`;
          await GH.deleteFolder(S.pub.full_name, S.pub.default_branch, name, msg);
          await GH.deleteFolder(S.priv.full_name, S.priv.default_branch, name, msg);
        } else await FS.removeOffering(S.folder, c, t);
        close();
        toast(`Deleted ${name}.`);
        S.offerings && S.offerings.delete(name);
        listAll();
        go({ page: "home" });
      } catch (e) { ok.disabled = false; ok.textContent = "Delete"; m.querySelector("#del-err").textContent = e.message; }
    };
  });
}

function newExamDialog(c, t) {
  const all = S.offerings ? [...S.offerings.values()].sort((a, b) => termOrder(a.t, b.t) || a.c.localeCompare(b.c)).flatMap(o => o.exams.map(e => `${o.c}/${o.t}/${e}`)) : [];
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

// ── Choosing the repositories (GitHub) ───────────────────────────────
async function setupPage(changing = false) {
  Lectern.show(null);
  document.body.className = "lt-on-app lt-on-page";
  $("#lt-bar").hidden = false; $("#lt-page").hidden = false;
  renderBar();
  renderPath(changing && S.priv && S.pub ? [HOME_STEP, { label: "Change repository" }] : [{ label: "Choose a repository" }]);
  pageHTML(`<div class="lt-in"><h1>Choose your course repository</h1>
    <p class="lt-lede">The repository your course pages publish from with GitHub Pages, e.g. <code>courses-utor</code>. Grades and exams go in its private twin, <code>courses-utor-private</code>.</p>
    <div id="lt-setup"><div class="lt-loading" style="min-height:160px">Finding your repositories…</div></div></div>`);
  let got, cfg = {};
  const load = () => Promise.all([GH.repos(), fetch("/api/github/config").then(r => r.json()).catch(() => ({}))]);
  try { [got, cfg] = await load(); }
  catch (e) { $("#lt-setup").innerHTML = `<p class="lt-note err">${esc(e.message)}</p>`; return; }
  const install = cfg.app_slug ? `https://github.com/apps/${encodeURIComponent(cfg.app_slug)}/installations/new` : "https://github.com/settings/installations";
  const box = $("#lt-setup");
  let repos = got.repos.slice().sort((a, b) => a.full_name.localeCompare(b.full_name));
  const pubs = () => repos.filter(r => !r.private);
  const twinOf = name => `${name}-private`;
  const seen = name => repos.find(r => r.full_name.toLowerCase() === String(name).toLowerCase());
  let pick = S.pub ? S.pub.full_name : (pubs().find(r => seen(twinOf(r.full_name))) || {}).full_name || "";
  let note = "";   // after trying to create the twin: "exists" (it's there, Lectern just can't see it) or an error

  const draw = () => {
    const chosen = seen(pick), twin = chosen ? twinOf(chosen.full_name) : "", twinRepo = twin && seen(twin);
    const short = n => esc(String(n).split("/")[1]);
    box.innerHTML = !repos.length || !pubs().length
      ? `<div class="lt-note" style="margin-top:28px"><b>Lectern can't see your course repository yet.</b> On GitHub, give Lectern access to it (and to its <code>-private</code> twin), then come back here.</div>
         <p style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap"><a class="lt-btn primary" href="${esc(install)}" target="_blank" rel="noopener">${ICON.gh}Give Lectern access on GitHub</a><button type="button" class="lt-btn" data-recheck>Check again</button></p>`
      : `<div class="lt-form lt-pick"><label>Repository
          <select id="lt-repo"><option value="">Choose…</option>${pubs().map(r => `<option value="${esc(r.full_name)}"${r.full_name === pick ? " selected" : ""}>${esc(r.full_name)}</option>`).join("")}</select>
          <small>Not in the list? <a href="${esc(install)}" target="_blank" rel="noopener">Give Lectern access to it on GitHub</a>.</small></label></div>
        ${!chosen || twinRepo ? ""
          : `<div class="lt-twin">
              <p class="lt-twin-h">${ICON.lock}<span>Lectern can't see <code>${short(twin)}</code>, where grades and exams go.</span></p>
              <div class="lt-twin-opts">
                <div class="lt-opt"><b>It already exists</b><span>Give Lectern access to it on GitHub. This page checks again when you come back.</span><a class="lt-btn primary" href="${esc(install)}" target="_blank" rel="noopener">${ICON.gh}Give access</a></div>
                <div class="lt-opt"><b>It doesn't exist yet</b><span>Lectern makes it for you, private.</span><button type="button" class="lt-btn" id="lt-create">Create ${short(twin)}</button></div>
              </div>
              ${note === "exists" ? `<p class="lt-note">${short(twin)} is already on GitHub: Lectern just can't see it. Use <b>Give access</b>, then <button type="button" class="lt-link" data-recheck>check again</button>.</p>` : note ? `<p class="lt-note err">${esc(note)}</p>` : ""}
            </div>`}
        <p class="lt-err" id="lt-setup-err" style="margin-top:12px"></p>
        <p style="margin-top:22px"><button type="button" class="lt-btn primary" id="lt-done"${twinRepo ? "" : " disabled"}>${chosen ? `Use ${short(chosen.full_name)}` : "Continue"}</button></p>`;
    const sel = $("#lt-repo"); if (sel) sel.onchange = () => { pick = sel.value; note = ""; draw(); };
    box.querySelectorAll("[data-recheck]").forEach(b => { b.onclick = () => recheck(true); });
    const create = $("#lt-create");
    if (create) create.onclick = async () => {
      create.disabled = true; create.textContent = "Creating…";
      try {
        const [owner, name] = twin.split("/");
        const repo = await GH.createPrivate(owner, name, S.user.login);
        repos.push(repo); note = "";
        toast(`Made ${repo.full_name}.`);
      } catch (e) {
        note = e.status === 422 ? "exists" : `${e.message}${e.status === 403 || e.status === 404 ? " Lectern needs Administration (read and write) on all your repositories to make one; you can also make it on GitHub (private) and give Lectern access." : ""}`;
      }
      draw();
    };
    const done = $("#lt-done");
    if (done) done.onclick = async () => {
      done.disabled = true;
      try {
        S.pub = await GH.repo(chosen.full_name);
        S.priv = await GH.repo(twin);
        store.set(REPOS_KEY, { priv: S.priv.full_name, pub: S.pub.full_name });
        S.offerings = null; S.listError = null;
        window.removeEventListener("focus", onFocus);
        connectAll(); listAll();
        go({ page: "home" });
      } catch (e) { done.disabled = false; $("#lt-setup-err").innerHTML = `<span class="lt-note err">${esc(e.message)}</span>`; }
    };
  };
  // Back from GitHub (after giving access): look again, without a reload.
  async function recheck(showing) {
    if (showing) box.style.opacity = ".5";
    try { const [g] = await load(); repos = g.repos.slice().sort((a, b) => a.full_name.localeCompare(b.full_name)); note = ""; } catch (_) {}
    box.style.opacity = "";
    if (!pick) pick = (pubs().find(r => seen(twinOf(r.full_name))) || {}).full_name || "";
    draw();
  }
  const onFocus = () => { if (document.body.contains(box)) recheck(false); else window.removeEventListener("focus", onFocus); };
  window.addEventListener("focus", onFocus);
  draw();
}

// ── Cross-links: Grades → the course page, and evaluations ↔ their exams and handouts ──
const num = x => (Number.isFinite(+x) ? +x : 0);
const fmtW = n => String(Math.round(num(n) * 100) / 100);

// A file in the private repository (grades, exams), from GitHub or from the folder.
async function readPriv(path) {
  if (S.mode === "github") return GH.readText(S.priv.full_name, S.priv.default_branch, path);
  try {
    let d = S.folder.priv; const parts = path.split("/"), name = parts.pop();
    for (const p of parts) d = await d.getDirectoryHandle(p);
    return await (await (await d.getFileHandle(name)).getFile()).text();
  } catch (_) { return null; }
}

// The gradebook for an offering: the Grade Builder's copy when it has that one open (so changes not yet
// saved count too), else the file in the private repository.
async function getBook(c, t) {
  const g = Lectern.tools.grades, path = `${c}/${t}/grades.json`;
  if (g && g.api && g.api.state().path === path) return g.api.book();
  if (!offering(c, t).grades) return null;
  const text = await readPriv(path);
  try { return text ? JSON.parse(text) : null; } catch (_) { return null; }
}

// What the course page shows from a gradebook: each evaluation and group with its weight, date and rules.
// Never students or marks: only this goes to the public page.
function schemeOf(b, from) {
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
  const brief = e => ({ id: e.id, name: e.name, short: e.short || "", type: e.type === "test" ? "test" : "assignment", date: e.date || "", time: e.time || "" });
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
  // The course rules (Grades → Settings), worded for students. Automatic fail shows by default;
  // rounding and grade ranges don't (the course page chooses).
  const P = b.policies || {}, policies = [], pc = x => `${fmtW(x)}%`;
  const target = t => t.startsWith("g:") ? ((groups.find(g => g.id === t.slice(2)) || {}).name ? `your average on ${groups.find(g => g.id === t.slice(2)).name}` : "") : ((b.evals || []).find(e => e.id === t) || {}).name ? `your mark on ${(b.evals || []).find(e => e.id === t).name}` : "";
  const CODE = { IPR: "IPR (in progress)", SDF: "SDF (standing deferred)", INC: "INC (incomplete)", NGA: "NGA (no grade available)", GWR: "GWR (grade withheld pending review)", AII: "AII (academic integrity issue)", WDR: "WDR (withdrawn)" };
  (P.autofail || []).forEach(a => {
    const ev = a.target && !a.target.startsWith("g:") ? (b.evals || []).find(e => e.id === a.target) : null;
    const w = a.when === "missed" || a.when === "deferred" ? (ev ? `you don't submit ${ev.name}` : "") : a.target && target(a.target);
    if (!w) return;
    const cond = a.when === "missed" ? `If ${w}` : a.when === "deferred" ? `If ${ev.name} is deferred for you` : `If ${w} is below ${pc(a.below)}`;
    const res = a.effect === "code" ? `your course grade is ${CODE[a.code] || a.code}` : `your course grade is ${a.effect === "set" ? "set to" : "at most"} ${pc(a.value)}`;
    policies.push({ id: `fail:${a.id}`, kind: "autofail", title: a.effect === "code" || (a.when || "below") !== "below" ? "Course Grade Rules" : "Automatic Fail", show: true, text: `${cond}, ${res}.` });
  });
  const R = P.round || {};
  if (num(R.step) > 0) policies.push({ id: "round", kind: "round", title: "Rounding", show: false, text: R.dir === "up" ? `Course grades are rounded up to ${num(R.step) === 1 ? "a whole percent" : `a multiple of ${pc(R.step)}`}.` : R.dir === "down" ? `Course grades are rounded down to ${num(R.step) === 1 ? "a whole percent" : `a multiple of ${pc(R.step)}`}.` : `Course grades are rounded to the nearest ${num(R.step) === 1 ? "whole percent" : pc(R.step)}.` });
  (P.buckets || []).forEach(x => policies.push({ id: `range:${x.id}`, kind: "range", title: "Grade Adjustments", show: false, text: `A course grade from ${pc(x.from)} to ${pc(x.to)} becomes ${pc(x.value)}.` }));
  // Every evaluation by its date for the course page, makeups too (each says what it's a makeup for).
  return { from, units, evals: (b.evals || []).map(e => ({ ...brief(e), ...(e.makeupFor ? { makeupFor: e.makeupFor } : {}) })), policies };
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
      t.api.setScheme(b ? schemeOf(b, `${r.c}/${r.t}/grades.json`) : null, { edit: v => go({ page: "tool", tool: "grades", part: v === "settings" ? "settings" : "evals", c: r.c, t: r.t }) });
    }
    if (tool === "grades") t.api.setLinks(await docLinks(r.c, r.t));
  } catch (e) { console.warn("[Lectern] cross-link:", e); }
}

// ── The builders ─────────────────────────────────────────────────────
const localRepo = () => `local/${S.folder.pair.priv}`;
function connection(tool) {
  if (S.mode === "local" && tool === "course") return { mode: "local", dir: S.folder.pub, site: S.folder.site };
  if (S.mode === "local") return { mode: "github", repo: localRepo(), branch: "main", token: "folder" };
  const r = TOOLS[tool].repo === "pub" ? S.pub : S.priv;
  return { mode: "github", repo: r.full_name, branch: r.default_branch, token: GH.token() };
}
function connectAll() {
  Object.entries(Lectern.tools).forEach(([name, t]) => {
    if (!t.api) return;
    try { t.api.connect(connection(name)); } catch (e) { console.error(e); }
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
  if (!(t && t.api.state().path === target)) {
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
      t.api.connect(connection(tool));
      const st = t.api.state();
      if (st.path !== target && st.unsaved && st.path) {
        const discard = await confirmBox("Not saved", `<code>${esc(st.path)}</code> has changes that aren't saved yet. Open <code>${esc(target)}</code> instead and lose them?`, "Discard and open", "Keep editing it");
        if (my !== seq) return;
        if (!discard) return go(routeForPath(tool, st.path));
      }
      const o = offering(r.c, r.t);
      const has = tool === "course" ? o.page : tool === "grades" ? o.grades : o.exams.includes(r.e);
      await t.api.open(folder, has, opts && opts.copyFrom, opts && opts.title, opts || {});
      const where = S.mode === "github" ? "on GitHub" : "in your folder";
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
  else if (t.api.where && !(history.state || {}).lt) history.replaceState({ ...(history.state || {}), lt: t.api.where() }, "");
  toolPath(t);
  window.scrollTo(0, scrolls[routeKey(S.route)] || 0);
}

// ── Start ────────────────────────────────────────────────────────────
$("title").dataset.splash = document.title;
(async () => {
  const back = GH.consumeRedirect();
  if (back && back.error) return showSplash(back.error, true);
  if (GH.hasToken()) return startGitHub();
  if (store.get(MODE_KEY) === "local" && FS.supported) {
    const f = await FS.remembered();
    if (f && f.granted) return startLocal(f.handle);
    if (f) return showSplash("", false, f.handle);
  }
  showSplash();
})();
