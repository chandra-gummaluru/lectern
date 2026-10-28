/* Discussions in Lectern: the teaching team takes part here (on the course page they only look). It's the
   course page's own discussion (discuss.js), drawn with the course page's own styles (/css/hub-in-lectern.css:
   hub.css scoped to .hb), so it looks exactly as students see it.

     #/<course>/<term>/discussions                      every post in the offering: unanswered first, by item, searchable
     #/<course>/<term>/discussions/<target>/<post id>   one post, with its comments: reply, endorse, pin, remove

   Each evaluation, activity and announcement in Lectern also has its own discussion under it (mountDiscussion). */

let cssOn = false;
export function css() {
  if (cssOn) return; cssOn = true;
  const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "/css/hub-in-lectern.css"; document.head.appendChild(l);
}
const KIND = { eval: "Evaluation", act: "Activity", ann: "Announcement" };
const CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/></svg>';
const ago = s => { const d = (Date.now() / 1000 - s); return d < 60 ? "just now" : d < 3600 ? `${Math.floor(d / 60)} min ago` : d < 86400 ? `${Math.floor(d / 3600)} h ago` : d < 86400 * 30 ? `${Math.floor(d / 86400)} d ago` : new Date(s * 1000).toLocaleDateString("en-CA", { month: "short", day: "numeric" }); };
const plain = t => String(t || "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/@\{[pus]:[^}]*\}/g, "@someone").replace(/\*\*|[*`~=]/g, "").replace(/\s+/g, " ").trim();

// The course page's discussion of one thing (target: eval:<id>, act:<id>, ann:<id>), in host.
export function mountDiscussion(host, { handle, c, t, target, post = null, link, onPost = null }) {
  css();
  host.classList.add("hb", "lt-dc");
  host.innerHTML = `<section class="dc"></section>`;
  return import("/static/js/discuss.js").then(x => x.mount(host.firstElementChild, { api: `/api/hub/${encodeURIComponent(handle)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`,
    target, post, onPost, link, app: true, signIn: "/" }));
}

export function discussionsPage({ $, esc, pageHTML, go, api, renderPath, steps, handle, c, t, r, here, hashOf }) {
  css();
  const A = `/api/hub/${encodeURIComponent(handle)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`;
  const link = (tg, id) => hashOf({ page: "discuss", c, t, tg, id: String(id) });
  if (r.tg && r.id) {   // one post: as on the course page
    renderPath([...steps, { label: "Discussions", go: () => go({ page: "discuss", c, t }) }, { label: "Post" }]);
    pageHTML(`<div class="lt-in lt-dc-page"><div class="hb lt-dc"><article class="ec-card dc-page" id="dc-host"></article></div></div>`);
    const host = $("#dc-host");
    import("/static/js/discuss.js").then(x => x.mount(host, { api: A, target: r.tg, post: +r.id, link, app: true, signIn: "/",
      onPost: p => { if (here()) renderPath([...steps, { label: "Discussions", go: () => go({ page: "discuss", c, t }) }, { label: p ? p.title || "Post" : "Post" }]); } }));
    return;
  }
  renderPath([...steps, { label: "Discussions" }]);
  const S = discussionsPage.S = discussionsPage.S && discussionsPage.S.key === `${handle}/${c}/${t}` ? discussionsPage.S : { key: `${handle}/${c}/${t}`, show: "open", item: "", q: "" };
  pageHTML(`<div class="lt-in lt-dc-page"><div class="lx"><div class="lx-head"><h1>Discussions</h1></div>
    <p class="lx-help">Students' posts on the course page, from every evaluation, activity and announcement. You answer them here: students see your replies on the course page.</p></div>
    <div class="hb lt-dc" id="dc-all"><p class="dc-none">Reading the discussions…</p></div></div>`);
  let D = null;
  const box = () => $("#dc-all");
  const nameOf = tg => { const n = (D.names || {})[tg]; return n ? `${n.name}${n.title && n.kind === "eval" && n.title !== n.name ? ` / ${n.title}` : ""}` : KIND[tg.split(":")[0]] || "Discussion"; };
  function draw() {
    const b = box(); if (!b) return;
    const live = D.posts.filter(p => !p.deleted && !p.removed);
    const open = live.filter(p => !p.answered);
    const items = [...new Set(D.posts.map(p => p.target))].sort((x, y) => nameOf(x).localeCompare(nameOf(y)));
    const qs = S.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const L = (S.show === "open" ? open : S.show === "all" ? D.posts : D.posts.filter(p => p.removed || p.deleted))
      .filter(p => !S.item || p.target === S.item)
      .filter(p => { const w = `${p.title} ${plain(p.body)} ${p.who && p.who.name} ${p.who && p.who.real || ""} ${nameOf(p.target)}`.toLowerCase(); return qs.every(x => w.includes(x)); })
      .sort((x, y) => (S.show === "open" ? x.at - y.at : y.last - x.last));
    b.innerHTML = `<section class="dc"><div class="dc-head"><h2 class="ec-sec dc-title">${S.show === "open" ? "Unanswered" : S.show === "all" ? "All posts" : "Removed"} <span>· ${L.length} post${L.length === 1 ? "" : "s"}</span></h2>
        <div class="dc-tools"><label class="dc-search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/></svg><input type="search" placeholder="Search posts" aria-label="Search posts" value="${esc(S.q)}"></label>
          <select class="lt-dc-item" aria-label="Which item"><option value="">Everything</option>${items.map(tg => `<option value="${esc(tg)}"${S.item === tg ? " selected" : ""}>${esc(`${KIND[tg.split(":")[0]]}: ${nameOf(tg)}`)}</option>`).join("")}</select>
          <div class="dc-sort" role="tablist"><button data-show="open" aria-pressed="${S.show === "open"}">Unanswered${open.length ? ` ${open.length}` : ""}</button><button data-show="all" aria-pressed="${S.show === "all"}">All</button></div></div></div>
      <div class="dc-threads">${L.map(p => { const w = p.who;
        return `<div class="dc-t${w && w.team ? " dc-team" : ""}${p.removed || p.deleted ? " gone" : ""}">
          <span class="dc-vote dc-up dc-ro"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V6M6 11l6-6 6 6"/></svg><b>${p.votes}</b></span>
          <button class="dc-t-b" data-open="${esc(p.target)}|${p.id}">
            <span class="dc-t-flags"><span class="lt-dc-where">${CHAT}Discussion Post</span>${p.answered ? "" : `<span class="lt-dc-open">Unanswered</span>`}${p.removed ? `<span class="dc-flag">Removed</span>` : ""}${p.deleted ? `<span class="dc-flag">Deleted by its author</span>` : ""}</span>
            <b class="dc-t-title">${esc(p.title || "(untitled)")}<span class="lt-dc-of"> / ${esc(nameOf(p.target))}</span></b>
            <span class="dc-t-meta">${w ? `${w.team ? `<span class="dc-staffname">${esc(w.name)}</span>` : esc(w.name)}${w.real ? ` <i class="dc-real">${esc(w.real)}</i>` : ""} · ` : ""}${ago(p.at)} · ${p.comments} comment${p.comments === 1 ? "" : "s"}</span>
            ${p.body ? `<span class="dc-t-clip">${esc(plain(p.body))}</span>` : ""}
          </button></div>`; }).join("") || `<p class="dc-none">${S.show === "open" ? (D.posts.length ? "Nothing unanswered: every post has a reply from the teaching team." : "No posts yet.") : qs.length || S.item ? "No posts match." : "No posts yet."}</p>`}</div></section>`;
    const inp = b.querySelector(".dc-search input");
    inp.oninput = () => { S.q = inp.value; const at = inp.selectionStart; draw(); const i = box().querySelector(".dc-search input"); i.focus(); i.setSelectionRange(at, at); };
    b.querySelector(".lt-dc-item").onchange = e => { S.item = e.target.value; draw(); };
    b.querySelectorAll("[data-show]").forEach(x => { x.onclick = () => { S.show = x.dataset.show; draw(); }; });
    b.querySelectorAll("[data-open]").forEach(x => { x.onclick = () => { const [tg, id] = x.dataset.open.split("|"); go({ page: "discuss", c, t, tg, id }); }; });
  }
  api(`${A}/discussion/all`).then(d => { if (!here()) return; D = d; draw(); }, e => { const b = box(); if (b) b.innerHTML = `<p class="dc-none">${esc(e.message)}</p>`; });
}

// How many posts nobody on the teaching team has answered yet (the offering card's badge).
export const unanswered = (api, handle, c, t) => api(`/api/hub/${encodeURIComponent(handle)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}/discussion/all`)
  .then(d => d.posts.filter(p => !p.answered && !p.removed && !p.deleted).length);
