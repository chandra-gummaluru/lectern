/* The admin panel (/admin): signing in (email, password and a two-factor code), then invitations,
   accounts, old courses to import, and the other admins. Its own session, separate from Lectern's.
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
function withPassword(title, text, label, run) {
  modal(`<h2>${esc(title)}</h2><form novalidate><p>${text}</p><div class="lt-form">
      <label>Your password<input type="password" id="ap-pw" autocomplete="current-password"></label></div>
      <p class="lt-err"></p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn lt-btn-danger">${esc(label)}</button></div></form>`, (m, close) => {
    m.querySelector("[data-no]").onclick = close;
    m.querySelector("form").onsubmit = async e => {
      e.preventDefault();
      const go = m.querySelector("[type=submit]"); go.disabled = true;
      try { await run(m.querySelector("#ap-pw").value); close(); draw(); } catch (x) { m.querySelector(".lt-err").textContent = x.message; go.disabled = false; }
    };
  });
}

// ── Signing in ───────────────────────────────────────────────────────
function showSignIn(msg = "") {
  $("#ad-app").hidden = true; $("#ad-signin").hidden = false;
  document.body.className = "lt-on-splash";
  const st = $("#ad-status"); st.className = `sp-hint${msg ? " is-error" : ""}`; st.textContent = msg;
  setTimeout(() => $("#ad-email").focus(), 0);
}
wireShow($("#ad-form"));
$("#ad-form").onsubmit = async e => {
  e.preventDefault();
  const go = $("#ad-go"), st = $("#ad-status");
  if (!secureHere()) { st.className = "sp-hint is-error"; st.textContent = "This page isn't secure (no HTTPS), so it won't send your password."; return; }
  go.disabled = true; go.textContent = "Signing in…"; st.textContent = "";
  try {
    const d = await api("/api/admin/login", { email: $("#ad-email").value.trim(), password: $("#ad-pw").value, code: $("#ad-code").value.replace(/\s+/g, "") });
    $("#ad-pw").value = ""; $("#ad-code").value = "";
    start(d.admin);
  } catch (x) { st.className = "sp-hint is-error"; st.textContent = x.message; $("#ad-code").value = ""; }
  finally { go.disabled = false; go.textContent = "Sign in"; }
};
$("#ad-out").onclick = async () => { try { await api("/api/admin/logout", {}); } catch (_) {} location.replace("/admin"); };

let me = null;
function start(admin) {
  me = admin;
  $("#ad-signin").hidden = true; $("#ad-app").hidden = false;
  document.body.className = "lt-on-app lt-on-page";
  $("#ad-who").textContent = admin.name ? `${admin.name} · ${admin.email}` : admin.email;
  draw();
}

// ── The panel ────────────────────────────────────────────────────────
let area = "pub";
async function draw() {
  const page = $("#ad-page");
  let d;
  try { d = await api("/api/admin/overview"); } catch (x) { if (x.code !== "signed-out") page.innerHTML = `<div class="lt-in"><p class="lt-note err">${esc(x.message)}</p></div>`; return; }
  const userOpts = d.users.map(u => `<option value="${u.id}">${esc(u.name || u.email)} (${esc(u.email)})</option>`).join("");
  page.innerHTML = `<div class="lt-in lt-account">
    <h1>Admin</h1>
    <p class="lt-lede">Lectern is invite-only: invite each person by email; the link works once, for 7 days. ${d.email ? "" : "<b>The server can't send email</b> (no SMTP settings), so you'll get links to send yourself."}</p>

    <div class="lt-sec"><h2>Invite Someone</h2></div>
    <section class="lt-panel">
      <form id="ad-inv" class="lt-team-add" novalidate>
        <input type="email" id="ad-inv-email" placeholder="name@utoronto.ca" aria-label="Email" autocomplete="off">
        <button type="submit" class="lt-btn primary">Invite</button>
      </form>
      <div id="ad-inv-msg"></div>
    </section>

    ${d.invites.length ? `<div class="lt-sec"><h2>Waiting Invitations</h2><span>${d.invites.length}</span></div>
    <div class="lt-olist">${d.invites.map(i => `<div class="lt-orow lt-user"><div class="lt-user-who"><b>${esc(i.email)}</b><span>sent ${esc(day(i.created))}, works until ${esc(day(i.expires))}</span></div>
      <span class="lt-orow-r"><button type="button" class="lt-link" data-revoke="${esc(i.id)}">Cancel</button></span></div>`).join("")}</div>` : ""}

    <div class="lt-sec"><h2>Accounts</h2><span>${d.users.length}</span></div>
    ${d.users.length ? `<div class="lt-olist">${d.users.map(u => `<div class="lt-orow lt-user">
      <div class="lt-user-who"><b>${esc(u.name || u.email)}</b><span>${esc(u.email)} · <a href="${esc(u.site)}" target="_blank" rel="noopener">${esc(u.handle)}</a> · last sign-in ${esc(when(u.lastLogin))}</span></div>
      <span class="lt-tags">${u.twoFactor ? `<span class="lt-tag ok">2FA</span>` : `<span class="lt-tag dim">No 2FA</span>`}${u.teams ? `<span class="lt-tag dim">On ${u.teams} team${u.teams === 1 ? "" : "s"}</span>` : ""}${u.disabled ? `<span class="lt-tag bad">Off</span>` : ""}${u.locked ? `<span class="lt-tag bad">Waiting (wrong passwords)</span>` : ""}</span>
      <span class="lt-orow-r ad-acts">
        <button type="button" class="lt-link" data-u="${u.id}" data-act="sign-out">Sign out everywhere</button>
        ${u.locked ? `<button type="button" class="lt-link" data-u="${u.id}" data-act="unlock">Let them try again</button>` : ""}
        ${u.twoFactor ? `<button type="button" class="lt-link" data-u="${u.id}" data-act="reset-2fa">Turn off 2FA</button>` : ""}
        ${u.disabled ? `<button type="button" class="lt-link" data-u="${u.id}" data-act="enable">Turn on</button>` : `<button type="button" class="lt-link lt-del" data-u="${u.id}" data-act="disable">Turn off</button>`}
      </span></div>`).join("")}</div>` : `<p class="lt-hint">No accounts yet: invite someone above.</p>`}

    <div class="lt-sec"><h2>Import Old Courses</h2></div>
    <section class="lt-panel">
      <p class="lt-row-text">From the two GitHub repositories Lectern used before: on GitHub, <b>Code → Download ZIP</b> for each, then import each into the account it belongs to. Only files the account doesn't have yet are added: nothing of theirs is changed, and they're emailed about it.</p>
      ${d.users.length ? `<form id="ad-imp" class="ad-import" novalidate style="margin-top:14px">
        <label class="lt-form" style="margin:0"><span style="font-size:13px;font-weight:600">Account</span><select id="ad-imp-user" class="lt-filter">${userOpts}</select></label>
        <div class="lt-seg" role="group" aria-label="Which repository">
          <button type="button" data-area="pub" aria-pressed="${area === "pub"}">Public: course pages</button><button type="button" data-area="priv" aria-pressed="${area === "priv"}">Private: grades and exams</button>
        </div>
        <div class="ad-file"><label class="lt-btn"><input type="file" id="ad-imp-file" accept=".zip,application/zip" hidden>Choose ZIP…</label><span id="ad-imp-name">No file chosen</span></div>
        <div><button type="submit" class="lt-btn primary">Import</button></div>
      </form>` : `<p class="lt-row-text" style="margin-top:10px">Invite the account first.</p>`}
    </section>

    <div class="lt-sec"><h2>Admins</h2><span>Added on the server: <code>python app.py admin them@example.com</code></span></div>
    <div class="lt-olist">${d.admins.map(a => `<div class="lt-orow lt-user">
      <div class="lt-user-who"><b>${esc(a.name || a.email)}${a.id === d.me ? " (you)" : ""}</b><span>${esc(a.email)} · last sign-in ${esc(when(a.lastLogin))}</span></div>
      <span class="lt-tags">${a.disabled ? `<span class="lt-tag bad">Off</span>` : ""}</span>
      <span class="lt-orow-r ad-acts">${a.id === d.me ? "" : a.disabled ? `<button type="button" class="lt-link" data-a="${a.id}" data-act="enable">Turn on</button>` : `<button type="button" class="lt-link lt-del" data-a="${a.id}" data-act="disable">Turn off</button>`}</span>
    </div>`).join("")}</div>
  </div>`;

  $("#ad-inv").onsubmit = async e => {
    e.preventDefault();
    const btn = e.target.querySelector("[type=submit]"); btn.disabled = true;
    try {
      const r = await api("/api/admin/invites", { email: $("#ad-inv-email").value.trim() });
      if (r.emailed) { toast(`Invitation emailed to ${r.email}.`); return draw(); }
      await draw();
      $("#ad-inv-msg").innerHTML = `<p class="lt-note">Send <b>${esc(r.email)}</b> this link (only to them: it works for whoever has it):
        <span class="lt-linkbox"><input type="text" readonly value="${esc(r.link)}"><button type="button" class="lt-btn" data-copy>Copy</button></span></p>`;
      $("#ad-inv-msg [data-copy]").onclick = async () => { try { await navigator.clipboard.writeText(r.link); toast("Copied."); } catch (_) { $("#ad-inv-msg input").select(); } };
    } catch (x) { toast(x.message); } finally { btn.disabled = false; }
  };
  page.querySelectorAll("[data-revoke]").forEach(b => { b.onclick = async () => { await api("/api/admin/invites/revoke", { id: b.dataset.revoke }); draw(); }; });
  page.querySelectorAll("[data-u]").forEach(b => {
    b.onclick = async () => {
      const u = d.users.find(x => x.id === Number(b.dataset.u)), act = b.dataset.act, go = password => api(`/api/admin/users/${u.id}`, { action: act, password });
      if (act === "reset-2fa") return withPassword("Turn off their two-factor sign-in?", `For ${esc(u.email)}, e.g. after a lost phone. They're signed out and emailed, and can turn it on again.`, "Turn it off", go);
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
  page.querySelectorAll("[data-area]").forEach(b => { b.onclick = () => { area = b.dataset.area; page.querySelectorAll("[data-area]").forEach(x => x.setAttribute("aria-pressed", String(x === b))); }; });
  const imp = $("#ad-imp");
  const fileIn = $("#ad-imp-file");
  if (fileIn) fileIn.onchange = () => { $("#ad-imp-name").textContent = fileIn.files[0] ? fileIn.files[0].name : "No file chosen"; };
  if (imp) imp.onsubmit = async e => {
    e.preventDefault();
    const f = $("#ad-imp-file").files[0], btn = imp.querySelector("[type=submit]");
    if (!f) return toast("Choose the ZIP file first.");
    const fd = new FormData(); fd.append("user", $("#ad-imp-user").value); fd.append("area", area); fd.append("zip", f);
    btn.disabled = true; btn.textContent = "Importing…";
    try {
      const r = await api("/api/admin/import", fd, { form: true });
      toast(`Imported ${r.files} file${r.files === 1 ? "" : "s"}.${r.already ? ` ${r.already} they already had were left as they are.` : ""}${r.skipped.length ? ` Skipped ${r.skipped.length}.` : ""}`);
      $("#ad-imp-file").value = ""; $("#ad-imp-name").textContent = "No file chosen";
    } catch (x) { toast(x.message); } finally { btn.disabled = false; btn.textContent = "Import"; }
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
