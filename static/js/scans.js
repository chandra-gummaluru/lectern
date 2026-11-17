/* Print and Scan: an exam on paper (server/scanning.py), at #/<course>/<term>/scans/<exam>[/<booklet> | /questions/<label>].

   One page, top to bottom:
     Print       the student copy (kept as the copy the scans are marked against), the answer key and the marking
                 guide, as PDFs made on the server: one row per version.
     Scans       the scanned PDFs (or images) uploaded so far, + Upload Scans, and Mark the Scans (it runs on the
                 server: the page shows how far it's got).
     Results     By Booklet: whose each is, its marks so far, and what's left to look at; By Question: each question,
                 how many of its answers are done. Click one to review it.
     Gradebook   Send Marks: each finished booklet's total becomes the student's mark for the exam's evaluation.
   A booklet's own page: the cover (whose it is: confirm or pick the student), then each question with a picture of
   the answer, what the grader read, the answer, and its score to confirm or change. A question's own page: every
   booklet's answer to it, one under another (To Look At, or All), to mark one question across the class.
   Scores save as you go. */

const SVG = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const SCAN_ICON = SVG('<path d="M7 8V3h10v5"/><rect x="3" y="8" width="18" height="9" rx="2"/><path d="M7 14h10v7H7z"/>');
const UP = SVG('<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5"/><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15"/>');
const TRASH = SVG('<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>');
const DOC = SVG('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>');
const LEFT = SVG('<path d="m15 18-6-6 6-6"/>');
const PLUS = SVG('<path d="M12 5v14M5 12h14"/>');
const SEARCH = SVG('<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>');
const RIGHT = SVG('<path d="m9 18 6-6-6-6"/>');
// A question's two marks: who marked it (the computer, or by hand: yellow) and whether it's done (a check).
const COMPUTER = SVG('<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>');
const HAND = SVG('<path d="M18 11V6a2 2 0 0 0-4 0v5"/><path d="M14 10V4a2 2 0 0 0-4 0v6"/><path d="M10 10.5V6a2 2 0 0 0-4 0v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.9-6-2.4l-3.6-3.6a2 2 0 0 1 2.8-2.8L7 15"/>');
const TICK = SVG('<path d="m6 12.5 4 4L18 8"/>');
const WARN = SVG('<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2h.01"/>');
function marks(x) {
  const s = x.status, by = x.by ? ` by ${x.by}` : "";
  if (s === "missing") return { src: "", done: false, tip: "This page wasn't in the scans" };
  const computer = s === "auto" || s === "check" || (s === "done" && !x.typed && x.machine != null && x.score === x.machine);
  const done = s === "auto" || s === "done";
  const tip = computer ? (s === "auto" ? "Marked by the computer" : s === "check" ? "Marked by the computer: it wasn't sure, so look at it" : `Marked by the computer, checked${by}`)
    : done ? `Marked by hand${by}` : "To be marked by hand";
  return { src: computer ? "computer" : "hand", done, tip };
}
const marksHTML = (x, esc) => { const m = marks(x);
  return `<span class="sc-marks" title="${esc(m.tip)}" aria-label="${esc(m.tip)}">${m.src ? `<span class="sc-src">${m.src === "computer" ? COMPUTER : HAND}</span>` : ""}<span class="sc-done${m.done ? " on" : ""}">${m.done ? TICK : ""}</span></span>`; };
const fmtN = x => (x == null ? "–" : String(Math.round(x * 100) / 100));
const when = s => { const d = new Date(s * 1000); return isNaN(d) ? "" : d.toLocaleString("en-CA", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); };
const size = b => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const ui = { show: "open", q: "", by: "booklet", qShow: "", qWas: "" };
const editing = new Set();   // answers whose reading is open to type ("<booklet>|<question>")

export function scansPage({ $, esc, pageHTML, toast, confirmBox, go, api, renderPath, steps, owner, unsaved, openExam }, r) {
  const params = x => new URLSearchParams({ ...(owner ? { owner } : {}), offering: `${r.c}/${r.t}`, exam: r.e, ...x }).toString();
  const body = x => ({ ...(owner ? { owner } : {}), offering: `${r.c}/${r.t}`, exam: r.e, ...x });
  const key = location.hash;
  const here = () => location.hash === key && document.body.contains(box);
  pageHTML(`<div class="lt-in lt-scans"><div class="lx ed"><div id="sc-box"><div class="lt-loading" style="min-height:160px">Reading the exam…</div></div></div></div>`);
  const box = $("#sc-box");
  let S = null, R = null, timer = 0;
  // Whose a booklet is: "Last, First", or, not matched with confidence, "Unmatched, Student 3" and XXXXXXXXXX.
  const matched = b => b.student.status === "auto" || b.student.status === "done";
  const whoOf = b => { if (matched(b) && b.student.name) return b.student.name.split(" ").reverse().join(", ").replace(/^, /, "");
    const un = ((R && R.booklets) || []).filter(x => !matched(x)); return `Unmatched, Student ${un.indexOf(b) + 1}`; };
  const numOf = b => (matched(b) ? b.student.num : "X".repeat(((R && R.students && R.students[0] && R.students[0].num) || "0000000000").length));
  const pathTo = extra => renderPath([...steps, { label: S ? S.exam.title : "Exam", go: openExam }, ...(extra ? [{ label: "Print and Scan", go: () => go({ ...r, b: "" }) }, { label: extra }] : [{ label: "Print and Scan" }])]);

  async function load() {
    try {
      S = await api(`/api/scans?${params()}`);
      if (S.results) R = await api(`/api/scans/results?${params()}`);
    } catch (e) { if (here()) box.innerHTML = `<p class="lt-note err">Couldn't open it. ${esc(e.message)}</p>`; return; }
    if (!here()) return;
    r.q ? drawQuestion() : r.b ? drawBooklet() : draw();
    clearTimeout(timer);
    if (S.job && S.job.state === "running") timer = setTimeout(load, 1500);
  }

  // ── The page ──
  function draw() {
    pathTo();
    const X = S.exam, can = S.can, N = X.versions;
    const notes = [
      !S.latex ? `<p class="lt-note"><b>This Lectern can't make PDFs:</b> its server doesn't have LaTeX. Ask whoever runs it to install TeX Live (see the README).</p>` : "",
      !X.scan ? `<p class="lt-note"><b>Marking from scans is off for this exam.</b> Turn it on in the exam's <button type="button" class="lt-link" data-open>Settings</button> (Pages), save, then print it here: the student copy then has the corner squares and codes the grader needs.</p>` : "",
      unsaved() ? `<p class="lt-note"><b>The exam has changes that aren't saved.</b> The PDFs are made from the saved exam: save it first.</p>` : "",
      !S.eval ? `<p class="lt-note">This exam isn't linked to an evaluation in the gradebook, so its marks have nowhere to go. Open it from its evaluation's <b>Build</b> button in Evaluations.</p>` : "",
    ].join("");
    const pdfURL = (doc, v, print) => `/api/scans/pdf?${params({ doc, ...(v ? { v } : {}), ...(print ? { print: 1 } : {}) })}`;
    const copy = c => {
      const p = c.printed;
      const state = p ? `Printed ${esc(when(p.at))}${p.by ? ` by ${esc(p.by)}` : ""}${p.changed ? ` <span class="sc-warn">· the exam has changed since, so print it again before the test</span>` : ""}`
        : X.scan ? "Not printed from here yet." : "";
      return `<div class="sc-copy">${N > 1 ? `<b class="sc-v">Version ${esc(c.version)}</b>` : ""}
        <div class="sc-docs">
          <a class="lt-btn sc-sm" href="${pdfURL("student", c.version, can.print && X.scan)}" target="_blank" rel="noopener" data-print>${DOC}Student Copy</a>
          <a class="lt-btn sc-sm" href="${pdfURL("key", c.version)}" target="_blank" rel="noopener">${DOC}Answer Key</a>
          <a class="lt-btn sc-sm" href="${pdfURL("guide", c.version)}" target="_blank" rel="noopener">${DOC}Marking Guide</a></div>
        ${state ? `<p class="lx-help sc-state">${state}</p>` : ""}</div>`;
    };
    const job = S.job || {}, running = job.state === "running";
    const files = S.uploads.map(u => `<div class="sc-file">${DOC}<span class="sc-fname">${esc(u.name)}</span>
        <span class="sc-fmeta">${u.pages ? `${u.pages} page${u.pages === 1 ? "" : "s"} · ` : ""}${size(u.size)} · ${esc(when(u.at))}${u.by ? ` · ${esc(u.by)}` : ""}</span>
        ${can.upload ? `<button type="button" class="sc-del" data-del="${esc(u.file)}" title="Delete this scan" aria-label="Delete ${esc(u.name)}"${running ? " disabled" : ""}>${TRASH}</button>` : ""}</div>`).join("");
    const jobLine = running ? `<p class="sc-job"><span class="sc-spin" aria-hidden="true"></span>Marking… ${job.booklets ? `${job.booklets} booklet${job.booklets === 1 ? "" : "s"} so far` : "lining up the pages"}${job.pages ? ` (${job.pages} pages)` : ""}.</p>`
      : job.state === "failed" ? `<p class="lt-note err">${esc(job.error || "The marking stopped.")}</p>`
      : job.state === "done" ? `<p class="lx-help">Marked ${esc(when(job.finished))}${job.by ? ` by ${esc(job.by)}` : ""}: ${job.booklets} booklet${job.booklets === 1 ? "" : "s"}${job.unread ? `, ${job.unread} page${job.unread === 1 ? "" : "s"} not placed` : ""}.</p>` : "";
    const res = S.results;
    box.innerHTML = `<div class="lx-editor sc-ed">
      <div class="lx-ed-head"><span class="lx-kicon big" aria-hidden="true">${SCAN_ICON}</span>
        <div class="gr-tt"><p class="gr-kind">Print and Scan</p><h2>${esc(X.title)}${S.eval ? `<span class="lt-req-of"> / ${esc(S.eval.name)}</span>` : ""}</h2></div>
        <span class="lx-acts"><button type="button" class="lt-btn sc-sm" data-open title="Open it in the Exam Builder">${DOC}Open Exam</button>
          ${can.upload && (S.uploads.length || res) ? `<button type="button" class="lx-ic" id="sc-wipe" title="Delete the scans and results" aria-label="Delete the scans and results"${running ? " disabled" : ""}>${TRASH}</button>` : ""}</span></div>
      <p class="lt-req-meta">${fmtN(X.total)} marks${N > 1 ? ` · ${N} versions` : ""}${S.eval ? ` · for ${esc(S.eval.name)}` : ""}</p>
      ${notes}
      <h3 class="lx-sec">Print</h3>
      <p class="lx-help">Print the student copy at actual size. Scans are marked against the copy downloaded here.</p>
      ${S.copies.map(copy).join("")}
      <h3 class="lx-sec">Scans</h3>
      <p class="lx-help">Whole booklets, one after another, as PDFs of 200 dpi or more. Pages can be in any order, either way up.</p>
      ${files ? `<div class="sc-files">${files}</div>` : ""}
      <div class="sc-up" id="sc-up"></div>
      ${can.upload ? `<div class="lx-adds"><label class="lt-btn add${X.scan && !running ? "" : " sc-dis"}">${PLUS}Upload Scans<input type="file" id="sc-file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,application/pdf,image/*" multiple hidden${X.scan && !running ? "" : " disabled"}></label>
        <button type="button" class="lt-btn primary" id="sc-mark"${S.uploads.length && X.scan && !running ? "" : " disabled"}>${res ? "Mark Them Again" : "Mark the Scans"}</button></div>` : ""}
      ${jobLine}
      ${res ? resultsHTML(res) : ""}
    </div>`;
    box.querySelectorAll("[data-open]").forEach(b => { b.onclick = openExam; });
    box.querySelectorAll("[data-print]").forEach(a => { a.addEventListener("click", () => { if (a.href.includes("print=1")) setTimeout(() => here() && load(), 4000); }); });
    box.querySelectorAll("[data-del]").forEach(b => { b.onclick = async () => {
      if (!await confirmBox("Delete this scan?", "It's removed from this exam. Its results stay until you mark the scans again.", "Delete")) return;
      try { await api("/api/scans/delete", body({ file: b.dataset.del })); load(); } catch (e) { toast(e.message); } }; });
    const fi = $("#sc-file"); if (fi) fi.onchange = () => uploadAll([...fi.files]);
    const mk = $("#sc-mark"); if (mk) mk.onclick = async () => {
      mk.disabled = true;
      try { await api("/api/scans/mark", body({})); load(); } catch (e) { mk.disabled = false; toast(e.message); } };
    const wipe = $("#sc-wipe"); if (wipe) wipe.onclick = async () => {
      if (!await confirmBox("Delete the scans and results?", "The scanned pages, what was read from them, every score given here and the printed copy go. Marks already sent to the gradebook stay.", "Delete Everything")) return;
      try { await api("/api/scans/delete", body({ all: true })); R = null; load(); } catch (e) { toast(e.message); } };
    if (res) wireResults();
  }

  function resultsHTML(res) {
    const bs = (R && R.booklets) || [];
    const words = ui.q.toLowerCase().split(/\s+/).filter(Boolean);
    const hay = b => `${whoOf(b)} ${matched(b) ? b.student.num : ""} ${b.student.read || ""}`.toLowerCase();
    const found = bs.filter(b => words.every(w => hay(b).includes(w)));
    const open = found.filter(b => !b.ready), done = found.filter(b => b.ready);
    const list = ui.show === "open" ? open : ui.show === "done" ? done : found;
    const seg = (k, l, n) => `<button type="button" data-show="${k}" aria-pressed="${ui.show === k}">${l}${n != null ? ` ${n}` : ""}</button>`;
    const nameOf = b => esc(whoOf(b));
    const left = b => b.open ? `${b.open} to look at` : matched(b) ? "finished" : "student to match";
    const row = b => `<div class="dc-t lt-rq-row sc-r"><span class="lt-rq-st"><span class="sc-done${b.ready ? " on" : ""}" title="${b.ready ? "Finished" : "Not finished"}">${b.ready ? TICK : ""}</span></span>
        <button type="button" class="dc-t-b" data-b="${bs.indexOf(b) + 1}"><b class="dc-t-title">${nameOf(b)}${b.version ? `<span class="lt-dc-of"> / Version ${esc(b.version)}</span>` : ""}</b>
          <span class="dc-t-meta">${esc(numOf(b))} · ${fmtN(b.total)} of ${fmtN(b.out_of)} · ${left(b)}</span></button></div>`;
    const unread = res.unread.length ? `<p class="lt-note"><b>${res.unread.length} page${res.unread.length === 1 ? "" : "s"} couldn't be placed:</b> ${res.unread.slice(0, 8).map(u => `${esc(u.page)} (${esc(u.why)})`).join("; ")}${res.unread.length > 8 ? "; …" : ""}.</p>` : "";
    const notes = res.notes.map(n => `<p class="lt-note">${esc(n)}</p>`).join("");
    const sent = res.sent ? ` Sent ${res.sent.n} ${esc(when(res.sent.at))}${res.sent.by ? ` by ${esc(res.sent.by)}` : ""}.` : "";
    const title = ui.show === "open" ? "To Look At" : ui.show === "done" ? "Finished" : "All";
    const gradebook = `<h3 class="lx-sec">Gradebook</h3>
      <p class="lx-help">${S.eval ? `Each finished booklet's total becomes the student's mark for ${esc(S.eval.name)}.${sent}` : "This exam isn't linked to an evaluation."}</p>
      ${S.can.mark && S.eval ? `<div class="lx-adds"><button type="button" class="lt-btn primary" id="sc-send"${res.ready ? "" : " disabled"}>Send ${res.ready} Mark${res.ready === 1 ? "" : "s"} to ${esc(S.eval.name)}</button></div>` : ""}`;
    const bySeg = `<span class="lx-seg sc-by" role="group" aria-label="Show">${[["booklet", "By Booklet"], ["question", "By Question"]].map(([v, l]) => `<button type="button" data-by="${v}" aria-pressed="${ui.by === v}">${l}</button>`).join("")}</span>`;
    if (ui.by === "question") {
      const qs = labels().map(l => { const a = answersTo(l); return { l, pts: a[0] ? a[0].x.points : 0, n: a.length, open: a.filter(y => isOpen(y.x)).length, missing: a.filter(y => y.x.status === "missing").length }; });
      const qrow = q => `<div class="dc-t lt-rq-row sc-r"><span class="lt-rq-st"><span class="sc-done${q.open ? "" : " on"}" title="${q.open ? "Not finished" : "Finished"}">${q.open ? "" : TICK}</span></span>
          <button type="button" class="dc-t-b" data-gq="${esc(q.l)}"><b class="dc-t-title">Question ${esc(q.l)}</b>
            <span class="dc-t-meta">${fmtN(q.pts)} mark${q.pts === 1 ? "" : "s"} · ${q.n - q.open - q.missing} of ${q.n} done${q.open ? ` · ${q.open} to look at` : ""}</span></button></div>`;
      return `${unread}${notes}<div class="sc-bybar">${bySeg}</div>
      <div class="hb lt-dc sc-dc"><section class="dc">
        <div class="dc-head"><h2 class="ec-sec dc-title">Questions <span>· ${qs.length}</span></h2></div>
        <div class="dc-threads">${qs.map(qrow).join("")}</div>
      </section></div>
      ${gradebook}`;
    }
    return `${unread}${notes}<div class="sc-bybar">${bySeg}</div>
      <div class="hb lt-dc sc-dc"><section class="dc">
        <div class="dc-head"><h2 class="ec-sec dc-title">${title} <span>· ${list.length} booklet${list.length === 1 ? "" : "s"}</span></h2>
          <div class="dc-tools"><label class="dc-search">${SEARCH}<input type="search" id="sc-q" placeholder="Search booklets" aria-label="Search booklets" value="${esc(ui.q)}"></label>
            <div class="dc-sort" role="tablist">${seg("open", "To Look At", open.length)}${seg("done", "Finished", done.length)}${seg("all", "All", null)}</div></div></div>
        ${list.length ? `<div class="dc-threads">${list.map(row).join("")}</div>` : `<p class="dc-none">${words.length ? "No booklets match your search." : ui.show === "open" ? "Nothing left to look at." : "None yet."}</p>`}
      </section></div>
      ${gradebook}`;
  }

  function wireResults() {
    box.querySelectorAll("[data-show]").forEach(b => { b.onclick = () => { ui.show = b.dataset.show; draw(); }; });
    box.querySelectorAll("[data-by]").forEach(b => { b.onclick = () => { ui.by = b.dataset.by; draw(); }; });
    box.querySelectorAll(".sc-dc [data-gq]").forEach(b => { b.onclick = () => go({ ...r, b: "", q: b.dataset.gq }); });
    const qi = $("#sc-q"); if (qi) qi.oninput = () => { ui.q = qi.value; const at = qi.selectionStart; draw(); const i = $("#sc-q"); if (i) { i.focus(); i.setSelectionRange(at, at); } };
    box.querySelectorAll("[data-b]").forEach(b => { b.onclick = () => go({ ...r, b: b.dataset.b }); });
    const s = $("#sc-send"); if (s) s.onclick = async () => {
      s.disabled = true;
      try {
        let d = await api("/api/scans/send", body({}));
        if (d.differ.length) {
          const list = d.differ.slice(0, 6).map(x => `${x.name || x.num}: ${fmtN(x.was)} → ${fmtN(x.now)}`).join(", ");
          const ok = await confirmBox(`Replace ${d.differ.length} mark${d.differ.length === 1 ? "" : "s"}?`,
            esc(`${d.differ.length === 1 ? "A student already has" : `${d.differ.length} students already have`} a different mark for ${S.eval.name} (${list}${d.differ.length > 6 ? ", …" : ""}).${d.sent ? ` The other ${d.sent} went in.` : ""}`), "Replace Them");
          if (ok) { const again = await api("/api/scans/send", body({ replace: true })); d = { ...again, sent: d.sent + again.sent }; }
        }
        toast(d.sent ? `Sent ${d.sent} mark${d.sent === 1 ? "" : "s"} to ${S.eval.name}.` : "Nothing new to send: the gradebook has these marks already.");
        load();
      } catch (e) { s.disabled = false; toast(e.message); }
    };
  }

  // ── Uploading, a file at a time, with how far each has got ──
  async function uploadAll(files) {
    const up = $("#sc-up");
    for (const f of files) {
      const row = document.createElement("div");
      row.className = "sc-file sc-going";
      row.innerHTML = `${UP}<span class="sc-fname">${esc(f.name)}</span><span class="sc-fmeta">Uploading… <b>0%</b></span><span class="sc-bar"><i></i></span>`;
      up.append(row);
      try {
        await new Promise((ok, no) => {
          const x = new XMLHttpRequest(), fd = new FormData();
          fd.append("file", f);
          x.open("POST", `/api/scans/upload?${params()}`);
          x.setRequestHeader("X-Lectern", "1");
          x.upload.onprogress = e => { if (e.lengthComputable) { const p = Math.round(100 * e.loaded / e.total); row.querySelector("b").textContent = `${p}%`; row.querySelector(".sc-bar i").style.width = `${p}%`; } };
          x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch (_) {} x.status < 300 ? ok(d) : no(new Error(d.error || `Couldn't upload it (${x.status}).`)); };
          x.onerror = () => no(new Error("Couldn't reach Lectern's server."));
          x.send(fd);
        });
        row.remove();
      } catch (e) { row.querySelector(".sc-fmeta").textContent = e.message; row.classList.add("err"); }
    }
    if (here()) load();
  }

  // ── One booklet ──
  function drawBooklet() {
    const bs = (R && R.booklets) || [], i = Math.max(1, Math.min(bs.length, Number(r.b) || 1)), b = bs[i - 1];
    if (!b) { pathTo("Booklet"); box.innerHTML = `<p class="lx-empty">That booklet isn't there any more. <button type="button" class="lt-link" id="sc-back">See all of them</button></p>`; $("#sc-back").onclick = () => go({ ...r, b: "" }); return; }
    const st = b.student, can = S.can.mark;
    const name = whoOf(b);
    pathTo(name);
    const nextOpen = bs.findIndex((x, k) => k > i - 1 && !x.ready) + 1 || bs.findIndex(x => !x.ready && x !== b) + 1;
    const people = (R.students || []).slice().sort((a, c) => `${a.last} ${a.first}`.localeCompare(`${c.last} ${c.first}`));
    const picker = `<select id="sc-who" aria-label="Whose booklet"><option value="">Choose the student…</option>${people.map(p => `<option value="${esc(p.num)}"${p.num === st.num ? " selected" : ""}>${esc(`${p.last}, ${p.first}`)} · ${esc(p.num)}</option>`).join("")}</select>`;
    const sure = st.status === "auto" || st.status === "done";
    const cands = (st.candidates || []).filter(x => x.num !== st.num);
    const pages = b.where || (b.pages || []).join(", ");
    const q = x => qCard(x, b, `Question ${esc(x.label)}`);
    box.innerHTML = `<div class="lx-editor sc-ed sc-book">
      <div class="lx-ed-head"><span class="lx-kicon big" aria-hidden="true">${SCAN_ICON}</span>
        <div class="gr-tt"><p class="gr-kind">Booklet ${i} of ${bs.length}</p><h2>${esc(name)}<span class="lt-req-of"> / ${esc(S.exam.title)}</span></h2></div>
        <span class="lx-acts">${nextOpen ? `<button type="button" class="lt-btn sc-sm" data-go="${nextOpen}">Next to Look At</button>` : ""}
          <button type="button" class="lx-ic" data-go="${i - 1}" title="The booklet before" aria-label="The booklet before"${i > 1 ? "" : " disabled"}>${LEFT}</button><button type="button" class="lx-ic" data-go="${i + 1}" title="The next booklet" aria-label="The next booklet"${i < bs.length ? "" : " disabled"}>${RIGHT}</button></span></div>
      <p class="lt-req-meta">${esc(numOf(b))} · ${b.version ? `Version ${esc(b.version)} · ` : ""}${esc(pages)} · ${fmtN(b.total)} of ${fmtN(b.out_of)} · ${b.ready ? "finished" : `${b.open || "nothing"} to look at`}</p>
      <h3 class="lx-sec">Student</h3>
      ${b.cover ? `<img class="sc-pic sc-cover" src="${esc(b.cover)}" alt="The cover's name and number boxes, as scanned">` : ""}
      ${sure ? `<p class="lx-help">${st.status === "done" ? `Chosen${st.by ? ` by ${esc(st.by)}` : ""}.` : `Found from the student number${st.read && st.read !== st.num ? ` (read as ${esc(st.read)})` : ""}.`}</p>`
        : `<p class="sc-note">${WARN}<span>${esc(st.note || "Not sure whose booklet this is. Check the cover.")}${st.read ? ` The number reads as ${esc(st.read)}.` : ""}</span></p>`}
      ${can ? `<div class="sc-pick">${!sure ? [st.num && { num: st.num, name: st.name }, ...cands].filter(Boolean).slice(0, 3).map(x => `<button type="button" class="lt-btn sc-sm" data-cand="${esc(x.num)}">${esc(x.name || x.num)} · ${esc(x.num)}</button>`).join("") : ""}${picker}</div>` : ""}
      <h3 class="lx-sec">Questions</h3>
      <p class="lx-help sc-key"><span class="sc-src">${COMPUTER}</span> marked by the computer <span class="sc-src">${HAND}</span> marked by hand <span class="sc-done on">${TICK}</span> done <span class="sc-done"></span> not done yet</p>
      <div class="sc-qs">${b.questions.map(q).join("")}</div>
    </div>`;
    box.querySelectorAll("[data-go]").forEach(x => { x.onclick = () => go({ ...r, b: x.dataset.go }); });
    const save = what => review(b, what).then(ok => { if (ok) { const y = window.scrollY; drawBooklet(); window.scrollTo(0, y); } });
    box.querySelectorAll("[data-cand]").forEach(x => { x.onclick = () => save({ student: x.dataset.cand }); });
    const w = $("#sc-who"); if (w) w.onchange = () => save({ student: w.value });
    wireCards(drawBooklet);
  }

  // ── One question, in every booklet ──
  // The questions, in the exam's order (each booklet has the same labels; versions may differ in their answers).
  const labels = () => { const seen = []; ((R && R.booklets) || []).forEach(b => b.questions.forEach(x => { if (!seen.includes(x.label)) seen.push(x.label); })); return seen; };
  const answersTo = label => ((R && R.booklets) || []).map(b => ({ b, x: b.questions.find(y => y.label === label) })).filter(a => a.x);
  const isOpen = x => x.status === "check" || x.status === "manual";
  function drawQuestion() {
    const L = labels(), k = L.indexOf(r.q), all = answersTo(r.q);
    if (k < 0) { pathTo("Question"); box.innerHTML = `<p class="lx-empty">That question isn't in the results. <button type="button" class="lt-link" id="sc-back">See all of them</button></p>`; $("#sc-back").onclick = () => go({ ...r, q: "" }); return; }
    pathTo(`Question ${r.q}`);
    const open = all.filter(a => isOpen(a.x)), pts = all[0] ? all[0].x.points : 0;
    if (!ui.qShow || (ui.qShow === "open" && !open.length && ui.qWas !== r.q)) ui.qShow = open.length ? "open" : "all";
    ui.qWas = r.q;
    const list = ui.qShow === "open" ? open : all;
    const nextOpen = L.slice(k + 1).concat(L.slice(0, k)).find(l => answersTo(l).some(a => isOpen(a.x)));
    const answers = [...new Set(all.map(a => a.x.answer).filter(Boolean))];
    const who = a => esc(whoOf(a.b));
    const seg = (v, l, n) => `<button type="button" data-qshow="${v}" aria-pressed="${ui.qShow === v}">${l}${n != null ? ` ${n}` : ""}</button>`;
    box.innerHTML = `<div class="lx-editor sc-ed sc-book">
      <div class="lx-ed-head"><span class="lx-kicon big" aria-hidden="true">${SCAN_ICON}</span>
        <div class="gr-tt"><p class="gr-kind">Every Booklet's Answer</p><h2>Question ${esc(r.q)}<span class="lt-req-of"> / ${esc(S.exam.title)}</span></h2></div>
        <span class="lx-acts">${nextOpen ? `<button type="button" class="lt-btn sc-sm" data-gq="${esc(nextOpen)}">Next to Look At</button>` : ""}
          <button type="button" class="lx-ic" data-gq="${esc(L[k - 1] || "")}" title="The question before" aria-label="The question before"${k > 0 ? "" : " disabled"}>${LEFT}</button><button type="button" class="lx-ic" data-gq="${esc(L[k + 1] || "")}" title="The next question" aria-label="The next question"${k < L.length - 1 ? "" : " disabled"}>${RIGHT}</button></span></div>
      <p class="lt-req-meta">${fmtN(pts)} mark${pts === 1 ? "" : "s"}${answers.length ? ` · answer ${answers.map(esc).join(" or ")}` : ""} · ${all.length - open.length} of ${all.length} done</p>
      <div class="hb lt-dc sc-dc"><section class="dc"><div class="dc-head"><h2 class="ec-sec dc-title">${ui.qShow === "open" ? "To Look At" : "Every Answer"} <span>· ${list.length}</span></h2>
        <div class="dc-tools"><div class="dc-sort" role="tablist">${seg("open", "To Look At", open.length)}${seg("all", "All", all.length)}</div></div></div>
        ${list.length ? "" : `<p class="dc-none">Nothing left to look at in this question.${nextOpen ? ` <button type="button" class="lt-link" data-gq="${esc(nextOpen)}">Question ${esc(nextOpen)}</button> has some.` : ""}</p>`}</section></div>
      <p class="lx-help sc-key"><span class="sc-src">${COMPUTER}</span> marked by the computer <span class="sc-src">${HAND}</span> marked by hand <span class="sc-done on">${TICK}</span> done <span class="sc-done"></span> not done yet</p>
      <div class="sc-qs">${list.map(a => qCard(a.x, a.b, `<button type="button" class="lt-link sc-qwho" data-book="${(R.booklets.indexOf(a.b)) + 1}" title="Open their booklet">${who(a)}</button>${a.b.version ? `<span class="sc-qv">Version ${esc(a.b.version)}</span>` : ""}`)).join("")}</div>
    </div>`;
    box.querySelectorAll("[data-gq]").forEach(x => { x.onclick = () => x.dataset.gq && go({ ...r, b: "", q: x.dataset.gq }); });
    box.querySelectorAll("[data-qshow]").forEach(x => { x.onclick = () => { ui.qShow = x.dataset.qshow; drawQuestion(); }; });
    box.querySelectorAll("[data-book]").forEach(x => { x.onclick = () => go({ ...r, q: "", b: x.dataset.book }); });
    wireCards(drawQuestion);
  }

  // A question's answer, as a card: who marked it and whether it's done, its score, a picture of it, what was read.
  function qCard(x, b, title) {
    const s = x.status, can = S.can.mark && s !== "missing", id = `${b.key}|${x.label}`;
    const choice = Array.isArray(x.options), readable = choice || x.read != null;
    const open = can && readable && (editing.has(id) || (s === "manual" && x.ask === "type"));
    const ask = s === "check" ? x.ask : "";
    const readV = x.read == null || x.read === "" ? "nothing" : x.read;
    let read = "";
    if (readable) {
      const shown = open && !choice
        ? `<input class="sc-readin" type="text" value="${esc(x.read || "")}" placeholder="What does it say?" aria-label="What the answer says" spellcheck="false">`
        : can ? `<button type="button" class="sc-readv" data-edit title="Not what it says? Click to change it">${esc(readV)}</button>` : `<b>${esc(readV)}</b>`;
      read = `<p class="sc-read">${choice && (open || ask === "choice") ? "" : `Read: ${shown}`}${x.answer ? `${choice && (open || ask === "choice") ? "" : " · "}Answer: <b>${esc(x.answer)}</b>` : ""}${x.typed ? ` <span class="sc-by">(typed${x.by ? ` by ${esc(x.by)}` : ""})</span>` : ""}</p>`;
    }
    const pick = choice && can && (open || ask === "choice") ? `<div class="sc-qa"><span class="sc-qlab">Their answer:</span><span class="lx-seg" role="group">${x.options.map(o => `<button type="button" data-opt="${esc(o)}" aria-pressed="${x.multi ? String(x.read).split(", ").includes(o) : x.read === o}">${esc(o)}</button>`).join("")}</span>${x.multi ? `<button type="button" class="lt-btn sc-sm" data-optsave>Save</button>` : ""}${editing.has(id) ? `<button type="button" class="lt-btn sc-sm" data-readcancel>Cancel</button>` : ""}</div>` : "";
    const note = s === "missing" ? `<p class="sc-note">${WARN}<span>This page wasn't in the scans.</span></p>` : ask && x.note ? `<p class="sc-note">${WARN}<span>${esc(x.note)}</span></p>` : "";
    const acts = !can ? ""
      : open && !choice ? `<div class="sc-qa"><button type="button" class="lt-btn sc-sm primary" data-readsave>Save</button>${s !== "manual" ? `<button type="button" class="lt-btn sc-sm" data-readcancel>Cancel</button>` : ""}${s === "manual" ? `<button type="button" class="lt-btn sc-sm" data-full>Full Marks</button><button type="button" class="lt-btn sc-sm" data-zero>Zero</button>` : ""}</div>`
      : ask === "read" ? `<div class="sc-qa"><button type="button" class="lt-btn sc-sm" data-yes>Yes</button><button type="button" class="lt-btn sc-sm" data-no>No</button></div>`
      : ask === "working" ? `<div class="sc-qa"><button type="button" class="lt-btn sc-sm" data-yes title="Give part marks in the score box">Yes</button><button type="button" class="lt-btn sc-sm" data-keep>No</button></div>`
      : s === "manual" ? `<div class="sc-qa"><button type="button" class="lt-btn sc-sm" data-full>Full Marks</button><button type="button" class="lt-btn sc-sm" data-zero>Zero</button></div>`
      : s === "done" ? `<div class="sc-qa"><button type="button" class="lt-link sc-undo" data-undo>Undo</button></div>` : "";
    return `<div class="sc-q st-${s}" data-k="${esc(b.key)}" data-q="${esc(x.label)}">
        <div class="sc-qh"><b>${title}</b>${marksHTML(x, esc)}
          <span class="sc-score"><input type="number" min="0" max="${x.points}" step="0.5" value="${x.score == null ? "" : fmtN(x.score)}" aria-label="Score"${can ? "" : " disabled"}><span>/ ${fmtN(x.points)}</span></span></div>
        ${x.picture ? `<img class="sc-pic" src="${esc(x.picture)}" alt="The answer, as scanned" loading="lazy">` : ""}
        ${read}${note}${pick}${acts}
      </div>`;
  }
  // A decision about a booklet (its student, or a question's score): saved, and the booklet as it is now kept.
  async function review(b, what, el) {
    try {
      const d = await api("/api/scans/review", body({ booklet: b.key, ...what }));
      const i = R.booklets.findIndex(x => x.key === b.key);
      if (i >= 0) R.booklets[i] = d.booklet;
      api(`/api/scans?${params()}`).then(x => { S = x; }).catch(() => {});
      return true;
    } catch (e) { toast(e.message); if (el) el.focus(); return false; }
  }
  function wireCards(redraw) {
    box.querySelectorAll(".sc-q[data-k]").forEach(el => {
      const b = R.booklets.find(y => y.key === el.dataset.k), x = b && b.questions.find(y => y.label === el.dataset.q), inp = el.querySelector(".sc-score input");
      if (!x) return;
      const id = `${b.key}|${x.label}`;
      // After a decision, the page is drawn again where it was (on a question's To Look At, the card it was leaves the list).
      const again = ok => { if (ok) { editing.delete(id); const y = window.scrollY; redraw(); window.scrollTo(0, y); } };
      const put = v => review(b, { label: x.label, score: v }, inp).then(again);
      const say = text => review(b, { label: x.label, read: text }).then(again);
      inp.onchange = () => { const v = inp.value.trim(); if (v === "") return; const n = Number(v); if (!(n >= 0 && n <= x.points)) { toast(`A score from 0 to ${fmtN(x.points)}.`); inp.value = x.score == null ? "" : fmtN(x.score); return; } put(n); };
      inp.onkeydown = e => { if (e.key === "Enter") inp.blur(); };
      const on = (sel, fn) => { const k = el.querySelector(sel); if (k) k.onclick = fn; };
      const editNow = () => { editing.add(id); const y = window.scrollY; redraw(); window.scrollTo(0, y);
        const ri = box.querySelector(`.sc-q[data-k="${CSS.escape(b.key)}"][data-q="${CSS.escape(x.label)}"] .sc-readin`); if (ri) { ri.focus(); ri.select(); } };
      on("[data-yes]", () => (x.ask === "working" ? (inp.focus(), inp.select()) : put(x.score)));
      on("[data-keep]", () => put(x.score));
      on("[data-no]", editNow);
      on("[data-edit]", editNow);
      on("[data-full]", () => put(x.points));
      on("[data-zero]", () => put(0));
      on("[data-undo]", () => put(null));
      on("[data-readcancel]", () => { editing.delete(id); const y = window.scrollY; redraw(); window.scrollTo(0, y); });
      const ri = el.querySelector(".sc-readin");
      if (ri) {
        on("[data-readsave]", () => say(ri.value));
        ri.onkeydown = e => { if (e.key === "Enter") say(ri.value); if (e.key === "Escape") { editing.delete(id); redraw(); } };
      }
      const opts = [...el.querySelectorAll("[data-opt]")];
      opts.forEach(o => { o.onclick = () => {
        if (!x.multi) return say(o.dataset.opt);
        o.setAttribute("aria-pressed", String(o.getAttribute("aria-pressed") !== "true")); }; });
      on("[data-optsave]", () => say(opts.filter(o => o.getAttribute("aria-pressed") === "true").map(o => o.dataset.opt).join("")));
    });
  }

  load();
  return { leave: () => clearTimeout(timer) };
}
