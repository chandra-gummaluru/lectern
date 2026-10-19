/* Folder mode for the Grade Builder and the Exam Builder.

   Both builders talk to GitHub through a handful of REST calls (list the files, read one, and save
   with blobs → tree → commit → move the branch). In folder mode Lectern answers those same calls from
   a folder on this computer instead, so the builders work unchanged: reading is reading a file, and
   "moving the branch" writes the commit's files (and removes the ones it deletes). Commit and push
   with git as usual.

   makeLocalGitHub(dir, fullName) → an async fetch(url, options) for https://api.github.com/repos/<fullName>/…
*/

const enc = new TextEncoder();
async function sha1(bytes) {
  const h = await crypto.subtle.digest("SHA-1", bytes);
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("");
}
function toB64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
const fromB64 = s => Uint8Array.from(atob(String(s).replace(/\s/g, "")), c => c.charCodeAt(0));
const reply = (status, data) => new Response(data == null ? null : JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
const notFound = () => reply(404, { message: "Not Found" });

export function makeLocalGitHub(dir, fullName) {
  const blobs = new Map();     // sha → bytes, from POST blobs
  const trees = new Map();     // tree sha → entries
  const commits = new Map();   // commit sha → tree sha
  let n = 0;

  async function handleAt(path, create) {
    const parts = path.split("/").filter(Boolean), name = parts.pop();
    let d = dir;
    for (const p of parts) d = await d.getDirectoryHandle(p, { create });
    return { d, name };
  }
  async function readFile(path) {
    try { const { d, name } = await handleAt(path, false); return await (await d.getFileHandle(name)).getFile(); }
    catch (_) { return null; }
  }
  async function writeFile(path, bytes) {
    const { d, name } = await handleAt(path, true);
    const w = await (await d.getFileHandle(name, { create: true })).createWritable();
    await w.write(bytes); await w.close();
  }
  async function removeFile(path) {
    try { const { d, name } = await handleAt(path, false); await d.removeEntry(name); } catch (_) {}
  }
  async function walk(d, prefix, out) {
    for await (const [name, h] of d.entries()) {
      if (name.startsWith(".")) continue;
      const p = prefix ? `${prefix}/${name}` : name;
      if (h.kind === "directory") { out.push({ path: p, type: "tree", mode: "040000" }); await walk(h, p, out); }
      else out.push({ path: p, type: "blob", mode: "100644", sha: `path:${p}` });   // read when a commit uses it
    }
    return out;
  }

  return async function localFetch(url, opts = {}) {
    const u = new URL(url), method = (opts.method || "GET").toUpperCase();
    const pre = `/repos/${fullName}`;
    if (!u.pathname.startsWith(pre)) return notFound();
    const rest = decodeURIComponent(u.pathname.slice(pre.length));
    const body = opts.body ? JSON.parse(opts.body) : null;

    if (rest === "" || rest === "/") return reply(200, { full_name: fullName, name: fullName.split("/")[1], private: true, default_branch: "main" });
    if (rest.startsWith("/branches/")) return reply(200, { name: "main", commit: { sha: "local" } });
    if (rest.startsWith("/git/ref/heads/") || (rest.startsWith("/git/refs/heads/") && method === "GET")) return reply(200, { object: { sha: "local" } });
    if (rest.startsWith("/git/commits/") && method === "GET") {
      const sha = rest.split("/").pop();
      return reply(200, { sha, tree: { sha: commits.get(sha) || "local" } });
    }
    if (rest.startsWith("/git/trees/") && method === "GET") return reply(200, { sha: "local", tree: await walk(dir, "", []), truncated: false });
    if (rest.startsWith("/contents/") && method === "GET") {
      const path = rest.slice("/contents/".length), f = await readFile(path);
      if (!f) return notFound();
      const bytes = new Uint8Array(await f.arrayBuffer());
      return reply(200, { path, name: f.name, size: f.size, sha: await sha1(bytes), encoding: "base64", content: toB64(bytes) });
    }
    if (rest === "/commits" && method === "GET") {
      const f = await readFile(u.searchParams.get("path") || "");
      return reply(200, f ? [{ sha: "local", commit: { committer: { date: new Date(f.lastModified).toISOString() } } }] : []);
    }
    if (rest === "/git/blobs" && method === "POST") {
      const bytes = body.encoding === "base64" ? fromB64(body.content) : enc.encode(body.content);
      const sha = await sha1(bytes);
      blobs.set(sha, bytes);
      return reply(201, { sha });
    }
    if (rest === "/git/trees" && method === "POST") {
      const sha = `tree-${++n}`;
      trees.set(sha, body.tree || []);
      return reply(201, { sha });
    }
    if (rest === "/git/commits" && method === "POST") {
      const sha = `commit-${++n}`;
      commits.set(sha, body.tree);
      return reply(201, { sha, html_url: "" });
    }
    if (rest.startsWith("/git/refs/heads/") && method === "PATCH") {
      // "Move the branch": write the commit's files into the folder, and remove the ones it deletes.
      const entries = trees.get(commits.get(body.sha)) || [];
      for (const e of entries) {
        if (e.sha == null && e.content == null) { await removeFile(e.path); continue; }
        let bytes = e.content != null ? enc.encode(e.content) : blobs.get(e.sha);
        if (!bytes && String(e.sha).startsWith("path:")) { const f = await readFile(e.sha.slice(5)); if (f) bytes = new Uint8Array(await f.arrayBuffer()); }
        if (bytes) await writeFile(e.path, bytes);
      }
      blobs.clear();
      return reply(200, { object: { sha: body.sha } });
    }
    return reply(404, { message: `Not available in folder mode: ${method} ${rest}` });
  };
}
