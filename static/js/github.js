/* Sign in with GitHub (a GitHub App's user login) and the few GitHub calls
   Lectern itself makes: who you are, which repositories it can use, the files
   in them, and creating the public repository. The builders make their own
   calls with the same token. Tokens stay in this browser; only the sign-in
   code and refreshes pass through Lectern's server. */

const KEY = "lectern.github";          // { access_token, refresh_token, expires_at, refresh_expires_at }
const STATE = "lectern.state";
// Sign-ins last only as long as this tab (sessionStorage); "stay signed in" is off for now.

let tok = null;
const listeners = new Set();

export class GhError extends Error { constructor(status, msg) { super(msg); this.status = status; } }

function read() {
  try {
    localStorage.removeItem(KEY);          // drop a sign-in kept by an older version
    tok = JSON.parse(sessionStorage.getItem(KEY) || "null");
  } catch (_) { tok = null; }
}
function write() {
  try {
    localStorage.removeItem(KEY); sessionStorage.removeItem(KEY);
    if (tok) sessionStorage.setItem(KEY, JSON.stringify(tok));
  } catch (_) {}
}
function fromResponse(d) {
  const now = Date.now();
  return {
    access_token: d.access_token,
    refresh_token: d.refresh_token || (tok && tok.refresh_token) || "",
    expires_at: d.expires_in ? now + Number(d.expires_in) * 1000 : 0,                       // 0: doesn't expire
    refresh_expires_at: d.refresh_token_expires_in ? now + Number(d.refresh_token_expires_in) * 1000 : 0,
  };
}

export const token = () => (tok ? tok.access_token : "");
export const hasToken = () => { if (!tok) read(); return !!(tok && tok.access_token); };
export const onToken = fn => { listeners.add(fn); return () => listeners.delete(fn); };

/** The sign-in coming back from GitHub: tokens (or an error) in the URL's #fragment. */
export function consumeRedirect() {
  const h = location.hash.slice(1);
  if (!/(^|&)gh_/.test(h)) return null;
  const p = new URLSearchParams(h);
  history.replaceState(null, "", location.pathname + location.search + "#/");
  let expected = "";
  try { expected = sessionStorage.getItem(STATE) || ""; sessionStorage.removeItem(STATE); } catch (_) {}
  if (!expected || p.get("state") !== expected) return { error: "That sign-in didn't start here. Please try again." };
  if (p.get("gh_error")) return { error: p.get("gh_error") };
  tok = fromResponse({
    access_token: p.get("gh_access_token"), refresh_token: p.get("gh_refresh_token"),
    expires_in: p.get("gh_expires_in"), refresh_token_expires_in: p.get("gh_refresh_token_expires_in"),
  });
  write();
  return { ok: true };
}

/** Off to GitHub to sign in; it comes back to /api/github/callback, then here. */
export async function startSignIn() {
  let cfg;
  try { cfg = await (await fetch("/api/github/config")).json(); }
  catch (_) { throw new GhError(0, "Couldn't reach Lectern's server."); }
  if (!cfg.configured) throw new GhError(0, "Sign-in with GitHub isn't set up on this server yet (see the README: LECTERN_GH_CLIENT_ID and LECTERN_GH_CLIENT_SECRET).");
  const state = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, "0")).join("");
  try { sessionStorage.setItem(STATE, state); } catch (_) {}
  // prompt=select_account: GitHub always shows its account picker (with "Use a different account"),
  // instead of quietly reusing whoever is signed in to github.com in this browser.
  const q = new URLSearchParams({ client_id: cfg.client_id, redirect_uri: cfg.redirect_uri, state, prompt: "select_account" });
  location.assign(`${cfg.authorize_url}?${q}`);
}

export function signOut() {
  tok = null; write();
  try { sessionStorage.removeItem(STATE); } catch (_) {}
}

// Sign-ins last 8 hours: swap the refresh token for a new one a little before then.
let refreshing = null, timer = 0;
async function refresh() {
  if (!tok || !tok.refresh_token) throw new GhError(401, "Your GitHub sign-in has ended. Please sign in again.");
  if (!refreshing) refreshing = (async () => {
    let res, data = {};
    try { res = await fetch("/api/github/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: tok.refresh_token }) }); data = await res.json(); }
    catch (_) { throw new GhError(0, "Couldn't reach Lectern's server to renew your sign-in."); }
    if (!res.ok || !data.access_token) {
      if (res.status === 401) { signOut(); throw new GhError(401, data.error || "Your GitHub sign-in has ended. Please sign in again."); }
      throw new GhError(res.status, data.error || "Couldn't renew your GitHub sign-in.");
    }
    tok = fromResponse(data); write(); schedule();
    listeners.forEach(fn => { try { fn(tok.access_token); } catch (e) { console.error(e); } });
  })().finally(() => { refreshing = null; });
  return refreshing;
}
export function schedule() {
  clearTimeout(timer);
  if (!tok || !tok.expires_at) return;
  const wait = tok.expires_at - Date.now() - 10 * 60 * 1000;         // ten minutes early
  timer = setTimeout(() => refresh().catch(e => console.warn("[Lectern] refresh:", e.message)), Math.max(wait, 5000));
}
async function fresh() {
  if (!tok) read();
  if (!tok) throw new GhError(401, "Please sign in with GitHub.");
  if (tok.expires_at && tok.expires_at - Date.now() < 2 * 60 * 1000) await refresh();
}
// A computer that slept through the timer catches up when it wakes.
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && tok && tok.expires_at) fresh().catch(() => {}); });

export async function api(path, opts = {}, retried = false) {
  await fresh();
  let res;
  try {
    res = await fetch(`https://api.github.com${path}`, {
      ...opts,
      headers: { Accept: "application/vnd.github+json", Authorization: `Bearer ${tok.access_token}`, "X-GitHub-Api-Version": "2022-11-28", ...(opts.body ? { "Content-Type": "application/json" } : {}) },
    });
  } catch (_) { throw new GhError(0, "Couldn't reach GitHub. Check your internet connection."); }
  if (res.status === 401 && !retried && tok.refresh_token) { await refresh(); return api(path, opts, true); }
  if (res.ok) return res.status === 204 ? null : res.json();
  let detail = ""; try { detail = (await res.json()).message || ""; } catch (_) {}
  const msg = {
    401: "GitHub didn't accept the sign-in. Please sign in again.",
    403: /rate limit/i.test(detail) ? "GitHub's rate limit was reached. Wait a few minutes and try again." : `GitHub refused this: ${detail || "Lectern doesn't have permission"}.`,
    404: "Not found on GitHub (or Lectern isn't allowed to see it).",
  }[res.status] || `GitHub said: ${detail || res.status}`;
  throw new GhError(res.status, msg);
}

export const user = () => api("/user");
export const repo = name => api(`/repos/${name}`);

/** Every repository the Lectern app was given, across the installations you can use. */
export async function repos() {
  const inst = await api("/user/installations?per_page=100");
  const out = [];
  for (const i of inst.installations || []) {
    for (let page = 1; page < 20; page++) {
      const r = await api(`/user/installations/${i.id}/repositories?per_page=100&page=${page}`);
      out.push(...r.repositories);
      if (r.repositories.length < 100) break;
    }
  }
  const seen = new Set();
  return { installations: inst.installations || [], repos: out.filter(r => !seen.has(r.full_name) && seen.add(r.full_name)) };
}

/** All files and folders in a repository (an empty repository has none). */
export async function tree(name, branch) {
  try { return (await api(`/repos/${name}/git/trees/${encodeURIComponent(branch)}?recursive=1`)).tree; }
  catch (e) { if (e.status === 409) return []; throw e; }    // 409: the repository has no commits yet
}

/** Create the public repository for course pages and turn on GitHub Pages. */
export async function createPublic(owner, name, login) {
  const body = JSON.stringify({ name, private: false, auto_init: true, has_issues: false, has_wiki: false, has_projects: false,
    description: "Course pages and their files, published with GitHub Pages (made with Lectern)." });
  const r = owner.toLowerCase() === String(login).toLowerCase()
    ? await api("/user/repos", { method: "POST", body })
    : await api(`/orgs/${encodeURIComponent(owner)}/repos`, { method: "POST", body });
  let pagesError = null;
  for (let k = 0; k < 4; k++) {            // the first commit can take a moment to land
    try {
      await api(`/repos/${r.full_name}/pages`, { method: "POST", body: JSON.stringify({ build_type: "legacy", source: { branch: r.default_branch || "main", path: "/" } }) });
      pagesError = null; break;
    } catch (e) {
      pagesError = e;
      if (e.status === 409) { pagesError = null; break; }   // already on
      await new Promise(res => setTimeout(res, 1500));
    }
  }
  return { repo: r, pagesError };
}

/** A file's text (UTF-8), or null when it isn't there. */
export async function readText(name, branch, path) {
  try {
    const f = await api(`/repos/${name}/contents/${path.split("/").map(encodeURIComponent).join("/")}?ref=${encodeURIComponent(branch)}`);
    return new TextDecoder().decode(Uint8Array.from(atob(String(f.content).replace(/\s/g, "")), c => c.charCodeAt(0)));
  } catch (e) { if (e.status === 404) return null; throw e; }
}

/** Delete every file under a folder, in one commit. Returns how many files went. */
export async function deleteFolder(name, branch, folder, message) {
  const head = (await api(`/repos/${name}/git/ref/heads/${encodeURIComponent(branch)}`)).object.sha;
  const base = (await api(`/repos/${name}/git/commits/${head}`)).tree.sha;
  let all;
  try { all = (await api(`/repos/${name}/git/trees/${base}?recursive=1`)).tree; } catch (e) { if (e.status === 409) return 0; throw e; }
  const gone = all.filter(x => x.type === "blob" && x.path.startsWith(`${folder}/`));
  if (!gone.length) return 0;
  const tree = await api(`/repos/${name}/git/trees`, { method: "POST", body: JSON.stringify({ base_tree: base, tree: gone.map(x => ({ path: x.path, mode: x.mode || "100644", type: "blob", sha: null })) }) });
  const commit = await api(`/repos/${name}/git/commits`, { method: "POST", body: JSON.stringify({ message, tree: tree.sha, parents: [head] }) });
  await api(`/repos/${name}/git/refs/heads/${encodeURIComponent(branch)}`, { method: "PATCH", body: JSON.stringify({ sha: commit.sha }) });
  return gone.length;
}

/** Create the private repository for grades and exams. */
export async function createPrivate(owner, name, login) {
  const body = JSON.stringify({ name, private: true, auto_init: true, has_issues: false, has_wiki: false, has_projects: false,
    description: "Grades and exams (made with Lectern). Private." });
  return owner.toLowerCase() === String(login).toLowerCase()
    ? api("/user/repos", { method: "POST", body })
    : api(`/orgs/${encodeURIComponent(owner)}/repos`, { method: "POST", body });
}

/** The GitHub Pages address a repository publishes to. */
export function siteFor(full) {
  const [owner, name] = full.split("/"), host = `${owner.toLowerCase()}.github.io`;
  return name.toLowerCase() === host ? `https://${host}/` : `https://${host}/${name}/`;
}
