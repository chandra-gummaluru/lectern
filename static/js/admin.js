/* The admin panel (/admin): signing in (email, password and a two-factor code), then invitations,
   accounts (and deleting them), email settings, and the other admins. Its own session, separate from Lectern's.
   Admins are added only on the server: python app.py admin you@example.com */
import { wireShow, secureHere } from "./auth.js";
import { enhanceSelects } from "./select.js";
enhanceSelects();   // every dropdown drawn as the About picker

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const when = t => t ? new Date(t * 1000).toLocaleString("en-CA", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "never";
const day = t => t ? new Date(t * 1000).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" }) : "";

class ApiError extends Error { constructor(status, msg, code) { super(msg); this.status = status; this.code = code; } }
async function api(path, body, { form } = {}) {
  let res, data = {};
  try {
    res = await fetch(path, {
      method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
      headers: { "X-Lectern": "1", ...(body !== undefined && !form ? { "Content-Type": "application/json" } : {}) },
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    });
  } catch (_) { throw new ApiError(0, "Couldn't reach Lectern's server."); }
  try { data = await res.json(); } catch (_) {}
  if (res.status === 401 && data.code === "signed-out") { showSignIn(data.error); throw new ApiError(401, data.error, "signed-out"); }
  if (!res.ok) throw new ApiError(res.status, data.error || `Something went wrong (${res.status}).`, data.code);
  return data;
}

function toast(msg) {
  const root = $("#lt-toast-root"); root.className = "lt-toasts";
  const el = document.createElement("div"); el.className = "lt-toast"; el.textContent = msg; root.append(el);
  setTimeout(() => el.remove(), 4200);
}
function modal(html, onReady) {
  const bg = document.createElement("div");
  bg.className = "lt-modal-bg";
  bg.innerHTML = `<div class="lt-modal" role="dialog" aria-modal="true">${html}</div>`;
  $("#lt-modal-root").append(bg);
  const m = bg.firstElementChild, close = () => { bg.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = e => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey, true);
  bg.addEventListener("mousedown", e => { if (e.target === bg) close(); });
  onReady(m, close);
  const first = m.querySelector("input, .primary"); if (first) first.focus();
}
// Turning something off: the admin's password again.
function withPassword(title, text, label, run, kind = "lt-btn-danger") {
  modal(`<h2>${esc(title)}</h2><form novalidate><p>${text}</p><div class="lt-form">
      <label>Your password<input type="password" id="ap-pw" autocomplete="current-password"></label></div>
      <p class="lt-err"></p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn ${kind}">${esc(label)}</button></div></form>`, (m, close) => {
    m.querySelector("[data-no]").onclick = close;
    m.querySelector("form").onsubmit = async e => {
      e.preventDefault();
      const go = m.querySelector("[type=submit]"); go.disabled = true;
      try { await run(m.querySelector("#ap-pw").value); close(); draw(); } catch (x) { m.querySelector(".lt-err").textContent = x.message; go.disabled = false; }
    };
  });
}

// ── Signing in ───────────────────────────────────────────────────────
function step(n) {
  $("#lxa-step1").hidden = n !== 1; $("#lxa-step2").hidden = n !== 2;
  setTimeout(() => (n === 1 ? ($("#lxa-email").value ? $("#lxa-pw") : $("#lxa-email")) : $("#lxa-code")).focus(), 0);
}
function say(msg) { const st = $("#lxa-status"); st.className = `sp-hint${msg ? " is-error" : ""}`; st.textContent = msg; }
function showSignIn(msg = "") {
  $("#lxa-app").hidden = true; $("#lxa-signin").hidden = false;
  document.body.className = "lt-on-splash";
  say(msg); step(1);
}
wireShow($("#lxa-form"));
$("#lxa-back").onclick = () => { $("#lxa-code").value = ""; say(""); step(1); };
// Step 1 only asks; nothing is sent until there's a code too, so the server checks all three together
// (and a password on its own never gets a yes or no).
$("#lxa-form").onsubmit = async e => {
  e.preventDefault();
  if (!secureHere()) return say("This page isn't secure (no HTTPS), so it won't send your password.");
  const email = $("#lxa-email").value.trim(), password = $("#lxa-pw").value;
  if (!$("#lxa-step1").hidden) {
    if (!email || !password) return say("Enter your email and password.");
    say(""); return step(2);
  }
  const code = $("#lxa-code").value.replace(/\s+/g, "");
  if (!/^\d{6}$/.test(code)) return say("Enter the 6-digit code from your authenticator app.");
  const go = $("#lxa-go2"); go.disabled = true; go.textContent = "Signing in…"; say("");
  try {
    const d = await api("/api/admin/login", { email, password, code });
    $("#lxa-pw").value = ""; $("#lxa-code").value = "";
    start(d.admin);
  } catch (x) {
    say(x.message); $("#lxa-code").value = "";
    if (x.code === "bad-login" || x.code === "disabled") { $("#lxa-pw").value = ""; step(1); } else step(2);
  }
  finally { go.disabled = false; go.textContent = "Continue"; }
};
// The account menu, as in Lectern: who's signed in, and Sign out.
const USER_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/></svg>';
const CHEV = '<svg class="lt-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
let acctMenu = null;
function closeAcct() { if (acctMenu) { acctMenu.remove(); acctMenu = null; $("#lxa-acct").setAttribute("aria-expanded", "false"); } }
$("#lxa-acct").onclick = e => {
  e.stopPropagation();
  if (acctMenu) return closeAcct();
  acctMenu = document.createElement("div");
  acctMenu.className = "lt-menu"; acctMenu.setAttribute("role", "menu");
  acctMenu.innerHTML = `<p>Signed in as <b>${esc(me && (me.name || me.email))}</b><br><span class="lt-menu-sub">${esc(me && me.email)}</span></p><hr>
       <button type="button" role="menuitem" data-m="out">Sign out</button>`;
  $("#lxa-acct").after(acctMenu);
  $("#lxa-acct").setAttribute("aria-expanded", "true");
  acctMenu.onclick = async ev => {
    if (!ev.target.closest("[data-m=out]")) return;
    closeAcct();
    try { await api("/api/admin/logout", {}); } catch (_) {}
    location.replace("/admin");
  };
};
document.addEventListener("click", e => { if (acctMenu && !acctMenu.contains(e.target)) closeAcct(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeAcct(); });

let me = null;
function start(admin) {
  me = admin;
  $("#lxa-signin").hidden = true; $("#lxa-app").hidden = false;
  document.body.className = "lt-on-app lt-on-page";
  $("#lxa-acct").innerHTML = `${USER_SVG}<span>${esc(admin.name || admin.email)}</span>${CHEV}`;
  draw();
}

// ── The panel ────────────────────────────────────────────────────────
async function draw() {
  const page = $("#lxa-page");
  let d;
  try { d = await api("/api/admin/overview"); } catch (x) { if (x.code !== "signed-out") page.innerHTML = `<div class="lt-in"><p class="lt-note err">${esc(x.message)}</p></div>`; return; }
  page.innerHTML = `<div class="lt-in lt-account">
    <h1>Admin</h1>
    ${d.email ? "" : `<p class="lt-lede"><b>Email isn't set up</b>, so you'll get invitation links to send yourself: set it up under <a href="#lxa-mail">Email</a>.</p>`}

    <div class="lt-sec"><h2>Accounts</h2></div>
    <div class="lt-st-head"><p class="lt-part-text">Each person with an account can make course offerings and invite their teaching team. Invite them by email: the link works once, for 7 days.</p>
      <div class="lt-st-acts"><button type="button" class="lt-btn add" id="lxa-invite">${PLUS}Invite Someone</button></div></div>
    <div class="lt-st-bar"><p class="lt-part-text lt-st-count">${d.users.length ? `${d.users.length} account${d.users.length === 1 ? "" : "s"}` : "No accounts yet."}${d.invites.length ? ` · ${d.invites.length} invited` : ""}</p></div>
    ${d.users.length || d.invites.length ? `<div class="lt-olist lxa-users">${d.invites.map(i => `<div class="lt-orow lt-user">
      <div class="lt-user-who"><b>${esc(i.email)}</b><span>Invited ${esc(day(i.created))} · <em>the link works until ${esc(day(i.expires))}</em></span></div>
      <span class="lt-tags"><span class="lt-tag dim">Invited</span></span>
      <span class="lt-orow-r"><button type="button" class="lt-link" data-revoke="${esc(i.id)}">Cancel</button></span></div>`).join("")}${d.users.map(u => `<div class="lt-orow lt-user">
      <div class="lt-user-who"><b>${esc(u.name || u.email)}</b><span>${esc(u.email)} · <a href="${esc(u.site)}" target="_blank" rel="noopener">${esc(u.handle)}</a> · last sign-in ${esc(when(u.lastLogin))}</span></div>
      <span class="lt-tags">${u.twoFactor ? `<span class="lt-tag ok">2FA</span>` : `<span class="lt-tag dim">No 2FA</span>`}${u.teams ? `<span class="lt-tag dim">On ${u.teams} team${u.teams === 1 ? "" : "s"}</span>` : ""}${u.disabled ? `<span class="lt-tag bad">Off</span>` : ""}${u.locked ? `<span class="lt-tag bad">Waiting (wrong passwords)</span>` : ""}</span>
      <span class="lt-orow-r lxa-more-wrap"><button type="button" class="lxa-more" data-more="${u.id}" aria-haspopup="menu" aria-expanded="false" aria-label="Manage ${esc(u.email)}" title="Manage">${DOTS}</button></span></div>`).join("")}</div>` : ""}

    <div class="lt-sec"><h2>Email</h2></div>
    <section class="em-body" id="lxa-mail"><p class="lt-part-text">Loading…</p></section>

    <div class="lt-sec"><h2>Admins</h2><span>Added on the server: <code>python app.py admin them@example.com</code></span></div>
    <div class="lt-olist">${d.admins.map(a => `<div class="lt-orow lt-user">
      <div class="lt-user-who"><b>${esc(a.name || a.email)}${a.id === d.me ? " (you)" : ""}</b><span>${esc(a.email)} · last sign-in ${esc(when(a.lastLogin))}</span></div>
      <span class="lt-tags">${a.disabled ? `<span class="lt-tag bad">Off</span>` : ""}</span>
      <span class="lt-orow-r lxa-acts">${a.id === d.me ? "" : a.disabled ? `<button type="button" class="lt-link" data-a="${a.id}" data-act="enable">Turn on</button>` : `<button type="button" class="lt-link lt-del" data-a="${a.id}" data-act="disable">Turn off</button>`}</span>
    </div>`).join("")}</div>
  </div>`;

  $("#lxa-invite").onclick = () => inviteDialog(d.email);
  page.querySelectorAll("[data-revoke]").forEach(b => { b.onclick = async () => { await api("/api/admin/invites/revoke", { id: b.dataset.revoke }); draw(); }; });
  page.querySelectorAll("[data-more]").forEach(b => { b.onclick = e => { e.stopPropagation(); userMenu(b, d.users.find(x => x.id === Number(b.dataset.more))); }; });
  page.querySelectorAll("[data-a]").forEach(b => {
    b.onclick = async () => {
      const a = d.admins.find(x => x.id === Number(b.dataset.a)), act = b.dataset.act, go = password => api(`/api/admin/admins/${a.id}`, { action: act, password });
      withPassword(act === "disable" ? "Turn this admin off?" : "Turn this admin back on?", `${esc(a.email)}${act === "disable" ? " is signed out and can't sign in to the admin panel." : " can sign in to the admin panel again."}`, act === "disable" ? "Turn off" : "Turn on", go);
    };
  });
  drawEmail();
}

// Inviting someone: a dialog, as Add a Student is in Lectern. Without email, it shows the link to send them.
const PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';
function inviteDialog(emailOn) {
  modal(`<h2>Invite Someone</h2><form novalidate>
      <div class="lt-form"><label>Email<input type="email" id="iv-email" placeholder="name@utoronto.ca" autocomplete="off" autocapitalize="off" spellcheck="false">
        <small>${emailOn ? "They're emailed a link to make their account. It works once, for 7 days." : "Email isn't set up, so you'll get the link to send them yourself. It works once, for 7 days."}</small></label></div>
      <div id="iv-link"></div>
      <p class="lt-err"></p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn primary">Invite</button></div></form>`, (m, close) => {
    const go = m.querySelector("[type=submit]"), err = m.querySelector(".lt-err"), inp = m.querySelector("#iv-email");
    m.querySelector("[data-no]").onclick = close;
    setTimeout(() => inp.focus(), 0);
    m.querySelector("form").onsubmit = async e => {
      e.preventDefault();
      if (go.dataset.done) return close();
      go.disabled = true; err.textContent = "";
      try {
        const r = await api("/api/admin/invites", { email: inp.value.trim() });
        draw();
        if (r.emailed) { close(); toast(`Invitation emailed to ${r.email}.`); return; }
        inp.readOnly = true;
        m.querySelector("#iv-link").innerHTML = `<p class="lt-note">Send <b>${esc(r.email)}</b> this link (only to them: it works for whoever has it):
          <span class="lt-linkbox"><input type="text" readonly value="${esc(r.link)}"><button type="button" class="lt-btn" data-copy>Copy</button></span></p>`;
        m.querySelector("[data-copy]").onclick = async () => { try { await navigator.clipboard.writeText(r.link); toast("Copied."); } catch (_) { m.querySelector("#iv-link input").select(); } };
        m.querySelector("[data-no]").hidden = true; go.textContent = "Done"; go.dataset.done = "1";
      } catch (x) { err.textContent = x.message; }
      finally { go.disabled = false; }
    };
  });
}

// Each account's actions, in a menu (⋯).
const DOTS = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>`;
let openMenu = null;
function closeUserMenu() { if (openMenu) { openMenu.btn.setAttribute("aria-expanded", "false"); openMenu.el.remove(); openMenu = null; } }
document.addEventListener("click", closeUserMenu);
document.addEventListener("keydown", e => { if (e.key === "Escape" && openMenu) { const b = openMenu.btn; closeUserMenu(); b.focus(); } });
function userMenu(btn, u) {
  const again = openMenu && openMenu.btn === btn;
  closeUserMenu();
  if (again) return;
  const el = document.createElement("div");
  el.className = "lt-menu lxa-menu"; el.setAttribute("role", "menu");
  const item = (act, label, cls = "") => `<button type="button" role="menuitem" data-act="${act}"${cls ? ` class="${cls}"` : ""}>${label}</button>`;
  el.innerHTML = `<p><b>${esc(u.name || u.email)}</b><br><span class="lt-menu-sub">${esc(u.email)}</span></p><hr>
    ${item("sign-out", "Sign out everywhere")}
    ${u.locked ? item("unlock", "Let them try again") : ""}
    ${u.twoFactor ? item("reset-2fa", "Turn off two-factor sign-in") : ""}
    ${u.disabled ? item("enable", "Turn account on") : item("disable", "Turn account off")}<hr>
    ${item("delete", "Delete account…", "lxa-danger")}`;
  btn.after(el); btn.setAttribute("aria-expanded", "true");
  openMenu = { el, btn };
  el.querySelector("[role=menuitem]").focus();
  el.onclick = e => { e.stopPropagation(); const m = e.target.closest("[data-act]"); if (!m) return; closeUserMenu(); userAct(u, m.dataset.act); };
}
async function userAct(u, act) {
  const go = password => api(`/api/admin/users/${u.id}`, { action: act, password });
  if (act === "delete") return deleteUser(u);
  if (act === "reset-2fa") return withPassword("Turn off their two-factor sign-in?", `For ${esc(u.email)}, e.g. after a lost phone. They're signed out and emailed, and can turn it on again.`, "Turn it off", go);
  if (act === "disable") return withPassword("Turn this account off?", `${esc(u.email)} is signed out and can't sign in, and their published course pages stop showing. Nothing is deleted: you can turn it back on.`, "Turn it off", go);
  try { await go(""); toast({ "sign-out": `Signed ${u.email} out everywhere.`, unlock: "They can try again now.", enable: "Turned on." }[act] || "Done."); draw(); } catch (x) { toast(x.message); }
}

// Deleting an account: the admin's password, and their email typed out.
function deleteUser(u) {
  modal(`<h2>Delete this account?</h2><form novalidate>
      <p><b>${esc(u.name || u.email)}</b> (${esc(u.email)}) can't sign in any more, their course pages go offline, they leave every teaching team${u.teams ? ` (${u.teams})` : ""}, and the teams on their own offerings end. They're emailed.</p>
      <p>Their files aren't erased: they're moved to <code>data/deleted/</code> on the server, for whoever runs it to remove when sure. Their page address (<code>${esc(u.handle)}</code>) isn't given to anyone else. To just stop them signing in, turn the account off instead.</p>
      <div class="lt-form">
        <label>Type their email to confirm<input type="text" id="dl-email" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="${esc(u.email)}"></label>
        <label>Your password<input type="password" id="dl-pw" autocomplete="current-password"></label></div>
      <p class="lt-err"></p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn lt-btn-danger" disabled>Delete account</button></div></form>`, (m, close) => {
    const go = m.querySelector("[type=submit]"), typed = m.querySelector("#dl-email");
    typed.oninput = () => { go.disabled = typed.value.trim().toLowerCase() !== u.email.toLowerCase(); };
    m.querySelector("[data-no]").onclick = close;
    m.querySelector("form").onsubmit = async e => {
      e.preventDefault();
      if (go.disabled) return;
      go.disabled = true;
      try {
        await api(`/api/admin/users/${u.id}`, { action: "delete", confirm: typed.value.trim(), password: m.querySelector("#dl-pw").value });
        close(); toast(`Deleted ${u.email}.`); draw();
      } catch (x) { m.querySelector(".lt-err").textContent = x.message; go.disabled = false; }
    };
  });
}

// Email: the SMTP settings. Saving sends a test email to you first; nothing is saved unless it goes through.
// Email: the server's own sender, as a row like the Sender row on an offering's Email card. It opens in place.
let mailEditing = false;
async function drawEmail() {
  const box = $("#lxa-mail");
  if (!box) return;
  let e;
  try { e = await api("/api/admin/email"); } catch (x) { box.innerHTML = `<p class="lt-note err">${esc(x.message)}</p>`; return; }
  const set = !!e.host, sec = e.security || "starttls";
  const who = set ? esc(e.from || e.user || "No From address") : "Not set up: invitations, password resets and students' sign-in codes can't be emailed.";
  const via = set ? `Through ${esc(e.host)} · ${{ starttls: "STARTTLS", ssl: "SSL", none: "no encryption" }[sec] || esc(sec)}${e.port ? ` · port ${esc(e.port)}` : ""}${e.source === "env" ? " · from the server's <code>.env</code>" : ""}` : "";
  const form = `<form id="lxa-mail-f" class="em-form" novalidate><div class="lx-grid two">
      <label class="lx-f lx-span2">From<input type="text" id="ml-from" value="${esc(e.from)}" placeholder="Lectern &lt;lectern@example.com&gt;" autocomplete="off" spellcheck="false"></label>
      <label class="lx-f">SMTP Server<input type="text" id="ml-host" value="${esc(e.host)}" placeholder="smtp.gmail.com" autocomplete="off" spellcheck="false"></label>
      <label class="lx-f">Security<select id="ml-sec">${[["starttls", "STARTTLS"], ["ssl", "SSL"], ["none", "None"]].map(([v, t]) => `<option value="${v}"${v === sec ? " selected" : ""}>${t}</option>`).join("")}</select></label>
      <label class="lx-f">Port<input type="text" id="ml-port" inputmode="numeric" value="${esc(e.port)}" placeholder="${sec === "ssl" ? "465" : "587"}"></label>
      <label class="lx-f">Username<input type="text" id="ml-user" value="${esc(e.user)}" autocomplete="off" spellcheck="false"></label>
      <label class="lx-f lx-span2">Password<input type="password" id="ml-pw" autocomplete="new-password" placeholder="${e.hasPassword ? "Unchanged" : "For Gmail, an app password"}"></label>
    </div>
    <p class="lx-help">Lectern sends a test email to <b>${esc(me.email)}</b> first; the settings are kept only if it goes through. The password is kept encrypted and never shown again.${e.source === "env" ? " Saving here takes over from the server's <code>.env</code>." : ""} Leave From blank to send from the username.</p>
    <div class="lt-part-acts em-acts"><button type="button" class="lt-btn" id="ml-cancel">Cancel</button><button type="submit" class="lt-btn primary">Send Test and Save</button></div></form>`;
  box.innerHTML = `<div class="pp-rows em-rows lxa-mail-rows"><div class="em-row${mailEditing ? " open" : ""}"><div class="em-line">
      <div class="em-txt"><b>Sender</b><span class="em-val${set ? "" : " em-none"}">${who}</span>${via ? `<span class="em-via">${via}</span>` : ""}</div>
      ${mailEditing ? "" : `<div class="em-btns">${e.source === "panel" ? `<button type="button" class="lt-btn" id="ml-rm">Remove</button>` : ""}<button type="button" class="lt-btn" id="ml-edit">${set ? "Change" : "Set Up"}</button></div>`}
    </div>${mailEditing ? form : ""}</div></div>
    <p class="lx-help em-foot">Used for invitations, password resets, security notices and students' sign-in codes, and for each course's emails unless it has its own sender. Any SMTP login works: for Gmail, <code>smtp.gmail.com</code> and an app password.</p>`;
  if (!mailEditing) {
    $("#ml-edit").onclick = () => { mailEditing = true; drawEmail().then(() => $("#ml-from") && $("#ml-from").focus()); };
    const rm = $("#ml-rm");
    if (rm) rm.onclick = () => withPassword("Remove the email settings?", "Lectern goes back to the server's <code>.env</code> settings, or to no email (links to send yourself).", "Remove",
      async password => { await api("/api/admin/email", { action: "remove", password }); toast("Email settings removed."); });
    return;
  }
  $("#ml-sec").onchange = () => { $("#ml-port").placeholder = $("#ml-sec").value === "ssl" ? "465" : "587"; };
  $("#ml-cancel").onclick = () => { mailEditing = false; drawEmail(); };
  $("#lxa-mail-f").onsubmit = ev => {
    ev.preventDefault();
    const s = { host: $("#ml-host").value.trim(), security: $("#ml-sec").value, port: $("#ml-port").value.trim(), user: $("#ml-user").value.trim(), smtpPassword: $("#ml-pw").value, from: $("#ml-from").value.trim() };
    if (!s.host) return toast("Enter the SMTP server first.");
    withPassword("Save the email settings?", `Lectern sends a test email to <b>${esc(me.email)}</b> first; they're saved only if it goes through.`, "Send Test and Save",
      async password => { await api("/api/admin/email", { ...s, password }); mailEditing = false; toast(`It works: the test went to ${me.email}. Saved.`); }, "primary");
  };
}

// ── Start ────────────────────────────────────────────────────────────
(async () => {
  try {
    const d = await api("/api/admin/me");
    if (d.signedIn) return start(d.admin);
  } catch (_) {}
  showSignIn();
})();
