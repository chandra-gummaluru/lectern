/* Attendance: who was there for a test, taken by the teaching team scanning students' ID cards with a phone's
   camera (server/attendance.py). A section of the evaluation's editor, above Grading (the test card's Take
   Attendance button opens it).

   + Take Attendance (with Session Information: the room, or the last names you're taking) begins your session;
   each card held up shows who it is (by its printed name and number, read with OCR), and Correct puts them in.
   Not Them (or Enter by Hand) finds the student by name or number: the best match, and Correct. A student is in once, whoever scans them: the second time says who entered them.
   Leaving the page ends your session, with its count. The section shows every session (each person's, with its
   note and count) and the total, as they happen. */

const SVG = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const ATTEND_ICON = SVG('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="m9 13 2 2 4-4.5"/>');
const SCAN = SVG('<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><path d="M7 12h10"/>');
const SEARCH = SVG('<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>');
const TRASH = SVG('<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>');
const PLUS = SVG('<path d="M12 5v14M5 12h14"/>');
const CHECK = SVG('<path d="m5 12.5 4.5 4.5L19 7"/>');
const ini = n => String(n || "").split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join("").toUpperCase() || "?";
const hm = s => { const d = new Date(s * 1000); return isNaN(d) ? "" : d.toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit", hour12: false }); };

// ── Reading what's printed on the card (OCR: Tesseract, as WebAssembly in a worker, static/vendor/tesseract/):
// its name and student number, matched against the class list (server: identify) ──
const TS = "/static/vendor/tesseract/";
let ocrP = null;
function ocr() {
  return ocrP || (ocrP = new Promise((ok, no) => {
    const go = () => window.Tesseract.createWorker("eng", 1, { workerPath: `${TS}worker.min.js`, corePath: TS, langPath: TS.replace(/\/$/, ""), workerBlobURL: false, gzip: true })
      .then(w => w.setParameters({ tessedit_pageseg_mode: "11" }).then(() => ok(w))).catch(no);
    if (window.Tesseract) return go();
    const s = document.createElement("script"); s.src = `${TS}tesseract.min.js`; s.onload = go; s.onerror = () => { ocrP = null; no(new Error("The card reader couldn't load.")); };
    document.head.appendChild(s);
  }));
}
// The card, as framed (the guide on the camera): cropped, grey and sharpened a little, for OCR.
function cardFrame(v, cv) {
  const w = v.videoWidth, h = v.videoHeight; if (!w || !h) return null;
  // The guide is 84% of the view's width, at a card's shape, centred; the view shows the video "cover".
  const box = v.getBoundingClientRect(), k = Math.max(box.width / w, box.height / h);
  const vw = box.width / k, vh = box.height / k, gw = vw * 0.84, gh = gw / 1.586;
  const sx = (w - vw) / 2 + (vw - gw) / 2, sy = (h - vh) / 2 + (vh - Math.min(gh, vh * 0.94)) / 2;
  cv.width = 1200; cv.height = Math.round(1200 / 1.586);
  const cx = cv.getContext("2d", { willReadFrequently: true });
  cx.filter = "grayscale(1) contrast(1.35)";
  cx.drawImage(v, sx, sy, gw, Math.min(gh, vh * 0.94), 0, 0, cv.width, cv.height);
  return cv;
}

// The evaluation editor's Attendance section (above Grading): mounted once per evaluation (Lectern.attendanceEl)
// and kept, so the editor redrawing (as you change things) doesn't stop the camera.
// Two ways: the section (scan: false), with the total, + Take Attendance and the sessions; and the page that taking it
// opens (scan: true), with the camera, until you leave it (which ends your session).
export function mountAttendance(host, { esc, toast, api, owner, c, t, e, scan = false, onScan = () => {}, onDone: done = () => {}, path = () => {} }) {
  const Q = `owner=${encodeURIComponent(owner)}&offering=${encodeURIComponent(`${c}/${t}`)}&e=${encodeURIComponent(e)}`;
  const B = x => ({ owner: owner || undefined, offering: `${c}/${t}`, e, ...x });
  let O = null, S = null, timer = 0, cam = null, busy = false, polling = false;
  const $ = s => host.querySelector(s);
  const onDone = () => { clearTimeout(timer); stopCam(); host.innerHTML = ""; done(); };   // (the page: its camera off, and gone)
  const here = () => host.isConnected;
  if (!scan) host.classList.add("at-sec");
  // Its typing is its own: not the editor's (which would take it as a change to the gradebook).
  ["input", "change", "keydown"].forEach(k => host.addEventListener(k, ev => ev.stopPropagation()));
  host.innerHTML = `<p class="ed-help">Reading attendance…</p>`;

  const load = () => api(`/api/attendance?${Q}`).then(d => { O = d; return d; });
  function poll() { if (scan && !S) return; clearTimeout(timer); polling = true; timer = setTimeout(() => { if (!here()) { polling = false; return; } load().then(() => { if (S) drawCounts(); else refreshOverview(); poll(); }, () => poll()); }, 5000); }

  // ── The overview: the total; a new session's information and + Take Attendance (or, yours still going, Continue
  // Scanning); and every session. It's kept up to date in place, so what's being typed stays. ──
  const metaHTML = () => `${O.total} of ${O.enrolled} students in · ${O.sessions.length} session${O.sessions.length === 1 ? "" : "s"}`;
  const sessHTML = () => O.sessions.length ? `<div class="at-sess">${O.sessions.slice().reverse().map(s => `<div class="at-row${s.stopped ? "" : " live"}">
      <span class="lt-cmt-av" aria-hidden="true">${esc(ini(s.by))}</span>
      <div class="at-rb"><p><b>${esc(s.by)}</b>${s.note ? `<span class="at-note">${esc(s.note)}</span>` : ""}</p><p class="at-when">${s.stopped ? `${hm(s.started)}–${hm(s.stopped)}` : `<span class="at-dot"></span>Scanning now, since ${hm(s.started)}`} · ${s.count} student${s.count === 1 ? "" : "s"} in</p></div>${O.canDelete ? `<button type="button" class="lx-ic quiet at-del" data-at-del="${s.id}" title="Delete this session" aria-label="Delete this session">${TRASH}</button>` : ""}</div>`).join("")}</div>`
    : `<p class="ed-help">No one has taken attendance yet. Each person who takes it starts their own session, so each has its own count.</p>`;
  const mine = () => O.sessions.find(s => s.mine && !s.stopped);
  function bindSessions(box) {
    // Delete: click once and it turns red; click again, within a few seconds, to delete.
    box.querySelectorAll("[data-at-del]").forEach(b => { b.onclick = () => {
      const se = O.sessions.find(x => String(x.id) === b.dataset.atDel); if (!se) return;
      if (!b.classList.contains("armed")) {
        box.querySelectorAll(".at-del.armed").forEach(x => x.classList.remove("armed"));
        b.classList.add("armed"); b.title = `Click again to delete it, and the ${se.count} student${se.count === 1 ? "" : "s"} it put in`;
        clearTimeout(b._t); b._t = setTimeout(() => { b.classList.remove("armed"); b.title = "Delete this session"; }, 4000);
        return;
      }
      clearTimeout(b._t); b.disabled = true;
      api("/api/attendance/delete", B({ session: se.id })).then(d => { toast(`Session deleted: ${d.removed} student${d.removed === 1 ? "" : "s"} taken out.`); return load().then(drawOverview); }, x => { b.disabled = false; toast(x.message); });
    }; });
  }
  function refreshOverview() {   // the poll: the total and the sessions, in place
    if (scan) return;
    const m = $("#at-meta"), l = $("#at-sess-box"); if (!m || !l) return drawOverview();
    if (!!mine() !== !!$("#at-resume") && !(($("#at-note") || {}).value)) return drawOverview();
    m.textContent = metaHTML();
    if (!l.querySelector(".at-del.armed")) { l.innerHTML = sessHTML(); bindSessions(l); }   // (not while a delete waits for its second click)
  }
  function drawOverview() {
    const open = mine();
    host.innerHTML = `<p class="ed-help at-sum" id="at-meta">${metaHTML()}</p>
      ${open ? `<div class="at-acts"><button type="button" class="lt-btn" id="at-resume">${SCAN}Continue Scanning</button></div>`
        : `<div class="at-start"><label class="pf"><span>Session Information</span><input type="text" id="at-note" maxlength="120" placeholder="e.g. BA 1170, last names A–L" autocomplete="off"></label>
          <p class="ed-help">Who you're taking attendance of, so it's easy to tell the sessions apart later.</p>
          <div class="at-go-row"><button type="button" class="lt-btn add" id="at-go">${PLUS}Take Attendance</button></div></div>`}
      <h4 class="ed-sub">Sessions</h4>
      <div id="at-sess-box">${sessHTML()}</div>`;
    bindSessions(host);
    if (open) { $("#at-resume").onclick = () => onScan(); return; }
    const goB = $("#at-go"), note = $("#at-note");
    const startIt = () => { goB.disabled = true; api("/api/attendance/start", B({ note: note.value })).then(() => onScan(), x => { goB.disabled = false; toast(x.message); }); };
    goB.onclick = startIt; note.onkeydown = ev => { if (ev.key === "Enter") { ev.preventDefault(); startIt(); } };
  }

  // ── Scanning: the evaluation, with Enter by Hand; this session's line; the camera ──
  function scanner() {
    path(O.eval);
    const tt = `${esc(O.eval.name)}${O.eval.title && O.eval.title !== O.eval.name ? `<span class="lt-req-of"> / ${esc(O.eval.title)}</span>` : ""}`;
    host.innerHTML = `<div class="lx-editor lt-req-ed at-card at-scan">
      <div class="lx-ed-head"><span class="lx-kicon big" aria-hidden="true">${ATTEND_ICON}</span><div class="gr-tt"><p class="gr-kind">Attendance</p><h2>${tt}</h2></div>
        <button type="button" class="lt-btn lx-acts at-hand" id="at-hand">${SEARCH}Enter by Hand</button></div>
      <p class="lt-req-meta">${S.note ? `${esc(S.note)} · ` : ""}<span id="at-mine">${S.count || 0}</span> this session · <span id="at-all">${O.total}</span> of ${O.enrolled} in all</p>
      <div class="at-cam" id="at-cam"><video id="at-video" playsinline muted disablepictureinpicture></video><div class="at-aim"></div><p class="at-cam-msg" id="at-cam-msg"></p><div id="at-res" class="at-res"></div></div>
    </div>`;
    $("#at-hand").onclick = () => findStudent();
    startCam();
  }
  function drawCounts() { const a = $("#at-all"); if (a) a.textContent = O.total; }
  // Taken out of the page for a moment (the editor redrawing) is fine; gone for longer (the editor closed), the camera stops.
  let goneAt = 0;
  const away = () => { if (here()) { goneAt = 0; return false; } if (!goneAt) goneAt = Date.now(); return Date.now() - goneAt > 1500; };
  async function startCam() {
    const v = $("#at-video"), msg = $("#at-cam-msg");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      if (!S || !v.isConnected) { stream.getTracks().forEach(x => x.stop()); return; }
      cam = stream; v.srcObject = stream; await v.play(); msg.textContent = "";
      const tick = () => {   // (the camera: kept going, and off once the page is gone)
        if (!cam) return;
        if (away()) return stopCam();
        if (here() && v.paused) v.play().catch(() => {});
        setTimeout(tick, 250);
      };
      tick();
      // What's printed on it, read a few times a second.
      const cv = document.createElement("canvas");
      let reading = false, lastWho = "", lastWhoAt = 0;
      ocr().then(w => {
        const look = async () => {
          if (!cam) return;
          if (!busy && !reading && here() && v.readyState >= 2) {
            reading = true;
            try {
              const f = cardFrame(v, cv);
              const text = f ? (await w.recognize(f)).data.text : "";
              if (!busy && cam && text.replace(/\W/g, "").length >= 6) {
                const d = await api("/api/attendance/identify", B({ text }));
                const s0 = d.students && d.students[0];
                if (s0 && !busy && !(s0.num === lastWho && Date.now() - lastWhoAt < 4000)) { lastWho = s0.num; lastWhoAt = Date.now(); recognised(d); }
              }
            } catch (_) { /* try again */ }
            reading = false;
          }
          setTimeout(look, 350);
        };
        look();
      }, () => {});
    } catch (x) {
      if (msg) msg.textContent = x && x.name === "NotAllowedError" ? "Lectern can't use the camera: allow it in your browser's settings, or enter students by hand." : `The camera didn't start${x && x.message ? ` (${x.message})` : ""}. You can enter students by hand.`;
      const cm = $("#at-cam"); if (cm) cm.classList.add("off");
    }
  }
  function stopCam() { if (cam) { cam.getTracks().forEach(x => x.stop()); cam = null; } }
  // Leaving the page (anywhere: the path, Back) ends your session, with its count; the section then shows it.
  function stopping() {
    if (!S) return; const se = S; S = null; busy = true; clearTimeout(timer); stopCam(); host.innerHTML = "";
    api("/api/attendance/stop", B({ session: se.id })).then(d => { toast(`Stopped: ${d.count} student${d.count === 1 ? "" : "s"} in this session.`); }, x => toast(x.message))
      .finally(() => window.dispatchEvent(new CustomEvent("lt-attendance", { detail: e })));
  }
  if (scan) { const off = () => { window.removeEventListener("hashchange", off); stopping(); }; window.addEventListener("hashchange", off); }
  else window.addEventListener("lt-attendance", ev => { if (ev.detail === e && here() && O) load().then(refreshOverview); });
  // Who it is (or what's wrong) covers the camera, until it's dealt with.
  const res = html => { const r = $("#at-res"); if (r) { r.innerHTML = html; const c = $("#at-cam"); if (c) c.scrollIntoView({ block: "nearest" }); } return r; };
  const resume = (after = 0) => setTimeout(() => { busy = false; const r = $("#at-res"); if (r && !r.querySelector("input")) r.innerHTML = ""; }, after);
  const buzz = ms => { try { navigator.vibrate && navigator.vibrate(ms); } catch (_) { /* no */ } };
  const whoHTML = (s, kick) => `<p class="gr-kind">${esc(kick)}</p><h3>${esc([s.last, s.first].filter(Boolean).join(", "))}</h3><p class="at-meta">${esc([s.num, s.email].filter(Boolean).join(" · "))}</p>`;
  function already(s, a) {
    buzz([80, 60, 80]);
    const r = res(`<div class="at-panel bad">${whoHTML(s, "Already entered")}<p class="at-why">This student was already entered${a && a.by ? ` by ${esc(a.by)}` : ""}${a && a.at ? ` at ${hm(a.at)}` : ""}.</p>
      <div class="at-pacts"><button type="button" class="lt-btn primary" data-next>Next</button></div></div>`);
    r.querySelector("[data-next]").onclick = () => resume();
  }
  // The card, read by its text: its best match, Correct puts them in.
  function recognised(d) {
    busy = true; buzz(40);
    const s = d.students[0];
    if (s.already) return already(s, s.already);
    const r = res(`<div class="at-panel ask">${whoHTML(s, "Is this them?")}
      <div class="at-pacts"><button type="button" class="lt-btn" data-no>Not Them</button><button type="button" class="lt-btn primary" data-yes>${CHECK}Correct</button></div></div>`);
    r.querySelector("[data-yes]").onclick = () => markIn(s);
    r.querySelector("[data-no]").onclick = () => findStudent();
  }
  // By hand: a name or number, and the best match as you type; Correct (or Enter) puts them in.
  function findStudent() {
    busy = true;
    const r = res(`<div class="at-panel find"><p class="gr-kind">Enter by Hand</p>
      <label class="at-q">${SEARCH}<input type="search" id="at-q" placeholder="Last name, first name or number" autocomplete="off" autocapitalize="words"></label>
      <div class="at-best" id="at-best"></div>
      <div class="at-pacts"><button type="button" class="lt-btn" data-cancel>Cancel</button><button type="button" class="lt-btn primary" data-yes disabled>${CHECK}Correct</button></div></div>`);
    const inp = r.querySelector("#at-q"), box = r.querySelector("#at-best"), yes = r.querySelector("[data-yes]");
    let best = null, n = 0;
    r.querySelector("[data-cancel]").onclick = () => { r.innerHTML = ""; resume(); };
    yes.onclick = () => { if (best) best.already ? already(best, best.already) : markIn(best, true); };
    inp.onkeydown = ev => { if (ev.key === "Enter" && !yes.disabled) { ev.preventDefault(); yes.click(); } };
    inp.oninput = () => {
      const q = inp.value.trim(), k = ++n;
      if (q.length < 2) { best = null; yes.disabled = true; box.innerHTML = ""; return; }
      api(`/api/attendance/search?${Q}&q=${encodeURIComponent(q)}`).then(d => {
        if (k !== n) return;
        best = d.students[0] || null;
        const a = best && best.already; yes.disabled = !best || !!a;   // (already in: it says so, and there's nothing to do)
        box.innerHTML = best ? `<h3>${esc([best.last, best.first].filter(Boolean).join(", "))}</h3><p class="at-meta">${esc([best.num, best.email].filter(Boolean).join(" · "))}</p>${a ? `<p class="at-why at-bad-t">Already entered${a.by ? ` by ${esc(a.by)}` : ""}${a.at ? ` at ${hm(a.at)}` : ""}.</p>` : ""}`
          : `<p class="at-why">No one on the class list matches.</p>`;
      }, x => { best = null; yes.disabled = true; box.innerHTML = `<p class="at-why">${esc(x.message)}</p>`; });
    };
    setTimeout(() => inp.focus(), 0);
  }
  function markIn(s, hand = false) {
    res(`<div class="at-panel"><p class="at-why">Putting ${esc(s.first)} in…</p></div>`);
    api("/api/attendance/mark", B({ session: S.id, student: s.num, hand: hand || undefined })).then(d => {
      buzz(120);
      S.count = d.count; O.total += 1;
      const m = $("#at-mine"); if (m) m.textContent = d.count; drawCounts();
      res(`<div class="at-panel ok"><span class="at-ok">${CHECK}</span><div><h3>${esc(`${s.first} ${s.last}`)} is in.</h3></div></div>`);
      resume(1300);
    }, x => {
      if (x.code === "already") return api(`/api/attendance/search?${Q}&q=${encodeURIComponent(s.num)}`).then(d => already(s, (d.students.find(y => y.num === s.num) || {}).already), () => already(s, null));
      if (x.code === "stopped" || x.code === "no-session") { toast(x.message); S = null; stopCam(); onDone(); return; }
      res(`<div class="at-panel bad"><p class="at-why">${esc(x.message)}</p><div class="at-pacts"><button type="button" class="lt-btn primary" data-next>Next</button></div></div>`).querySelector("[data-next]").onclick = () => resume();
    });
  }

  // The page: your session (one you started, still going), or, none, back to the section.
  load().then(() => { if (!scan) { drawOverview(); poll(); return; } S = mine(); if (!S) return onDone(); scanner(); poll(); },
    x => { host.innerHTML = `<p class="ed-help err">Couldn't read the attendance. ${esc(x.message)}</p>`; });
  // The section, put back (the editor redrawing, or back from taking attendance): up to date.
  host._back = () => { if (scan || !O) return; if (!polling) poll(); load().then(refreshOverview); };
  host._stop = stopCam;
  return host;
}
