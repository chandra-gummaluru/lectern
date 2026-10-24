/* The course hub: an offering's course page in tabs (/c/<handle>/<course>/<term>/).

   One call to the hub's API (server/hub.py) brings back the course, who's looking, every tab (and
   whether this viewer may open it) and the content of the tabs they may open. The rest is drawing:
   the address's #part says which tab (#week, #lectures…; #week/4 is a particular week).

   Each tab is drawn by hub-view.js, which the Course Page Builder uses too. This week is put together
   there from the other tabs this viewer can see. */
(() => {
"use strict";

const root = document.getElementById("hb");
const $ = id => document.getElementById(id);
let D = null;

const { esc, LOCK } = window.HubView;
const tab = id => D.tabs.find(t => t.id === id);

function lockedHTML(t) {
  return `<div class="hb-locked">${LOCK}<h2>${esc(t.title)}</h2><p>${t.id === "accommodations" ? "Sign in to ask for accommodations and follow your requests." : "This part of the course page is for people in the course. Sign in to see it."}</p>
    <a class="hb-btn primary" href="${esc(D.signIn || D.lectern)}">Sign in</a></div>`;
}

// ── The page ─────────────────────────────────────────────────────────
function route() {
  const [id, arg] = decodeURIComponent(location.hash.slice(1)).split("/");
  const t = tab(id) || (tab("week").open ? tab("week") : D.tabs.find(x => x.open) || D.tabs[0]);
  return { t, arg };
}

function draw() {
  const { t, arg } = route();
  $("hb-tabs").innerHTML = `<div class="hb-tabs-in" role="tablist">${D.tabs.map(x => `<a class="hb-tab" role="tab" href="#${x.id}" aria-selected="${x === t}"${x.open ? "" : ' title="Sign in to see this"'}>${esc(x.title)}${!x.open || x.mark ? LOCK : ""}</a>`).join("")}</div>`;
  const sel = $("hb-tabs").querySelector('[aria-selected="true"]');
  if (sel) sel.scrollIntoView({ block: "nearest", inline: "nearest" });
  const m = $("hb-main");
  try { m.innerHTML = t.open ? HubView.draw(D, t.id, arg) : lockedHTML(t); }
  catch (e) { console.error(e); m.innerHTML = `<p class="hb-empty">Something went wrong showing this part of the page.</p>`; }
  const nowWk = t.id === "lectures" && m.querySelector(".hb-week.now");
  if (nowWk && !arg) requestAnimationFrame(() => scrollTo({ top: nowWk.getBoundingClientRect().top + scrollY - $("hb-tabs").offsetHeight - 16 }));
  document.title = `${t.title} · ${D.course.code || D.course.title}`;
}

function header() {
  const c = D.course, v = D.viewer;
  $("hb-sub").textContent = [c.term, c.school].filter(Boolean).join(" · ");
  $("hb-title").textContent = [c.code, c.title].filter(Boolean).join(": ") || "Course page";
  $("hb-title").title = $("hb-title").textContent;
  const ROLE = { owner: "Instructor", instructor: "Instructor", ta: "TA", student: "Student" };
  // Students sign in to this course page (its own sign-in: email and a code); the teaching team is signed in to Lectern.
  $("hb-who").innerHTML = v.signedIn
    ? `Signed in as <b>${esc(v.name)}</b>${v.role ? `<span class="hb-role">${esc(ROLE[v.role] || v.role)}</span>` : ""}${v.role === "student" ? ` <button type="button" class="hb-si-out" id="hb-out">Sign out</button>` : ""}`
    : `<a class="hb-btn" href="${esc(D.signIn || D.lectern)}">Sign in</a>`;
  const out = $("hb-out");
  if (out) out.onclick = async () => { out.disabled = true; await fetch(`${root.dataset.api}/sign-out`, { method: "POST", credentials: "same-origin", headers: { "X-Lectern": "1" } }).catch(() => {}); location.reload(); };
  const bar = $("hb-staff");
  if (v.staff) {
    const base = location.pathname;
    bar.innerHTML = `<div class="hb-staff-in">${v.preview
      ? `<span class="grow">You're seeing this page as a visitor who isn't signed in.</span><a href="${esc(base + location.hash)}">Back to your view</a>`
      : `<span class="grow">You're on the teaching team. Tabs marked ${LOCK.replace("<svg", '<svg style="width:12px;height:12px;vertical-align:-1px"')} are hidden from visitors who aren't signed in.</span><a href="${esc(base + "?as=public" + location.hash)}">See it as a visitor</a><a href="${esc(D.lectern)}">Edit in Lectern</a>`}</div>`;
    bar.hidden = false;
  }
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
  // For staff, a signed-in-only tab is open but still marked.
  D.tabs.forEach(t => { t.mark = D.viewer.staff && t.visibility === "signed-in"; });
  header();
  draw();
  addEventListener("hashchange", () => { scrollTo({ top: 0 }); draw(); });
}
load();
})();
