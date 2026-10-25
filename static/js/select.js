/* Every dropdown in Lectern looks like the About picker (pick.js's pickOne): a button showing what's
   chosen, and a list under it, under its headings (a select's <optgroup>s), with a search field when
   there are many. The <select> itself stays, hidden, under it: code reads and sets its value and hears
   its "change" as before, and the button follows it (options redrawn, value set, disabled).

     enhanceSelects(root = document.body)   once: enhances the selects there now and any added later.
   A select with data-native, multiple or a size of more than 1 is left alone.
*/
const CARET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const SEARCH_FROM = 9;   // options before a search field shows

let open = null;   // { sel, pop, close }
const closeOpen = () => { if (open) open.close(); };
document.addEventListener("mousedown", e => { if (open && !open.pop.contains(e.target) && !open.btn.contains(e.target)) closeOpen(); }, true);
window.addEventListener("resize", closeOpen);
document.addEventListener("scroll", e => { if (open && !open.pop.contains(e.target)) closeOpen(); }, true);

const proto = HTMLSelectElement.prototype;
const VALUE = Object.getOwnPropertyDescriptor(proto, "value"), INDEX = Object.getOwnPropertyDescriptor(proto, "selectedIndex");

function enhance(sel) {
  if (sel.__pks || sel.multiple || sel.size > 1 || sel.hasAttribute("data-native") || !sel.isConnected) return;
  sel.__pks = true;
  // Where it sat: a block (a form field), or inline in a sentence or a row of filters.
  const cs = getComputedStyle(sel), pd = sel.parentElement ? getComputedStyle(sel.parentElement).display : "";
  const inline = /inline/.test(cs.display) || /flex|grid/.test(pd) && !sel.closest("label.lx-f, label.pf, .lt-form label, .lx-f");
  const host = document.createElement("span");
  host.className = `pks${inline ? " pks-inline" : ""}`;
  host.innerHTML = `<button type="button" class="pk-btn pk1-btn pks-btn" aria-haspopup="listbox" aria-expanded="false"><span class="pk1-cur"></span>${CARET}</button>`;
  const btn = host.firstElementChild;
  if (sel.id) btn.dataset.for = sel.id;
  const aria = sel.getAttribute("aria-label") || (sel.closest("label") ? "" : sel.title);
  if (aria) btn.setAttribute("aria-label", aria);
  sel.after(host);
  sel.classList.add("pks-native"); sel.tabIndex = -1; sel.setAttribute("aria-hidden", "true");
  sel.addEventListener("focus", () => btn.focus());

  const items = () => [...sel.options].map(o => ({ v: o.value, label: o.label || o.textContent, group: o.parentElement.tagName === "OPTGROUP" ? o.parentElement.label : "", disabled: o.disabled || (o.parentElement.tagName === "OPTGROUP" && o.parentElement.disabled), on: o.selected, kick: o.dataset.kick || "", icon: o.dataset.icon || "" }));
  const row = o => `${o.icon ? `<span class="pk1-ic">${o.icon}</span>` : ""}<span class="pk1-t">${o.kick ? `<small>${esc(o.kick)}</small>` : ""}<b>${esc(o.label)}</b></span>`;
  const show = () => {
    const o = sel.options[sel.selectedIndex];
    btn.querySelector(".pk1-cur").innerHTML = o ? row({ label: o.label || o.textContent, kick: o.dataset.kick, icon: o.dataset.icon }) : `<span class="pk1-t pk1-empty"><b>&nbsp;</b></span>`;
    btn.disabled = sel.disabled;
    host.hidden = sel.hidden;
    if (sel.title) btn.title = sel.title;
  };
  // The select's value set by code (no event): the button follows.
  Object.defineProperty(sel, "value", { configurable: true, get() { return VALUE.get.call(this); }, set(v) { VALUE.set.call(this, v); show(); } });
  Object.defineProperty(sel, "selectedIndex", { configurable: true, get() { return INDEX.get.call(this); }, set(v) { INDEX.set.call(this, v); show(); } });
  new MutationObserver(() => { show(); if (open && open.sel === sel) open.redraw(); }).observe(sel, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["selected", "disabled", "label", "hidden", "title"] });
  sel.addEventListener("change", show);

  const choose = v => {
    closeOpen(); btn.focus();
    if (v === VALUE.get.call(sel)) return;
    VALUE.set.call(sel, v); show();
    sel.dispatchEvent(new Event("input", { bubbles: true }));
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const openList = () => {
    if (open && open.sel === sel) return closeOpen();
    closeOpen();
    const all = items(), many = all.length >= SEARCH_FROM;
    const pop = document.createElement("div");
    pop.className = "pk-pop pk1-pop pks-pop"; pop.setAttribute("role", "listbox");
    pop.innerHTML = `${many ? `<div class="pk1-q"><input type="search" placeholder="Search…" aria-label="Search" autocomplete="off" spellcheck="false"></div>` : ""}<div class="pk1-list"></div>`;
    const list = pop.querySelector(".pk1-list"), q = pop.querySelector("input");
    let at = -1;
    const redraw = () => {
      const f = String(q ? q.value : "").trim().toLowerCase(), L = items();
      let html = "", last = "";
      L.filter(o => !f || [o.label, o.group, o.kick].some(x => String(x).toLowerCase().includes(f))).forEach(o => {
        if (o.group !== last) { if (o.group) html += `<p class="pk1-h">${esc(o.group)}</p>`; last = o.group; }
        html += `<button type="button" class="pk1-opt" role="option" data-v="${esc(o.v)}" aria-selected="${o.on}"${o.disabled ? " disabled" : ""} tabindex="-1">${row(o)}${o.on ? CHECK : ""}</button>`;
      });
      list.innerHTML = html || `<p class="pk-none">Nothing matches.</p>`;
      at = -1;
    };
    const opts = () => [...list.querySelectorAll(".pk1-opt:not(:disabled)")];
    const mark = () => opts().forEach((b, i) => { b.classList.toggle("on", i === at); if (i === at) { b.scrollIntoView({ block: "nearest" }); if (!q) b.focus(); } });
    list.addEventListener("click", e => { const b = e.target.closest(".pk1-opt"); if (b && !b.disabled) choose(b.dataset.v); });
    pop.addEventListener("keydown", e => {
      const L = opts();
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); at = Math.max(0, Math.min(L.length - 1, at + (e.key === "ArrowDown" ? 1 : -1))); mark(); }
      else if (e.key === "Enter") { e.preventDefault(); const b = L[at >= 0 ? at : q ? 0 : -1]; if (b) choose(b.dataset.v); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeOpen(); btn.focus(); }
      else if (e.key === "Tab") closeOpen();
    });
    if (q) q.addEventListener("input", redraw);
    redraw();
    // On the page itself (fixed), so a dialog's or a card's edges don't cut it off.
    document.body.append(pop);
    const r = btn.getBoundingClientRect(), h = pop.offsetHeight, below = innerHeight - r.bottom - 8;
    pop.style.minWidth = `${Math.max(r.width, 180)}px`;
    pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - pop.offsetWidth - 8))}px`;
    pop.style.top = below < h && r.top > below ? `${Math.max(8, r.top - h - 4)}px` : `${r.bottom + 4}px`;
    btn.setAttribute("aria-expanded", "true");
    open = { sel, btn, pop, redraw, close: () => { pop.remove(); btn.setAttribute("aria-expanded", "false"); open = null; } };
    const cur = list.querySelector('[aria-selected="true"]');
    if (cur) { cur.scrollIntoView({ block: "nearest" }); at = opts().indexOf(cur); }
    if (q) q.focus(); else (cur || opts()[0] || btn).focus();
  };
  btn.addEventListener("click", e => { e.preventDefault(); openList(); });
  btn.addEventListener("keydown", e => { if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); openList(); } });
  show();
}

export function enhanceSelects(root = document.body) {
  const run = n => { if (n.nodeType !== 1) return; if (n.tagName === "SELECT") enhance(n); else n.querySelectorAll && n.querySelectorAll("select").forEach(enhance); };
  run(root);
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(run))).observe(root, { childList: true, subtree: true });
}
