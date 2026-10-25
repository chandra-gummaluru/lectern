/* A dropdown of tick boxes: a button saying what's ticked ("LEC0101, LEC0201", or what none means), and a
   list under it to tick and untick. For choosing several of a few things, e.g. an activity's groups.

     pickMany(host, { options: [[value, label]…], value: [values], empty: "Everyone in the course",
                      label, disabled, onChange(values) }) → { get, set }

   pickOne: a dropdown for choosing one of many, each with its icon, a small grey line over its name, under
   headings; a search field filters them as you type (↑/↓ and Enter work there too).

     pickOne(host, { options: [{ value, label, kick, icon, group }…], value, empty: "Nothing in particular",
                     emptyHint, search: "Search…", label, id, disabled, onChange(value) }) → { get, set }
*/
const CARET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

let open = null;   // the list that's open: { host, close }
document.addEventListener("mousedown", e => { if (open && !open.host.contains(e.target)) open.close(); }, true);
document.addEventListener("keydown", e => { if (open && e.key === "Escape") { const b = open.host.querySelector("button"); open.close(); if (b) b.focus(); } }, true);

export function pickMany(host, { options = [], value = [], empty = "None", label = "", id = "", disabled = false, onChange = () => {} } = {}) {
  let v = value.map(String);
  host.classList.add("pk");
  host.innerHTML = `<button type="button" class="pk-btn"${id ? ` id="${esc(id)}"` : ""} aria-haspopup="listbox" aria-expanded="false"${label ? ` aria-label="${esc(label)}"` : ""}${disabled ? " disabled" : ""}><span></span>${CARET}</button>`;
  const btn = host.firstElementChild;
  const text = () => { const n = options.filter(([k]) => v.includes(String(k))).map(([, l]) => l); return n.length ? n.join(", ") : empty; };
  const show = () => { btn.querySelector("span").textContent = text(); host.dataset.value = v.join(","); };
  const close = () => { const p = host.querySelector(".pk-pop"); if (p) p.remove(); btn.setAttribute("aria-expanded", "false"); if (open && open.host === host) open = null; };
  btn.onclick = () => {
    if (open && open.host === host) return close();
    if (open) open.close();
    const pop = document.createElement("div");
    pop.className = "pk-pop"; pop.setAttribute("role", "listbox"); pop.setAttribute("aria-multiselectable", "true");
    pop.innerHTML = options.map(([k, l]) => `<label class="pk-opt"><input type="checkbox" value="${esc(k)}"${v.includes(String(k)) ? " checked" : ""}><span>${esc(l)}</span></label>`).join("")
      || `<p class="pk-none">Nothing to choose yet.</p>`;
    pop.addEventListener("change", e => {
      const k = e.target.value;
      v = e.target.checked ? [...new Set([...v, k])] : v.filter(x => x !== k);
      show(); onChange(v.slice());
    });
    host.append(pop); btn.setAttribute("aria-expanded", "true");
    open = { host, close };
  };
  show();
  return { get: () => v.slice(), set: nv => { v = (nv || []).map(String); show(); } };
}

const CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
const NONE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M6 18 18 6"/></svg>';

export function pickOne(host, { options = [], value = "", empty = "None", emptyHint = "", search = "Search…", label = "", id = "", disabled = false, onChange = () => {} } = {}) {
  let v = String(value || "");
  host.classList.add("pk", "pk1");
  host.innerHTML = `<button type="button" class="pk-btn pk1-btn"${id ? ` id="${esc(id)}"` : ""} aria-haspopup="listbox" aria-expanded="false"${label ? ` aria-label="${esc(label)}"` : ""}${disabled ? " disabled" : ""}><span class="pk1-cur"></span>${CARET}</button>`;
  const btn = host.firstElementChild;
  const row = o => `<span class="pk1-ic">${o.icon || ""}</span><span class="pk1-t">${o.kick ? `<small>${esc(o.kick)}</small>` : ""}<b>${esc(o.label)}</b></span>`;
  const show = () => {
    const o = options.find(x => String(x.value) === v);
    btn.querySelector(".pk1-cur").innerHTML = o ? row(o) : `<span class="pk1-ic">${NONE}</span><span class="pk1-t pk1-empty"><b>${esc(empty)}</b></span>`;
    host.dataset.value = v;
  };
  const close = () => { const p = host.querySelector(".pk-pop"); if (p) p.remove(); btn.setAttribute("aria-expanded", "false"); if (open && open.host === host) open = null; };
  const choose = k => { close(); btn.focus(); if (k === v) return; v = k; show(); onChange(v); };
  btn.onclick = () => {
    if (open && open.host === host) return close();
    if (open) open.close();
    const pop = document.createElement("div");
    pop.className = "pk-pop pk1-pop"; pop.setAttribute("role", "listbox");
    const many = options.length > 6;
    pop.innerHTML = `${many ? `<div class="pk1-q"><input type="search" placeholder="${esc(search)}" aria-label="${esc(search)}" autocomplete="off" spellcheck="false"></div>` : ""}<div class="pk1-list"></div>`;
    const list = pop.querySelector(".pk1-list"), q = pop.querySelector("input");
    let at = -1;
    const draw = () => {
      const f = String(q ? q.value : "").trim().toLowerCase();
      const hit = o => !f || [o.label, o.kick, o.group].some(x => String(x || "").toLowerCase().includes(f));
      let html = f ? "" : `<button type="button" class="pk1-opt" role="option" data-v="" aria-selected="${v === ""}"><span class="pk1-ic">${NONE}</span><span class="pk1-t pk1-empty"><b>${esc(empty)}</b>${emptyHint ? `<small>${esc(emptyHint)}</small>` : ""}</span>${v === "" ? CHECK : ""}</button>`;
      let last = null;
      options.filter(hit).forEach(o => {
        if (o.group && o.group !== last) { html += `<p class="pk1-h">${esc(o.group)}</p>`; last = o.group; }
        const on = String(o.value) === v;
        html += `<button type="button" class="pk1-opt" role="option" data-v="${esc(o.value)}" aria-selected="${on}">${row(o)}${on ? CHECK : ""}</button>`;
      });
      list.innerHTML = html || `<p class="pk-none">Nothing matches.</p>`;
      at = -1;
    };
    const opts = () => [...list.querySelectorAll(".pk1-opt")];
    const mark = () => opts().forEach((b, i) => { b.classList.toggle("on", i === at); if (i === at) b.scrollIntoView({ block: "nearest" }); });
    list.addEventListener("click", e => { const b = e.target.closest(".pk1-opt"); if (b) choose(b.dataset.v); });
    pop.addEventListener("keydown", e => {
      const L = opts();
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); at = Math.max(0, Math.min(L.length - 1, at + (e.key === "ArrowDown" ? 1 : -1))); mark(); }
      else if (e.key === "Enter" && e.target === q) { e.preventDefault(); const b = L[at >= 0 ? at : 0]; if (b) choose(b.dataset.v); }
    });
    if (q) q.addEventListener("input", draw);
    draw();
    host.append(pop); btn.setAttribute("aria-expanded", "true");
    open = { host, close };
    if (q) q.focus();
    const cur = list.querySelector('[aria-selected="true"]'); if (cur) cur.scrollIntoView({ block: "nearest" });
  };
  show();
  return { get: () => v, set: nv => { v = String(nv || ""); show(); } };
}
