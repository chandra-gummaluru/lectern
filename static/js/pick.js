/* A dropdown of tick boxes: a button saying what's ticked ("LEC0101, LEC0201", or what none means), and a
   list under it to tick and untick. For choosing several of a few things, e.g. an activity's groups.

     pickMany(host, { options: [[value, label]…], value: [values], empty: "Everyone in the course",
                      label, disabled, onChange(values) }) → { get, set }
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
