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
import { pickMany } from "./pick.js";

const SVG = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const SCAN_ICON = SVG('<path d="M7 8V3h10v5"/><rect x="3" y="8" width="18" height="9" rx="2"/><path d="M7 14h10v7H7z"/>');
const UP = SVG('<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5"/><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15"/>');
const TRASH = SVG('<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>');
const DOC = SVG('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>');
const LEFT = SVG('<path d="m15 18-6-6 6-6"/>');
const PLUS = SVG('<path d="M12 5v14M5 12h14"/>');
const SEARCH = SVG('<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>');
const RIGHT = SVG('<path d="m9 18 6-6-6-6"/>');
const LET = "ABCDEF";
// The grader's warning, short: its first sentence ("Not sure of the handwriting.").
// A little pie for "x / y": how much of it is done (full, and green, when it all is).
const pie = (n, of) => {
  const f = of ? Math.max(0, Math.min(1, n / of)) : 0, a = 2 * Math.PI * f;
  const wedge = f >= 1 ? `<circle cx="6" cy="6" r="5"/>` : f > 0 ? `<path d="M6 6V1A5 5 0 ${f > 0.5 ? 1 : 0} 1 ${(6 + 5 * Math.sin(a)).toFixed(2)} ${(6 - 5 * Math.cos(a)).toFixed(2)}Z"/>` : "";
  return `<svg class="sc-pie${f >= 1 ? " full" : ""}" viewBox="0 0 12 12" aria-hidden="true"><circle class="o" cx="6" cy="6" r="5.25"/>${wedge}</svg>`;
};
const firstSentence = t => (String(t || "").match(/^.*?[.?!](\s|$)/) || [String(t || "")])[0].trim();
const TICK = SVG('<path d="m6 12.5 4 4L18 8"/>');
// The Scans steps' icons: pages scanned, a student matched, a booklet graded.
const PAGES = SVG('<path d="M8 3h7l4 4v11a1.5 1.5 0 0 1-1.5 1.5H8A1.5 1.5 0 0 1 6.5 18V4.5A1.5 1.5 0 0 1 8 3z"/><path d="M15 3v4h4"/><path d="M3.5 7v12.5A1.5 1.5 0 0 0 5 21h9.5"/>');
const PERSON = SVG('<circle cx="12" cy="8" r="3.6"/><path d="M5 20.2c.9-3.7 3.7-5.7 7-5.7s6.1 2 7 5.7"/>');
const GRADED = SVG('<rect x="4" y="4" width="16" height="16" rx="2.5"/><path d="m8.5 12.3 2.4 2.4 4.7-5.1"/>');
const CROSS = SVG('<path d="M7 7l10 10M17 7 7 17"/>');
const WARN = SVG('<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2h.01"/>');
const fmtN = x => (x == null ? "–" : String(Math.round(x * 100) / 100));
// A booklet's mark, as the course page and gradebook show one: the percent big, its points under it.
const markHTML = b => { const pc = b.out_of ? Math.round(b.total / b.out_of * 1000) / 10 : null;
  return `<div class="sc-mk"><b>${pc != null ? `${fmtN(pc)}%` : fmtN(b.total)}</b><small>${fmtN(b.total)} / ${fmtN(b.out_of)}${b.ready ? "" : " so far"}</small></div>`; };
const when = s => { const d = new Date(s * 1000); return isNaN(d) ? "" : d.toLocaleString("en-CA", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); };
const size = b => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
// Booklet Matching's page (whose each booklet is), in the questions' place in the address: #/…/scans/<exam>/questions/students.
const MATCH = "students";
// Booklets Scanned's page (its uploads, and Upload Scans): #/…/scans/<exam>/questions/scans.
const UPLOADS = "scans";
const ui = { mSkip: [], show: "open", q: "", by: "question", allFor: "", sentKey: "", differ: [], qShow: "", qWas: "", sure: false, keep: new Set(), keepFor: "", fixing: false, fixWas: "", fixCur: "", fixDone: 0, pending: null };
const editing = new Set();   // answers whose reading is open to type ("<booklet>|<question>")
const adding = new Set();    // answers with the New Comment form open
const noting = new Set();    // answers with the note box opened, though it has no note yet
// A comment's marks as the marking guide writes them: −1, +2, ±0.
const dl = d => (d == null ? "" : d > 0 ? `+${fmtN(d)}` : d < 0 ? `−${fmtN(-d)}` : "±0");

// into: an element to draw the Scans part in (an evaluation's page in Grades, in its Scripts and Scans); drawn there, its
// booklets, questions and Fix Scans still open as pages of their own, and come back to the evaluation (openEval).
export function scansPage({ $, esc, pageHTML, toast, confirmBox, go, api, renderPath, steps, owner, unsaved, openExam, openEval, into, sending, scriptName, listInto }, r) {
  const params = x => new URLSearchParams({ ...(owner ? { owner } : {}), offering: `${r.c}/${r.t}`, exam: r.e, ...x }).toString();
  const body = x => ({ ...(owner ? { owner } : {}), offering: `${r.c}/${r.t}`, exam: r.e, ...x });
  const key = location.hash;
  const here = () => location.hash === key && document.body.contains(box);
  if (!into) pageHTML(`<div class="lt-in lt-scans"><div class="lx ed"><div id="sc-box"><div class="lt-loading" style="min-height:160px">Reading the exam…</div></div></div></div>`);
  else into.innerHTML = `<div class="sc-embed"><p class="lx-help">Reading the scans…</p></div>`;
  const box = into ? into.firstChild : $("#sc-box");
  let S = null, R = null, timer = 0;
  // Whose a booklet is: "Last, First", or, not matched with confidence, "Unmatched, Student 3" and XXXXXXXXXX.
  const matched = b => b.student.status === "auto" || b.student.status === "done";
  const whoOf = b => { if (matched(b) && b.student.name) return b.student.name.split(" ").reverse().join(", ").replace(/^, /, "");
    const un = ((R && R.booklets) || []).filter(x => !matched(x)); return `Unmatched, Student ${un.indexOf(b) + 1}`; };
  const numOf = b => (matched(b) ? b.student.num : "X".repeat(((R && R.students && R.students[0] && R.students[0].num) || "0000000000").length));
  // Back from a booklet, a question or Fix Scans: to the evaluation the exam is linked to (its Scans are there), or
  // else to this exam's own Print and Scan page.
  const home = () => (S && S.eval && openEval ? openEval(S.eval.id) : go({ ...r, b: "", q: "" }));
  const pathTo = extra => { if (into) return;
    renderPath(S && S.eval && openEval ? [...steps, { label: "Evaluations", go: () => openEval("") }, { label: S.eval.name, go: () => openEval(S.eval.id) }, { label: extra || "Scans" }]
      : [...steps, { label: S ? S.exam.title : "Exam", go: openExam }, ...(extra ? [{ label: "Print and Scan", go: home }, { label: extra }] : [{ label: "Print and Scan" }])]); };

  async function load() {
    try {
      S = await api(`/api/scans?${params()}`);
      if (S.results) R = await api(`/api/scans/results?${params()}`);
    } catch (e) {
      if (!here()) return;
      if (into) {     // its script, not saved yet (or not readable): Edit, and Upload Scans greyed out, with why
        box.innerHTML = `<div class="lx-adds sc-top"><button type="button" class="lt-btn" id="sc-edit">${DOC}Edit ${esc(scriptName || "Script")}</button><button type="button" class="lt-btn" disabled>${PLUS}Upload Scans</button></div>
          <p class="lx-help">${esc(e.message)}</p>`;
        box.querySelector("#sc-edit").onclick = openExam;
      } else box.innerHTML = `<p class="lt-note err">Couldn't open it. ${esc(e.message)}</p>`;
      return; }
    if (!here()) return;
    into ? draw() : r.q === MATCH ? drawMatching() : r.q === UPLOADS ? drawUploads() : r.q ? drawQuestion() : r.b ? drawBooklet() : draw();
    clearTimeout(timer);
    if ((S.job && S.job.state === "running") || (S.results && S.results.mail && S.results.mail.state === "running")) timer = setTimeout(load, 1500);
  }

  // ── The page ──
  function draw() {
    pathTo();
        const X = S.exam, can = S.can, N = X.versions, what = X.layout === "handout" ? "handout" : "exam";   // what it is, in words
    const notes = [
      !S.latex ? `<p class="lt-note"><b>This Lectern can't make PDFs:</b> its server doesn't have LaTeX. Ask whoever runs it to install TeX Live (see the README).</p>` : "",
      !X.scan ? `<p class="lt-note"><b>Marking from scans is off for this ${what}.</b> Tick Marking from Scans in the <button type="button" class="lt-link" data-open>Exam Builder</button> (with nothing selected), save, then print it ${into ? "from the Exam Builder (Student Copy)" : "here"}: the student copy then has the corner squares and codes the grader needs.</p>` : "",
      unsaved() ? `<p class="lt-note"><b>The exam has changes that aren't saved.</b> The PDFs are made from the saved exam: save it first.</p>` : "",
      !S.eval && !into ? `<p class="lt-note">This exam isn't linked to an evaluation in the gradebook, so its marks have nowhere to go. Open it from its evaluation's <b>Build</b> button in Evaluations.</p>` : "",
    ].join("");
    const pdfURL = (doc, v, print) => `/api/scans/pdf?${params({ doc, ...(v ? { v } : {}), ...(print ? { print: 1 } : {}) })}`;
    const copy = c => {
      const p = c.printed;
      const state = p ? `Printed ${esc(when(p.at))}${p.by ? ` by ${esc(p.by)}` : ""}${p.changed ? ` <span class="sc-warn">· the ${what} has changed since, so print it again before handing it out</span>` : ""}`
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
    if (into) {
      // As Crowdmark: how many booklets are in, fully scanned, of how many wrote it (its attendance, else the class),
      // as scans are uploaded (each upload is marked by itself); then what needs a look; then Upload Scans, Fix
      // Scans and Grading (its booklets and questions, sending marks and emailing booklets, on a page of its own).
      const bs = (R && R.booklets) || [], want = (S.wrote && S.wrote.n) || 0;
      const whole = bs.filter(b => !(b.missing || []).length).length, part = bs.length - whole;
      const partNum = bs.filter(b => (b.missing || []).length && b.booklet != null).length, twins = bs.filter(b => b.twins).length;
      const loose = bs.filter(b => !matched(b)).length, unread = res ? res.unread.length : 0;
      const fresh = S.uploads.some(u => u.at > (job.finished || 0));   // not read yet (it couldn't start, or stopped)
      const ok = X.scan && !running, pct = want ? Math.min(100, Math.round(100 * whole / want)) : 0;
      const pl = (n, one, many) => `${n} ${n === 1 ? one : many}`;
      const ready = bs.filter(b => b.ready).length, freshMail = bs.filter(b => b.ready && !b.emailed).length;
      const m = (res && res.mail) || {}, mailing = m.state === "running";
      const allDone = bs.length > 0 && ready === bs.length, nMatched = bs.length - loose;
      // Two buttons: the script (in the Exam Builder) and Upload Scans; how many are scanned is the list's first row.
      const meter = `<div class="lx-adds sc-top"><button type="button" class="lt-btn" id="sc-edit" title="Its questions, answers and marking scheme, and its PDFs, in the Exam Builder">${DOC}Edit ${what === "handout" ? "Handout" : "Test"} Script</button>${res && S.can.print ? `<button type="button" class="lt-btn" id="sc-email"${allDone && !mailing ? "" : " disabled"} title="${allDone ? "Email each student their own booklet, marked: their pages with each question's score and comments drawn on, as a PDF" : "Once every booklet is graded"}">Email ${allDone ? (freshMail && freshMail < ready ? `${freshMail} New Booklet${freshMail === 1 ? "" : "s"}` : `${ready} Booklet${ready === 1 ? "" : "s"}`) : "Booklets"}</button>` : ""}</div>
        ${ui.differ && ui.differ.length ? `<ul class="sc-looks"><li>${pl(ui.differ.length, "student already has", "students already have")} a different mark in the gradebook: <button type="button" class="lt-link" id="sc-replace">use the scanned ${ui.differ.length === 1 ? "mark" : "marks"}</button></li></ul>` : ""}
        ${job.state === "failed" ? `<p class="lt-note err">${esc(job.error || "The marking stopped.")} <button type="button" class="lt-link" data-scans>See the scans</button></p>` : ""}`;
      const sentLine = !res ? "" : [res.sent ? `Marks last put in the gradebook ${esc(when(res.sent.at)).replace(/\.$/, "")}.` : "",
        mailing ? `Emailing… ${m.done || 0} of ${m.total || 0}.` : m.state === "done" ? `Emailed ${(m.total || 0) - (m.failed || []).length} of ${m.total || 0} booklets ${esc(when(m.finished))}.` : ""].filter(Boolean).join(" ");
      const acts = "";
      // Printed, and the test changed since: say so (nothing else about the printing here).
      const changed = S.copies.some(c => c.printed && c.printed.changed);
      const pages = S.uploads.reduce((t, u) => t + (u.pages || 0), 0);
      // Part of the evaluation's Scripts and Scans (no heading of its own): the scans, under the script.
      box.innerHTML = `${notes}
        ${changed ? `<p class="lt-note">The ${what === "handout" ? "handout" : "test"} has changed since it was printed: print it again before handing it out.</p>` : ""}
        ${meter}
        <div class="sc-up" id="sc-up"></div>
        ${X.scan ? `<div class="sc-qlist${res ? "" : " off"}">${res ? resultsHTML(res) : `<div class="hb lt-dc sc-dc"><section class="dc">
          <div class="dc-threads">${scanRow(true)}${matchRow(null, true)}${questionRows((S.questions || []).map(l => ({ l })), true)}</div></section></div>`}</div>` : ""}

        ${sentLine ? `<p class="lx-help sc-sent">${sentLine}</p>` : ""}${m.state === "failed" ? `<p class="lt-note err">${esc(m.error || "The emails stopped.")}</p>` : ""}
        `;
    } else if (S.eval && openEval) {
      return openEval(S.eval.id);     // its questions and booklets are on the evaluation's page now
    } else
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
    const ed = box.querySelector("#sc-edit"); if (ed) ed.onclick = openExam;
    box.querySelectorAll("[data-print]").forEach(a => { a.addEventListener("click", () => { if (a.href.includes("print=1")) setTimeout(() => here() && load(), 4000); }); });
    wireFiles();
    box.querySelectorAll("[data-scans]").forEach(b => { b.onclick = () => { window.scrollTo(0, 0); go({ ...r, b: "", q: UPLOADS }); }; });
    if (into) {          // Assign Graders, on and off (before the scans too); its dropdowns
      if (into && canAssign()) {
        mountGraders();
        // A dropdown in the scrolling list opens upwards when there isn't room for its list under it in the list.
        box.querySelector(".sc-qlist")?.addEventListener("click", e => { const h = e.target.closest("[data-gpk]"); if (!h) return;
          const list = h.closest(".dc-threads");
          requestAnimationFrame(() => { const pop = h.querySelector(".pk-pop"); if (!pop || !list) return;
            const below = list.getBoundingClientRect().bottom - h.getBoundingClientRect().bottom;
            h.classList.toggle("up", below < pop.offsetHeight + 8); }); });
      }
    }
    if (into && res) {
      wireResults();       // its questions (or booklets), and Email Booklets
      const rp = box.querySelector("#sc-replace"); if (rp) rp.onclick = () => autoSend(true);
      autoSend(false);
    } else if (res) wireResults();
    // On the evaluation's page, the Grading list goes in its Marks section (listInto), not under the buttons.
    if (into && listInto) { const q = box.querySelector(".sc-qlist"); listInto.replaceChildren(...(q ? [q] : [])); }
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
          <span class="dc-t-meta">${b.booklet != null ? `Booklet ${b.booklet} · ` : ""}${esc(numOf(b))} · ${fmtN(b.total)} / ${fmtN(b.out_of)} · ${left(b)}${(b.missing || []).length ? ` · page${b.missing.length === 1 ? "" : "s"} ${b.missing.join(", ")} missing` : ""}</span></button></div>`;
    const unread = into ? "" : res.unread.length ? `<p class="lt-note"><b>${res.unread.length} page${res.unread.length === 1 ? "" : "s"} couldn't be placed:</b> ${res.unread.slice(0, 8).map(u => `${esc(u.page)} (${esc(u.why)})`).join("; ")}${res.unread.length > 8 ? "; …" : ""}.</p>` : "";
    const notes = res.notes.map(n => `<p class="lt-note">${esc(n)}</p>`).join("");
    const sent = res.sent ? ` Sent ${res.sent.n} ${esc(when(res.sent.at))}${res.sent.by ? ` by ${esc(res.sent.by)}` : ""}.` : "";
    const title = ui.show === "open" ? "To Look At" : ui.show === "done" ? "Finished" : "All";
    const gradebook = `<h3 class="lx-sec">Gradebook</h3>
      <p class="lx-help">${S.eval ? `Each finished booklet's total becomes the student's mark for ${esc(S.eval.name)}.${sent}` : "This exam isn't linked to an evaluation."}</p>
      ${S.can.mark && S.eval ? `<div class="lx-adds"><button type="button" class="lt-btn primary" id="sc-send"${res.ready ? "" : " disabled"}>Send ${res.ready} Mark${res.ready === 1 ? "" : "s"} to ${esc(S.eval.name)}</button></div>` : ""}`;
    // Each student their own booklet, marked, by email (a PDF of their pages with the scores and comments drawn on).
    const m = res.mail || {}, mailing = m.state === "running", ready = bs.filter(b => b.ready).length, fresh = bs.filter(b => b.ready && !b.emailed).length;
    const mailLine = mailing ? `<p class="sc-job"><span class="sc-spin" aria-hidden="true"></span>Emailing… ${m.done || 0} of ${m.total || 0}.</p>`
      : m.state === "failed" ? `<p class="lt-note err">${esc(m.error || "The emails stopped.")}</p>`
      : m.state === "done" ? `<p class="lx-help">Emailed ${esc(when(m.finished))}${m.by ? ` by ${esc(m.by)}` : ""}: ${(m.total || 0) - (m.failed || []).length} of ${m.total || 0}${m.answers ? ", with the right answers" : ""}.</p>${(m.failed || []).length ? `<p class="lt-note err"><b>${m.failed.length} didn't go:</b> ${m.failed.slice(0, 6).map(f => `${esc(f.name)} (${esc(f.why)})`).join("; ")}${m.failed.length > 6 ? "; …" : ""}.</p>` : ""}` : "";
    const students = `<h3 class="lx-sec">Marked Booklets</h3>
      <p class="lx-help">Email each student their own booklet, marked: their pages, with each question's score and comments drawn on, as a PDF. Only finished booklets go.${res.emailed ? ` ${res.emailed} emailed so far.` : ""}</p>
      ${S.can.print ? `<div class="lx-adds"><button type="button" class="lt-btn" id="sc-email"${ready && !mailing ? "" : " disabled"}>Email ${fresh && fresh < ready ? `${fresh} New Booklet${fresh === 1 ? "" : "s"}` : `${ready} Booklet${ready === 1 ? "" : "s"}`}</button></div>` : ""}
      ${mailLine}`;
    // Fix Scans: once marked, go through what the grader wasn't sure of, question by question.
    const unsureN = labels().reduce((t, l) => t + unsureIn(l).length, 0);
    const fixBar = S.can.mark && !into && !(S.eval && openEval) ? `<div class="sc-fixbar"><button type="button" class="lt-btn${unsureN ? " primary" : ""}" id="sc-fix"${unsureN ? "" : " disabled"}>Fix Scans</button>
      <span class="lx-help">${unsureN ? `${unsureN} answer${unsureN === 1 ? "" : "s"} the computer wasn't sure how to read, in ${fixLabels().length} question${fixLabels().length === 1 ? "" : "s"}.` : "Every answer the computer marks was read with confidence, or has been checked."}</span></div>` : "";
    const linked = into || (S.eval && openEval);   // on the evaluation's page: Send Marks and Email Booklets are its buttons
    const bySeg = `<span class="lx-seg sc-by" role="group" aria-label="Show">${[["booklet", "By Booklet"], ["question", "By Question"]].map(([v, l]) => `<button type="button" data-by="${v}" aria-pressed="${ui.by === v}">${l}</button>`).join("")}</span>`;
    if (into || ui.by === "question") {          // on the evaluation's page: always by question (Match Booklets finds the booklets)
      const qs = labels().map(l => { const a = answersTo(l); return { l, hand: byHand(l), pts: a[0] ? a[0].x.points : 0, n: a.length, open: a.filter(y => isOpen(y.x)).length, missing: a.filter(y => y.x.status === "missing").length }; });
      return `${unread}${notes}${fixBar}${into ? "" : `<div class="sc-bybar">${bySeg}</div>`}
      <div class="hb lt-dc sc-dc"><section class="dc">
        ${into ? "" : `<div class="dc-head"><h2 class="ec-sec dc-title">Questions <span>· ${qs.length}</span></h2></div>`}
        <div class="dc-threads">${into ? scanRow() + matchRow(bs) : ""}${questionRows(qs)}</div>
      </section></div>
      ${linked ? "" : `${gradebook}${students}`}`;
    }
    return `${unread}${notes}${fixBar}<div class="sc-bybar">${bySeg}</div>
      <div class="hb lt-dc sc-dc"><section class="dc">
        <div class="dc-head"><h2 class="ec-sec dc-title">${title} <span>· ${list.length} booklet${list.length === 1 ? "" : "s"}</span></h2>
          <div class="dc-tools"><label class="dc-search">${SEARCH}<input type="search" id="sc-q" placeholder="Search booklets" aria-label="Search booklets" value="${esc(ui.q)}"></label>
            <div class="dc-sort" role="tablist">${seg("open", "To Look At", open.length)}${seg("done", "Finished", done.length)}${seg("all", "All", null)}</div></div></div>
        ${list.length ? `<div class="dc-threads">${list.map(row).join("")}</div>` : `<p class="dc-none">${words.length ? "No booklets match your search." : ui.show === "open" ? "Nothing left to look at." : "None yet."}</p>`}
      </section></div>
      ${linked ? "" : `${gradebook}${students}`}`;
  }

  function wireResults() {
    box.querySelectorAll("[data-show]").forEach(b => { b.onclick = () => { ui.show = b.dataset.show; draw(); }; });
    box.querySelectorAll("[data-by]").forEach(b => { b.onclick = () => { ui.by = b.dataset.by; draw(); }; });
    box.querySelectorAll(".sc-dc [data-gq]").forEach(b => { b.onclick = () => openQ(b.dataset.gq); });
    box.querySelectorAll(".sc-dc [data-match]").forEach(b => { b.onclick = () => { ui.mSkip = []; window.scrollTo(0, 0); go({ ...r, b: "", q: MATCH }); }; });
    const qi = box.querySelector("#sc-q"); if (qi) qi.oninput = () => { ui.q = qi.value; const at = qi.selectionStart; draw(); const i = box.querySelector("#sc-q"); if (i) { i.focus(); i.setSelectionRange(at, at); } };
    box.querySelectorAll("[data-b]").forEach(b => { b.onclick = () => go({ ...r, b: b.dataset.b }); });
    const fx = box.querySelector("#sc-fix"); if (fx) fx.onclick = () => { const first = fixLabels()[0]; if (first) openQ(first); };
    wireSend();
  }

  // Each finished booklet's total goes into the gradebook by itself (students see it once the evaluation's marks are
  // shown): on the evaluation's page, whenever the finished booklets' totals change. Not over a different mark already
  // there (the card says so; replace: use the scanned ones, after asking), nor while the gradebook has changes not saved.
  let sendingNow = false;
  async function autoSend(replace) {
    if (!S.eval || !S.can.mark || sendingNow || !R) return;
    const key = R.booklets.filter(b => b.ready).map(b => `${b.key}:${b.total}`).join("|");
    if (!key || (!replace && ui.sentKey === key)) return;
    if (sending && sending.before()) return replace && toast(sending.before());
    if (replace) {
      const list = ui.differ.slice(0, 6).map(x => `${x.name || x.num}: ${fmtN(x.was)} → ${fmtN(x.now)}`).join(", ");
      if (!await confirmBox(`Replace ${ui.differ.length} mark${ui.differ.length === 1 ? "" : "s"}?`, esc(`In the gradebook now: ${list}${ui.differ.length > 6 ? ", …" : ""}.`), "Replace")) return;
    }
    sendingNow = true;
    try {
      const d = await api("/api/scans/send", body(replace ? { replace: true } : {}));
      ui.sentKey = key; ui.differ = replace ? [] : d.differ;
      if (d.sent && sending) await sending.after();
      if (d.sent || replace || d.differ.length) load();
    } catch (e) { console.warn("[Lectern] marks to the gradebook:", e); }
    sendingNow = false;
  }

  // Email Booklets (each student their own, marked); Send Marks on an exam's own page.
  function wireSend() {
    const em = box.querySelector("#sc-email"); if (em) em.onclick = async () => {
      const bs = R.booklets.filter(b => b.ready), fresh = bs.filter(b => !b.emailed), again = fresh.length && fresh.length < bs.length;
      let answers = false;
      const watch = e => { if (e.target && e.target.id === "sc-ans") answers = e.target.checked; };
      document.addEventListener("change", watch);
      const n = again ? fresh.length : bs.length;
      const ok = await confirmBox(`Email ${n} student${n === 1 ? "" : "s"} their booklet${n === 1 ? "" : "s"}?`,
        `Each gets their own pages, marked, as a PDF, from the course's email.${again ? ` The ${bs.length - fresh.length} already emailed aren't sent again.` : ""}</p>
         <p><label class="lt-check"><input type="checkbox" id="sc-ans"> Show the right answers <small>(by each wrong answer, in green)</small></label>`, "Email Them");
      document.removeEventListener("change", watch);
      if (!ok) return;
      em.disabled = true;
      try {
        const d = await api("/api/scans/email", body({ answers, ...(again ? { booklets: fresh.map(b => b.key) } : {}) }));
        toast(d.emailing ? `Emailing ${d.emailing} booklet${d.emailing === 1 ? "" : "s"}…${d.missing.length ? ` ${d.missing.length} student${d.missing.length === 1 ? " has" : "s have"} no email address: ${d.missing.slice(0, 3).join(", ")}${d.missing.length > 3 ? ", …" : ""}.` : ""}`
          : d.missing.length ? `No one to email: ${d.missing.length} student${d.missing.length === 1 ? " has" : "s have"} no email address.` : "No finished booklets to email.");
        load();
      } catch (e) { em.disabled = false; toast(e.message); }
    };
    const s = box.querySelector("#sc-send"); if (s) s.onclick = async () => {
      const no = sending && sending.before(); if (no) return toast(no);   // the gradebook open here with changes not saved
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
        if (sending && d.sent) await sending.after();
        load();
      } catch (e) { s.disabled = false; toast(e.message); }
    };
  }

  // ── Uploading, a file at a time, with how far each has got ──
  async function uploadAll(files) {
    const up = box.querySelector("#sc-up");
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

  // Its uploads: delete one, upload more, read the new ones (when they weren't by themselves), delete them all.
  function wireFiles() {
    box.querySelectorAll("[data-del]").forEach(b => { b.onclick = async () => {
      if (!await confirmBox("Delete this scan?", "It's removed from this exam. Its results stay until you mark the scans again.", "Delete")) return;
      try { await api("/api/scans/delete", body({ file: b.dataset.del })); load(); } catch (e) { toast(e.message); } }; });
    const fi = box.querySelector("#sc-file"); if (fi) fi.onchange = () => uploadAll([...fi.files]);
    const mk = box.querySelector("#sc-mark"); if (mk) mk.onclick = async () => {
      mk.disabled = true;
      try { await api("/api/scans/mark", body({})); load(); } catch (e) { mk.disabled = false; toast(e.message); } };
    const wipe = box.querySelector("#sc-wipe"); if (wipe) wipe.onclick = async () => {
      if (!await confirmBox("Delete the scans and results?", "The scanned pages, what was read from them, every score given here and the printed copy go. Marks already sent to the gradebook stay.", "Delete Everything")) return;
      try { await api("/api/scans/delete", body({ all: true })); R = null; load(); } catch (e) { toast(e.message); } };
  }

  // ── Booklets Scanned: every upload, Upload Scans, and what's wrong with the scans ──
  function drawUploads() {
    pathTo("Booklets Scanned");
    const X = S.exam, can = S.can, job = S.job || {}, running = job.state === "running", res = S.results;
    const bs = (R && R.booklets) || [], want = (S.wrote && S.wrote.n) || 0, pl = (n, one, many) => `${n} ${n === 1 ? one : many}`;
    const whole = bs.filter(b => !(b.missing || []).length).length, part = bs.filter(b => (b.missing || []).length);
    const twins = bs.filter(b => b.twins).length, unread = res ? res.unread : [];
    const fresh = S.uploads.some(u => u.at > (job.finished || 0));
    // The uploads already read (their pages are in the results): the others say they're being read, while it reads.
    const readFiles = new Set([...bs.flatMap(b => b.pages || []), ...(res && res.unread ? res.unread.map(u => u.page) : [])]
      .map(p => String(p).replace(/ p\.\d+$/, "")));
    const looks = [
      ...part.map(b => `${b.booklet != null ? `Booklet ${b.booklet}` : esc(whoOf(b))} is missing page${b.missing.length === 1 ? "" : "s"} ${b.missing.join(", ")}: ${b.booklet != null ? "upload them" : "scan the booklet again, whole"}`),
      twins ? `${pl(twins, "booklet has", "booklets have")} the same number as another (photocopied?)` : "",
      ...(res && res.unread ? res.unread : []).slice(0, 12).map(u => `${esc(u.page)} couldn't be placed: ${esc(u.why)}`),
      bs.length > want && want ? `${bs.length - want} more booklet${bs.length - want === 1 ? "" : "s"} than students ${S.wrote.from === "attendance" ? "at the test" : "in the class"}` : "",
    ].filter(Boolean);
    const files = S.uploads.map(u => `<div class="sc-file">${DOC}<span class="sc-fname">${esc(u.name)}</span>
        <span class="sc-fmeta">${running && !readFiles.has(u.file) && !readFiles.has(u.name) ? `<span class="sc-reading"><span class="sc-spin" aria-hidden="true"></span>Reading…</span> · ` : ""}${u.pages ? `${u.pages} page${u.pages === 1 ? "" : "s"} · ` : ""}${size(u.size)} · ${esc(when(u.at))}${u.by ? ` · ${esc(u.by)}` : ""}</span>
        ${can.upload ? `<button type="button" class="sc-del" data-del="${esc(u.file)}" title="Delete this scan" aria-label="Delete ${esc(u.name)}"${running ? " disabled" : ""}>${TRASH}</button>` : ""}</div>`).join("");
    box.innerHTML = `<div class="lx-editor sc-ed sc-book">
      <div class="lx-ed-head">
        <div class="gr-tt"><h2>${esc(S.eval ? S.eval.name : X.title)}<span class="lt-req-of"> / ${esc(X.title)}</span></h2></div>
        ${can.upload && (S.uploads.length || res) ? `<span class="lx-acts"><button type="button" class="lx-ic" id="sc-wipe" title="Delete all the scans and results" aria-label="Delete all the scans and results"${running ? " disabled" : ""}>${TRASH}</button></span>` : ""}</div>
      <p class="lt-req-meta">${pie(whole, want)}${whole} / ${want || "?"} scanned</p>
      <p class="lx-help">Upload the scans as PDFs of 200 dpi or more, either way up.</p>
      ${looks.length ? `<ul class="sc-looks">${looks.map(x => `<li>${x}</li>`).join("")}</ul>` : ""}
      ${job.state === "failed" ? `<p class="lt-note err">${esc(job.error || "The marking stopped.")}</p>` : ""}
      ${can.upload && fresh && !running ? `<div class="lx-adds"><button type="button" class="lt-btn" id="sc-mark"${X.scan ? "" : " disabled"}>Read the New Scans</button></div>` : ""}
      <div class="sc-up" id="sc-up"></div>
      ${files ? `<div class="sc-files">${files}</div>` : `<p class="lx-empty">No scans yet.</p>`}
      <div class="sc-okbar sc-ubar"><span class="spacer"></span>
        ${can.upload ? `<label class="lt-btn${X.scan ? "" : " sc-dis"}"${X.scan ? "" : ` title="Tick Marking from Scans in the Exam Builder first"`}>${PLUS}Upload Scans<input type="file" id="sc-file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,application/pdf,image/*" multiple hidden${X.scan ? "" : " disabled"}></label>` : ""}<button type="button" class="lt-btn primary" data-udone>Done</button></div>
    </div>`;
    box.querySelectorAll("[data-udone]").forEach(x => { x.onclick = home; });
    wireFiles();
  }

  // ── Booklet Matching: every booklet's cover, and whose it is ──
  function drawMatching() {
    // One booklet at a time, as checking a question: its cover, whose the computer thinks it is (chosen already in the
    // list, if it read a number), and Okay; Skip leaves it for later. Students who have a booklet are greyed out.
    const bs = (R && R.booklets) || [], can = S.can.mark;
    pathTo("Booklet Matching");
    const open = bs.filter(b => !matched(b)), n = bs.length - open.length;
    ui.mSkip = (ui.mSkip || []).filter(k => open.some(b => b.key === k));
    const cur = open.find(b => !ui.mSkip.includes(b.key)) || open[0];
    const people = (R.students || []).slice().sort((a, c) => `${a.last} ${a.first}`.localeCompare(`${c.last} ${c.first}`));
    const taken = new Set(bs.filter(matched).map(b => b.student.num));
    let body = `<p class="lx-help sc-fixnext">Every booklet is matched. <button type="button" class="lt-link" data-mdone>Back to ${esc(S.eval ? S.eval.name : "the scans")}</button>.</p>`;
    if (cur) {
      const st = cur.student, i = bs.indexOf(cur) + 1, guess = st.num && !taken.has(st.num) ? st.num : "";
      body = `<div class="sc-qs"><div class="sc-mcard" data-k="${esc(cur.key)}">
          <p class="sc-note">${WARN}<span>${esc(firstSentence(st.note || "Not sure whose booklet this is."))}</span></p>
          ${cur.cover ? `<img class="sc-pic sc-cover" src="${esc(cur.cover)}" alt="The cover's name and number boxes, as scanned">` : `<p class="lx-help">The cover isn't in the scans: <button type="button" class="lt-link" data-open-b="${i}">open the booklet</button> to see whose it is.</p>`}
        </div></div>
        <div class="sc-okbar sc-mbar">${can ? `<select id="sc-mwho" aria-label="Whose booklet"><option value="">Choose the student…</option>${people.map(p => {
            const other = taken.has(p.num);
            return `<option value="${esc(p.num)}"${p.num === guess ? " selected" : ""}${other ? ` disabled class="sc-taken"` : ""}>${esc(`${p.last}, ${p.first}`)} · ${esc(p.num)}${other ? " · has a booklet" : ""}</option>`; }).join("")}</select>` : ""}<span class="spacer"></span>${open.length > 1 ? `<button type="button" class="lt-link" data-mskip>Skip</button>` : ""}<button type="button" class="lt-btn primary" data-mok${guess ? "" : " disabled"}>Okay</button></div>`;
    }
    box.innerHTML = `<div class="lx-editor sc-ed sc-book">
      <div class="lx-ed-head">
        <div class="gr-tt"><h2>${cur ? (cur.booklet != null ? `Booklet ${cur.booklet}` : `Booklet ${bs.indexOf(cur) + 1}`) : esc(S.eval ? S.eval.name : S.exam.title)}<span class="lt-req-of"> / ${esc(S.exam.title)}</span></h2></div>
</div>
      <p class="lt-req-meta">${pie(n, bs.length)}${n} / ${bs.length} matched</p>
      ${body}
    </div>`;
    box.querySelectorAll("[data-mdone]").forEach(x => { x.onclick = home; });
    box.querySelectorAll("[data-open-b]").forEach(x => { x.onclick = () => go({ ...r, q: "", b: x.dataset.openB }); });
    const sel = box.querySelector("#sc-mwho"), ok = box.querySelector("[data-mok]");
    if (sel && ok) sel.onchange = () => { ok.disabled = !sel.value; };
    const sk = box.querySelector("[data-mskip]"); if (sk) sk.onclick = () => { ui.mSkip.push(cur.key); if (ui.mSkip.length >= open.length) ui.mSkip = []; drawMatching(); };
    if (ok) { ok.focus(); ok.onclick = async () => {
      if (!sel || !sel.value) return;
      ok.disabled = true;
      if (await review(cur, { student: sel.value })) { window.scrollTo(0, 0); drawMatching(); } else ok.disabled = false; }; }
  }

  // ── One booklet ──
  function drawBooklet() {
        const bs = (R && R.booklets) || [], i = Math.max(1, Math.min(bs.length, Number(r.b) || 1)), b = bs[i - 1];
    if (!b) { pathTo("Booklet"); box.innerHTML = `<p class="lx-empty">That booklet isn't there any more. <button type="button" class="lt-link" id="sc-back">See all of them</button></p>`; box.querySelector("#sc-back").onclick = home; return; }
    const st = b.student, can = S.can.mark;
    const name = whoOf(b);
    pathTo(name);
    const nextOpen = bs.findIndex((x, k) => k > i - 1 && !x.ready) + 1 || bs.findIndex(x => !x.ready && x !== b) + 1;
    const people = (R.students || []).slice().sort((a, c) => `${a.last} ${a.first}`.localeCompare(`${c.last} ${c.first}`));
    const picker = `<select id="sc-who" aria-label="Whose booklet"><option value="">Choose the student…</option>${people.map(p => `<option value="${esc(p.num)}"${p.num === st.num ? " selected" : ""}>${esc(`${p.last}, ${p.first}`)} · ${esc(p.num)}</option>`).join("")}</select>`;
    const sure = st.status === "auto" || st.status === "done";
    const pages = b.where || (b.pages || []).join(", ");
    const q = x => qCard(x, b, `Question ${esc(x.label)}`);
    // The questions as the work goes: first make sure what the computer read is right (it marks those), then mark the rest.
    // Of those the computer marks, only what it wasn't sure of (an unclear bubble, handwriting it couldn't read for
    // certain) is shown; the rest behind a link. One fixed here stays until you leave the booklet.
    if (ui.keepFor !== b.key) { ui.keepFor = b.key; ui.keep = new Set(); ui.sure = false; }
    const read = b.questions.filter(x => !isJudged(x));
    read.forEach(x => { if (x.status === "check" || x.status === "manual" || x.status === "missing") ui.keep.add(x.label); });
    const unsure = read.filter(x => ui.keep.has(x.label)), sureOnes = read.filter(x => !ui.keep.has(x.label));
    const checks = ui.sure ? read : unsure, byHand = b.questions.filter(isJudged);
    box.innerHTML = `<div class="lx-editor sc-ed sc-book">
      <div class="lx-ed-head sc-hasmk"><span class="lx-kicon big" aria-hidden="true">${SCAN_ICON}</span>
        <div class="gr-tt"><p class="gr-kind">Booklet ${i} of ${bs.length}</p><h2>${esc(name)}<span class="lt-req-of"> / ${esc(S.exam.title)}</span></h2></div>
        ${markHTML(b)}
        <span class="lx-acts"><a class="lt-btn sc-sm" href="/api/scans/annotated?${params({ booklet: b.key })}" target="_blank" rel="noopener" title="Their booklet with its marking drawn on, as they'd get it by email">${DOC}Marked PDF</a>${nextOpen ? `<button type="button" class="lt-btn sc-sm" data-go="${nextOpen}">Next to Look At</button>` : ""}
          <button type="button" class="lx-ic" data-go="${i - 1}" title="The booklet before" aria-label="The booklet before"${i > 1 ? "" : " disabled"}>${LEFT}</button><button type="button" class="lx-ic" data-go="${i + 1}" title="The next booklet" aria-label="The next booklet"${i < bs.length ? "" : " disabled"}>${RIGHT}</button></span></div>
      <p class="lt-req-meta">${b.booklet != null ? `Booklet ${b.booklet} · ` : ""}${esc(numOf(b))} · ${b.version ? `Version ${esc(b.version)} · ` : ""}${esc(pages)} · ${b.ready ? "finished" : `${b.open || "nothing"} to look at`}${b.emailed ? ` · emailed ${esc(when(b.emailed))}` : ""}</p>
      <h3 class="lx-sec">Student</h3>
      ${b.cover ? `<img class="sc-pic sc-cover" src="${esc(b.cover)}" alt="The cover's name and number boxes, as scanned">` : ""}
      ${sure ? (st.status === "done" && (b.studentHistory || []).length ? historyHTML(b.studentHistory) : `<p class="lx-help">${st.status === "done" ? `Chosen${st.by ? ` by ${esc(st.by)}` : ""}.` : `Found from the student number${st.read && st.read !== st.num ? ` (read as ${esc(st.read)})` : ""}.`}</p>`)
        : `<p class="sc-note">${WARN}<span>${esc(st.note || "Not sure whose booklet this is. Check the cover.")}${st.read ? ` The number reads as ${esc(st.read)}.` : ""}</span></p>`}
      ${can ? `<div class="sc-pick">${picker}</div>` : ""}
      ${read.length ? `<h3 class="lx-sec">Check What Was Read</h3>
      <p class="lx-help">${unsure.length ? `The computer wasn't sure what ${unsure.length === 1 ? "this one says" : `these ${unsure.length} say`}. Make each copy match the scan; it marks them from that.` : "The computer read every answer it marks with confidence: nothing to check."}${sureOnes.length ? ` <button type="button" class="lt-link" data-sure>${ui.sure ? "Hide" : "Show"} the ${sureOnes.length} it was sure of</button>` : ""}</p>
      ${checks.length ? `<div class="sc-qs">${checks.map(q).join("")}</div>` : ""}` : ""}
      ${byHand.length ? `<h3 class="lx-sec">Mark by Hand</h3><p class="lx-help">Give each a score: tick the rubric's comments that apply, or type it.</p>
      <div class="sc-qs">${byHand.map(q).join("")}</div>` : ""}
    </div>`;
    box.querySelectorAll("[data-go]").forEach(x => { x.onclick = () => go({ ...r, b: x.dataset.go }); });
    const showSure = box.querySelector("[data-sure]"); if (showSure) showSure.onclick = () => { ui.sure = !ui.sure; const y = window.scrollY; drawBooklet(); window.scrollTo(0, y); };
    const save = what => review(b, what).then(ok => { if (ok) { const y = window.scrollY; drawBooklet(); window.scrollTo(0, y); } });
    const w = box.querySelector("#sc-who"); if (w) w.onchange = () => save({ student: w.value });
    wireCards(drawBooklet);
  }

  // ── One question, in every booklet ──
  // The questions, in the exam's order (each booklet has the same labels; versions may differ in their answers).
  const labels = () => { const seen = []; ((R && R.booklets) || []).forEach(b => b.questions.forEach(x => { if (!seen.includes(x.label)) seen.push(x.label); })); return seen; };
  const answersTo = label => ((R && R.booklets) || []).map(b => ({ b, x: b.questions.find(y => y.label === label) })).filter(a => a.x);
  const isOpen = x => x.status === "check" || x.status === "manual";
  // Fix Scans: question by question, the answers whose reading the grader wasn't sure of (not the ones a person marks).
  const unsureIn = l => answersTo(l).filter(a => isOpen(a.x) && !isJudged(a.x));
  const fixLabels = () => labels().filter(l => unsureIn(l).length);
  // Grade, a question at a time: one the computer marks is checked against its scans (the answers it wasn't sure
  // how to read, one at a time; every answer, if you ask); one marked by hand is the grader (every booklet's answer).
  const byHand = l => answersTo(l).some(a => isJudged(a.x));
  const toDo = () => labels().filter(l => answersTo(l).some(a => isOpen(a.x)));
  // The questions as rows (qs: {l, hand, n, open, missing}; off: no scans yet, so none opens), each sub-question,
  // 9(a), 9(b)…, under its question as its parts.
  // Booklets Scanned, the list's first row (not opened): how many are in, whole, of how many wrote it; while
  // the scans are being read, says so.
  function scanRow(off) {
    const bs = (R && R.booklets) || [], want = (S.wrote && S.wrote.n) || 0, job = S.job || {};
    const whole = off ? 0 : bs.filter(b => !(b.missing || []).length).length, done = want && whole >= want;
    const reading = job.state === "running" ? ` · <span class="sc-spin" aria-hidden="true"></span>reading the scans${job.booklets ? `: ${job.booklets} so far` : ""}` : "";
    return `<div class="dc-t lt-rq-row sc-r sc-scan-row"><span class="lt-rq-st"><span class="sc-done${done ? " on" : ""}">${done ? TICK : ""}</span></span>
      <button type="button" class="dc-t-b" data-scans><b class="dc-t-title">Booklets Scanned</b><span class="dc-t-meta" title="${want ? `Booklets with every page scanned, of the ${want} ${S.wrote.from === "attendance" ? "students at the test (its attendance)" : "students in the class"}` : "No students in the class yet"}">${pie(whole, want)}${whole} / ${want || "?"} scanned${reading}</span></button></div>`;
  }
  // Booklet Matching, as a row like a question's: whose each booklet is (read from the cover, or picked).
  function matchRow(bs, off) {
    const n = bs ? bs.filter(matched).length : 0, all = bs ? bs.length : 0, done = !off && n === all;
    return `<div class="dc-t lt-rq-row sc-r sc-match-row"><span class="lt-rq-st">${off ? `<span class="sc-done"></span>` : `<span class="sc-done${done ? " on" : ""}" title="${done ? "Finished" : "Not finished"}">${done ? TICK : ""}</span>`}</span>
      <button type="button" class="dc-t-b" data-match${off ? " disabled" : ""}><b class="dc-t-title">Booklet Matching</b>
        <span class="dc-t-meta"${off ? "" : ` title="Booklets whose student is known: read from the cover, or picked by a person"`}>${off ? "No scans yet" : `${pie(n, all)}${n} / ${all} matched`}</span></button></div>`;
  }
  // Who marks a question: their initials at the end of its row; the owner and coordinators click to choose
  // (none chosen: anyone on the team). A TA's list has only theirs, and the ones nobody is on.
  const gradersOf = l => (S.graders && S.graders[l]) || [];
  const isMine = l => S.can.print || !gradersOf(l).length || gradersOf(l).includes(S.me);
  const initials = n => String(n || "?").split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join("").toUpperCase();
  // Who marks each question: a dropdown on each question's row, for the owner and coordinators, once there's someone else to mark.
  const canAssign = () => S.can.print && (S.markers || []).length > 1;
  const gradersNames = l => gradersOf(l).map(id => ((S.markers || []).find(m => m.id === id) || {}).name).filter(Boolean);
  // Assign Graders (the owner and coordinators): each question row gets Lectern's tick-box dropdown of the team.
  function mountGraders() {
    box.querySelectorAll("[data-gpk]").forEach(host => {
      const l = host.dataset.gpk;
      pickMany(host, { options: (S.markers || []).map(m => ({ value: m.id, label: m.name, icon: PERSON })),
        value: gradersOf(l), empty: "Anyone on the team", noun: "graders", icon: PERSON, label: `Who marks question ${l}`,
        onChange: async v => {
          try { const d = await api("/api/scans/graders", body({ label: l, users: v.map(Number) })); S.graders = d.graders; }
          catch (e) { toast(e.message); } } });
    });
  }
  function questionRows(qs, off) {
    qs = qs.filter(q => isMine(q.l));
    const groups = [];
    qs.forEach(q => { const m = /^(.+?)\((.+)\)$/.exec(q.l), last = groups[groups.length - 1];
      if (!m) return groups.push({ q });
      q = { ...q, part: m[2] };
      if (last && last.parts && last.n === m[1]) { last.parts.push(q); last.open += q.open || 0; }
      else groups.push({ n: m[1], parts: [q], open: q.open || 0 }); });
    const tick = done => off ? `<span class="sc-done"></span>` : `<span class="sc-done${done ? " on" : ""}" title="${done ? "Finished" : "Not finished"}">${done ? TICK : ""}</span>`;
    const qrow = (q, sub) => `<div class="dc-t lt-rq-row sc-r sc-graded${sub ? " sc-sub" : ""}"><span class="lt-rq-st">${tick(!q.open)}</span>
        <button type="button" class="dc-t-b" data-gq="${esc(q.l)}"${off ? " disabled" : ""}><b class="dc-t-title">${sub ? `<span class="sc-part">(${esc(q.part)})</span>` : `Question ${esc(q.l)}`}</b>
          <span class="dc-t-meta"${off ? "" : ` title="${q.hand ? "Marked by hand: the booklets whose answer is marked" : "Marked by the computer: the booklets whose answer it read with confidence, or a person has checked against the scan"}"`}>${off ? "No scans yet" : `${pie(q.n - q.open - q.missing, q.n)}${q.n - q.open - q.missing} / ${q.n} ${q.hand ? "marked" : "read"}`}${into && !canAssign() && gradersNames(q.l).length ? ` · ${esc(gradersNames(q.l).join(", "))}` : ""}</span></button>${into && canAssign() ? `<div class="sc-gpk" data-gpk="${esc(q.l)}"></div>` : ""}</div>`;
    return groups.map(g => g.parts ? `<div class="dc-t sc-qgroup"><span class="lt-rq-st">${tick(!g.open)}</span>
        <div class="dc-t-b sc-qg-h"><b class="dc-t-title">Question ${esc(g.n)}</b><span class="dc-t-meta">${g.parts.length} parts</span></div></div>
        ${g.parts.map(q => qrow(q, true)).join("")}` : qrow(g.q)).join("");
  }
  const openQ = l => { if (!l) return; ui.allFor = ""; ui.fixWas = ""; ui.qWas = ""; window.scrollTo(0, 0); go({ ...r, b: "", q: l }); };
  function drawFix() {
    const L = labels(), all = answersTo(r.q), key = a => `${a.b.key}|${a.x.label}`;
    if (ui.fixWas !== r.q) { ui.fixWas = r.q; ui.fixCur = ""; ui.fixDone = 0; }
    // One answer at a time: the one being checked stays until Okay (a fix saves it, but you see it first).
    const unsure = unsureIn(r.q), cur = (ui.fixCur && all.find(a => key(a) === ui.fixCur)) || unsure[0];
    ui.fixCur = cur ? key(cur) : "";
    const left = unsure.filter(a => !cur || key(a) !== key(cur)).length + (cur ? 1 : 0), n = ui.fixDone + left;
    const todo = toDo(), after = L.slice(L.indexOf(r.q) + 1).find(l => todo.includes(l)), back = !after && todo.find(l => l !== r.q);
    pathTo(`Question ${r.q}`);
    box.innerHTML = `<div class="lx-editor sc-ed sc-book sc-fixing">
      <div class="lx-ed-head">
        <div class="gr-tt"><h2>Question ${esc(r.q)}<span class="lt-req-of"> / ${esc(S.exam.title)}</span></h2></div>
        <span class="lx-acts">${after ? `<button type="button" class="lt-btn sc-sm" data-fixgo="${esc(after)}">Next Question${RIGHT}</button>` : ""}<button type="button" class="lt-btn sc-sm" data-fixall>See Every Answer</button><button type="button" class="lt-btn sc-sm" data-fixdone>${after ? "Stop" : "Done"}</button></span></div>
      <p class="lt-req-meta">${cur ? `${ui.fixDone + 1} of ${n} the computer wasn't sure how to read` : "Every answer matches its scan"} · ${todo.length ? `${todo.length} question${todo.length === 1 ? "" : "s"} still to grade` : "every question graded"}</p>
      ${cur ? `<div class="sc-qs">${qCard(cur.x, cur.b, "")}</div>
        <div class="sc-okbar"><button type="button" class="lt-btn primary" data-fixok>Okay</button></div>`
      : `<p class="lx-help sc-fixnext">${after ? `Question ${esc(r.q)} is checked. <button type="button" class="lt-link" data-fixgo="${esc(after)}">On to Question ${esc(after)}</button>.`
        : back ? `Question ${esc(r.q)} is checked, but <button type="button" class="lt-link" data-fixgo="${esc(back)}">Question ${esc(back)}</button> still has answers to grade.`
        : "Question " + esc(r.q) + " is checked, and that's every question graded."}</p>`}
    </div>`;
    box.querySelectorAll("[data-fixgo]").forEach(x => { x.onclick = () => openQ(x.dataset.fixgo); });
    box.querySelectorAll("[data-fixdone]").forEach(x => { x.onclick = home; });
    box.querySelectorAll("[data-fixall]").forEach(x => { x.onclick = () => { ui.allFor = r.q; ui.qWas = ""; drawQuestion(); }; });
    const ok = box.querySelector("[data-fixok]");
    if (ok) {
      ok.focus();
      ok.onclick = async () => {
        ok.disabled = true;
        await ui.pending;                                   // a fix being saved (leaving its box) goes first
        const b = R.booklets.find(z => z.key === cur.b.key), x = b && b.questions.find(q => q.label === r.q);
        if (!x) return drawFix();
        const blanks = x.blanks && x.blanks.length > 1 ? x.blanks : null;
        const needs = blanks ? blanks.findIndex(y => y.status === "manual") : x.status === "manual" ? 0 : -1;
        if (needs >= 0) { ok.disabled = false; return toast(blanks ? `Type what blank ${needs + 1} says first.` : "Type what it says first."); }
        let fine = true;                                    // still as the grader read it: Okay says it's right
        if (blanks) { for (const y of blanks) if (y.status === "check") fine = fine && await reviewNow(b, { label: x.label, blank: y.id, keep: true }); }
        else if (x.status === "check") {
          const said = x.options && x.options[0] === "True" ? String(x.read || "").split(", ").filter(v => v && v !== "none").join(", ") : String(x.read || "").split(", ").filter(v => v && v !== "none").join("");
          fine = await reviewNow(b, x.ask === "choice" ? { label: x.label, read: said } : { label: x.label, score: x.score });
        }
        if (!fine) { ok.disabled = false; return; }
        ui.fixCur = ""; ui.fixDone += 1; drawFix();
      };
    }
    wireCards(drawFix);
  }
  function drawQuestion() {
    const L = labels(), k = L.indexOf(r.q), all = answersTo(r.q);
    if (k >= 0 && !byHand(r.q) && ui.allFor !== r.q) return drawFix();    // marked by the computer: check it
    if (k < 0) { pathTo("Question"); box.innerHTML = `<p class="lx-empty">That question isn't in the results. <button type="button" class="lt-link" id="sc-back">See all of them</button></p>`; box.querySelector("#sc-back").onclick = home; return; }
    pathTo(`Question ${r.q}`);
    const open = all.filter(a => isOpen(a.x)), pts = all[0] ? all[0].x.points : 0;
    // Every booklet's answer, the ones still to mark first (one marked stays where it is until you leave).
    if (ui.qWas !== r.q) { ui.qWas = r.q; ui.qOrder = [...open, ...all.filter(a => !isOpen(a.x))].map(a => a.b.key); }
    const list = all.slice().sort((a, c) => ui.qOrder.indexOf(a.b.key) - ui.qOrder.indexOf(c.b.key));
    const nextOpen = L.slice(k + 1).concat(L.slice(0, k)).find(l => answersTo(l).some(a => isOpen(a.x)));
    const answers = [...new Set(all.map(a => a.x.answer).filter(Boolean))];
    const who = a => esc(whoOf(a.b));
    box.innerHTML = `<div class="lx-editor sc-ed sc-book">
      <div class="lx-ed-head">
        <div class="gr-tt"><h2>Question ${esc(r.q)}<span class="lt-req-of"> / ${esc(S.exam.title)}</span></h2></div>
        <span class="lx-acts">${!byHand(r.q) ? `<button type="button" class="lt-btn sc-sm" data-gback>Check the Unsure Ones</button>` : ""}${nextOpen ? `<button type="button" class="lt-btn sc-sm" data-gq="${esc(nextOpen)}">Next to Look At</button>` : ""}
          <button type="button" class="lx-ic" data-gq="${esc(L[k - 1] || "")}" title="The question before" aria-label="The question before"${k > 0 ? "" : " disabled"}>${LEFT}</button><button type="button" class="lx-ic" data-gq="${esc(L[k + 1] || "")}" title="The next question" aria-label="The next question"${k < L.length - 1 ? "" : " disabled"}>${RIGHT}</button></span></div>
      <p class="lt-req-meta">${fmtN(pts)} mark${pts === 1 ? "" : "s"}${answers.length ? ` · answer ${answers.map(esc).join(" or ")}` : ""} · ${pie(all.length - open.length, all.length)}${all.length - open.length} / ${all.length} ${byHand(r.q) ? "marked" : "read"}</p>
      <div class="sc-qs">${list.map(a => qCard(a.x, a.b, a.b.version ? `<span class="sc-qv">Version ${esc(a.b.version)}</span>` : "")).join("")}</div>
    </div>`;
    box.querySelectorAll("[data-gq]").forEach(x => { x.onclick = () => openQ(x.dataset.gq); });
    box.querySelectorAll("[data-gback]").forEach(x => { x.onclick = () => { ui.allFor = ""; drawFix(); }; });
    box.querySelectorAll("[data-book]").forEach(x => { x.onclick = () => go({ ...r, q: "", b: x.dataset.book }); });
    wireCards(drawQuestion);
  }

  // A question's answer, as a card: who marked it and whether it's done, its score, a picture of it, what was read.
  // ── The typed copy of an answer: what was read, drawn as the paper has it, to correct ──
  // Under the scan, each answer piece as on paper: bubbles or tick boxes with their options (click to fill or empty
  // them; a student can fill two, or none), or boxes, fractions, rows of cells and blank lines holding what was read
  // (type in them). In the Marked view the same copy shows a tick or cross by each answer and the right ones in green.
  const pieceOf = x => (R && R.pieces && R.pieces[x.id]) || null;
  function digiChoice(x, node, can) {
    const vals = x.options || node.opts.map((_, k) => (node.type === "tf" ? ["True", "False"][k] : LET[k]));
    const picked = new Set(String(x.read || "").split(", "));
    return `<div class="dz dz-choice${node.type === "ms" ? " sq" : ""}" role="group" aria-label="What they answered">${vals.map((v, k) => {
      const on = picked.has(v), ok = node.right.includes(k);
      return `<button type="button" class="dz-opt${on ? " on" : ""}${ok ? " right" : ""}" data-hot="${esc(v)}" aria-pressed="${on}"${can ? "" : " disabled"} title="${on ? "Filled: click if it isn't" : "Click if they filled this one"}">
          <span class="dz-mk" aria-hidden="true">${on ? `<span class="sc-pk ${ok ? "ok" : "no"}">${ok ? TICK : CROSS}</span>` : ""}</span><span class="dz-b" aria-hidden="true"></span><span class="dz-t">${esc(node.opts[k] || v)}</span></button>`;
    }).join("")}</div>`;
  }
  function digiField(kind, n, value, can, label) {
    const v = value == null || value === "blank" || value === "nothing" ? "" : String(value), dis = can ? "" : " disabled";
    const input = (cls, val, l, more = "") => `<input class="${cls}" type="text" value="${esc(val)}" aria-label="${esc(l)}" spellcheck="false" autocomplete="off"${more}${dis}>`;
    if (kind === "frac") { const [a = "", c = ""] = v.split("/"); return `<span class="dz-field dz-frac">${input("dz-box", a.replace(/^\?$/, ""), `${label}: top`)}<i></i>${input("dz-box", c.replace(/^\?$/, ""), `${label}: bottom`)}</span>`; }
    if (kind === "cells") { const vs = v.split(/\s+/); return `<span class="dz-field dz-cells">${Array.from({ length: n }, (_, i) => input("dz-cell", (vs[i] || "").replace(/^[_?]$/, ""), `${label}: cell ${i + 1}`, ' maxlength="2"')).join("")}</span>`; }
    return `<span class="dz-field">${input(kind === "blank" ? "dz-line" : kind === "box" ? "dz-box wide" : "dz-box", v, label, ' placeholder="What does it say?"')}</span>`;
  }
  const fieldValue = f => { const vs = [...f.querySelectorAll("input")].map(i => i.value.trim()), k = f.dataset.kind || "";
    return f.classList.contains("dz-frac") || k === "frac" ? (vs.some(Boolean) ? `${vs[0]}/${vs[1]}` : "") : f.classList.contains("dz-cells") || k === "cells" ? vs.map(c => c || "_").join(" ") : vs[0]; };
  // What a piece got, for the Marked view: a tick, or a cross and the right answer under it in green.
  const fieldMarks = (score, pts, answer) => score == null ? "" : `<span class="dz-mk">${score >= pts - 1e-9 ? `<span class="sc-pk ok">${TICK}</span>` : `<span class="sc-pk no">${CROSS}</span>`}</span>${score < pts - 1e-9 && answer ? `<span class="dz-ans">${esc(answer)}</span>` : ""}`;

  // The typed copy drawn on the exam itself: the same piece of the printed copy as the scan, clean, with what was read
  // put back on it: bubbles filled (click to fill or empty), boxes, blanks and cells holding what was read (type in them).
  const at = ([l, t, w, h]) => `left:${l * 100}%;top:${t * 100}%;width:${w * 100}%;height:${h * 100}%`;
  function paperChoice(x, node, can) {
    const vals = x.options || node.opts.map((_, k) => (node.type === "tf" ? ["True", "False"][k] : LET[k]));
    const picked = new Set(String(x.read || "").split(", ")), sq = node.type === "ms";
    return `<div class="pp${sq ? " sq" : ""}" role="group" aria-label="What they answered"><img class="pp-img" src="${esc(x.paper)}" alt="" aria-hidden="true"><div class="pp-on">${x.fields.map(([r], k) => {
      const v = vals[k], on = picked.has(v), ok = node.right.includes(k);
      return `<button type="button" class="pp-opt${on ? " on" : ""}${ok ? " right" : ""}" data-hot="${esc(v)}" aria-pressed="${on}" style="${at(r)}"${can ? "" : " disabled"} title="${on ? "Filled: click if it isn't" : "Click if they filled this one"}" aria-label="${esc(node.opts[k] || v)}">${on ? `<span class="pp-mk sc-pk ${ok ? "ok" : "no"}" aria-hidden="true">${ok ? TICK : CROSS}</span>` : ""}</button>`;
    }).join("")}</div></div>`;
  }
  function paperField(p, kind, value, can, label, marks) {
    const v = value == null || value === "blank" || value === "nothing" ? "" : String(value), rects = p.fields[0] || [];
    const parts = kind === "frac" ? v.split("/").map(z => z.replace(/^\?$/, "")) : kind === "cells" ? v.split(/\s+/).map(z => z.replace(/^[_?]$/, "")) : [v];
    const ratio = p.size ? p.size[1] / p.size[0] : .25;
    return `<div class="dz-one"><div class="pp dz-field pp-${kind}" data-kind="${kind}" style="--r:${ratio}"><img class="pp-img" src="${esc(p.paper)}" alt="" aria-hidden="true"><div class="pp-on">${rects.map((r, i) => `<input class="pp-in" type="text" value="${esc(parts[i] || "")}" style="${at(r)};--h:${r[3]}" aria-label="${esc(label)}${rects.length > 1 ? ` ${i + 1}` : ""}" spellcheck="false" autocomplete="off"${kind === "cells" ? ' maxlength="2"' : ""}${can ? "" : " disabled"}>`).join("")}${marks ? `<span class="pp-marks" style="${at(rects[rects.length - 1] || [0, 0, 0, 0])}">${marks}</span>` : ""}</div></div></div>`;
  }

  // An answer's edit history: who changed what, and when (newest first), folded under its last change.
  function historyHTML(h) {
    if (!h || !h.length) return "";
    const last = h[h.length - 1];
    return `<details class="sc-hist"><summary>Changed by ${esc(last.by)}, ${esc(when(last.at))}${h.length > 1 ? ` · ${h.length} changes` : ""}</summary>
      <ol>${h.slice().reverse().map(e => `<li><span class="sc-hist-w">${esc(when(e.at))}</span><b>${esc(e.by)}</b><span>${esc(e.what)}</span></li>`).join("")}</ol></details>`;
  }

  // Whether a person marks a question (writing, room for working, or a rubric to give), or the computer does, from what
  // it read (then a person only makes sure it read it right).
  function isJudged(x) {
    const node = pieceOf(x), choice = Array.isArray(x.options) || (node && node.type !== "written");
    return !choice && (!node || !node.comps.length || !!node.space || ((R.rubrics || {})[x.id] || { lines: [] }).lines.length > 0);
  }

  // A question's answer, as a card: who marked it and whether it's done, its score, the scan, the typed copy.
  function qCard(x, b, title) {
    const s = x.status, can = S.can.mark && s !== "missing", id = `${b.key}|${x.label}`;
    const blanks = x.blanks && x.blanks.length > 1 ? x.blanks : null;
    const node = pieceOf(x), choice = Array.isArray(x.options) || (node && node.type !== "written");
    const one = node && node.type === "written" && node.comps.length === 1 && !blanks ? node.comps[0] : null;
    const ask = s === "check" ? x.ask : "";
    // Comments and a note only where a person judges the answer (writing, or room for working, or a rubric to give),
    // not where they're only making sure what the computer read is right.
    const judged = isJudged(x);
    const by = historyHTML(x.history);
    // The typed copy: of a choice question, or of its one answer piece (several blanks have a row each, below).
    const onPaper = x.paper && Array.isArray(x.fields) && x.fields.length;
    const digi = s === "missing" ? "" : choice && node && onPaper ? paperChoice(x, node, can) : choice && node ? digiChoice(x, node, can)
      : one && onPaper ? paperField(x, one.kind, x.read, can, "What they wrote", fieldMarks(x.score, x.points, x.answer))
      : one ? `<div class="dz dz-one">${digiField(one.kind, one.n, x.read, can, "What they wrote")}${fieldMarks(x.score, x.points, x.answer)}</div>` : "";
    const note = s === "missing" ? `<p class="sc-note">${WARN}<span>This page wasn't in the scans.</span></p>`
      : ask && x.note ? `<p class="sc-note">${WARN}<span>${esc(ask === "working" ? x.note : firstSentence(x.note))}</span></p>` : "";
    // Confirming a reading: one click, when the grader's reading is right.
    const confirm = can && (ask === "read" || ask === "choice") ? `<div class="sc-qa"><button type="button" class="lt-btn sc-sm sc-rr" data-${ask === "choice" ? "hotok" : "yes"}>${TICK}Read Right</button></div>` : "";
    const acts = !can ? ""
      : confirm ? confirm
      : ask === "working" ? `<div class="sc-qa"><button type="button" class="lt-btn sc-sm" data-yes title="Give part marks in the score box">Yes</button><button type="button" class="lt-btn sc-sm" data-keep>No</button></div>`
      : s === "manual" && !one && judged ? `<div class="sc-qa"><button type="button" class="lt-btn sc-sm" data-full>Full Marks</button><button type="button" class="lt-btn sc-sm" data-zero>Zero</button></div>`
      : s === "done" ? `<div class="sc-qa"><button type="button" class="lt-link sc-undo" data-undo>Undo</button></div>` : "";
    return `<div class="sc-q st-${s}${judged ? " judged" : " readq"}" data-k="${esc(b.key)}" data-q="${esc(x.label)}">
        <div class="sc-qh"><h4 class="sc-qt">${title}</h4>
          <span class="sc-score"><input type="number" min="0" max="${x.points}" step="0.5" value="${x.score == null ? "" : fmtN(x.score)}" placeholder="–" aria-label="Score"${can ? "" : " disabled"}><span>/ ${fmtN(x.points)}</span></span></div>
        ${note}
        ${x.picture && !blanks ? `<div class="sc-pair${one && one.kind === "frac" ? " side" : ""}"><img class="sc-pic" src="${esc(x.picture)}" alt="The answer, as scanned" loading="lazy">${digi}</div>` : digi}${by}
        ${blanks ? `<div class="sc-bls">${blanks.map((y, k) => blankRow(y, k, b, x, can, node)).join("")}</div>` : ""}
        ${acts}
        ${judged ? commentsHTML(x, b, can) : ""}
      </div>`;
  }
  // A question's comments for the student: the grader's (for what it marked down), the rubric's as buttons that set the
  // score (from full marks or zero, as the exam says), a new one (saved into the exam's rubric), and a note.
  function commentsHTML(x, b, can) {
    if (x.status === "missing") return "";
    const id = `${b.key}|${x.label}`, rb = (R && R.rubrics && R.rubrics[x.id]) || { marking: "full", lines: [] };
    const given = new Set((x.comments || []).map(c => c.id)), auto = x.auto || [];
    // One list, as the marking guide writes it: the marks in a column, the comment beside them.
    const row = (c, extra = "") => `<span class="sc-cm-d${c.delta > 0 ? " up" : c.delta < 0 ? " down" : ""}">${dl(c.delta)}</span><span class="sc-cm-t">${esc(c.text)}</span>${extra}`;
    const grader = auto.map(c => `<li class="sc-cm-r sc-cm-auto"><span class="sc-cm-k" aria-hidden="true"></span>${row(c, `<span class="sc-cm-by">Grader</span>`)}</li>`).join("");
    const note = x.forStudent || noting.has(id) ? (can ? `<label class="sc-cm-note"><span class="sc-fk">Note for the student</span><input class="sc-cnote-in" type="text" value="${esc(x.forStudent || "")}" placeholder="Write a note…" aria-label="A note for this student" maxlength="2000"></label>`
      : `<p class="sc-cm-note"><span class="sc-fk">Note</span><span>${esc(x.forStudent)}</span></p>`) : "";
    if (!can) {
      const all = [...(x.comments || []).map(c => `<li class="sc-cm-r on"><span class="sc-cm-k" aria-hidden="true"></span>${row(c)}</li>`), grader].join("");
      return all || x.forStudent ? `<div class="sc-cm">${all ? `<ul class="sc-cm-l">${all}</ul>` : ""}${note}</div>` : "";
    }
    const lines = rb.lines.map(l => `<li><button type="button" class="sc-cm-r${given.has(l.id) ? " on" : ""}" data-rub="${esc(l.id)}" aria-pressed="${given.has(l.id)}" title="${given.has(l.id) ? "Take this comment back" : "Give this comment"}"><span class="sc-cm-k" aria-hidden="true">${given.has(l.id) ? TICK : ""}</span>${row(l)}</button></li>`).join("");
    const form = adding.has(id) ? `<div class="sc-newc"><input class="sc-nd" type="text" inputmode="decimal" placeholder="${rb.marking === "zero" ? "+1" : "−1"}" aria-label="Marks" title="Marks off (−1) or on (+1). A number without a sign counts ${rb.marking === "zero" ? "on" : "off"}, as this question starts from ${rb.marking === "zero" ? "zero" : "full marks"}.">
        <input class="sc-nt" type="text" placeholder="The comment, as the student will read it" aria-label="The comment" maxlength="300">
        <button type="button" class="lt-btn sc-sm primary" data-csave>Add</button><button type="button" class="lt-btn sc-sm" data-ccancel>Cancel</button></div>` : "";
    const links = `<div class="sc-cm-acts">${form ? "" : `<button type="button" class="sc-cm-a" data-addc>${PLUS}Add a Comment</button>`}${x.forStudent || noting.has(id) ? "" : `<button type="button" class="sc-cm-a" data-addn>${PLUS}Note for the Student</button>`}</div>`;
    const list = lines + grader;
    return `<div class="sc-cm${list || note || form ? "" : " sc-cm-min"}">
        ${list ? `<p class="sc-fk sc-cm-h">Comments${rb.lines.length ? `<i> · tick the ones that apply; from ${rb.marking === "zero" ? "zero" : "full marks"}</i>` : ""}</p><ul class="sc-cm-l">${list}</ul>` : ""}
        ${form}${note}${links}
      </div>`;
  }
  // One blank of several in a question: its picture, what was read beside its answer, and its own score; one the
  // grader wasn't sure of asks "Is this what it says?", and one with words in it waits, open, for a person to type it.
  function blankRow(y, k, b, x, can, node) {
    const s = y.status, piece = node && node.comps ? node.comps.find(c => c.id === y.id) : null;
    const kind = (piece && piece.kind) || y.kind || "num", n = (piece && piece.n) || 1;
    const by = y.typed ? `<small class="sc-by">changed${y.by ? ` by ${esc(y.by)}` : ""}</small>` : "";
    const warn = s === "check" ? `<p class="sc-note">${WARN}<span>${esc(firstSentence(y.note || "Not sure what this says."))}</span></p>` : "";
    const ask = s === "check" && can ? `<div class="sc-qa"><button type="button" class="lt-btn sc-sm sc-rr" data-byes>${TICK}Read Right</button></div>` : "";
    return `<div class="sc-bl st-${s}" data-blank="${esc(y.id)}">
        <span class="sc-bn" aria-label="Blank ${k + 1}">${k + 1}</span>
        <div class="sc-bm">
          ${warn}
          <div class="sc-pair${kind === "frac" ? " side" : ""}">${y.picture ? `<img class="sc-pic sc-bpic" src="${esc(y.picture)}" alt="Blank ${k + 1}, as scanned" loading="lazy">` : ""}
          ${y.paper && Array.isArray(y.fields) && y.fields.length ? paperField(y, kind, y.read, can, `What they wrote in blank ${k + 1}`, fieldMarks(y.score, y.points, y.answer))
            : `<div class="dz dz-one">${digiField(kind, n, y.read, can, `What they wrote in blank ${k + 1}`)}${fieldMarks(y.score, y.points, y.answer)}</div>`}</div>${by}
          ${ask}
        </div>
        <span class="sc-score sc-bscore"><input type="number" min="0" max="${y.points}" step="0.5" value="${y.score == null ? "" : fmtN(y.score)}" placeholder="–" aria-label="Score for blank ${k + 1}"${can ? "" : " disabled"}><span>/ ${fmtN(y.points)}</span></span>
      </div>`;
  }
  // A decision about a booklet (its student, or a question's score): saved, and the booklet as it is now kept.
  // Every decision goes through here; ui.pending is the last one, so Okay in Fix Scans can wait for a fix being saved.
  function review(b, what, el) { ui.pending = reviewNow(b, what, el); return ui.pending; }
  async function reviewNow(b, what, el) {
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
      const b = R.booklets.find(y => y.key === el.dataset.k), x = b && b.questions.find(y => y.label === el.dataset.q), inp = el.querySelector(".sc-qh .sc-score input");
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
      // Comments: a rubric comment given or taken back (the score follows), a new one, and a note.
      el.querySelectorAll("[data-rub]").forEach(c => { c.onclick = () => {
        const ids = [...el.querySelectorAll("[data-rub]")].filter(k => (k === c) !== (k.getAttribute("aria-pressed") === "true")).map(k => k.dataset.rub);
        review(b, { label: x.label, rubric: ids }).then(again); }; });
      on("[data-addc]", () => { adding.add(id); const y = window.scrollY; redraw(); window.scrollTo(0, y);
        const f = box.querySelector(`.sc-q[data-k="${CSS.escape(b.key)}"][data-q="${CSS.escape(x.label)}"] .sc-nd`); if (f) f.focus(); });
      on("[data-ccancel]", () => { adding.delete(id); const y = window.scrollY; redraw(); window.scrollTo(0, y); });
      const nd = el.querySelector(".sc-nd"), nt = el.querySelector(".sc-nt");
      if (nd && nt) {
        const zero = ((R.rubrics || {})[x.id] || {}).marking === "zero";
        const add = async () => {
          const raw = nd.value.trim().replace("−", "-");
          if (!/^[+-]?\d*\.?\d+$/.test(raw)) { toast("How many marks: −1, +2, or 0."); nd.focus(); return; }
          const n = /^[+-]/.test(raw) ? Number(raw) : (zero ? 1 : -1) * Number(raw);
          if (!nt.value.trim()) { toast("Write the comment."); nt.focus(); return; }
          try {
            const d = await api("/api/scans/comment", body({ booklet: b.key, label: x.label, text: nt.value, delta: n }));
            const k = R.booklets.findIndex(z => z.key === b.key); if (k >= 0) R.booklets[k] = d.booklet;
            const fresh = await api(`/api/scans/results?${params()}`); R.rubrics = fresh.rubrics;
            adding.delete(id); const y = window.scrollY; redraw(); window.scrollTo(0, y);
          } catch (e) { toast(e.message); }
        };
        on("[data-csave]", add);
        [nd, nt].forEach(f => { f.onkeydown = e => { if (e.key === "Enter") add(); if (e.key === "Escape") { adding.delete(id); redraw(); } }; });
      }
      on("[data-addn]", () => { noting.add(id); const y = window.scrollY; redraw(); window.scrollTo(0, y);
        const f = box.querySelector(`.sc-q[data-k="${CSS.escape(b.key)}"][data-q="${CSS.escape(x.label)}"] .sc-cnote-in`); if (f) f.focus(); });
      const ni = el.querySelector(".sc-cnote-in");
      if (ni) { ni.onchange = () => review(b, { label: x.label, note: ni.value }).then(ok => { if (ok) toast("Note saved."); }); ni.onkeydown = e => { if (e.key === "Enter") ni.blur(); }; }
      // The typed copy: a piece's boxes saved when you leave them (or press Enter), if they changed; cells move on as you type.
      const watch = (f, save) => { if (!f) return; const was = fieldValue(f);
        const go = () => { const v = fieldValue(f); if (v !== was) save(v); };
        f.addEventListener("focusout", e => { if (!f.contains(e.relatedTarget)) go(); });
        f.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); go(); } if (e.key === "Escape") { f.querySelectorAll("input").forEach(i => { i.value = i.defaultValue; }); e.target.blur(); } });
        if (f.classList.contains("dz-cells") || f.dataset.kind === "cells") f.querySelectorAll("input").forEach((i, k, all) => { i.oninput = () => { if (i.value && all[k + 1]) all[k + 1].focus(); }; }); };
      watch(el.querySelector(":scope > .sc-pair > .dz-one .dz-field, :scope > .dz-one .dz-field"), v => say(v));   // not a blank row's
      // Each blank of several: its reading, a yes to the grader's, or its own score.
      el.querySelectorAll(".sc-bl[data-blank]").forEach(row => {
        const bid = row.dataset.blank, y = (x.blanks || []).find(z => z.id === bid), bkey = `${id}|${bid}`;
        if (!y) return;
        const done = ok => { if (ok) { editing.delete(bkey); const sy = window.scrollY; redraw(); window.scrollTo(0, sy); } };
        const send = what => review(b, { label: x.label, blank: bid, ...what }).then(done);
        const bon = (sel, fn) => { const k = row.querySelector(sel); if (k) k.onclick = fn; };
        watch(row.querySelector(".dz-field"), v => send({ read: v }));
        const openIt = () => { editing.add(bkey); const sy = window.scrollY; redraw(); window.scrollTo(0, sy);
          const ri = box.querySelector(`.sc-q[data-k="${CSS.escape(b.key)}"][data-q="${CSS.escape(x.label)}"] .sc-bl[data-blank="${CSS.escape(bid)}"] .sc-readin`); if (ri) { ri.focus(); ri.select(); } };
        bon("[data-byes]", () => send({ keep: true }));
        bon("[data-bno]", openIt);
        bon("[data-bedit]", openIt);
        bon("[data-bcancel]", () => { editing.delete(bkey); const sy = window.scrollY; redraw(); window.scrollTo(0, sy); });
        const ri = row.querySelector(".sc-readin");
        if (ri) {
          bon("[data-bsave]", () => send({ read: ri.value }));
          ri.onkeydown = e => { if (e.key === "Enter") send({ read: ri.value }); if (e.key === "Escape" && y.status !== "manual") { editing.delete(bkey); redraw(); } };
        }
        const bi = row.querySelector(".sc-bscore input");
        bi.onchange = () => { const v = bi.value.trim(); if (v === "") return; const n = Number(v);
          if (!(n >= 0 && n <= y.points)) { toast(`A score from 0 to ${fmtN(y.points)}.`); bi.value = y.score == null ? "" : fmtN(y.score); return; }
          send({ score: n }); };
        bi.onkeydown = e => { if (e.key === "Enter") bi.blur(); };
      });
      // Their answer picked on the scan: a bubble (one answer), or a box ticked or unticked (multiple answers).
      // Each click fills or empties that bubble, as on paper: a student can fill two, or none (then it's wrong).
      const said = ks => (x.options[0] === "True" ? ks.join(", ") : ks.join(""));
      el.querySelectorAll("[data-hot]").forEach(h => { h.onclick = () => {
        say(said([...el.querySelectorAll("[data-hot]")].filter(k => (k === h) !== (k.getAttribute("aria-pressed") === "true")).map(k => k.dataset.hot))); }; });
      on("[data-hotok]", () => say(said(String(x.read || "").split(", ").filter(v => v && v !== "none"))));
      const opts = [...el.querySelectorAll("[data-opt]")];
      opts.forEach(o => { o.onclick = () => {
        if (!x.multi) return say(o.dataset.opt);
        o.setAttribute("aria-pressed", String(o.getAttribute("aria-pressed") !== "true")); }; });
      on("[data-optsave]", () => say(opts.filter(o => o.getAttribute("aria-pressed") === "true").map(o => o.dataset.opt).join("")));
    });
  }

  load();
  return { leave: () => clearTimeout(timer), load };
}
