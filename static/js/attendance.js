/* Attendance: who was there for a test, taken by the teaching team scanning students' ID cards with a phone's
   camera (server/attendance.py). A section of the evaluation's editor, above Grading (the test card's Take
   Attendance button opens it).

   + Take Attendance (with Session Information: the room, or the last names you're taking) begins your session;
   each card held up shows who it is (by its barcode, if it's registered; or by its printed name and number, read
   with OCR), and Correct puts them in. Not Them (or a card nobody has) finds the student by name or number, and
   registers the card to them. A student is in once, whoever scans them: the second time says who entered them.
   Leaving the page ends your session, with its count. The section shows every session (each person's, with its
   note and count) and the total, as they happen. */

const SVG = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const ATTEND_ICON = SVG('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="m9 13 2 2 4-4.5"/>');
const SCAN = SVG('<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><path d="M7 12h10"/>');
const SEARCH = SVG('<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>');
const TRASH = SVG('<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>');
const PLUS = SVG('<path d="M12 5v14M5 12h14"/>');
const CHECK = SVG('<path d="m5 12.5 4.5 4.5L19 7"/>');
const FORMATS = ["codabar", "code_39", "code_128", "code_93", "itf", "ean_13", "ean_8", "upc_a", "qr_code"];
const ini = n => String(n || "").split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join("").toUpperCase() || "?";
const hm = s => { const d = new Date(s * 1000); return isNaN(d) ? "" : d.toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit", hour12: false }); };

// ── The camera, and reading barcodes from it: the browser's own reader where there is one, else ZXing (zxing-cpp,
// as WebAssembly: static/vendor/), which reads TCards' Codabar well ──
let zx = null;
function loadZXing() {
  if (window.ZXingWASM) return Promise.resolve(window.ZXingWASM);
  return zx || (zx = new Promise((ok, no) => {
    const s = document.createElement("script"); s.src = "/static/vendor/zxing-wasm-reader-2.2.4.js";
    s.onload = () => { window.ZXingWASM.prepareZXingModule({ overrides: { locateFile: (p, pre) => (p.endsWith(".wasm") ? "/static/vendor/zxing_reader-2.2.4.wasm" : pre + p) } }); ok(window.ZXingWASM); };
    s.onerror = () => { zx = null; no(new Error("The barcode reader couldn't load.")); };
    document.head.appendChild(s);
  }));
}
async function reader() {
  if ("BarcodeDetector" in window) {
    try {
      const have = await window.BarcodeDetector.getSupportedFormats();
      const f = FORMATS.filter(x => have.includes(x));
      if (f.includes("codabar")) { const bd = new window.BarcodeDetector({ formats: f }); return async v => { const r = await bd.detect(v); return r.length ? r[0].rawValue : ""; }; }
    } catch (_) { /* use ZXing */ }
  }
  const Z = await loadZXing();
  const opts = { tryHarder: true, maxNumberOfSymbols: 1, formats: ["Codabar", "Code39", "Code93", "Code128", "ITF", "EAN-13", "EAN-8", "UPC-A", "QRCode"] };
  const cv = document.createElement("canvas"), cx = cv.getContext("2d", { willReadFrequently: true });
  return async v => {
    const w = v.videoWidth, h = v.videoHeight; if (!w || !h) return "";
    const k = Math.min(1, 1280 / w); cv.width = Math.round(w * k); cv.height = Math.round(h * k);
    cx.drawImage(v, 0, 0, cv.width, cv.height);
    const r = await Z.readBarcodes(cx.getImageData(0, 0, cv.width, cv.height), opts);
    const ok = r.find(x => x.isValid && x.text);
    return ok ? ok.text : "";
  };
}

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
  let O = null, S = null, timer = 0, cam = null, busy = false, lastCode = "", lastAt = 0, polling = false;
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

  // ── Scanning: this session's line, with Stop; the camera; Enter by Hand ──
  function scanner() {
    path(O.eval);
    const tt = `${esc(O.eval.name)}${O.eval.title && O.eval.title !== O.eval.name ? `<span class="lt-req-of"> / ${esc(O.eval.title)}</span>` : ""}`;
    host.innerHTML = `<div class="lx-editor lt-req-ed at-card at-scan">
      <div class="lx-ed-head"><span class="lx-kicon big" aria-hidden="true">${ATTEND_ICON}</span><div class="gr-tt"><p class="gr-kind">Attendance</p><h2>${tt}</h2></div></div>
      <p class="lt-req-meta">${S.note ? `${esc(S.note)} · ` : ""}<span id="at-mine">${S.count || 0}</span> this session · <span id="at-all">${O.total}</span> of ${O.enrolled} in all</p>
      <div class="at-cam" id="at-cam"><video id="at-video" playsinline muted disablepictureinpicture></video><div class="at-aim"></div><p class="at-cam-msg" id="at-cam-msg"></p><div id="at-res" class="at-res"></div></div>
      <div class="at-hand-row"><button type="button" class="lt-btn at-hand" id="at-hand">${SEARCH}Enter by Hand</button></div>
    </div>`;
    $("#at-hand").onclick = () => findStudent("");
    startCam();
  }
  function drawCounts() { const a = $("#at-all"); if (a) a.textContent = O.total; }
  // Taken out of the page for a moment (the editor redrawing) is fine; gone for longer (the editor closed), the camera stops.
  let goneAt = 0;
  const away = () => { if (here()) { goneAt = 0; return false; } if (!goneAt) goneAt = Date.now(); return Date.now() - goneAt > 1500; };
  async function startCam() {
    const v = $("#at-video"), msg = $("#at-cam-msg");
    try {
      const read = await reader();
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      if (!S || !v.isConnected) { stream.getTracks().forEach(x => x.stop()); return; }
      cam = stream; v.srcObject = stream; await v.play(); msg.textContent = "";
      const tick = async () => {
        if (!cam) return;
        if (away()) return stopCam();
        if (here() && v.paused) v.play().catch(() => {});
        if (!busy && here() && v.readyState >= 2) {
          let code = ""; try { code = await read(v); } catch (_) { code = ""; }
          if (code && !(code === lastCode && Date.now() - lastAt < 2500)) { lastCode = code; lastAt = Date.now(); scanned(code); }
        }
        setTimeout(tick, 120);
      };
      tick();
      // And its printed name and number, a few times a second's worth apart (OCR is slower than a barcode).
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
    const r = res(`<div class="at-panel bad">${whoHTML(s, "Already entered")}<p class="at-why">${esc(`${s.first} ${s.last}`)} was already entered${a && a.by ? ` by ${esc(a.by)}` : ""}${a && a.at ? ` at ${hm(a.at)}` : ""}.</p>
      <div class="at-pacts"><button type="button" class="lt-btn primary" data-next>Next</button></div></div>`);
    r.querySelector("[data-next]").onclick = () => resume();
  }
  function scanned(code) {
    busy = true; buzz(40);
    res(`<div class="at-panel"><p class="at-why">Looking up the card…</p></div>`);
    api("/api/attendance/lookup", B({ card: code })).then(d => {
      if (!d.student) return findStudent(d.card, true);
      if (d.already) return already(d.student, d.already);
      const r = res(`<div class="at-panel ask">${whoHTML(d.student, "Is this them?")}
        <div class="at-pacts"><button type="button" class="lt-btn" data-no>Not Them</button><button type="button" class="lt-btn primary" data-yes>${CHECK}Correct</button></div></div>`);
      r.querySelector("[data-yes]").onclick = () => markIn(d.student, "");
      r.querySelector("[data-no]").onclick = () => findStudent(d.card);
    }, x => { res(`<div class="at-panel bad"><p class="at-why">${esc(x.message)}</p><div class="at-pacts"><button type="button" class="lt-btn primary" data-next>Next</button></div></div>`).querySelector("[data-next]").onclick = () => resume(); });
  }
  // The card, read by its text: who it is (Correct puts them in), or, not sure, which of a few it is.
  function recognised(d) {
    busy = true; buzz(40);
    const L = d.students, s = L[0];
    if (d.sure) {
      if (s.already) return already(s, s.already);
      const r = res(`<div class="at-panel ask">${whoHTML(s, "Is this them?")}
        <div class="at-pacts"><button type="button" class="lt-btn" data-no>Not Them</button><button type="button" class="lt-btn primary" data-yes>${CHECK}Correct</button></div></div>`);
      r.querySelector("[data-yes]").onclick = () => markIn(s, "");
      r.querySelector("[data-no]").onclick = () => findStudent("");
      return;
    }
    const r = res(`<div class="at-panel find"><p class="gr-kind">Which one is it?</p><p class="at-why">The card could be any of these.</p>
      <div class="at-hits">${L.map((x, i) => `<button type="button" class="at-hit${x.already ? " in" : ""}" data-i="${i}"><b>${esc([x.last, x.first].filter(Boolean).join(", "))}</b><span>${esc([x.num, x.email].filter(Boolean).join(" · "))}</span>${x.already ? `<em>Already in</em>` : ""}</button>`).join("")}</div>
      <div class="at-pacts"><button type="button" class="lt-btn" data-other>Someone Else</button><button type="button" class="lt-btn" data-cancel>Cancel</button></div></div>`);
    r.querySelectorAll("[data-i]").forEach(b => { b.onclick = () => { const x = L[+b.dataset.i]; x.already ? already(x, x.already) : markIn(x, ""); }; });
    r.querySelector("[data-other]").onclick = () => findStudent("");
    r.querySelector("[data-cancel]").onclick = () => { r.innerHTML = ""; resume(); };
  }
  // Find the student by name or number: a card that's unknown, or someone else's, is registered to them.
  function findStudent(card, unknown = false) {
    busy = true;
    const r = res(`<div class="at-panel find">
      <p class="gr-kind">${card ? (unknown ? "A card nobody has registered" : "Not them") : "Enter by hand"}</p>
      <p class="at-why">${card ? `Find the student: card <b>${esc(card)}</b> will be registered to them.` : "Find the student by name or number."}</p>
      <label class="at-q">${SEARCH}<input type="search" id="at-q" placeholder="Last name, first name or number" autocomplete="off" autocapitalize="words"></label>
      <div class="at-hits" id="at-hits"></div>
      <div class="at-pacts"><button type="button" class="lt-btn" data-cancel>Cancel</button></div></div>`);
    const inp = r.querySelector("#at-q"), hits = r.querySelector("#at-hits");
    r.querySelector("[data-cancel]").onclick = () => { r.innerHTML = ""; resume(); };
    let n = 0;
    inp.oninput = () => {
      const q = inp.value.trim(), k = ++n;
      if (q.length < 2) { hits.innerHTML = ""; return; }
      api(`/api/attendance/search?${Q}&q=${encodeURIComponent(q)}`).then(d => {
        if (k !== n) return;
        hits.innerHTML = d.students.length ? d.students.map((s, i) => `<button type="button" class="at-hit${s.already ? " in" : ""}" data-i="${i}"><b>${esc([s.last, s.first].filter(Boolean).join(", "))}</b><span>${esc([s.num, s.email].filter(Boolean).join(" · "))}</span>${s.already ? `<em>Already in</em>` : ""}</button>`).join("")
          : `<p class="lx-help">No one on the class list matches.</p>`;
        hits.querySelectorAll("[data-i]").forEach(b => { b.onclick = () => { const s = d.students[+b.dataset.i]; s.already ? already(s, s.already) : markIn(s, card, !card); }; });
      }, x => { hits.innerHTML = `<p class="lx-help">${esc(x.message)}</p>`; });
    };
    setTimeout(() => inp.focus(), 0);
  }
  function markIn(s, card, hand = false) {
    res(`<div class="at-panel"><p class="at-why">Putting ${esc(s.first)} in…</p></div>`);
    api("/api/attendance/mark", B({ session: S.id, student: s.num, card: card || undefined, hand: hand || undefined })).then(d => {
      buzz(120);
      S.count = d.count; O.total += 1;
      const m = $("#at-mine"); if (m) m.textContent = d.count; drawCounts();
      res(`<div class="at-panel ok"><span class="at-ok">${CHECK}</span><div><h3>${esc(`${s.first} ${s.last}`)} is in.</h3>${card ? `<p class="at-meta">Card ${esc(card)} is now registered to them.</p>` : ""}</div></div>`);
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
  // Put back after being away: the camera picks up again if it's still on; if it stopped, the overview (with Continue Scanning).
  // The section, put back (the editor redrawing, or back from taking attendance): up to date.
  host._back = () => { if (scan || !O) return; if (!polling) poll(); load().then(refreshOverview); };
  host._stop = stopCam;
  return host;
}
