/* Your account (#/account): your name, your course pages' address, your password, two-factor sign-in
   (an authenticator app, and recovery codes for when the phone isn't there) and where you're signed in.
   (Inviting people and looking after accounts is the admin panel's: /admin, admin.js.) */
import { api, PW_RULE, codeFields, wireCode } from "./auth.js";

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const when = t => t ? new Date(t * 1000).toLocaleString("en-CA", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "never";
const day = t => t ? new Date(t * 1000).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" }) : "";

// A short name for a browser, from its user agent.
function device(ua) {
  ua = String(ua || "");
  const b = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "A browser";
  const os = /iPhone|iPad/.test(ua) ? "iPhone or iPad" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${b} on ${os}` : b;
}

function form(m, onSubmit) {
  const f = m.querySelector("form"), err = m.querySelector(".lt-err"), go = m.querySelector("[type=submit]");
  f.onsubmit = async e => {
    e.preventDefault(); err.textContent = ""; go.disabled = true;
    try { await onSubmit(); } catch (x) { err.textContent = x.message; } finally { go.disabled = false; }
  };
}

function download(name, text) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  a.download = name; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

function showCodes(ctx, codes, close) {
  const text = `Lectern recovery codes for ${ctx.S.user.email}\nEach works once, in place of a code from your authenticator app.\n\n${codes.join("\n")}\n`;
  return `<h2>Your recovery codes</h2>
    <p>If your phone isn't there, each of these signs you in once instead of a code. Keep them somewhere safe (a password manager, or printed). <b>They aren't shown again.</b></p>
    <ol class="lt-codes">${codes.map(c => `<li><code>${esc(c)}</code></li>`).join("")}</ol>
    <div class="lt-modal-acts" style="justify-content:flex-start"><button type="button" class="lt-btn" data-copy>Copy</button><button type="button" class="lt-btn" data-dl>Download</button></div>
    <label class="lt-check"><input type="checkbox" data-saved> I've saved them</label>
    <div class="lt-modal-acts"><button type="button" class="lt-btn primary" data-done disabled>Done</button></div>`;
}
function wireCodes(ctx, m, codes, close) {
  const text = `Lectern recovery codes for ${ctx.S.user.email}\nEach works once, in place of a code from your authenticator app.\n\n${codes.join("\n")}\n`;
  m.querySelector("[data-copy]").onclick = async () => { try { await navigator.clipboard.writeText(text); ctx.toast("Copied."); } catch (_) { ctx.toast("Couldn't copy: use Download."); } };
  m.querySelector("[data-dl]").onclick = () => download("lectern-recovery-codes.txt", text);
  m.querySelector("[data-saved]").onchange = e => { m.querySelector("[data-done]").disabled = !e.target.checked; };
  m.querySelector("[data-done]").onclick = close;
}

// ── #/account ────────────────────────────────────────────────────────
export async function accountPage(ctx) {
  const { S, pageHTML, modal, toast } = ctx;
  const u = S.user;
  pageHTML(`<div class="lt-in lt-account">
    <h1>Your Account</h1>
    <p class="lt-lede">Signed in as <b>${esc(u.email)}</b>.</p>

    <div class="lt-sec"><h2>Profile</h2></div>
    <section class="lt-panel">
      <form id="ac-prof" class="lt-form lt-narrow" novalidate>
        <label>Name<input type="text" id="ac-name" value="${esc(u.name)}" autocomplete="name"></label>
        <label>Email<input type="email" value="${esc(u.email)}" readonly><small>To change it, ask your Lectern admin.</small></label>
        <div><button type="submit" class="lt-btn">Save name</button></div>
      </form>
      <p class="lt-row-text">Your course pages are published at <a href="${esc(u.site)}" target="_blank" rel="noopener"><code>${esc(u.site)}</code></a>, e.g. <code>${esc(u.site)}csc258/f26/info.html</code>.</p>
    </section>

    <div class="lt-sec"><h2>Password</h2></div>
    <section class="lt-panel lt-row">
      <p class="lt-row-text">Last changed ${esc(day(u.passwordChanged))}. Changing it signs you out everywhere else.</p>
      <button type="button" class="lt-btn" id="ac-pw">Change password</button>
    </section>

    <div class="lt-sec"><h2>Two-Factor Sign-In</h2></div>
    <section class="lt-panel lt-row">
      ${u.twoFactor
        ? `<p class="lt-row-text"><span class="lt-on">On</span> Signing in needs your password and a code from your authenticator app. <b>${u.recoveryLeft}</b> recovery code${u.recoveryLeft === 1 ? "" : "s"} left${u.recoveryLeft <= 3 ? ": make new ones soon" : ""}.</p>
           <span class="lt-row-acts"><button type="button" class="lt-btn" id="ac-rec">New recovery codes</button><button type="button" class="lt-btn" id="ac-off">Turn off</button></span>`
        : `<p class="lt-row-text"><span class="lt-off">Off</span> Add a code from an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password…) to signing in, so a stolen password isn't enough. Recommended: Lectern holds students' grades.</p>
           <button type="button" class="lt-btn primary" id="ac-on">Turn on</button>`}
    </section>

    <div class="lt-sec"><h2>Where You're Signed In</h2><button type="button" class="lt-btn" id="ac-others" hidden>Sign out everywhere else</button></div>
    <div id="ac-sessions"><div class="lt-loading" style="min-height:80px">Loading…</div></div>
  </div>`);

  const again = user => { if (user) ctx.setUser(user); accountPage(ctx); };
  const $ = s => document.querySelector(s);

  $("#ac-prof").onsubmit = async e => {
    e.preventDefault();
    try { again((await api("/api/auth/profile", { name: $("#ac-name").value })).user); toast("Saved."); } catch (x) { toast(x.message); }
  };

  $("#ac-pw").onclick = () => modal(`<h2>Change password</h2>
    <form novalidate><div class="lt-form">
      <input type="email" autocomplete="username" value="${esc(u.email)}" hidden readonly>
      <label>Current password<input type="password" id="cp-cur" autocomplete="current-password"></label>
      <label>New password<input type="password" id="cp-new" autocomplete="new-password"><small>${PW_RULE}</small></label>
      <label>New password, again<input type="password" id="cp-new2" autocomplete="new-password"></label>
    </div><p class="lt-err"></p>
    <div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn primary">Change password</button></div></form>`, (m, close) => {
    m.querySelector("[data-no]").onclick = close;
    form(m, async () => {
      if (m.querySelector("#cp-new").value !== m.querySelector("#cp-new2").value) throw new Error("The two new passwords aren't the same.");
      const d = await api("/api/auth/password", { current: m.querySelector("#cp-cur").value, password: m.querySelector("#cp-new").value });
      close(); toast("Password changed. Other devices are signed out."); again(d.user);
    });
  });

  const on = $("#ac-on");
  if (on) on.onclick = () => modal(`<h2>Turn on two-factor sign-in</h2>
    <form novalidate><p>First, your password.</p><div class="lt-form">
      <input type="email" autocomplete="username" value="${esc(u.email)}" hidden readonly>
      <label>Password<input type="password" id="tf-pw" autocomplete="current-password"></label></div>
    <p class="lt-err"></p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn primary">Continue</button></div></form>`, (m, close) => {
    m.querySelector("[data-no]").onclick = close;
    form(m, async () => {
      const s = await api("/api/auth/2fa/setup", { password: m.querySelector("#tf-pw").value });
      m.innerHTML = `<h2>Scan this with your app</h2>
        <p>In your authenticator app, add an account and scan the code. Or type in the key.</p>
        <div class="lt-qr">${s.qr}</div>
        <p class="lt-key">Key: <code>${esc(s.secret)}</code></p>
        <form novalidate><div class="lt-form"><label>Then enter the 6-digit code it shows<input type="text" id="tf-code" inputmode="numeric" autocomplete="one-time-code" maxlength="7" placeholder="123456"></label></div>
        <p class="lt-err"></p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn primary">Turn on</button></div></form>`;
      m.querySelector("[data-no]").onclick = close;
      m.querySelector("#tf-code").focus();
      form(m, async () => {
        const d = await api("/api/auth/2fa/enable", { code: m.querySelector("#tf-code").value.replace(/\s+/g, "") });
        ctx.setUser(d.user);
        m.innerHTML = showCodes(ctx, d.codes);
        wireCodes(ctx, m, d.codes, () => { close(); toast("Two-factor sign-in is on."); again(); });
      });
    });
  }, { sticky: true });

  const rec = $("#ac-rec");
  if (rec) rec.onclick = () => modal(`<h2>New recovery codes</h2>
    <form novalidate><p>This replaces your old recovery codes: they stop working.</p><div class="lt-form">
      <input type="email" autocomplete="username" value="${esc(u.email)}" hidden readonly>
      <label>Password<input type="password" id="rc-pw" autocomplete="current-password"></label>
      ${codeFields("rc", true)}</div>
    <p class="lt-err"></p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn primary">Make new codes</button></div></form>`, (m, close) => {
    m.querySelector("[data-no]").onclick = close;
    const get = wireCode(m, "rc");
    form(m, async () => {
      const d = await api("/api/auth/recovery", { password: m.querySelector("#rc-pw").value, ...get() });
      ctx.setUser(d.user);
      m.innerHTML = showCodes(ctx, d.codes);
      wireCodes(ctx, m, d.codes, () => { close(); again(); });
    });
  }, { sticky: true });

  const off = $("#ac-off");
  if (off) off.onclick = () => modal(`<h2>Turn off two-factor sign-in?</h2>
    <form novalidate><p>Then your password alone signs you in.</p><div class="lt-form">
      <input type="email" autocomplete="username" value="${esc(u.email)}" hidden readonly>
      <label>Password<input type="password" id="to-pw" autocomplete="current-password"></label>
      ${codeFields("to", true)}</div>
    <p class="lt-err"></p><div class="lt-modal-acts"><button type="button" class="lt-btn" data-no>Cancel</button><button type="submit" class="lt-btn lt-btn-danger">Turn off</button></div></form>`, (m, close) => {
    m.querySelector("[data-no]").onclick = close;
    const get = wireCode(m, "to");
    form(m, async () => {
      const d = await api("/api/auth/2fa/disable", { password: m.querySelector("#to-pw").value, ...get() });
      close(); toast("Two-factor sign-in is off."); again(d.user);
    });
  });

  // Sessions
  let list;
  try { list = (await api("/api/auth/sessions")).sessions; }
  catch (x) { const el = $("#ac-sessions"); if (el) el.innerHTML = `<p class="lt-note err">${esc(x.message)}</p>`; return; }
  const box = $("#ac-sessions"); if (!box) return;
  box.innerHTML = `<div class="lt-olist">${list.map(s => `<div class="lt-orow lt-sess">
      <b>${esc(device(s.agent))}</b><span class="lt-orow-n">${esc(s.ip)} · signed in ${esc(when(s.created))} · last active ${esc(when(s.lastSeen))}</span>
      <span class="lt-orow-r">${s.current ? `<span class="lt-on">This one</span>` : `<button type="button" class="lt-link" data-out="${esc(s.id)}">Sign out</button>`}</span></div>`).join("")}</div>`;
  const others = $("#ac-others");
  others.hidden = list.length < 2;
  others.onclick = async () => { await api("/api/auth/sessions/revoke", { id: "others" }); toast("Signed out everywhere else."); accountPage(ctx); };
  box.querySelectorAll("[data-out]").forEach(b => { b.onclick = async () => { await api("/api/auth/sessions/revoke", { id: b.dataset.out }); accountPage(ctx); }; });
}
