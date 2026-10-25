/* A date (and time) field, as the Gradebook's Evaluations has it: one button saying when
   ("Wed, Oct 28, 2026 · 18:10"), and a calendar under it, with the time typed in (18:30, 6:30 pm, noon…).

     whenField(host, { date: "2026-10-28", time: "18:10", withTime, empty, timeLabel, timeHolder, id, label,
                       near, min, max, disabled, onChange({ date, time }) }) → { get, set }
   (min, max: the first and last day that can be chosen, e.g. an activity's week; others are greyed.)

   host gets the button (with id, if given) and data-date / data-time saying what's chosen. */

const CAL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>';
const PREV = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>';
const NEXT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>';
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

// Typed times: 18:30, 1830, 9, and also 6pm, 6:30 pm, noon, midnight → "HH:MM" ("" none; null: can't read it).
export function parseTime(v) {
  v = String(v).trim().toLowerCase().replace(/\./g, "");
  if (!v) return "";
  if (v === "noon") return "12:00"; if (v === "midnight") return "00:00";
  const m = /^(\d{1,2})(?::?(\d{2}))?\s*(a|p|am|pm)?$/.exec(v); if (!m) return null;
  let h = +m[1]; const mi = +(m[2] || 0);
  if (m[3]) { if (h < 1 || h > 12) return null; h = h % 12 + (m[3][0] === "p" ? 12 : 0); }
  if (h > 23 || mi > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(mi).padStart(2, "0")}`;
}

let open = null;   // the calendar that's open: { pop, close }
function closeOpen() { if (open) open.close(); }
document.addEventListener("mousedown", e => { if (open && !open.pop.contains(e.target) && !open.btn.contains(e.target)) closeOpen(); }, true);
document.addEventListener("keydown", e => { if (open && e.key === "Escape") { e.preventDefault(); const b = open.btn; closeOpen(); b.focus(); } }, true);
addEventListener("resize", closeOpen);

export function whenField(host, { date = "", time = "", withTime = true, empty = "Choose a date", timeLabel = "Time", timeHolder = "No time", id = "", label = "", near = "", min = "", max = "", disabled = false, onChange = () => {} } = {}) {
  let v = { date: date || "", time: withTime ? time || "" : "" };
  host.classList.add("lxw");
  host.innerHTML = `<button type="button" class="lxw-btn"${id ? ` id="${esc(id)}"` : ""}${label ? ` aria-label="${esc(label)}"` : ""}${disabled ? " disabled" : ""}>${CAL}<span></span></button>`;
  const btn = host.firstElementChild;
  const text = () => {
    if (!v.date) return empty;
    const d = new Date(`${v.date}T12:00`); if (isNaN(d)) return v.date;
    const day = d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
    return withTime && v.time ? `${day} · ${v.time}` : day;
  };
  const show = () => { btn.querySelector("span").textContent = text(); btn.classList.toggle("empty", !v.date); host.dataset.date = v.date; host.dataset.time = v.time; };
  const set = (k, x) => { if (v[k] === x) return; v = { ...v, [k]: x }; show(); onChange({ ...v }); };
  show();
  if (disabled) return { get: () => ({ ...v }), set: nv => { v = { date: nv.date || "", time: nv.time || "" }; show(); } };

  btn.onclick = () => {
    if (open && open.btn === btn) return closeOpen();
    closeOpen();
    let shown = new Date(`${v.date || near || min || iso(new Date())}T12:00`); shown.setDate(1);   // near: where to open with no date (e.g. its week)
    const pop = document.createElement("div");
    pop.className = "lxw-pop"; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", label || "Choose a date");
    const draw = () => {
      const first = new Date(shown), start = new Date(first); start.setDate(1 - first.getDay());
      const today = iso(new Date()), days = [];
      for (let k = 0; k < 42; k++) { const d = new Date(start); d.setDate(start.getDate() + k); days.push(d); }
      pop.innerHTML = `<div class="lxw-head"><button type="button" data-w="prev" aria-label="Previous month">${PREV}</button><b>${first.toLocaleDateString("en-CA", { month: "long", year: "numeric" })}</b><button type="button" data-w="next" aria-label="Next month">${NEXT}</button></div>
        <div class="lxw-days">${["S", "M", "T", "W", "T", "F", "S"].map(x => `<i>${x}</i>`).join("")}${days.map(d => `<button type="button" data-day="${iso(d)}"${(min && iso(d) < min) || (max && iso(d) > max) ? " disabled" : ""} class="${d.getMonth() !== first.getMonth() ? "out" : ""}${iso(d) === today ? " today" : ""}${iso(d) === v.date ? " on" : ""}">${d.getDate()}</button>`).join("")}</div>
        <div class="lxw-time">${withTime ? `<label>${esc(timeLabel)}<input type="text" class="lxw-t" value="${esc(v.time)}" placeholder="${esc(timeHolder)}" autocomplete="off"></label>` : `<span class="grow"></span>`}<button type="button" class="lxw-clear" data-w="clear">Clear</button></div>`;
    };
    draw();
    document.body.append(pop);
    const r = btn.getBoundingClientRect(), w = pop.offsetWidth;
    pop.style.top = `${r.bottom + scrollY + 6}px`;
    pop.style.left = `${Math.max(8 + scrollX, Math.min(r.left + scrollX, scrollX + document.documentElement.clientWidth - w - 8))}px`;
    open = { pop, btn, close: () => { pop.remove(); open = null; } };
    pop.addEventListener("mousedown", e => { if (!e.target.closest("input")) e.preventDefault(); });
    pop.addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.dataset.day) { set("date", b.dataset.day); shown = new Date(`${b.dataset.day}T12:00`); shown.setDate(1); if (!withTime) { closeOpen(); return; } }
      else if (b.dataset.w === "prev" || b.dataset.w === "next") shown.setMonth(shown.getMonth() + (b.dataset.w === "prev" ? -1 : 1));
      else if (b.dataset.w === "clear") { set("date", ""); set("time", ""); }
      draw();
      const t = pop.querySelector(".lxw-t"); if (t && b.dataset.day) t.focus();
    });
    pop.addEventListener("input", e => { if (!e.target.matches(".lxw-t")) return; const t = parseTime(e.target.value); e.target.classList.toggle("bad", t == null); if (t != null) set("time", t); });
    pop.addEventListener("keydown", e => {
      if (!e.target.matches(".lxw-t") || e.key !== "Enter") return;
      e.preventDefault(); const t = parseTime(e.target.value); if (t == null) { e.target.classList.add("bad"); return; }
      set("time", t); closeOpen(); btn.focus();
    });
  };
  return { get: () => ({ ...v }), set: nv => { v = { date: nv.date || "", time: withTime ? nv.time || "" : "" }; show(); } };
}
