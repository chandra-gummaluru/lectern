/* Where something happens: a place (a building or an address, found on the map as you type) and a room.

     placeField(host, { place, room, where, disabled, onChange({ place, room, where }) })

   place: { name, address?, lat?, lon? } (with lat/lon when it was picked from the search, so the course page
   can link it to a map); room: "BA 1170", "Room 2135"; where: the two in a line for lists ("BA 1170, Bahen
   Centre for Information Technology"), kept beside them for older readers. The search goes through Lectern's
   server (/api/places: server/places.py). An older Where (just text) shows as the room. */
import { api } from "./auth.js";

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
export const PIN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>';
const TYPE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 7V5h14v2M12 5v14M9 19h6"/></svg>';
export const whereOf = (place, room) => [String(room || "").trim(), String((place && place.name) || "").trim()].filter(Boolean).join(", ");
export const mapUrl = p => (p && Number.isFinite(+p.lat) && Number.isFinite(+p.lon) && (p.lat !== "" && p.lon !== "") ? `https://www.openstreetmap.org/?mlat=${+p.lat}&mlon=${+p.lon}#map=18/${+p.lat}/${+p.lon}` : "");
// An item's place and room, older ones (where only) read as the room.
export const placeOf = x => ({ place: x.place && typeof x.place === "object" ? x.place : null, room: x.place || x.room ? String(x.room || "") : String(x.where || "") });

let open = null;
const closeOpen = () => { if (open) open.close(); };
document.addEventListener("mousedown", e => { if (open && !open.pop.contains(e.target) && !open.host.contains(e.target)) closeOpen(); }, true);
window.addEventListener("resize", closeOpen);
document.addEventListener("scroll", e => { if (open && !open.pop.contains(e.target)) closeOpen(); }, true);

export function placeField(host, { place = null, room = "", disabled = false, onChange = () => {}, label = "Where" } = {}) {
  let P = place && place.name ? { ...place } : null, R = String(room || "");
  host.classList.add("plc");
  host.innerHTML = `<span class="plc-q"><span class="plc-ic">${PIN}</span><input type="text" class="plc-in" placeholder="Building or address" autocomplete="off" spellcheck="false" aria-label="${esc(label)}: building or address"${disabled ? " disabled" : ""}></span>
    <input type="text" class="plc-room" placeholder="Room" autocomplete="off" spellcheck="false" aria-label="${esc(label)}: room"${disabled ? " disabled" : ""}>`;
  const inp = host.querySelector(".plc-in"), rm = host.querySelector(".plc-room");
  const show = () => { inp.value = P ? P.name : ""; rm.value = R; host.classList.toggle("on-map", !!mapUrl(P)); inp.title = P && P.address ? `${P.name}, ${P.address}` : ""; };
  const tell = () => onChange({ place: P, room: R, where: whereOf(P, R) });
  show();
  if (disabled) return { get: () => ({ place: P, room: R }) };
  let timer = 0, seq = 0, at = -1;
  const close = () => { if (open && open.host === host) { open.pop.remove(); open = null; } };
  const choose = p => { P = p; close(); show(); tell(); };
  const draw = (q, list, note) => {
    if (!open || open.host !== host) {
      closeOpen();
      const pop = document.createElement("div"); pop.className = "pk-pop pk1-pop pks-pop plc-pop"; pop.setAttribute("role", "listbox");
      document.body.append(pop); open = { host, pop, close };
      pop.addEventListener("mousedown", e => { const b = e.target.closest("[data-i]"); if (!b) return; e.preventDefault(); const i = +b.dataset.i; choose(i < 0 ? { name: q } : open.list[i]); });
    }
    open.list = list; open.q = q; at = -1;
    open.pop.innerHTML = `<div class="pk1-list">${list.map((p, i) => `<button type="button" class="pk1-opt" data-i="${i}" tabindex="-1"><span class="pk1-ic">${PIN}</span><span class="pk1-t plc-t"><b>${esc(p.name)}</b>${p.address ? `<small>${esc(p.address)}</small>` : ""}</span></button>`).join("")}
      <button type="button" class="pk1-opt" data-i="-1" tabindex="-1"><span class="pk1-ic">${TYPE}</span><span class="pk1-t plc-t"><b>Use “${esc(q)}”</b><small>As typed, without a map</small></span></button>
      ${note ? `<p class="pk-none">${esc(note)}</p>` : ""}</div>`;
    const r = inp.getBoundingClientRect();
    open.pop.style.minWidth = `${Math.max(r.width, 280)}px`; open.pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - open.pop.offsetWidth - 8))}px`; open.pop.style.top = `${r.bottom + 4}px`;
  };
  inp.addEventListener("input", () => {
    clearTimeout(timer);
    const q = inp.value.trim(), my = ++seq;
    if (q.length < 3) { close(); return; }
    draw(q, (open && open.host === host && open.list) || [], "Searching…");
    timer = setTimeout(async () => {
      let list = [], note = "";
      try { const d = await api(`/api/places?q=${encodeURIComponent(q)}`); list = d.places || []; note = d.error || (d.off ? "" : list.length ? "" : "No places found."); }
      catch (e) { note = "The place search isn't answering right now."; }
      if (my === seq && document.activeElement === inp) draw(q, list, note);
    }, 350);
  });
  inp.addEventListener("keydown", e => {
    if (!open || open.host !== host) return;
    const B = [...open.pop.querySelectorAll("[data-i]")];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); at = Math.max(0, Math.min(B.length - 1, at + (e.key === "ArrowDown" ? 1 : -1))); B.forEach((b, i) => b.classList.toggle("on", i === at)); }
    else if (e.key === "Enter") { e.preventDefault(); const b = B[at >= 0 ? at : 0]; if (b) { const i = +b.dataset.i; choose(i < 0 ? { name: open.q } : open.list[i]); } }
    else if (e.key === "Escape") { e.stopPropagation(); close(); show(); }
  });
  // Left without picking one: what's typed is the place's name (no map), or nothing.
  inp.addEventListener("blur", () => setTimeout(() => {
    if (open && open.host === host) close();
    const v = inp.value.trim();
    if (v === (P ? P.name : "")) return;
    P = v ? { name: v } : null; show(); tell();
  }, 120));
  rm.addEventListener("change", () => { R = rm.value.trim(); tell(); });
  return { get: () => ({ place: P, room: R }) };
}
