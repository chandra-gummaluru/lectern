/* A discussion on the course page (server/discuss.py): the posts on an evaluation, an activity or an
   announcement, each a title and a body, opened to see its comments (nested, as on Reddit). Upvotes, no
   downvotes. A student posts by name or anonymous to classmates (their course alias); the teaching team's
   posts are highlighted, and they can pin, endorse and remove. @ mentions anyone in the course: the
   teaching team by name, students as each viewer sees them.

     mount(host, { api, target, signIn })      api: the hub's /api/hub/<handle>/<course>/<term>
*/
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const svg = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const I = {
  up: svg('<path d="M12 4 4.5 12.5H9V20h6v-7.5h4.5z"/>'),
  reply: svg('<path d="M9 7 4 12l5 5"/><path d="M4 12h10a6 6 0 0 1 6 6v1"/>'),
  pin: svg('<path d="M9 3h6l-1 6 3 3v2H7v-2l3-3z"/><path d="M12 14v7"/>'),
  ok: svg('<circle cx="12" cy="12" r="8.5"/><path d="m8.2 12.3 2.6 2.6 5-5.2"/>'),
  hide: svg('<path d="M3 3l18 18"/><path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c5 0 8.5 4.5 9.5 6-.4.6-1.2 1.7-2.4 2.8M6.3 7.6C4.3 9 3 11 2.5 12c1 1.5 4.5 6 9.5 6 1.4 0 2.7-.4 3.8-.9"/>'),
  mask: svg('<path d="M3 9c3-2 15-2 18 0 0 5-3 8-6 8-1.6 0-2.2-1.5-3-1.5S10.6 17 9 17c-3 0-6-3-6-8z"/><circle cx="8.5" cy="11" r="1.2"/><circle cx="15.5" cy="11" r="1.2"/>'),
  user: svg('<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>'),
  back: svg('<path d="m15 6-6 6 6 6"/>'),
  search: svg('<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>'),
  plus: svg('<path d="M12 5v14M5 12h14"/>'),
  trash: svg('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>'),
};
const ini = n => String(n || "?").split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join("").toUpperCase();
const ago = t => { const m = Math.round((Date.now() / 1000 - t) / 60); return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : m < 10080 ? `${Math.round(m / 1440)} d ago` : new Date(t * 1000).toLocaleDateString("en-CA", { month: "short", day: "numeric" }); };
const TOKEN = /@\{([pus]):([\w.@+-]{1,120})\}/g;

export function mount(host, { api, target, signIn }) {
  const S = { data: null, open: null, writing: false, replyTo: null, sort: "top", anon: false, folded: new Set(), err: "", q: "" };
  const call = (path, body) => fetch(`${api}/discussion${path}`, body ? { method: "POST", credentials: "same-origin", headers: { "X-Lectern": "1", "Content-Type": "application/json" }, body: JSON.stringify(body) } : { credentials: "same-origin" })
    .then(r => r.json().catch(() => ({})).then(d => { if (!r.ok) { const e = new Error(d.error || "Something went wrong. Try again in a moment."); e.status = r.status; throw e; } return d; }));
  const load = () => call(`?t=${encodeURIComponent(target)}`).then(d => { S.data = d; draw(); }, e => {
    host.innerHTML = head(0) + (e.status === 401 ? `<div class="dc-none">For people in the course. <a class="hb-btn" href="${esc(signIn)}">Sign in</a> to see the discussion and join it.</div>` : `<p class="dc-none">${esc(e.message)}</p>`);
  });
  const staff = () => S.data && S.data.me.kind === "staff";
  const posts = () => S.data.posts;
  const kids = id => posts().filter(p => p.parent === id);
  const tops = () => posts().filter(p => p.parent == null && (staff() || !(p.removed || p.deleted)));
  const words = p => [p.title, plain(p.body), p.who && p.who.name, ...kids(p.id).map(words)].join(" ").toLowerCase();
  const found = L => { const q = S.q.trim().toLowerCase().split(/\s+/).filter(Boolean); return q.length ? L.filter(p => { const w = words(p); return q.every(x => w.includes(x)); }) : L; };
  const count = id => kids(id).reduce((n, k) => n + 1 + count(k.id), 0);
  const sorted = L => L.slice().sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || (S.sort === "top" ? (b.votes + (b.endorsed ? 3 : 0)) - (a.votes + (a.endorsed ? 3 : 0)) || a.at - b.at : b.at - a.at));
  const nameOf = tok => (S.data.names || {})[tok];
  const body = t => esc(t).replace(TOKEN, (m, k, v) => { const n = nameOf(`${k}:${v}`); return n ? `<span class="at"${n.real ? ` title="${esc(n.name)} to classmates"` : ""}>@${esc(n.real || n.name)}</span>` : "@someone"; });
  const plain = t => String(t || "").replace(TOKEN, (m, k, v) => { const n = nameOf(`${k}:${v}`); return n ? `@${n.name}` : "@someone"; });
  const av = (w, cls = "") => `<span class="dc-av${cls}${w && w.anon ? " anon" : ""}${w && w.team ? " staff" : ""}">${!w ? "–" : w.anon ? I.mask : esc(ini(w.name))}</span>`;
  const whoHTML = w => `<b>${esc(w.name)}</b>${w.real ? `<span class="dc-real">${esc(w.real)}</span>` : ""}${w.you ? `<span class="dc-badge you">You</span>` : ""}`;
  const flags = (p, long) => `${p.pinned ? `<span class="dc-flag pin">${I.pin}Pinned</span>` : ""}${p.endorsed ? `<span class="dc-flag ok">${I.ok}${long ? `Endorsed by ${esc(p.endorsed.split(" ")[0])}` : "Endorsed"}</span>` : ""}${p.removed ? `<span class="dc-flag">${I.hide}${long && staff() ? "Removed: only the teaching team sees it" : "Removed"}</span>` : ""}${p.deleted ? `<span class="dc-flag">${I.trash}Deleted by its author</span>` : ""}`;

  function head(n) {
    const tools = S.data && !S.open ? `<div class="dc-tools"><label class="dc-search">${I.search}<input type="search" placeholder="Search posts" aria-label="Search posts" value="${esc(S.q)}"></label><div class="dc-sort" role="tablist"><button data-sort="top" aria-pressed="${S.sort === "top"}">Top</button><button data-sort="new" aria-pressed="${S.sort === "new"}">New</button></div>${S.writing ? "" : `<button class="hb-btn primary dc-new" data-new>${I.plus}New Post</button>`}</div>` : "";
    return `<div class="dc-head"><h2 class="ec-sec dc-title">Discussion${S.data ? ` <span>· ${n} post${n === 1 ? "" : "s"}</span>` : ""}</h2>${tools}</div>`;
  }
  function composer(kind) {   // "post" (a title and a body), "comment" (on the opened post), "reply" (to a comment)
    const me = S.data.me;
    const as = me.kind === "student" ? `<div class="dc-as" role="group" aria-label="Post as"><button data-as-anon="0" aria-pressed="${!S.anon}">${I.user}${esc(me.name)}</button><button data-as-anon="1" aria-pressed="${S.anon}" title="Classmates see you as ${esc(me.alias)}; the teaching team sees your name">${I.mask}Anonymous to Classmates</button></div><span class="dc-sp"></span>` : `<span class="dc-hint">You post as ${esc(me.name)}: the teaching team's posts are highlighted. Type @ to mention someone.</span>`;
    const ph = { post: "Say more: what you've tried, where you're stuck… (@ to mention)", comment: "Add a comment… (@ to mention)", reply: "Write a reply… (@ to mention)" }[kind];
    return `<div class="dc-box${kind === "reply" ? " sm" : ""}" data-kind="${kind}">${kind === "post" ? `<input type="text" class="dc-title-in" placeholder="Title, e.g. Question 3: a truth table, or just the expression?" maxlength="200" aria-label="Title">` : ""}<textarea placeholder="${ph}" aria-label="${kind === "post" ? "Your post" : "Your comment"}"></textarea>
      <div class="dc-box-foot">${as}${kind !== "comment" ? `<button class="hb-btn dc-post-btn" data-cancel>Cancel</button>` : ""}<button class="hb-btn primary dc-post-btn" data-send="${kind === "reply" ? S.replyTo : kind === "comment" ? S.open : ""}">${{ post: "Post", comment: "Comment", reply: "Reply" }[kind]}</button></div>
      ${S.err ? `<p class="dc-err" role="alert">${esc(S.err)}</p>` : ""}</div>`;
  }
  function rowHTML(p) {
    const n = count(p.id), w = p.who;
    return `<div class="dc-t${w && w.team ? " dc-team" : ""}${p.removed || p.deleted ? " gone" : ""}">
      <button class="dc-vote dc-up" data-up="${p.id}" aria-pressed="${p.voted}" title="Upvote">${I.up}<b>${p.votes}</b></button>
      <button class="dc-t-b" data-open="${p.id}">
        <span class="dc-t-flags">${flags(p)}</span>
        <b class="dc-t-title">${esc(p.title || "(removed)")}</b>
        <span class="dc-t-meta">${w ? `${av(w, " xs")}${esc(w.name)}${w.real ? ` <i class="dc-real">${esc(w.real)}</i>` : ""} · ` : ""}${ago(p.at)} · ${n} comment${n === 1 ? "" : "s"}</span>
        ${p.body ? `<span class="dc-t-clip">${esc(plain(p.body))}</span>` : ""}
      </button></div>`;
  }
  function acts(p, top) {
    const mine = p.who && p.who.you && !p.deleted;
    return `<div class="dc-acts"><button class="dc-up" data-up="${p.id}" aria-pressed="${p.voted}" title="Upvote">${I.up}${p.votes || ""}</button>
      ${top ? `<span class="dc-ncom">${count(p.id)} comment${count(p.id) === 1 ? "" : "s"}</span>` : `<button data-reply="${p.id}">${I.reply}Reply</button>`}
      <span class="dc-staffacts">${mine ? `<button data-del="${p.id}">${I.trash}Delete</button>` : ""}${staff() ? `${top ? `<button data-mod="pin" data-v="${p.id}" data-on="${!p.pinned}">${I.pin}${p.pinned ? "Unpin" : "Pin"}</button>` : ""}<button data-mod="endorse" data-v="${p.id}" data-on="${!p.endorsed}">${I.ok}${p.endorsed ? "Unendorse" : "Endorse"}</button><button data-mod="remove" data-v="${p.id}" data-on="${!p.removed}">${I.hide}${p.removed ? "Restore" : "Remove"}</button>` : ""}</span></div>`;
  }
  function commentHTML(p) {
    const w = p.who, K = sorted(kids(p.id)), open = !S.folded.has(p.id), n = count(p.id);
    const gone = !w;   // removed or deleted (students see only its place in the thread)
    return `<div class="dc-p${p.removed || p.deleted ? " gone" : ""}">
      <div class="dc-row${w && w.team ? " dc-team" : ""}"${w && w.team ? ` title="${esc(w.role || "")}"` : ""}>${av(w)}
        <div class="dc-b">${gone ? `<p class="dc-removed">${p.deleted ? "Deleted by its author." : "Removed by the teaching team."}</p>` : `
          <div class="dc-who">${whoHTML(w)}<span>${ago(p.at)}</span>${flags(p, true)}</div>
          <p class="dc-text">${body(p.body)}</p>${acts(p, false)}`}
          ${S.replyTo === p.id ? composer("reply") : ""}</div></div>
      ${K.length ? (open ? `<div class="dc-kids"><button class="dc-line" data-fold="${p.id}" title="Hide the replies" aria-label="Hide the replies"></button>${K.map(commentHTML).join("")}</div>` : `<button class="dc-more" data-fold="${p.id}">Show ${n} repl${n === 1 ? "y" : "ies"}</button>`) : ""}
    </div>`;
  }
  function threadHTML(p) {
    const w = p.who;
    return `<div class="dc-backrow"><button class="hb-btn dc-back" data-back>${I.back}All posts</button></div>
      <div class="dc-op${w && w.team ? " dc-team" : ""}${p.removed || p.deleted ? " gone" : ""}">
        ${w ? `<div class="dc-who">${av(w)}${whoHTML(w)}<span>${ago(p.at)}</span>${flags(p, true)}</div>
        <h3 class="dc-op-title">${esc(p.title)}</h3><p class="dc-text">${body(p.body)}</p>${acts(p, true)}` : `<p class="dc-removed">${p.deleted ? "Deleted by its author." : "Removed by the teaching team."}</p>`}
      </div>
      ${composer("comment")}
      <div class="dc-comments">${sorted(kids(p.id)).map(commentHTML).join("") || `<p class="dc-none">No comments yet.</p>`}</div>`;
  }
  function draw() {
    const L = tops(), p = S.open && posts().find(x => x.id === S.open);
    if (S.open && !p) S.open = null;
    const F = found(L);
    host.innerHTML = `${head(L.length)}${!p && S.writing ? composer("post") : ""}${p ? threadHTML(p) : `<div class="dc-threads">${sorted(F).map(rowHTML).join("") || `<p class="dc-none">${L.length ? "No posts match your search." : "No posts yet. Ask the first question."}</p>`}</div>`}`;
    const f = host.querySelector(".dc-box.sm textarea") || (S.writing && !p && host.querySelector(".dc-title-in")); if (f) f.focus();
  }
  const update = d => { S.data = d; S.err = ""; draw(); };

  // @: who can be mentioned, as this viewer sees them: everyone who's posted here (as they posted), and the
  // teaching team (and, for the teaching team, every student by name).
  function mentionable() {
    const seen = new Map();
    posts().forEach(p => { if (!p.who || p.who.you) return; const k = p.who.real ? `${p.who.real}|${p.who.anon}` : `${p.who.name}|${p.who.anon}`; if (!seen.has(k)) seen.set(k, { tok: `p:${p.id}`, label: p.who.real || p.who.name, sub: p.who.real ? `${p.who.name} here` : p.who.team ? p.who.role : "", anon: p.who.anon }); });
    const labels = new Set([...seen.values()].map(x => x.label));   // someone who's posted here: as they posted (not twice)
    (S.data.people || []).forEach(x => { if (x.name === S.data.me.name || labels.has(x.name)) return; labels.add(x.name); seen.set(`${x.tok}`, { tok: x.tok, label: x.name, sub: x.role || "", anon: false }); });
    return [...seen.values()];
  }
  let pop = null;
  const closePop = () => { if (pop) { pop.remove(); pop = null; } };
  function atPopup(ta) {
    closePop();
    const m = /(^|\s)@([^\s@]*)$/.exec(ta.value.slice(0, ta.selectionStart));
    if (!m) return;
    const q = m[2].toLowerCase(), L = mentionable().filter(x => `${x.label} ${x.sub}`.toLowerCase().includes(q)).slice(0, 6);
    if (!L.length) return;
    pop = document.createElement("div"); pop.className = "dc-at-pop";
    pop.innerHTML = L.map((x, i) => `<button type="button" data-i="${i}"${i === 0 ? ' class="on"' : ""}><span class="dc-av${x.anon ? " anon" : ""}">${x.anon ? I.mask : esc(ini(x.label))}</span>${esc(x.label)}${x.sub ? `<small>${esc(x.sub)}</small>` : ""}</button>`).join("");
    const box = host.closest(".hb") || document.body, r = ta.getBoundingClientRect(), h = box.getBoundingClientRect();
    pop.style.left = `${r.left - h.left + 10}px`; pop.style.top = `${r.bottom - h.top - 6}px`;
    box.append(pop);
    const pick = x => { const at = ta.selectionStart, before = ta.value.slice(0, at - m[2].length - 1); ta._m = [...(ta._m || []), x]; ta.value = `${before}@${x.label} ${ta.value.slice(at)}`; closePop(); ta.focus(); };
    pop.onmousedown = e => { const b = e.target.closest("[data-i]"); if (b) { e.preventDefault(); pick(L[+b.dataset.i]); } };
    ta._pick = () => pick(L[0]);
  }
  // What's written → what's sent: each @name picked becomes its mention token.
  const tokens = ta => (ta._m || []).reduce((t, x) => t.split(`@${x.label}`).join(`@{${x.tok}}`), ta.value.trim());

  host.addEventListener("input", e => {
    if (e.target.matches(".dc-search input")) { S.q = e.target.value; const at = e.target.selectionStart; draw(); const i = host.querySelector(".dc-search input"); if (i) { i.focus(); i.setSelectionRange(at, at); } return; } if (e.target.matches(".dc-box textarea")) { atPopup(e.target); e.target.style.height = "auto"; e.target.style.height = `${e.target.scrollHeight}px`; } });
  host.addEventListener("keydown", e => {
    if (pop && e.target._pick && (e.key === "Enter" || e.key === "Tab")) { e.preventDefault(); e.target._pick(); }
    else if (pop && e.key === "Escape") closePop();
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && e.target.matches(".dc-box textarea")) { const b = e.target.closest(".dc-box").querySelector("[data-send]"); if (b) b.click(); }
  });
  host.addEventListener("focusout", () => setTimeout(() => { if (!(document.activeElement && document.activeElement.matches && document.activeElement.matches(".dc-box textarea"))) closePop(); }, 150));
  host.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b || !S.data) return;
    const fail = err => { S.err = err.message; draw(); };
    if (b.dataset.sort) { S.sort = b.dataset.sort; return draw(); }
    if (b.hasAttribute("data-new")) { S.writing = true; S.err = ""; return draw(); }
    if (b.hasAttribute("data-cancel")) { S.writing = false; S.replyTo = null; S.err = ""; return draw(); }
    if (b.dataset.open) { S.open = +b.dataset.open; S.replyTo = null; S.err = ""; draw(); return host.scrollIntoView({ block: "start", behavior: "smooth" }); }
    if (b.hasAttribute("data-back")) { S.open = null; S.replyTo = null; S.err = ""; return draw(); }
    if (b.dataset.reply) { S.replyTo = +b.dataset.reply; S.err = ""; return draw(); }
    if (b.dataset.fold) { const id = +b.dataset.fold; S.folded.has(id) ? S.folded.delete(id) : S.folded.add(id); return draw(); }
    if (b.dataset.asAnon != null) {   // keep what's written
      const box = b.closest(".dc-box"), ta = box.querySelector("textarea"), ti = box.querySelector(".dc-title-in"), v = [ta.value, ta._m, ti && ti.value];
      S.anon = b.dataset.asAnon === "1"; draw();
      const nb = host.querySelector(`.dc-box[data-kind="${box.dataset.kind}"]`); if (!nb) return;
      const t2 = nb.querySelector("textarea"); t2.value = v[0]; t2._m = v[1]; if (v[2] != null) nb.querySelector(".dc-title-in").value = v[2]; t2.focus(); return;
    }
    if (b.dataset.up) { const p = posts().find(x => x.id === +b.dataset.up); return call(`/${p.id}/vote`, { on: !p.voted }).then(update, fail); }
    if (b.dataset.mod) return call(`/${b.dataset.v}/moderate`, { [b.dataset.mod]: b.dataset.on === "true" }).then(update, fail);
    if (b.dataset.del) { if (!confirm("Delete this? Classmates will see that it was deleted.")) return; return call(`/${b.dataset.del}/delete`, {}).then(update, fail); }
    if (b.dataset.send != null) {
      const box = b.closest(".dc-box"), ta = box.querySelector("textarea"), ti = box.querySelector(".dc-title-in"), text = tokens(ta);
      if (ti && !ti.value.trim()) return ti.focus();
      if (!text) return ta.focus();
      b.disabled = true;
      call("", { t: target, ...(b.dataset.send ? { parent: +b.dataset.send } : { title: ti.value.trim() }), body: text, anon: S.anon })
        .then(d => { if (!b.dataset.send) { S.open = d.id; S.writing = false; } S.replyTo = null; update(d); }, err => {   // keep what's written
          b.disabled = false; let el = box.querySelector(".dc-err"); if (!el) { el = document.createElement("p"); el.className = "dc-err"; el.setAttribute("role", "alert"); box.append(el); } el.textContent = err.message; });
    }
  });
  host.innerHTML = head(0) + `<p class="dc-none">Loading the discussion…</p>`;
  load();
}
