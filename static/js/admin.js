/* The admin panel (/admin): signing in (email, password and a two-factor code), then invitations,
   accounts (and deleting them), email settings, and the other admins. Its own session, separate from Lectern's.
   Admins are added only on the server: python app.py admin you@example.com */
import { wireShow, secureHere } from "./auth.js";

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
$("#lxa-out").onclick = async () => { try { await api("/api/admin/logout", {}); } catch (_) {} location.replace("/admin"); };

let me = null;
function start(admin) {
  me = admin;
  $("#lxa-signin").hidden = true; $("#lxa-app").hidden = false;
  document.body.className = "lt-on-app lt-on-page";
  $("#lxa-who").textContent = admin.name ? `${admin.name} · ${admin.email}` : admin.email;
  draw();
}

// ── The panel ────────────────────────────────────────────────────────
async function draw() {
  const page = $("#lxa-page");
  let d;
  try { d = await api("/api/admin/overview"); } catch (x) { if (x.code !== "signed-out") page.innerHTML = `<div class="lt-in"><p class="lt-note err">${esc(x.message)}</p></div>`; return; }
  page.innerHTML = `<div class="lt-in lt-account">
    <h1>Admin</h1>
    <p class="lt-lede">Lectern is invite-only: invite each person by email; the link works once, for 7 days. ${d.email ? "" : "<b>Email isn't set up</b>, so you'll get links to send yourself: set it up under <a href=\"#lxa-mail\">Email</a>."}</p>

    <div class="lt-sec"><h2>Invite Someone</h2></div>
    <section class="lt-panel">
      <form id="lxa-inv" class="lt-team-add" novalidate>
        <input type="email" id="lxa-inv-email" placeholder="name@utoronto.ca" aria-label="Email" autocomplete="off">
        <button type="submit" class="lt-btn primary">Invite</button>
      </form>
      <div id="lxa-inv-msg"></div>
    </section>

    ${d.invites.length ? `<div class="lt-sec"><h2>Waiting Invitations</h2><span>${d.invites.length}</span></div>
    <div class="lt-olist">${d.invites.map(i => `<div class="lt-orow lt-user"><div class="lt-user-who"><b>${esc(i.email)}</b><span>sent ${esc(day(i.created))}, works until ${esc(day(i.expires))}</span></div>
      <span class="lt-orow-r"><button type="button" class="lt-link" data-revoke="${esc(i.id)}">Cancel</button></span></div>`).join("")}</div>` : ""}

    <div class="lt-sec"><h2>Accounts</h2><span>${d.users.length}</span></div>
    ${d.users.length ? `<div class="lt-olist">${d.users.map(u => `<div class="lt-orow lt-user">
      <div class="lt-user-who"><b>${esc(u.name || u.email)}</b><span>${esc(u.email)} · <a href="${esc(u.site)}" target="_blank" rel="noopener">${esc(u.handle)}</a> · last sign-in ${esc(when(u.lastLogin))}</span></div>
      <span class="lt-tags">${u.twoFactor ? `<span class="lt-tag ok">2FA</span>` : `<span class="lt-tag dim">No 2FA</span>`}${u.teams ? `<span class="lt-tag dim">On ${u.teams} team${u.teams === 1 ? "" : "s"}</span>` : ""}${u.disabled ? `<span class="lt-tag bad">Off</span>` : ""}${u.locked ? `<span class="lt-tag bad">Waiting (wrong passwords)</span>` : ""}</span>
      <span class="lt-orow-r lxa-acts">
        <button type="button" class="lt-link" data-u="${u.id}" data-act="sign-out">Sign out everywhere</button>
        ${u.locked ? `<button type="button" class="lt-link" data-u="${u.id}" data-act="unlock">Let them try again</button>` : ""}
        ${u.twoFactor ? `<button type="button" class="lt-link" data-u="${u.id}" data-act="reset-2fa">Turn off 2FA</button>` : ""}
        ${u.disabled ? `<button type="button" class="lt-link" data-u="${u.id}" data-act="enable">Turn on</button>` : `<button type="button" class="lt-link lt-del" data-u="${u.id}" data-act="disable">Turn off</button>`}
        <button type="button" class="lt-link lt-del" data-u="${u.id}" data-act="delete">Delete</button>
      </span></div>`).join("")}</div>` : `<p class="lt-hint">No accounts yet: invite someone above.</p>`}

    <div class="lt-sec"><h2>Email</h2><span>${d.email ? "Set up" : "Off"}</span></div>
    <section class="lt-panel" id="lxa-mail"><div class="lt-loading" style="min-height:60px">Loading…</div></section>

    <div class="lt-sec"><h2>Admins</h2><span>Added on the server: <code>python app.py admin them@example.com</code></span></div>
    <div class="lt-olist">${d.admins.map(a => `<div class="lt-orow lt-user">
      <div class="lt-user-who"><b>${esc(a.name || a.email)}${a.id === d.me ? " (you)" : ""}</b><span>${esc(a.email)} · last sign-in ${esc(when(a.lastLogin))}</span></div>
      <span class="lt-tags">${a.disabled ? `<span class="lt-tag bad">Off</span>` : ""}</span>
      <span class="lt-orow-r lxa-acts">${a.id === d.me ? "" : a.disabled ? `<button type="button" class="lt-link" data-a="${a.id}" data-act="enable">Turn on</button>` : `<button type="button" class="lt-link lt-del" data-a="${a.id}" data-act="disable">Turn off</button>`}</span>
    </div>`).join("")}</div>
  </div>`;

  $("#lxa-inv").onsubmit = async e => {
    e.preventDefault();
    const btn = e.target.querySelector("[type=submit]"); btn.disabled = true;
    try {
      const r = await api("/api/admin/invites", { email: $("#lxa-inv-email").value.trim() });
      if (r.emailed) { toast(`Invitation emailed to ${r.email}.`); return draw(); }
      await draw();
      $("#lxa-inv-msg").innerHTML = `<p class="lt-note">Send <b>${esc(r.email)}</b> this link (only to them: it works for whoever has it):
        <span class="lt-linkbox"><input type="text" readonly value="${esc(r.link)}"><button type="button" class="lt-btn" data-copy>Copy</button></span></p>`;
      $("#lxa-inv-msg [data-copy]").onclick = async () => { try { await navigator.clipboard.writeText(r.link); toast("Copied."); } catch (_) { $("#lxa-inv-msg input").select(); } };
    } catch (x) { toast(x.message); } finally { btn.disabled = false; }
  };
  page.querySelectorAll("[data-revoke]").forEach(b => { b.onclick = async () => { await api("/api/admin/invites/revoke", { id: b.dataset.revoke }); draw(); }; });
  page.querySelectorAll("[data-u]").forEach(b => {
    b.onclick = async () => {
      const u = d.users.find(x => x.id === Number(b.dataset.u)), act = b.dataset.act, go = password => api(`/api/admin/users/${u.id}`, { action: act, password });
      if (act === "reset-2fa") return withPassword("Turn off their two-factor sign-in?", `For ${esc(u.email)}, e.g. after a lost phone. They're signed out and emailed, and can turn it on again.`, "Turn it off", go);
      if (act === "delete") return deleteUser(u);
      if (act === "disable") return withPassword("Turn this account off?", `${esc(u.email)} is signed out and can't sign in, and their published course pages stop showing. Nothing is deleted: you can turn it back on.`, "Turn it off", go);
      try { await go(""); toast({ "sign-out": `Signed ${u.email} out everywhere.`, unlock: "They can try again now.", enable: "Turned on." }[act] || "Done."); draw(); } catch (x) { toast(x.message); }
    };
  });
  page.querySelectorAll("[data-a]").forEach(b => {
    b.onclick = async () => {
      const a = d.admins.find(x => x.id === Number(b.dataset.a)), act = b.dataset.act, go = password => api(`/api/admin/admins/${a.id}`, { action: act, password });
      withPassword(act === "disable" ? "Turn this admin off?" : "Turn this admin back on?", `${esc(a.email)}${act === "disable" ? " is signed out and can't sign in to the admin panel." : " can sign in to the admin panel again."}`, act === "disable" ? "Turn off" : "Turn on", go);
    };
  });
  drawEmail();
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
async function drawEmail() {
  const box = $("#lxa-mail");
  if (!box) return;
  let e;
  try { e = await api("/api/admin/email"); } catch (x) { box.innerHTML = `<p class="lt-note err">${esc(x.message)}</p>`; return; }
  const sec = e.security || "starttls";
  box.innerHTML = `<p class="lt-row-text">${e.source === "panel" ? `Lectern sends email through <b>${esc(e.host)}</b>.`
      : e.source === "env" ? `Lectern sends email through <b>${esc(e.host)}</b>, from the server's <code>.env</code>. Saving here takes over from it.`
      : "Lectern emails invitations, password-reset links, security notices and students' receipts. Any SMTP login works: for Gmail, <code>smtp.gmail.com</code> and an app password."}</p>
    <form id="lxa-mail-f" class="lt-form lxa-mail" novalidate>
      <label class="lxa-wide">SMTP server<input type="text" id="ml-host" value="${esc(e.host)}" placeholder="smtp.gmail.com" autocomplete="off" spellcheck="false"></label>
      <label>Security<select id="ml-sec" class="lt-filter">${[["starttls", "STARTTLS"], ["ssl", "SSL"], ["none", "None"]].map(([v, t]) => `<option value="${v}"${v === sec ? " selected" : ""}>${t}</option>`).join("")}</select></label>
      <label>Port<input type="text" id="ml-port" inputmode="numeric" value="${esc(e.port)}" placeholder="${sec === "ssl" ? "465" : "587"}"></label>
      <label class="lxa-wide">Login<input type="text" id="ml-user" value="${esc(e.user)}" placeholder="lectern@example.com" autocomplete="off" spellcheck="false"></label>
      <label class="lxa-wide">Password<input type="password" id="ml-pw" autocomplete="new-password" placeholder="${e.hasPassword ? "Saved: leave blank to keep it" : "For Gmail, an app password"}"></label>
      <label class="lxa-wide">From<input type="text" id="ml-from" value="${esc(e.from)}" placeholder="Lectern <lectern@example.com>" spellcheck="false"><small>Leave blank to send from the login.</small></label>
      <div class="lxa-wide lxa-mail-acts"><button type="submit" class="lt-btn primary">Save and send me a test</button>${e.source === "panel" ? `<button type="button" class="lt-link lt-del" id="ml-rm">Remove these settings</button>` : ""}</div>
    </form>`;
  $("#ml-sec").onchange = () => { $("#ml-port").placeholder = $("#ml-sec").value === "ssl" ? "465" : "587"; };
  $("#lxa-mail-f").onsubmit = ev => {
    ev.preventDefault();
    const s = { host: $("#ml-host").value.trim(), security: $("#ml-sec").value, port: $("#ml-port").value.trim(), user: $("#ml-user").value.trim(), smtpPassword: $("#ml-pw").value, from: $("#ml-from").value.trim() };
    if (!s.host) return toast("Enter the SMTP server first.");
    withPassword("Save the email settings?", `Lectern sends a test email to <b>${esc(me.email)}</b> first; they're saved only if it goes through.`, "Send test and save",
      async password => { await api("/api/admin/email", { ...s, password }); toast(`Test email sent to ${me.email}. Settings saved.`); }, "primary");
  };
  const rm = $("#ml-rm");
  if (rm) rm.onclick = () => withPassword("Remove the email settings?", "Lectern goes back to the server's <code>.env</code> settings, or to no email (links to send yourself).", "Remove",
    async password => { await api("/api/admin/email", { action: "remove", password }); toast("Email settings removed."); });
}

// ── Start ────────────────────────────────────────────────────────────
(async () => {
  try {
    const d = await api("/api/admin/me");
    if (d.signedIn) return start(d.admin);
  } catch (_) {}
  showSignIn();
})();
