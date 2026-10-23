/* Lectern accounts in the browser: signing in (email, password, and a two-factor code when it's on),
   a forgotten password, an invitation, and signing in again when a session ends mid-work.

   The password goes only to Lectern's own server, inside HTTPS (this page won't send it over plain
   HTTP anywhere but localhost), and nothing here keeps it: no storage, no cookies. The server's session
   cookie is HttpOnly, so no script on the page can read it either.

   Invitation, team and reset links carry their token after # (…/#invite=…, #join=…, #reset=…), which browsers never
   send to a server or in a Referer; it's read here and taken out of the address straight away. */

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const $ = (s, r = document) => r.querySelector(s);
const HINT = "lectern.signedin";   // only a hint for the first paint (index.html): the server decides

export class AuthError extends Error { constructor(status, msg, code = "") { super(msg); this.status = status; this.code = code; } }

const LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/;
export const secureHere = () => location.protocol === "https:" || LOCAL.test(location.hostname);

let reauthing = null, reauthUI = null;
/** The shell's sign-in-again window (set by lectern.js): called when a request finds the session over. */
export function setReauth(fn) { reauthUI = fn; }
/** Sign in again (one window, however many requests noticed). Resolves when signed in. */
export function reauth() {
  if (!reauthUI) return Promise.reject(new AuthError(401, "Please sign in again."));
  if (!reauthing) reauthing = reauthUI().finally(() => { reauthing = null; });
  return reauthing;
}

/** A call to Lectern's API: JSON in and out, from this page (X-Lectern), with the session cookie.
    A session that ended mid-work gets the sign-in-again window, then the call is made again. */
export async function api(path, body, { method, retry = true } = {}) {
  let res, data = {};
  try {
    res = await fetch(path, {
      method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin", cache: "no-store",
      headers: { "X-Lectern": "1", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (_) { throw new AuthError(0, "Couldn't reach Lectern's server. Check your internet connection."); }
  try { data = await res.json(); } catch (_) { data = {}; }
  if (res.status === 401 && data.code === "signed-out" && retry && reauthUI) { await reauth(); return api(path, body, { method, retry: false }); }
  if (!res.ok) throw new AuthError(res.status, data.error || data.message || `Something went wrong (${res.status}).`, data.code || "");
  return data;
}

export async function me() {
  const d = await api("/api/auth/me");
  setHint(!!d.signedIn);
  return d;
}
export function setHint(on) { try { on ? localStorage.setItem(HINT, "1") : localStorage.removeItem(HINT); } catch (_) {} }

export async function signOut() {
  try { await api("/api/auth/logout", {}, { retry: false }); } catch (_) {}
  setHint(false);
}

function needSecure() {
  if (!secureHere()) throw new AuthError(0, "This page isn't secure (no HTTPS), so Lectern won't send your password. Open it with https://.");
}

// ── Password fields: Show / Hide ─────────────────────────────────────
export function wireShow(root) {
  root.querySelectorAll("[data-show]").forEach(b => {
    b.onclick = () => {
      const i = root.querySelector(`#${b.dataset.show}`), show = i.type === "password";
      i.type = show ? "text" : "password"; b.textContent = show ? "Hide" : "Show";
      b.setAttribute("aria-label", show ? "Hide password" : "Show password");
      i.focus();
    };
  });
}
const pwField = (id, label, auto, extra = "") => `<label class="sp-field"><span>${label}</span><span class="sp-pw"><input type="password" id="${id}" autocomplete="${auto}" required${extra}><button type="button" class="sp-show" data-show="${id}" aria-label="Show password">Show</button></span></label>`;
export const PW_RULE = "At least 12 characters. A few words together is strong and easy to remember.";

// A two-factor step: an authenticator code, or (instead) one of the recovery codes.
function codeFields(idPrefix, lt = false) {
  if (lt) return `<label data-k="code">Code from your authenticator app
      <input type="text" id="${idPrefix}-code" inputmode="numeric" autocomplete="one-time-code" maxlength="7" placeholder="6-digit code"></label>
    <label data-k="rec" hidden>Recovery code
      <input type="text" id="${idPrefix}-rec" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="abcde-fghij"><small>Each recovery code works once.</small></label>
    <button type="button" class="lt-link" data-swap style="justify-self:start">Use a recovery code instead</button>`;
  return `<label class="sp-field" data-k="code"><span>Code from your authenticator app</span>
      <input type="text" id="${idPrefix}-code" class="sp-code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9 ]*" maxlength="7" placeholder="6-digit code"></label>
    <label class="sp-field" data-k="rec" hidden><span>Recovery code</span>
      <input type="text" id="${idPrefix}-rec" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="abcde-fghij"><small>Each recovery code works once.</small></label>
    <button type="button" class="sp-link" data-swap>Use a recovery code instead</button>`;
}
export { codeFields, wireCode };
function wireCode(root, idPrefix) {
  let rec = false;
  const swap = root.querySelector("[data-swap]");
  swap.onclick = () => {
    rec = !rec;
    root.querySelector('[data-k="code"]').hidden = rec; root.querySelector('[data-k="rec"]').hidden = !rec;
    swap.textContent = rec ? "Use the authenticator app instead" : "Use a recovery code instead";
    root.querySelector(`#${idPrefix}-${rec ? "rec" : "code"}`).focus();
  };
  return () => rec ? { recovery: root.querySelector(`#${idPrefix}-rec`).value.trim() } : { code: root.querySelector(`#${idPrefix}-code`).value.replace(/\s+/g, "") };
}

// ── The splash: sign in, and the steps around it ─────────────────────
/** Wire the splash. onSignedIn(user, how, team) is called once there's a session ("login" | "invite" | "join";
    team: { owner, offering } after joining a teaching team). */
export function initSplash(onSignedIn) {
  let joining = "";   // a team invitation to accept once signed in (an existing account)
  const signedIn = async user => {
    if (!joining) return onSignedIn(user, "login");
    try {
      const j = await api("/api/teams/join", { token: joining }, { retry: false });
      onSignedIn(user, "join", { owner: j.owner, offering: j.offering });
    } catch (x) { onSignedIn(user, "login", null, x.message); }
  };
  const form = $("#sp-form"), panel = $("#sp-panel"), status = $("#splash-status");
  const say = (msg, err = true) => { status.className = `sp-hint${err ? " is-error" : ""}`; status.textContent = msg || ""; };
  const busy = (b, on, label) => { b.disabled = on; if (label) b.textContent = label; };
  wireShow(form);

  const showForm = (msg = "", err = false) => {
    panel.hidden = true; panel.innerHTML = ""; form.hidden = false; say(msg, err);
    setTimeout(() => ($("#sp-email").value ? $("#sp-pw") : $("#sp-email")).focus(), 0);
  };
  const showPanel = html => { form.hidden = true; panel.hidden = false; panel.innerHTML = html; say(""); wireShow(panel); };

  form.onsubmit = async e => {
    e.preventDefault();
    const go = $("#sp-go"), email = $("#sp-email").value.trim(), password = $("#sp-pw").value;
    if (!email || !password) return say("Enter your email and password.");
    busy(go, true, "Signing in…"); say("");
    try {
      needSecure();
      const d = await api("/api/auth/login", { email, password }, { retry: false });
      $("#sp-pw").value = "";
      if (d.twoFactor) return codeStep();
      setHint(true); signedIn(d.user);
    } catch (x) { say(x.message); if (x.code === "bad-login") { $("#sp-pw").select(); } }
    finally { busy(go, false, "Sign in"); }
  };

  function codeStep() {
    showPanel(`<form id="sp-2fa" novalidate><div class="sp-form">
        <h2>Two-factor sign-in</h2><p>Open your authenticator app and enter the 6-digit code for Lectern.</p>
        ${codeFields("sp2")}
        <button type="submit" class="sp-btn sp-btn--primary" id="sp2-go">Continue</button>
        <button type="button" class="sp-link" data-back>Back</button></div></form>`);
    const get = wireCode(panel, "sp2");
    panel.querySelector("[data-back]").onclick = () => showForm();
    $("#sp2-code").focus();
    $("#sp-2fa").onsubmit = async e => {
      e.preventDefault();
      const go = $("#sp2-go"); busy(go, true, "Checking…");
      try {
        const d = await api("/api/auth/login/2fa", get(), { retry: false });
        setHint(true); signedIn(d.user);
      } catch (x) {
        if (x.code === "expired") return showForm(x.message, true);
        say(x.message); busy(go, false, "Continue");
      }
    };
  }

  $("#sp-forgot").onclick = () => {
    showPanel(`<form id="sp-fg" novalidate><div class="sp-form">
        <h2>Forgot your password?</h2><p>We'll email you a link to choose a new one.</p>
        <label class="sp-field"><span>Email</span><input type="email" id="fg-email" autocomplete="username" value="${esc($("#sp-email").value.trim())}" required></label>
        <button type="submit" class="sp-btn sp-btn--primary" id="fg-go">Email me a link</button>
        <button type="button" class="sp-link" data-back>Back to sign in</button></div></form>`);
    panel.querySelector("[data-back]").onclick = () => showForm();
    $("#fg-email").focus();
    $("#sp-fg").onsubmit = async e => {
      e.preventDefault();
      const go = $("#fg-go"); busy(go, true, "Sending…");
      try {
        const d = await api("/api/auth/forgot", { email: $("#fg-email").value.trim() }, { retry: false });
        panel.querySelector(".sp-form").innerHTML = `<h2>Check your email</h2><p class="sp-ok">${esc(d.message)}</p><button type="button" class="sp-link" data-back>Back to sign in</button>`;
        panel.querySelector("[data-back]").onclick = () => showForm();
      } catch (x) { say(x.message); busy(go, false, "Email me a link"); }
    };
  };

  // A link from an email: #invite=…, #join=… or #reset=…
  const m = /^#(invite|join|reset)=([\w-]{20,200})$/.exec(location.hash);
  if (m) {
    history.replaceState(null, "", location.pathname + location.search + "#/");   // out of the address bar and history
    return m[1] === "invite" ? inviteStep(m[2]) : m[1] === "join" ? joinStep(m[2]) : resetStep(m[2]);
  }
  showForm();
  return null;

  async function resetStep(token) {
    showPanel(`<div class="sp-form"><p>Checking the link…</p></div>`);
    let info;
    try { info = await api("/api/auth/reset/check", { token }, { retry: false }); }
    catch (x) { return showForm(x.message, true); }
    showPanel(`<form id="sp-rs" novalidate><div class="sp-form">
        <h2>Choose a new password</h2><p>For <b>${esc(info.email)}</b>.</p>
        <input type="email" autocomplete="username" value="${esc(info.email)}" hidden readonly>
        ${pwField("rs-pw", "New password", "new-password", ' minlength="12"')}
        ${pwField("rs-pw2", "New password, again", "new-password")}
        <p style="text-align:left;font-size:12.5px;color:var(--ink-3)">${PW_RULE}</p>
        ${info.twoFactor ? codeFields("rs") : ""}
        <button type="submit" class="sp-btn sp-btn--primary" id="rs-go">Save the new password</button>
        <button type="button" class="sp-link" data-back>Back to sign in</button></div></form>`);
    const get = info.twoFactor ? wireCode(panel, "rs") : () => ({});
    panel.querySelector("[data-back]").onclick = () => showForm();
    $("#rs-pw").focus();
    $("#sp-rs").onsubmit = async e => {
      e.preventDefault();
      const pw = $("#rs-pw").value;
      if (pw !== $("#rs-pw2").value) return say("The two passwords aren't the same.");
      const go = $("#rs-go"); busy(go, true, "Saving…");
      try {
        needSecure();
        await api("/api/auth/reset", { token, password: pw, ...get() }, { retry: false });
        $("#sp-email").value = info.email;
        showForm("Your password is changed, and every device was signed out. Sign in with the new one.", false);
      } catch (x) { say(x.message); busy(go, false, "Save the new password"); if (x.status === 410) showForm(x.message, true); }
    };
  }

  async function inviteStep(token) {
    showPanel(`<div class="sp-form"><p>Checking the invitation…</p></div>`);
    let info;
    try { info = await api("/api/auth/invite/check", { token }, { retry: false }); }
    catch (x) { return showForm(x.message, true); }
    createStep(token, info, `You're invited as <b>${esc(info.email)}</b>.`, "/api/auth/invite/accept", "invite");
  }

  // A teaching team's invitation: accept it signed in (an account for that email), or by making the account.
  async function joinStep(token) {
    showPanel(`<div class="sp-form"><p>Checking the invitation…</p></div>`);
    let info;
    try { info = await api("/api/teams/join/check", { token }, { retry: false }); }
    catch (x) { return showForm(x.message, true); }
    const what = `${esc(info.ownerName)} asked you to join the teaching team for <b>${esc(info.offering.replace("/", " ").toUpperCase())}</b>, as ${info.role === "ta" ? "a TA" : "an instructor"}.`;
    const signIn = () => {
      joining = token;
      $("#sp-email").value = info.email;
      showForm();
      status.className = "sp-hint"; status.innerHTML = `${what} Sign in as <b>${esc(info.email)}</b> to accept.`;
    };
    showPanel(`<div class="sp-form">
        <h2>Join the teaching team</h2><p>${what}</p><p>For <b>${esc(info.email)}</b>.</p>
        <button type="button" class="sp-btn sp-btn--primary" id="jn-in">I have a Lectern account: sign in</button>
        ${info.canCreate ? `<button type="button" class="sp-btn sp-btn--quiet" id="jn-new">I'm new to Lectern: make an account</button>` : `<p style="font-size:12.5px;color:var(--ink-3)">New accounts for this address need your Lectern admin.</p>`}
      </div>`);
    $("#jn-in").onclick = signIn;
    const nw = $("#jn-new");
    if (nw) nw.onclick = () => createStep(token, info, `${what} Your account: <b>${esc(info.email)}</b>.`, "/api/teams/join/create", "join", signIn);
    $("#jn-in").focus();
  }

  function createStep(token, info, intro, endpoint, how, ifExists) {
    showPanel(`<form id="sp-iv" novalidate><div class="sp-form">
        <h2>Create your account</h2><p>${intro}</p>
        <input type="email" autocomplete="username" value="${esc(info.email)}" hidden readonly>
        <label class="sp-field"><span>Your name</span><input type="text" id="iv-name" autocomplete="name" required></label>
        <label class="sp-field"><span>Address for your course pages</span><input type="text" id="iv-handle" value="${esc(info.handle)}" autocapitalize="off" spellcheck="false" required>
          <small class="sp-addr" id="iv-addr"></small></label>
        ${pwField("iv-pw", "Password", "new-password", ' minlength="12"')}
        ${pwField("iv-pw2", "Password, again", "new-password")}
        <p style="text-align:left;font-size:12.5px;color:var(--ink-3)">${PW_RULE}</p>
        <button type="submit" class="sp-btn sp-btn--primary" id="iv-go">Create account</button></div></form>`);
    const h = $("#iv-handle"), addr = () => { $("#iv-addr").textContent = `${info.pages}${h.value.trim().toLowerCase() || "…"}/csc258/f26/info.html`; };
    h.addEventListener("input", addr); addr();
    $("#iv-name").focus();
    $("#sp-iv").onsubmit = async e => {
      e.preventDefault();
      const pw = $("#iv-pw").value;
      if (!$("#iv-name").value.trim()) return say("Enter your name.");
      if (pw !== $("#iv-pw2").value) return say("The two passwords aren't the same.");
      const go = $("#iv-go"); busy(go, true, "Creating…");
      try {
        needSecure();
        const d = await api(endpoint, { token, name: $("#iv-name").value.trim(), handle: h.value.trim().toLowerCase(), password: pw }, { retry: false });
        setHint(true); onSignedIn(d.user, how, d.team);
      } catch (x) {
        busy(go, false, "Create account");
        if (x.code === "exists" && ifExists) { ifExists(); return say(x.message); }
        say(x.message); if (x.status === 410) showForm(x.message, true);
      }
    };
  }
}

// ── Signing in again, without leaving the page (unsaved work stays) ──
/** The window for it, drawn with the shell's modal(). email: who was signed in. */
export function reauthWindow(modal, email, onSignOut) {
  return () => new Promise((resolve, reject) => {
    modal(`<h2>Sign in again</h2><p>Your session ended. Sign in again to carry on: nothing you haven't saved is lost.</p>
      <form id="ra-form" novalidate><div class="lt-form">
        <label>Email<input type="email" id="ra-email" value="${esc(email)}" autocomplete="username" readonly></label>
        <label>Password<input type="password" id="ra-pw" autocomplete="current-password" required></label>
        <div id="ra-2fa" hidden></div>
      </div>
      <p class="lt-err" id="ra-err"></p>
      <div class="lt-modal-acts"><button type="button" class="lt-btn" data-out>Sign out</button><button type="submit" class="lt-btn primary" id="ra-go">Sign in</button></div></form>`, (m, close) => {
      let step = "pw", get = null;
      const err = t => { m.querySelector("#ra-err").textContent = t || ""; };
      m.querySelector("[data-out]").onclick = () => { close(); reject(new AuthError(401, "Signed out.")); onSignOut(); };
      m.querySelector("#ra-form").onsubmit = async e => {
        e.preventDefault(); err("");
        const go = m.querySelector("#ra-go"); go.disabled = true;
        try {
          needSecure();
          let d;
          if (step === "pw") d = await api("/api/auth/login", { email, password: m.querySelector("#ra-pw").value }, { retry: false });
          else d = await api("/api/auth/login/2fa", get(), { retry: false });
          if (d.twoFactor) {
            step = "code";
            const box = m.querySelector("#ra-2fa");
            box.hidden = false;
            box.innerHTML = codeFields("ra", true);
            box.style.display = "grid"; box.style.gap = "12px";
            get = wireCode(box, "ra");
            m.querySelector("#ra-pw").closest("label").hidden = true;
            m.querySelector("#ra-code").focus();
            go.textContent = "Continue";
            return;
          }
          setHint(true); close(); resolve(d.user);
        } catch (x) {
          if (x.code === "expired") { step = "pw"; m.querySelector("#ra-2fa").hidden = true; m.querySelector("#ra-pw").closest("label").hidden = false; go.textContent = "Sign in"; }
          err(x.message);
        } finally { go.disabled = false; }
      };
      setTimeout(() => m.querySelector("#ra-pw").focus(), 0);
    }, { sticky: true });
  });
}
