/* Email: the last card on the offering's page (Lectern → the offering), for its coordinators.

   How the offering's email to students goes out (server/classmail.py):
     Sender               its own SMTP settings (From, server, login), tested with an email to you before
                          they're kept; without them, the server's (Lectern's admin's) are used.
     Signature            a sign-off added to each.
     Emails to Students   which of the automatic ones go out: marks out or changed, accommodation and remark
                          receipts and decisions, and whether a new announcement is emailed by default.
   Sign-in and confirmation codes always go: they're how students get in. */

const KINDS = [
  ["grades", "Marks", "When an evaluation's marks are out (on saving the gradebook), and Email Them for marks changed later."],
  ["accomReceipts", "Accommodation receipts", "A copy of each accommodation request, to the student who made it."],
  ["accomDecisions", "Accommodation decisions", "When a request is approved or rejected, with your note."],
  ["remarkReceipts", "Remark receipts", "A copy of each remark request, to the student who made it."],
  ["remarkDecisions", "Remark decisions", "When a remark request is decided, with your note."],
  ["announcements", "Announcements", "A new announcement is emailed when it's saved (each one can still be changed)."],
];

export function emailCard({ box, esc, toast, api, owner, c, t }) {
  const U = `/api/mail/${encodeURIComponent(owner)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`;
  let D = null, editing = false;
  const load = () => api(U).then(d => { D = d; draw(); }, e => { box.innerHTML = `<p class="lt-part-text">${esc(e.message)}</p>`; });

  function senderHTML() {
    const s = D.settings, own = s.source === "offering";
    if (!editing) return `<p class="lt-part-text">${s.host ? `Emails go out ${s.from ? `from <b>${esc(s.from)}</b> ` : ""}through <b>${esc(s.host)}</b>${own ? ", this offering's own settings." : ", Lectern's server settings."}` : "Email isn't set up: nothing goes to students until it is."}</p>
      <div class="lt-part-acts"><button type="button" class="lt-btn" id="em-edit">${own ? "Change the Sender" : "Use This Offering's Own Sender"}</button>${own ? `<button type="button" class="lt-btn" id="em-rm">Use Lectern's Instead</button>` : ""}</div>`;
    return `<div class="lx-grid two">
        <label class="lx-f lx-span2">From<input type="text" id="em-from" value="${esc(own ? s.from : "")}" placeholder="CSC258 &lt;csc258@utoronto.ca&gt;" autocomplete="off"></label>
        <label class="lx-f">SMTP Server<input type="text" id="em-host" value="${esc(own ? s.host : "")}" placeholder="smtp.gmail.com" autocomplete="off" spellcheck="false"></label>
        <label class="lx-f">Security<select id="em-sec">${[["starttls", "STARTTLS"], ["ssl", "SSL"], ["none", "None"]].map(([v, l]) => `<option value="${v}"${(own ? s.security : "starttls") === v ? " selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="lx-f">Port<input type="text" id="em-port" value="${esc(own ? s.port : "")}" placeholder="587" inputmode="numeric"></label>
        <label class="lx-f">Username<input type="text" id="em-user" value="${esc(own ? s.user : "")}" autocomplete="off" spellcheck="false"></label>
        <label class="lx-f">Password<input type="password" id="em-pw" placeholder="${own && s.hasPassword ? "Unchanged" : ""}" autocomplete="new-password"></label>
      </div>
      <p class="lx-help">Lectern sends a test email to <b>${esc(D.you)}</b> first; the settings are kept only if it goes through. The password is kept encrypted and never shown again.</p>
      <p class="em-err" id="em-err" role="alert"></p>
      <div class="lt-part-acts em-acts"><button type="button" class="lt-btn" id="em-cancel">Cancel</button><button type="button" class="lt-btn primary" id="em-save">Send Test and Save</button></div>`;
  }
  function draw() {
    const p = D.prefs;
    box.innerHTML = `
      <h3 class="lx-sec lx-first">Sender</h3>${senderHTML()}
      <h3 class="lx-sec">Signature</h3>
      <div class="lx-grid one"><label class="lx-f">Signature<textarea id="em-sig" rows="3" placeholder="e.g. — The CSC258 teaching team">${esc(p.signature)}</textarea></label></div>
      <p class="lx-help">Added to the end of every email to students.</p>
      <div class="lt-part-acts em-acts"><button type="button" class="lt-btn" id="em-psave" disabled>Save</button></div>
      <h3 class="lx-sec">Emails to Students</h3>
      <div class="em-kinds">${KINDS.map(([k, n, sub]) => `<label class="lx-tick"><input type="checkbox" data-kind="${k}"${p.send[k] !== false ? " checked" : ""}><b>${esc(n)}</b><span>${esc(sub)}</span></label>`).join("")}</div>
      <p class="lx-help">Sign-in and confirmation codes always go: they're how students get in.</p>`;
    const q = s => box.querySelector(s);
    const prefs = () => ({ replyTo: "", signature: q("#em-sig").value, send: Object.fromEntries([...box.querySelectorAll("[data-kind]")].map(x => [x.dataset.kind, x.checked])) });
    const savePrefs = (btn) => api(`${U}/prefs`, prefs()).then(r => { D.prefs = r.prefs; if (btn) btn.disabled = true; toast("Email settings saved."); }, e => toast(e.message));
    q("#em-sig").oninput = () => { q("#em-psave").disabled = false; };
    q("#em-psave").onclick = () => savePrefs(q("#em-psave"));
    box.querySelectorAll("[data-kind]").forEach(x => { x.onchange = () => savePrefs(); });
    if (!editing) {
      q("#em-edit").onclick = () => { editing = true; draw(); q("#em-from").focus(); };
      const rm = q("#em-rm"); if (rm) rm.onclick = () => api(`${U}/settings`, { action: "remove" }).then(r => { D.settings = r.settings; draw(); toast("Back to Lectern's sender."); }, e => toast(e.message));
      return;
    }
    q("#em-cancel").onclick = () => { editing = false; draw(); };
    q("#em-save").onclick = () => {
      const b = q("#em-save"), err = q("#em-err"); b.disabled = true; b.textContent = "Sending a test…"; err.textContent = "";
      api(`${U}/settings`, { from: q("#em-from").value.trim(), host: q("#em-host").value.trim(), security: q("#em-sec").value, port: q("#em-port").value.trim(), user: q("#em-user").value.trim(), smtpPassword: q("#em-pw").value })
        .then(r => { D.settings = r.settings; editing = false; draw(); toast(`It works: the test went to ${D.you}. Saved.`); },
          e => { b.disabled = false; b.textContent = "Send Test and Save"; err.textContent = e.message; });
    };
  }
  box.innerHTML = `<p class="lt-part-text">Loading…</p>`;
  load();
}
