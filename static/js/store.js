/* Your files on Lectern's server: the few calls the shell makes itself (the builders make their own,
   GitHub-style, which scope.js sends to the same place). Two areas, as there were two repositories:
   "pub" (course pages and their files, published) and "priv" (grades, exams, accommodation requests). */
import { api } from "./auth.js";

export const PUB = "pub", PRIV = "priv";
/** The names the builders know them by: "lectern/pub" and "lectern/priv" (scope.js routes these here). */
export const repoName = r => `lectern/${r}`;

const call = (repo, rest, body, method) => api(`/api/store/${repo}${rest}`, body, { method });

/** Every file and folder (GitHub's tree entries). */
export async function tree(repo) { return (await call(repo, "/git/trees/main?recursive=1")).tree; }

/** A file's text (UTF-8), or null when it isn't there. */
export async function readText(repo, path) {
  try {
    const f = await call(repo, `/contents/${path.split("/").map(encodeURIComponent).join("/")}?ref=main`);
    return new TextDecoder().decode(Uint8Array.from(atob(String(f.content).replace(/\s/g, "")), c => c.charCodeAt(0)));
  } catch (e) { if (e.status === 404) return null; throw e; }
}

/** A text file and its version (sha), or null when it isn't there. */
export async function readFile(repo, path) {
  try {
    const f = await call(repo, `/contents/${path.split("/").map(encodeURIComponent).join("/")}?ref=main`);
    return { text: new TextDecoder().decode(Uint8Array.from(atob(String(f.content).replace(/\s/g, "")), c => c.charCodeAt(0))), sha: f.sha };
  } catch (e) { if (e.status === 404) return null; throw e; }
}

/** Save a text file, in one save. With sha (the version read; null: it wasn't there), refuses (err.conflict)
 *  when it changed since. → its new version. */
export async function writeText(repo, path, text, message, sha) {
  const head = (await call(repo, "/git/ref/heads/main")).object.sha;
  if (sha !== undefined) {
    const now = await readFile(repo, path);
    if ((now ? now.sha : null) !== sha) { const e = new Error(`${path} was changed somewhere else since it was opened.`); e.conflict = true; throw e; }
  }
  const bytes = new TextEncoder().encode(text);
  let bin = ""; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  const blob = await call(repo, "/git/blobs", { content: btoa(bin), encoding: "base64" });
  const t = await call(repo, "/git/trees", { base_tree: head, tree: [{ path, mode: "100644", type: "blob", sha: blob.sha }] });
  const c = await call(repo, "/git/commits", { message, tree: t.sha, parents: [head] });
  await call(repo, "/git/refs/heads/main", { sha: c.sha }, "PATCH");
  return blob.sha;
}

/** Put one file (a File from the computer) at path, in one save. */
export async function upload(repo, path, file, message) {
  const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1] || ""); r.onerror = () => rej(new Error(`Couldn't read ${file.name}.`)); r.readAsDataURL(file); });
  const head = (await call(repo, "/git/ref/heads/main")).object.sha;
  const blob = await call(repo, "/git/blobs", { content: b64, encoding: "base64" });
  const t = await call(repo, "/git/trees", { base_tree: head, tree: [{ path, mode: "100644", type: "blob", sha: blob.sha }] });
  const c = await call(repo, "/git/commits", { message, tree: t.sha, parents: [head] });
  await call(repo, "/git/refs/heads/main", { sha: c.sha }, "PATCH");
}

/** Delete every file under a folder, in one save. Returns how many files went. (Kept in the server's history.) */
export async function deleteFolder(repo, folder, message) {
  const head = (await call(repo, "/git/ref/heads/main")).object.sha;
  const gone = (await tree(repo)).filter(x => x.type === "blob" && x.path.startsWith(`${folder}/`));
  if (!gone.length) return 0;
  const t = await call(repo, "/git/trees", { base_tree: head, tree: gone.map(x => ({ path: x.path, mode: "100644", type: "blob", sha: null })) });
  const c = await call(repo, "/git/commits", { message, tree: t.sha, parents: [head] });
  await call(repo, "/git/refs/heads/main", { sha: c.sha }, "PATCH");
  return gone.length;
}
