/* Students: the offering's class list, in the Students card on its page (Lectern → the offering).

   It's the gradebook's students: <course>/<term>/grades.json in the offering's private files, the file the
   Gradebook opens (it shows them for marks, but doesn't add or change them). Each student is
     { num, first, last, name: "Last, First", f: { email, <field id>: … }, dropped? }
   and what every student has is the gradebook's fields:
     fields: { idLabel, emailDomain, custom: [{ id: "email", label: "Email" }, { id, label }…] }
   The fields are set before the first student is added, and fixed from then on.

   Each enrolled student (not dropped) with an email can sign in to the course page with it and a code it
   emails them (server/students.py, which also says who has signed in and been sent the link).
   Instructors change the list; TAs see it. Each change saves straight away. */

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
// Anything the gradebook keeps for them besides their details: then they're dropped (kept), not deleted.
const keptFor = (b, num) => !!Object.keys((b.marks || {})[num] || {}).length || !!Object.keys((b.overrides || {})[num] || {}).length || !!(b.finals || {})[num]
  || !!((b.students || []).find(s => s.num === num) || {}).notes;

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

const ui = {};   // per offering: what's typed in Find a student

export async function studentsCard(ctx, c, t) {
  const { box, esc, toast, modal, confirmBox, Store, area, api, owner, lead, ICON, here, gradebook, changedBook, termName } = ctx;
  const path = `${c}/${t}/grades.json`, repo = area(Store.PRIV), key = `${owner}/${c}/${t}`;
  const base = `/api/students/${encodeURIComponent(owner)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`;
  const st = (ui[key] = ui[key] || { find: "" });
  let book = null, info = null;

  async function load() {
    try {
      const [f, d] = await Promise.all([Store.readFile(repo, path), api(base)]);
      book = f ? JSON.parse(f.text) : null; info = d;
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
    const enrolled = all.filter(s => !s.dropped), canMail = info.email && enrolled.some(s => !emailProblem(emailOf(s), F.emailDomain));
    const custom = F.custom.filter(f => f.id !== "email");
    const fields = lead && !locked ? `<div class="lt-st-fields">
        <p class="lt-st-h">What each student has <span>Set it before adding students: once there are students, it's fixed.</span></p>
        <div class="lt-form lt-st-grid">
          <label>Identifier<input type="text" id="sf-id" value="${esc(F.idLabel)}" placeholder="Student Identifier"${dis}><small>Its name, e.g. Student Number. Unique for each student.</small></label>
          <label>Email domain<input type="text" id="sf-dom" value="${esc(F.emailDomain)}" placeholder="e.g. mail.utoronto.ca" spellcheck="false"${dis}><small>Every student's email must be at it. Blank: any.</small></label>
        </div>
        <div class="lt-st-extra"><span class="lt-st-chip fixed">First Name</span><span class="lt-st-chip fixed">Last Name</span><span class="lt-st-chip fixed">Email</span>
          ${custom.map(f => `<span class="lt-st-chip">${esc(f.label)}<button type="button" data-sf-del="${esc(f.id)}" aria-label="Remove the field ${esc(f.label)}"${dis}>×</button></span>`).join("")}
          <form class="lt-st-newf" id="sf-new"><input type="text" id="sf-label" placeholder="Another field, e.g. UTORid" aria-label="Another field"${dis}><button type="submit" class="lt-btn add"${dis}>${ICON.plus}Add</button></form></div>
      </div>`
      : `<p class="lt-part-text lt-st-fixed"><b>Each student has</b> ${esc(F.idLabel)}, a first and last name, an email${F.emailDomain ? ` at @${esc(F.emailDomain)}` : ""}${custom.length ? `, and ${custom.map(f => esc(f.label)).join(", ")}` : ""}.${lead ? " Fixed, now there are students." : ""}</p>`;
    box.innerHTML = `<p class="lt-part-text">The class list: each student here can sign in to the course page, with their email and a code it emails them, and the gradebook has them for marks. The course page's link: <code>${esc(info.link)}</code> <button type="button" class="lt-link" id="st-copy">Copy</button></p>
      ${held ? `<p class="lt-note lt-st-note">${UNSAVED}</p>` : ""}
      ${lead && !info.email ? `<p class="lt-note lt-st-note">Email isn't set up on this server, so Lectern can't email students their link or a sign-in code.</p>` : ""}
      ${fields}
      ${lead ? `<div class="lt-st-acts"><button type="button" class="lt-btn add" id="st-add"${dis}>${ICON.plus}Add a Student</button><button type="button" class="lt-btn" id="st-import"${dis}>${ICON.upload || ""}Import a Class List</button></div>` : ""}
      <div class="lt-st-bar"><p class="lt-part-text lt-st-count">${all.length ? `${enrolled.length} student${enrolled.length === 1 ? "" : "s"}${all.length > enrolled.length ? ` · ${all.length - enrolled.length} dropped` : ""}` : "No students yet."}${lead && canMail ? ` · <button type="button" class="lt-link" id="st-all"${dis}>Email everyone the link</button>` : ""}</p>
        ${all.length > 8 ? `<input type="search" class="lt-st-find" id="st-find" placeholder="Find a student" value="${esc(st.find)}" aria-label="Find a student">` : ""}</div>
      ${all.length ? `<div class="lt-olist lt-st-list">${all.map(s => {
        const mail = emailOf(s), ok = !s.dropped && !emailProblem(mail, F.emailDomain), q = [s.name, s.first, s.last, s.num, mail, ...custom.map(f => fieldOf(s, f.id))].join(" ").toLowerCase();
        const who = `<b>${esc(s.name || [s.last, s.first].filter(Boolean).join(", ") || s.num)}</b><span>${esc(s.num)}${mail ? ` · ${esc(mail)}` : ""} · <em>${esc(stateOf(s, F))}</em></span>`;
        return `<div class="lt-orow lt-user${s.dropped ? " lt-st-dropped" : ""}" data-q="${esc(q)}">
          ${lead ? `<button type="button" class="lt-user-who lt-user-open" data-st-edit="${esc(s.num)}" title="Their details">${who}</button>` : `<div class="lt-user-who">${who}</div>`}
          ${lead ? `<span class="lt-orow-r">${s.dropped ? `<button type="button" class="lt-link" data-st-back="${esc(s.num)}"${dis}>Re-enrol</button>`
            : `${ok && info.email ? `<button type="button" class="lt-link" data-st-invite="${esc(mail)}">Email the link</button>` : ""}<button type="button" class="lt-link lt-del" data-st-remove="${esc(s.num)}"${dis}>Remove</button>`}</span>` : ""}</div>`;
      }).join("")}</div>` : ""}`;
    wire(F);
    filter();
  }
  function filter() {
    const q = st.find.trim().toLowerCase();
    box.querySelectorAll(".lt-st-list [data-q]").forEach(r => { r.hidden = !!q && !r.dataset.q.includes(q); });
  }

  function wire(F) {
    const $ = s => box.querySelector(s);
    $("#st-copy").onclick = async () => { try { await navigator.clipboard.writeText(info.link); toast("Copied the course page's link."); } catch (_) { toast(info.link); } };
    const find = $("#st-find"); if (find) find.oninput = () => { st.find = find.value; filter(); };
    if (!lead) return;
    const idIn = $("#sf-id"), domIn = $("#sf-dom");
    if (idIn) idIn.onchange = () => run(b => { b.fields = fieldsOf(b); b.fields.idLabel = idIn.value.trim() || "Student Identifier"; }, "Student fields");
    if (domIn) domIn.onchange = () => run(b => { b.fields = fieldsOf(b); b.fields.emailDomain = cleanDomain(domIn.value); }, "Student fields");
    const nf = $("#sf-new");
    if (nf) nf.onsubmit = e => {
      e.preventDefault();
      const label = $("#sf-label").value.trim(); if (!label) return $("#sf-label").focus();
      if (/^\s*e-?mail( address)?\s*$/i.test(label) || /^(first|last) ?name$/i.test(label)) { toast(`Every student has that already.`); return; }
      run(b => { b.fields = fieldsOf(b); if (b.fields.custom.some(f => f.label.toLowerCase() === label.toLowerCase())) return false; b.fields.custom.push({ id: uid(), label }); }, "Student fields")
        .then(() => { const i = box.querySelector("#sf-label"); if (i) i.focus(); });
    };
    box.querySelectorAll("[data-sf-del]").forEach(x => { x.onclick = () => run(b => { b.fields = fieldsOf(b); b.fields.custom = b.fields.custom.filter(f => f.id !== x.dataset.sfDel); }, "Student fields"); });
    $("#st-add").onclick = () => studentDialog(null);
    $("#st-import").onclick = importDialog;
    box.querySelectorAll("[data-st-edit]").forEach(x => { x.onclick = () => studentDialog(list().find(s => s.num === x.dataset.stEdit)); });
    box.querySelectorAll("[data-st-remove]").forEach(x => { x.onclick = () => remove(x.dataset.stRemove); });
    box.querySelectorAll("[data-st-back]").forEach(x => { x.onclick = () => run(b => { const s = b.students.find(y => y.num === x.dataset.stBack); if (!s) return false; delete s.dropped; }, "Re-enrol a student"); });
    box.querySelectorAll("[data-st-invite]").forEach(x => { x.onclick = async () => { try { await api(`${base}/invite`, { email: x.dataset.stInvite }); toast(`Emailed ${x.dataset.stInvite} the link.`); refreshInfo(); } catch (e) { toast(e.message); } }; });
    const all = $("#st-all");
    if (all) all.onclick = async () => {
      const n = list().filter(s => !s.dropped && !emailProblem(emailOf(s), F.emailDomain)).length;
      if (!await confirmBox("Email everyone the link?", `Each of the ${n} student${n === 1 ? "" : "s"} who can sign in gets an email with the course page's link.`, "Email Them")) return;
      try { const r = await api(`${base}/invite`, {}); toast(`Emailed ${r.invited} student${r.invited === 1 ? "" : "s"} the link.`); refreshInfo(); } catch (e) { toast(e.message); }
    };
  }

  async function remove(num) {
    const s = list().find(x => x.num === num); if (!s) return;
    const keep = keptFor(book, num), who = esc(s.name || s.num);
    if (!await confirmBox(keep ? "Drop them?" : "Take them off the class list?", keep
      ? `${who} has marks or notes in the gradebook, so they stay there as dropped: left out of the class's figures, and they can't sign in to the course page. You can re-enrol them.`
      : `${who} comes off the class list, and can't sign in to the course page any more.`, keep ? "Drop" : "Remove")) return;
    run(b => {
      const i = b.students.findIndex(x => x.num === num); if (i < 0) return false;
      if (keptFor(b, num)) b.students[i].dropped = true; else b.students.splice(i, 1);
    }, keep ? "Drop a student" : "Remove a student");
  }

  // One student: adding them, or their details (everything but the identifier, which their marks are kept by).
  function studentDialog(s) {
    const F = fieldsOf(book), custom = F.custom.filter(f => f.id !== "email");
    const v = (id, k) => esc(s ? (k ? fieldOf(s, k) : s[id] || "") : "");
    modal(`<h2>${s ? esc(s.name || s.num) : "Add a Student"}</h2>
      <div class="lt-form">
        <label>${esc(F.idLabel)}<input type="text" id="sd-num" value="${v("num")}" spellcheck="false" autocomplete="off"${s ? " readonly" : ""}>${s ? `<small>Their marks are kept by it, so it doesn't change.</small>` : ""}</label>
        <div class="two"><label>First Name<input type="text" id="sd-first" value="${v("first")}" autocomplete="off"></label><label>Last Name<input type="text" id="sd-last" value="${v("last")}" autocomplete="off"></label></div>
        <label>Email<input type="email" id="sd-email" value="${s ? esc(emailOf(s)) : ""}" placeholder="name@${esc(F.emailDomain || "example.com")}" spellcheck="false" autocomplete="off"><small>They sign in to the course page with it.</small></label>
        ${custom.map(f => `<label>${esc(f.label)}<input type="text" data-sd="${esc(f.id)}" value="${v("", f.id)}" spellcheck="false" autocomplete="off"></label>`).join("")}
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
        const f = { email };
        m.querySelectorAll("[data-sd]").forEach(i => { if (i.value.trim()) f[i.dataset.sd] = i.value.trim(); });
        const invite = !s && m.querySelector("#sd-invite") && m.querySelector("#sd-invite").checked;
        m.querySelector("[data-ok]").disabled = true;
        const done = await run(b => {
          const was = b.students.find(x => x.num === num);
          if (s && was) { was.first = val("#sd-first"); was.last = val("#sd-last"); was.f = Object.assign({}, was.f || {}, f); custom.forEach(x => { if (!f[x.id] && was.f) delete was.f[x.id]; }); withName(was); delete was.email; return; }
          if (was) return false;
          b.students.push(withName({ num, first: val("#sd-first"), last: val("#sd-last"), f }));
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
            seen.set(num, { num, first, last, f });
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
          const r = await run(b => {
            const fresh = [], dropped = [];
            P.forEach(p => {
              const s = b.students.find(x => x.num === p.num);
              if (s) { if (p.first) s.first = p.first; if (p.last) s.last = p.last; s.f = Object.assign({}, s.f || {}, p.f); withName(s); delete s.dropped; }
              else { b.students.push(withName({ num: p.num, first: p.first, last: p.last, f: p.f })); fresh.push(p); }
            });
            if (drop) b.students.forEach(s => { if (!s.dropped && !P.some(p => p.num === s.num)) { s.dropped = true; dropped.push(s); } });
            return { fresh, dropped };
          }, "Import a class list");
          if (!r) { m.querySelector("[data-ok]").disabled = false; return; }
          close();
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
