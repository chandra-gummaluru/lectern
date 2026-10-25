/* Students: the offering's class list, in the Students card on its page (Lectern → the offering).

   It's the gradebook's students: <course>/<term>/grades.json in the offering's private files, the file the
   Gradebook opens (it shows them for marks, but doesn't add or change them). Each student is
     { num, first, last, name: "Last, First", f: { email, <field id>: … }, dropped? }
   and what every student has is the gradebook's fields:
     fields: { idLabel, emailDomain, custom: [{ id: "email", label: "Email" }, { id, label }…] }
   The fields are set before the first student is added, and fixed from then on.

   Each enrolled student (not dropped) with an email can sign in to the course page with it and a code it
   emails them (server/students.py, which also says who has signed in and been sent the link).
   Instructors add students here (one at a time, or from a class list), and can send the course page's link
   to anyone who hasn't joined yet. Nothing else about a student changes here: clicking one opens their page in
   the gradebook (where they're dropped or deleted). The team sees the list. Each change saves straight away. */
import { SECTION_KINDS, SECTION_NAME, SECTION_ICON, sectionKind, sortSections, oneOfEach } from "./groups.js";

const uid = () => Math.random().toString(36).slice(2, 10);
const EMAIL = /^[^\s@,;<>]+@[a-z0-9-]+(\.[a-z0-9-]+)+$/i;
const BLANK_FIELDS = () => ({ idLabel: "Student Identifier", emailDomain: "", custom: [{ id: "email", label: "Email" }] });
const cleanDomain = d => String(d || "").trim().toLowerCase().replace(/^.*@/, "").replace(/[^a-z0-9.-]/g, "");
const cleanNum = v => String(v ?? "").trim().replace(/\.0+$/, "");
const withName = s => { s.name = [s.last, s.first].filter(Boolean).join(", "); return s; };
const emailOf = s => String(((s.f || {}).email ?? s.email) || "").trim();
const fieldOf = (s, id) => String(((s.f || {})[id] ?? s[id]) || "");

// What every student has. (An older gradebook without fields: what normalizeBook in the Gradebook makes of it.)
function fieldsOf(b) {
  const x = b && b.fields, list = (b && b.students) || [];
  const F = Object.assign(BLANK_FIELDS(), x || {});
  F.custom = ((x && x.custom) || []).filter(f => f && f.id).map(f => ({ id: String(f.id), label: String(f.label || "Field") }));
  if (!x) {
    if (list.length) F.idLabel = "Student number";
    [["utorid", "UTORid"], ["section", "Section"]].forEach(([k, label]) => { if (list.some(s => s && s[k])) F.custom.push({ id: k, label }); });
  }
  F.custom = [{ id: "email", label: "Email" }, ...F.custom.filter(f => f.id !== "email")];
  F.emailDomain = cleanDomain(F.emailDomain);
  return F;
}
function emailProblem(email, domain) {
  const v = String(email || "").trim().toLowerCase();
  if (!v) return "No email";
  if (!EMAIL.test(v)) return "Email isn't an address";
  return domain && !v.endsWith("@" + domain) ? `Email isn't @${domain}` : "";
}
// ── CSV (as the Gradebook reads class lists) ─────────────────────────
function parseCSV(text) {
  const rows = []; let row = [], cell = "", q = false;
  text = String(text).replace(/^﻿/, "");
  const first = text.split("\n")[0], tabs = (first.match(/\t/g) || []).length, commas = (first.match(/,/g) || []).length;
  if (!tabs && !commas) return text.split(/\r?\n/).map(l => l.trim()).filter(Boolean).map(l => l.split(/\s+/));
  const sep = tabs > commas ? "\t" : ",";
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; continue; }
    if (c === '"') q = true;
    else if (c === sep) { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += c;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.filter(r => r.some(x => String(x).trim() !== ""));
}
function guess(headers, tests) {
  const h = headers.map(x => String(x).toLowerCase().trim());
  for (const t of tests) { const k = h.findIndex(x => (t instanceof RegExp ? t.test(x) : x === t)); if (k >= 0) return k; }
  return -1;
}
const NUM_COL = [/student\s*(id\s*)?(number|#|no\.?)/, "sis user id", "id number", "student id", "student_number", "studentnumber", /^id$/, /\bid\b/];

const IDCARD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2.2"/><path d="M5.8 16c.6-1.6 1.8-2.4 3.2-2.4s2.6.8 3.2 2.4M14.5 10h3.5M14.5 13.5h3.5"/></svg>';
const ui = {};   // per offering: what's typed in Find a student

export async function studentsCard(ctx, c, t) {
  const { box, esc, toast, modal, confirmBox, Store, area, api, owner, lead, ICON, here, gradebook, changedBook, termName, openStudent, groups, groupIds } = ctx;
  const path = `${c}/${t}/grades.json`, repo = area(Store.PRIV), key = `${owner}/${c}/${t}`;
  const base = `/api/students/${encodeURIComponent(owner)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`;
  const st = (ui[key] = ui[key] || { find: "" });
  let book = null, info = null, G = [];   // G: the sections (a student is in one of each type)

  async function load() {
    try {
      const [f, d, g] = await Promise.all([Store.readFile(repo, path), api(base), groups ? groups().catch(() => []) : []]);
      book = f ? JSON.parse(f.text) : null; info = d; G = g || [];
      // The gradebook open with changes not saved yet (a student dropped or deleted there): its copy.
      const gb = gradebook(); if (gb && gb.api && gb.api.state().path === path && gb.api.state().unsaved) book = gb.api.book();
    } catch (e) { if (here()) box.innerHTML = `<p class="lt-note err">Couldn't read the class list. ${esc(e.message)}</p>`; return; }
    if (here()) draw();
  }
  const refreshInfo = async () => { try { info = await api(base); } catch (_) {} if (here()) draw(); };
  const blankBook = () => ({ format: "grade-builder/1", course: { code: c.toUpperCase(), term: termName(t) }, fields: BLANK_FIELDS(), evals: [], groups: [], students: [], marks: {}, overrides: {}, finals: {} });
  const UNSAVED = "The gradebook has changes that aren't saved yet. Save them (Save, in your account menu) before changing the students.";
  const busy = () => { const g = gradebook(); return !!(g && g.api.state().unsaved); };

  // Change the list: read the file as it is now, change it, write it back (once more if it changed meanwhile).
  async function write(fn, msg) {
    if (busy()) { toast(UNSAVED); return false; }
    for (let k = 0; ; k++) {
      const f = await Store.readFile(repo, path);
      const b = f ? JSON.parse(f.text) : blankBook();
      if (!Array.isArray(b.students)) b.students = [];
      const r = fn(b);
      if (r === false) return false;
      try { await Store.writeText(repo, path, JSON.stringify(b, null, 2) + "\n", msg, f ? f.sha : null); book = b; changedBook(!f); return r === undefined ? true : r; }
      catch (e) { if (!e.conflict || k) throw e; }
    }
  }
  const run = async (fn, msg) => { try { const r = await write(fn, msg); if (here()) draw(); return r; } catch (e) { toast(`Couldn't save the class list. ${e.message}`); return false; } };

  const list = () => ((book && book.students) || []).filter(s => s && s.num);
  const stateOf = (s, F) => {
    if (s.dropped) return "Dropped: can't sign in";
    const p = emailProblem(emailOf(s), F.emailDomain); if (p) return `${p}: can't sign in`;
    const x = (info.state || {})[emailOf(s).toLowerCase()] || {}, when = v => new Date(v * 1000).toLocaleDateString("en-CA", { month: "short", day: "numeric" });
    return x.last_in ? `Signed in ${when(x.last_in)}` : x.invited ? `Sent the link ${when(x.invited)}` : "Not signed in yet";
  };

  function draw() {
    const F = fieldsOf(book), all = list().slice().sort((a, b) => (!!a.dropped - !!b.dropped) || String(a.name || a.last || "").localeCompare(String(b.name || b.last || "")) || a.num.localeCompare(b.num));
    const locked = all.length > 0, held = lead && busy(), dis = held ? " disabled" : "";
    const enrolled = all.filter(s => !s.dropped), waiting = enrolled.filter(s => !emailProblem(emailOf(s), F.emailDomain) && !joined(s)), canMail = info.email && waiting.length;
    const custom = F.custom.filter(f => f.id !== "email");
    // What each student has, right here: each field a row (the identifier's name and the email domain typed
    // in theirs), until there are students; then it's fixed, and shown as a line.
    const fieldNames = [F.idLabel, "First Name", "Last Name", `Email${F.emailDomain ? ` (@${F.emailDomain})` : ""}`, ...custom.map(f => f.label)];
    const open = lead && !locked;
    const fixedRow = (n, note) => `<div class="lt-orow lt-sf-row fixed"><span class="lt-sf-n">${esc(n)}</span><span class="lt-sf-note">${esc(note)}</span></div>`;
    const fields = !lead ? "" : open ? `<div class="lt-st-fieldbox"><p class="lt-st-kick">What Each Student Has <span>Set it before adding students: once there are students, it's fixed.</span></p>
      <div class="lt-olist lt-sf-list">
        <div class="lt-orow lt-sf-row"><label class="lt-sf-l" for="sf-id">Identifier</label><input type="text" id="sf-id" value="${esc(F.idLabel)}" placeholder="e.g. Student Number" autocomplete="off"${dis}><span class="lt-sf-note">Unique for each student</span></div>
        ${fixedRow("First Name", "Every student has it")}${fixedRow("Last Name", "Every student has it")}
        <div class="lt-orow lt-sf-row"><label class="lt-sf-l" for="sf-dom">Email</label><span class="lt-sf-at">@</span><input type="text" id="sf-dom" value="${esc(F.emailDomain)}" placeholder="Any domain, e.g. mail.utoronto.ca" spellcheck="false" autocomplete="off"${dis}><span class="lt-sf-note">They sign in with it</span></div>
        ${custom.map(f => `<div class="lt-orow lt-sf-row"><span class="lt-sf-n">Field</span><input type="text" data-sf-name="${esc(f.id)}" value="${esc(f.label)}" placeholder="e.g. UTORid" aria-label="Field name" autocomplete="off"${dis}><button type="button" class="lt-btn lt-trash" data-sf-del="${esc(f.id)}" aria-label="Remove the field ${esc(f.label)}"${dis}>${ICON.trash}</button></div>`).join("")}
        ${st.newField ? `<div class="lt-orow lt-sf-row"><span class="lt-sf-n">New field</span><input type="text" id="sf-new" placeholder="The field's name, e.g. UTORid" aria-label="New field" autocomplete="off"${dis}><button type="button" class="lt-btn lt-trash" id="sf-new-x" aria-label="Don't add it">${ICON.trash}</button></div>` : ""}
      </div>
      <div class="lt-sf-add"><button type="button" class="lt-btn add" id="sf-add"${dis}>${ICON.plus}Add a Field</button></div></div>`
      : `<div class="lt-olist lt-st-fieldrow"><div class="lt-orow lt-user lt-sec-row"><div class="lt-user-who"><span class="lt-sec-ic" aria-hidden="true">${IDCARD}</span><span class="lt-sec-t"><small>What Each Student Has</small><b>${esc(fieldNames.join(", "))}</b><span>Fixed now that there are students.</span></span></div></div></div>`;
    box.innerHTML = `<div class="lt-st-head"><p class="lt-part-text">The class list: each student here can sign in to the course page, with their email and a code it emails them, and the gradebook has them for marks. The course page's link: <code>${esc(info.link)}</code> <button type="button" class="lt-link" id="st-copy">Copy</button></p>
      ${lead ? `<div class="lt-st-acts"><button type="button" class="lt-btn add" id="st-add"${dis}>${ICON.plus}Add a Student</button><button type="button" class="lt-btn" id="st-import"${dis}>${ICON.upload || ""}Import a Class List</button></div>` : ""}</div>
      ${held ? `<p class="lt-note lt-st-note">${UNSAVED}</p>` : ""}
      ${lead && !info.email ? `<p class="lt-note lt-st-note">Email isn't set up on this server, so Lectern can't email students their link or a sign-in code.</p>` : ""}
      ${fields}
      <div class="lt-st-bar"><p class="lt-part-text lt-st-count">${all.length ? `${enrolled.length} student${enrolled.length === 1 ? "" : "s"}${all.length > enrolled.length ? ` · ${all.length - enrolled.length} dropped` : ""}` : "No students yet."}${lead && canMail ? ` · <button type="button" class="lt-link" id="st-all">Send the link to the ${waiting.length} who haven't joined</button>` : ""}</p>
        ${all.length > 8 ? `<input type="search" class="lt-st-find" id="st-find" placeholder="Find a student" value="${esc(st.find)}" aria-label="Find a student">` : ""}</div>
      ${all.length ? `<div class="lt-olist lt-st-list">${all.map(s => {
        const mail = emailOf(s), ok = !s.dropped && !emailProblem(mail, F.emailDomain), q = [s.name, s.first, s.last, s.num, mail, ...custom.map(f => fieldOf(s, f.id))].join(" ").toLowerCase();
        const gs = groupNames(s);
        const who = `<b>${esc(s.name || [s.last, s.first].filter(Boolean).join(", ") || s.num)}</b><span>${esc(s.num)}${mail ? ` · ${esc(mail)}` : ""} · <em>${esc(stateOf(s, F))}</em>${G.length ? ` · ${gs.length ? esc(gs.join(", ")) : `<em class="lt-st-nogroup">No section</em>`}` : ""}</span>`;
        const sent = ((info.state || {})[mail.toLowerCase()] || {}).invited;
        return `<div class="lt-orow lt-user${s.dropped ? " lt-st-dropped" : ""}" data-q="${esc(q)}">
          <button type="button" class="lt-user-who lt-user-open" data-st-open="${esc(s.num)}" title="Their page in the gradebook">${who}</button>
          ${lead && ok && info.email && !joined(s) ? `<span class="lt-orow-r"><button type="button" class="lt-btn lt-st-send" data-st-invite="${esc(mail)}">${ICON.mail}${sent ? "Resend the Link" : "Send the Link"}</button></span>` : ""}</div>`;
      }).join("")}</div>` : ""}`;
    wire(F);
    filter();
  }
  const groupNames = s => (s.groups || []).map(id => (G.find(g => g.id === id) || {}).name).filter(Boolean);
  const joined = s => !!((info.state || {})[emailOf(s).toLowerCase()] || {}).last_in;
  function filter() {
    const q = st.find.trim().toLowerCase();
    box.querySelectorAll(".lt-st-list [data-q]").forEach(r => { r.hidden = !!q && !r.dataset.q.includes(q); });
  }

  function wire(F) {
    const $ = s => box.querySelector(s);
    $("#st-copy").onclick = async () => { try { await navigator.clipboard.writeText(info.link); toast("Copied the course page's link."); } catch (_) { toast(info.link); } };
    const find = $("#st-find"); if (find) find.oninput = () => { st.find = find.value; filter(); };
    box.querySelectorAll("[data-st-open]").forEach(x => { x.onclick = () => openStudent(x.dataset.stOpen); });
    if (!lead) return;
    // What each student has: each change saves.
    const saveF = fn => run(b => { b.fields = fieldsOf(b); return fn(b.fields); }, "Student fields");
    const taken = (label, not) => /^\s*e-?mail( address)?\s*$/i.test(label) || /^(first|last) ?name$/i.test(label) || fieldsOf(book).custom.some(f => f.id !== not && f.label.toLowerCase() === label.toLowerCase());
    const idIn = $("#sf-id"), domIn = $("#sf-dom");
    if (idIn) idIn.onchange = () => saveF(F2 => { F2.idLabel = idIn.value.trim() || "Student Identifier"; });
    if (domIn) domIn.onchange = () => saveF(F2 => { F2.emailDomain = cleanDomain(domIn.value); });
    box.querySelectorAll("[data-sf-name]").forEach(i => { i.onchange = () => { const v = i.value.trim(); if (!v || taken(v, i.dataset.sfName)) { toast(v ? `There's a field called ${v} already.` : "Give the field a name, or remove it."); return; } saveF(F2 => { const f = F2.custom.find(x => x.id === i.dataset.sfName); if (f) f.label = v; }); }; });
    box.querySelectorAll("[data-sf-del]").forEach(x => { x.onclick = () => saveF(F2 => { F2.custom = F2.custom.filter(f => f.id !== x.dataset.sfDel); }); });
    const addB = $("#sf-add"); if (addB) addB.onclick = () => { st.newField = true; draw(); const n = $("#sf-new"); if (n) n.focus(); };
    const nf = $("#sf-new");
    if (nf) {
      let done = false;
      const commit = () => { const v = nf.value.trim(); if (!v || done) return; done = true; if (taken(v)) { done = false; toast(`Every student has ${v} already.`); return; } st.newField = false; saveF(F2 => { F2.custom.push({ id: uid(), label: v }); }).then(() => { const b2 = $("#sf-add"); if (b2) b2.focus(); }); };
      nf.onchange = commit; nf.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); commit(); } if (e.key === "Escape") { st.newField = false; draw(); } };
      $("#sf-new-x").onclick = () => { st.newField = false; draw(); };
    }
    $("#st-add").onclick = () => studentDialog(null);
    $("#st-import").onclick = importDialog;
    box.querySelectorAll("[data-st-invite]").forEach(x => { x.onclick = async e => { e.stopPropagation(); try { await api(`${base}/invite`, { email: x.dataset.stInvite }); toast(`Emailed ${x.dataset.stInvite} the link.`); refreshInfo(); } catch (er) { toast(er.message); } }; });
    const all = $("#st-all");
    if (all) all.onclick = async () => {
      const to = list().filter(s => !s.dropped && !emailProblem(emailOf(s), F.emailDomain) && !joined(s)).map(emailOf), n = to.length;
      if (!await confirmBox("Send them the link?", `Each of the ${n} student${n === 1 ? "" : "s"} who ${n === 1 ? "hasn't" : "haven't"} signed in to the course page yet gets an email with its link.`, "Send It")) return;
      try { const r = await api(`${base}/invite`, { emails: to }); toast(`Emailed ${r.invited} student${r.invited === 1 ? "" : "s"} the link.`); refreshInfo(); } catch (e) { toast(e.message); }
    };
  }

  // Adding one student. (Once added, nothing about them changes here.)
  function studentDialog(s) {
    const F = fieldsOf(book), custom = F.custom.filter(f => f.id !== "email");
    const v = (id, k) => esc(s ? (k ? fieldOf(s, k) : s[id] || "") : "");
    modal(`<h2>${s ? esc(s.name || s.num) : "Add a Student"}</h2>
      <div class="lt-form">
        <label>${esc(F.idLabel)}<input type="text" id="sd-num" value="${v("num")}" spellcheck="false" autocomplete="off"${s ? " readonly" : ""}>${s ? `<small>Their marks are kept by it, so it doesn't change.</small>` : ""}</label>
        <div class="two"><label>First Name<input type="text" id="sd-first" value="${v("first")}" autocomplete="off"></label><label>Last Name<input type="text" id="sd-last" value="${v("last")}" autocomplete="off"></label></div>
        <label>Email<input type="email" id="sd-email" value="${s ? esc(emailOf(s)) : ""}" placeholder="name@${esc(F.emailDomain || "example.com")}" spellcheck="false" autocomplete="off"><small>They sign in to the course page with it.</small></label>
        ${custom.map(f => `<label>${esc(f.label)}<input type="text" data-sd="${esc(f.id)}" value="${v("", f.id)}" spellcheck="false" autocomplete="off"></label>`).join("")}
        ${G.length ? `<div class="two lt-st-secs">${SECTION_KINDS.filter(([k]) => G.some(g => sectionKind(g) === k)).map(([k]) => `<label>${esc(SECTION_NAME[k])}<select data-sd-k="${k}"><option value="" data-icon="${esc(SECTION_ICON[k])}">None</option>${sortSections(G.filter(g => sectionKind(g) === k)).map(g => `<option value="${esc(g.id)}" data-icon="${esc(SECTION_ICON[k])}"${s && (s.groups || []).includes(g.id) ? " selected" : ""}>${esc(g.name || "Untitled section")}</option>`).join("")}</select></label>`).join("")}</div><small class="lt-st-secs-h">One of each type, e.g. their lecture section and their tutorial section. At least one.</small>` : ""}
        ${!s && info.email ? `<label class="lt-check"><input type="checkbox" id="sd-invite" checked> Email them the course page's link</label>` : ""}
      </div>
      <p class="lt-err" id="sd-err"></p>
      <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn primary" data-ok>${s ? "Save" : "Add"}</button></div>`, (m, close) => {
      const val = id => m.querySelector(id).value.trim(), err = m.querySelector("#sd-err");
      m.querySelector("[data-no]").onclick = close;
      const ok = async () => {
        const num = s ? s.num : cleanNum(val("#sd-num")), email = val("#sd-email").toLowerCase();
        if (!num) { err.textContent = `Enter their ${F.idLabel.toLowerCase()}.`; return m.querySelector("#sd-num").focus(); }
        if (!s && list().some(x => x.num.toLowerCase() === num.toLowerCase())) { err.textContent = `${num} is on the list already: each ${F.idLabel.toLowerCase()} is one student's.`; return; }
        const p = emailProblem(email, F.emailDomain);
        if (p) { err.textContent = `${p}. Every student needs ${F.emailDomain ? `an @${F.emailDomain}` : "an"} email: they sign in with it.`; return m.querySelector("#sd-email").focus(); }
        if (list().some(x => x.num !== num && emailOf(x).toLowerCase() === email)) { err.textContent = `${email} is another student's email.`; return; }
        const gs = [...m.querySelectorAll("[data-sd-k]")].map(i => i.value).filter(Boolean);
        if (G.length && !gs.length) { err.textContent = "Pick their sections: every student is in at least one."; return; }
        const f = { email };
        m.querySelectorAll("[data-sd]").forEach(i => { if (i.value.trim()) f[i.dataset.sd] = i.value.trim(); });
        const invite = !s && m.querySelector("#sd-invite") && m.querySelector("#sd-invite").checked;
        m.querySelector("[data-ok]").disabled = true;
        const done = await run(b => {
          const was = b.students.find(x => x.num === num);
          if (s && was) { if (G.length) was.groups = gs; was.first = val("#sd-first"); was.last = val("#sd-last"); was.f = Object.assign({}, was.f || {}, f); custom.forEach(x => { if (!f[x.id] && was.f) delete was.f[x.id]; }); withName(was); delete was.email; return; }
          if (was) return false;
          b.students.push(withName({ num, first: val("#sd-first"), last: val("#sd-last"), f, ...(gs.length ? { groups: gs } : {}) }));
        }, s ? "A student's details" : "Add a student");
        if (!done) { m.querySelector("[data-ok]").disabled = false; return; }
        close();
        if (invite) { try { await api(`${base}/invite`, { email }); toast(`Added ${val("#sd-first") || num}, and emailed them the link.`); } catch (e) { toast(`Added them, but the link didn't go out. ${e.message}`); } refreshInfo(); }
        else toast(s ? "Saved." : `Added ${[val("#sd-first"), val("#sd-last")].filter(Boolean).join(" ") || num}.`);
      };
      m.querySelector("[data-ok]").onclick = ok;
      m.querySelectorAll("input[type=text], input[type=email]").forEach(i => i.addEventListener("keydown", e => { if (e.key === "Enter") ok(); }));
    });
  }

  // A class list from Quercus (its gradebook export) or ACORN: students already on the list (by identifier) are updated.
  function importDialog() {
    const F = fieldsOf(book), custom = F.custom.filter(f => f.id !== "email");
    modal(`<h2>Import a Class List</h2><p>A CSV from Quercus (its gradebook export) or ACORN. Students already on the list (by ${esc(F.idLabel.toLowerCase())}) are updated, not added twice.</p>
      <div id="im-src"><label class="lt-st-drop"><input type="file" accept=".csv,.tsv,.txt,text/csv" hidden><b>Choose a CSV file</b><span>or drop it here</span></label></div>
      <div id="im-map"></div>
      <p class="lt-err" id="im-err"></p>
      <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="button" class="lt-btn primary" data-ok disabled>Import</button></div>`, (m, close) => {
      m.querySelector("[data-no]").onclick = close;
      const src = m.querySelector("#im-src"), inp = src.querySelector("input");
      const read = f => { const r = new FileReader(); r.onload = () => show(String(r.result), f.name); r.onerror = () => toast(`Couldn't read ${f.name}.`); r.readAsText(f); };
      inp.onchange = () => inp.files[0] && read(inp.files[0]);
      src.addEventListener("dragover", e => e.preventDefault());
      src.addEventListener("drop", e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) read(f); });
      function show(text, name) {
        const rows = parseCSV(text), H = (rows[0] || []).map(h => String(h).trim()), body = rows.slice(1).filter(r => !/points possible/i.test(r.join(" ")));
        if (!H.length) { m.querySelector("#im-err").textContent = `${name} looks empty.`; return; }
        const cols = [
          { k: "num", label: `${F.idLabel} (required)`, g: guess(H, [F.idLabel.toLowerCase(), ...NUM_COL, "utorid", "sis login id"]), need: true },
          { k: "first", label: "First Name", g: guess(H, ["first name", "given name", /first/]) },
          { k: "last", label: "Last Name", g: guess(H, ["last name", "surname", "family name", /last/]) },
          { k: "name", label: "Or one name column (Last, First)", g: guess(H, ["student", "name", "full name", /^student name/]) },
          { k: "email", label: "Email", g: guess(H, ["email", "e-mail", /e-?mail/]) },
          { k: "g1", label: "Lecture section (e.g. LEC0101)", g: guess(H, ["lecture", "lecture section", "section", /^lec/, /lecture/, /section/]) },
          { k: "g2", label: "Tutorial section (e.g. TUT0102)", g: guess(H, ["tutorial", "tutorial section", /^tut/, /tutorial/]) },
          { k: "g3", label: "Lab section (e.g. PRA0101)", g: guess(H, ["lab", "lab section", "practical", /^pra/, /practical/, /\blab/]) },
          ...custom.map(f => ({ k: `f:${f.id}`, label: f.label, g: guess(H, [f.label.toLowerCase(), ...(/utorid/i.test(f.label) ? ["sis login id", "login id"] : /section/i.test(f.label) ? [/section/] : [])]) })),
        ];
        const sel = (i, c) => `<select id="im-c${i}">${c.need ? "" : `<option value="-1">(none)</option>`}${H.map((h, k) => `<option value="${k}"${k === c.g ? " selected" : ""}>${esc(h || `Column ${k + 1}`)}</option>`).join("")}</select>`;
        src.innerHTML = `<p class="lt-st-file"><b>${esc(name)}</b> · ${body.length} row${body.length === 1 ? "" : "s"}</p>`;
        const map = m.querySelector("#im-map");
        map.innerHTML = `<div class="lt-form lt-st-map">${cols.map((c, i) => `<label>${esc(c.label)}${sel(i, c)}</label>`).join("")}</div>
          <p class="lt-part-text lt-st-sum" id="im-sum"></p><div id="im-more"></div>`;
        const people = () => {
          const ix = cols.map((c, i) => +map.querySelector(`#im-c${i}`).value), at = (r, k) => { const i = ix[cols.findIndex(c => c.k === k)]; return i >= 0 ? String(r[i] ?? "").trim() : ""; };
          const seen = new Map();
          body.forEach(r => {
            const num = cleanNum(at(r, "num")); if (!num) return;
            let first = at(r, "first"), last = at(r, "last");
            if (!first && !last && at(r, "name")) { const n = at(r, "name"); if (n.includes(",")) [last, first] = n.split(",").map(x => x.trim()); else { const w = n.split(/\s+/); last = w.length > 1 ? w.pop() : w[0]; first = w.join(" "); } }
            const f = {}; const e = at(r, "email").toLowerCase(); if (e) f.email = e;
            custom.forEach(x => { const v = at(r, `f:${x.id}`); if (v) f[x.id] = v; });
            const gn = [["g1", "lecture"], ["g2", "tutorial"], ["g3", "lab"]].flatMap(([k, kind]) => at(r, k).split(/[,;\s]+/).map(v => v.trim()).filter(Boolean).map(name => ({ name, kind })));
            seen.set(num, { num, first, last, f, gn });
          });
          return [...seen.values()];
        };
        const have = () => new Map(list().map(s => [s.num, s]));
        const sum = () => {
          const P = people(), H2 = have(), upd = P.filter(p => H2.has(p.num)).length, bad = P.filter(p => emailProblem(p.f.email || emailOf(H2.get(p.num) || {}), F.emailDomain));
          const gone = list().filter(s => !s.dropped && !P.some(p => p.num === s.num));
          m.querySelector("#im-sum").innerHTML = `${P.length - upd} new student${P.length - upd === 1 ? "" : "s"}, ${upd} already on the list.${bad.length ? ` <b>${bad.length} ${bad.length === 1 ? "has" : "have"} no ${F.emailDomain ? `@${esc(F.emailDomain)} ` : ""}email</b>, so ${bad.length === 1 ? "they" : "they"} can't sign in until it's set.` : ""}`;
          m.querySelector("#im-more").innerHTML = `${gone.length && P.length ? `<label class="lt-check"><input type="checkbox" id="im-drop"> Drop the ${gone.length} student${gone.length === 1 ? "" : "s"} not in this file</label>` : ""}
            ${info.email && P.length > upd ? `<label class="lt-check"><input type="checkbox" id="im-invite"> Email the new students the course page's link</label>` : ""}`;
          m.querySelector("[data-ok]").disabled = !P.length;
        };
        map.addEventListener("change", e => { if (e.target.tagName === "SELECT") sum(); });
        sum();
        m.querySelector("[data-ok]").onclick = async () => {
          const P = people(), drop = m.querySelector("#im-drop") && m.querySelector("#im-drop").checked, invite = m.querySelector("#im-invite") && m.querySelector("#im-invite").checked;
          m.querySelector("[data-ok]").disabled = true;
          let ids = new Map();
          if (groupIds && P.some(p => p.gn.length)) { try { ids = await groupIds(P.flatMap(p => p.gn)); } catch (e) { m.querySelector("#im-err").textContent = `Couldn't make the sections. ${e.message}`; m.querySelector("[data-ok]").disabled = false; return; } }
          if (ids.size) G = await groups().catch(() => G);
          P.forEach(p => { p.groups = oneOfEach(p.gn.map(n => ids.get(n.name.toLowerCase())).filter(Boolean), G); });
          const r = await run(b => {
            const fresh = [], dropped = [];
            P.forEach(p => {
              const s = b.students.find(x => x.num === p.num);
              if (s) { if (p.first) s.first = p.first; if (p.last) s.last = p.last; s.f = Object.assign({}, s.f || {}, p.f); if (p.groups.length) s.groups = p.groups; withName(s); delete s.dropped; }
              else { b.students.push(withName({ num: p.num, first: p.first, last: p.last, f: p.f, ...(p.groups.length ? { groups: p.groups } : {}) })); fresh.push(p); }
            });
            if (drop) b.students.forEach(s => { if (!s.dropped && !P.some(p => p.num === s.num)) { s.dropped = true; dropped.push(s); } });
            return { fresh, dropped };
          }, "Import a class list");
          if (!r) { m.querySelector("[data-ok]").disabled = false; return; }
          close();
          if (ids.size) { G = await groups().catch(() => G); if (ctx.groupsChanged) ctx.groupsChanged(); if (here()) draw(); }
          let sent = "";
          const mails = r.fresh.map(p => p.f.email).filter(e => !emailProblem(e, F.emailDomain));
          if (invite && mails.length) { try { const x = await api(`${base}/invite`, { emails: mails }); sent = `; emailed ${x.invited} the link`; } catch (e) { sent = `; the links didn't go out (${e.message})`; } refreshInfo(); }
          toast(`Imported ${P.length} student${P.length === 1 ? "" : "s"} (${r.fresh.length} new)${r.dropped.length ? `; dropped ${r.dropped.length}` : ""}${sent}.`);
        };
      }
    });
  }

  load();
}
