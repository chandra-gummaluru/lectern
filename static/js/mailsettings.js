/* Email: the last card on the offering's page (Lectern → the offering), for its coordinators.

   How the offering's email to students goes out (server/classmail.py):
     Sender               its own SMTP settings (From, server, login), tested with an email to you before
                          they're kept; without them, the server's (Lectern's admin's) are used.
     Signature            a sign-off added to each.
     Emails to Students   which of the automatic ones go out: marks out or changed, accommodation and remark
                          receipts and decisions, and whether a new announcement is emailed by default.
   Sign-in and confirmation codes always go: they're how students get in. */


export function emailCard({ box, esc, toast, api, owner, c, t }) {
  const U = `/api/mail/${encodeURIComponent(owner)}/${encodeURIComponent(c)}/${encodeURIComponent(t)}`;
  let D = null, editing = false;
  const load = () => api(U).then(d => { D = d; draw(); }, e => { box.innerHTML = `<p class="lt-part-text">${esc(e.message)}</p>`; });

  let sigEditing = false;
  function senderForm() {
    const s = D.settings, own = s.source === "offering";
    return `<div class="em-form"><div class="lx-grid two">
        <label class="lx-f lx-span2">From<input type="text" id="em-from" value="${esc(own ? s.from : "")}" placeholder="CSC258 &lt;csc258@utoronto.ca&gt;" autocomplete="off"></label>
        <label class="lx-f">SMTP Server<input type="text" id="em-host" value="${esc(own ? s.host : "")}" placeholder="smtp.gmail.com" autocomplete="off" spellcheck="false"></label>
        <label class="lx-f">Security<select id="em-sec">${[["starttls", "STARTTLS"], ["ssl", "SSL"], ["none", "None"]].map(([v, l]) => `<option value="${v}"${(own ? s.security : "starttls") === v ? " selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="lx-f">Port<input type="text" id="em-port" value="${esc(own ? s.port : "")}" placeholder="587" inputmode="numeric"></label>
        <label class="lx-f">Username<input type="text" id="em-user" value="${esc(own ? s.user : "")}" autocomplete="off" spellcheck="false"></label>
        <label class="lx-f">Password<input type="password" id="em-pw" placeholder="${own && s.hasPassword ? "Unchanged" : ""}" autocomplete="new-password"></label>
      </div>
      <p class="lx-help">Lectern sends a test email to <b>${esc(D.you)}</b> first; the settings are kept only if it goes through. The password is kept encrypted and never shown again.</p>
      <p class="em-err" id="em-err" role="alert"></p>
      <div class="lt-part-acts em-acts"><button type="button" class="lt-btn" id="em-cancel">Cancel</button><button type="button" class="lt-btn primary" id="em-save">Send Test and Save</button></div></div>`;
  }
  function draw() {
    const s = D.settings, own = s.source === "offering", sig = (D.prefs.signature || "").trim();
    const who = s.host ? `${s.from ? esc(s.from) : "No From address"}` : "Not set up: nothing goes to students until it is.";
    const via = s.host ? `<span class="em-via">Through ${esc(s.host)} · ${own ? "this offering's own settings" : "Lectern's settings"}</span>` : "";
    box.innerHTML = `<div class="pp-rows em-rows">
      <div class="em-row${editing ? " open" : ""}"><div class="em-line">
          <div class="em-txt"><b>Sender</b><span class="em-val">${who}</span>${via}</div>
          ${editing ? "" : `<div class="em-btns">${own ? `<button type="button" class="lt-btn" id="em-rm">Use Lectern's</button>` : ""}<button type="button" class="lt-btn" id="em-edit">${own ? "Change" : "Use Our Own"}</button></div>`}
        </div>${editing ? senderForm() : ""}</div>
      <div class="em-row${sigEditing ? " open" : ""}"><div class="em-line">
          <div class="em-txt"><b>Signature</b>${sigEditing ? `<span class="em-via">Added to the end of every email to students.</span>` : sig ? `<span class="em-val em-sig">${esc(sig)}</span>` : `<span class="em-val em-none">None</span>`}</div>
          ${sigEditing ? "" : `<div class="em-btns"><button type="button" class="lt-btn" id="em-sedit">${sig ? "Edit" : "Add"}</button></div>`}
        </div>${sigEditing ? `<div class="em-form"><textarea id="em-sig" rows="3" placeholder="e.g. — The CSC258 teaching team">${esc(D.prefs.signature || "")}</textarea>
          <div class="lt-part-acts em-acts"><button type="button" class="lt-btn" id="em-scancel">Cancel</button><button type="button" class="lt-btn primary" id="em-psave">Save</button></div></div>` : ""}</div>
    </div>
    <p class="lx-help em-foot">Students are emailed only about a new announcement, a decision on their accommodation or remark request, and their marks being out or changed.</p>`;
    const q = x => box.querySelector(x);
    if (sigEditing) {
      q("#em-scancel").onclick = () => { sigEditing = false; draw(); };
      q("#em-psave").onclick = () => api(`${U}/prefs`, { replyTo: "", signature: q("#em-sig").value, send: {} }).then(r => { D.prefs = r.prefs; sigEditing = false; draw(); toast("Signature saved."); }, e => toast(e.message));
    } else q("#em-sedit").onclick = () => { sigEditing = true; draw(); q("#em-sig").focus(); };
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
