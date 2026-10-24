/* A course page's sign-in (templates/hub-signin.html): email, then the emailed code (server/students.py). */
(() => {
"use strict";
const $ = id => document.getElementById(id), root = $("si"), api = root.dataset.api;
const post = async (what, data) => {
  const r = await fetch(`${api}/${what}`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Lectern": "1" }, body: JSON.stringify(data) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Something went wrong. Try again.");
  return j;
};
let email = "";
const busy = (form, on, label) => { const b = form.querySelector("button[type=submit]"); b.disabled = on; if (label) b.textContent = label; };
$("si-email").onsubmit = async e => {
  e.preventDefault();
  email = $("si-e").value.trim(); $("si-err1").textContent = "";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { $("si-err1").textContent = "Enter your email address."; return; }
  busy($("si-email"), true, "Sending…");
  try {
    await post("code", { email });
    $("si-who").textContent = email; $("si-email").hidden = true; $("si-code").hidden = false; $("si-c").value = ""; $("si-c").focus();
  } catch (x) { $("si-err1").textContent = x.message; }
  busy($("si-email"), false, "Email Me a Code");
};
$("si-code").onsubmit = async e => {
  e.preventDefault();
  $("si-err2").textContent = "";
  const code = $("si-c").value.replace(/\D/g, "");
  if (code.length !== 6) { $("si-err2").textContent = "The code has 6 digits."; return; }
  busy($("si-code"), true, "Signing in…");
  try { const r = await post("verify", { email, code }); location.href = r.back || root.dataset.back; }
  catch (x) { $("si-err2").textContent = x.message; busy($("si-code"), false, "Sign In"); }
};
$("si-again").onclick = () => { $("si-code").hidden = true; $("si-email").hidden = false; $("si-e").focus(); };
})();
