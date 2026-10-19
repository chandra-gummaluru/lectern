/* Folder mode: a folder on this computer that holds both repositories side by
   side (e.g. courses/ and courses-private/, usually your git clones). The
   browser remembers the folder (a handle, not the files) in IndexedDB and
   asks your OK again after a restart. Chrome and Edge only. */

export const supported = typeof window.showDirectoryPicker === "function";

function idb(op, val) {
  return new Promise(res => {
    try {
      const r = indexedDB.open("lectern", 1);
      r.onupgradeneeded = () => r.result.createObjectStore("kv");
      r.onerror = () => res(null);
      r.onsuccess = () => {
        try {
          const st = r.result.transaction("kv", op === "get" ? "readonly" : "readwrite").objectStore("kv");
          const q = op === "put" ? st.put(val, "parent") : op === "del" ? st.delete("parent") : st.get("parent");
          q.onsuccess = () => res(q.result || null); q.onerror = () => res(null);
        } catch (_) { res(null); }
      };
    } catch (_) { res(null); }
  });
}

export async function choose() {
  try { return await window.showDirectoryPicker({ id: "lectern", mode: "readwrite" }); }
  catch (e) { if (e && e.name === "AbortError") return null; throw new Error("Couldn't open that folder. Try choosing it again."); }
}
/** The folder used last time: { handle, granted } or null. */
export async function remembered() {
  const h = await idb("get");
  if (!h) return null;
  let granted = false;
  try { granted = (await h.queryPermission({ mode: "readwrite" })) === "granted"; } catch (_) {}
  return { handle: h, granted };
}
export async function reconnect(h) {
  try { return (await h.requestPermission({ mode: "readwrite" })) === "granted"; } catch (_) { return false; }
}
export const forget = () => idb("del");

/** The repository pairs in a folder: every X (public) with an X-private (private) beside it. */
export async function pairs(parent) {
  const dirs = new Set();
  for await (const [n, h] of parent.entries()) if (h.kind === "directory" && !n.startsWith(".")) dirs.add(n);
  return [...dirs].filter(n => dirs.has(`${n}-private`)).sort().map(n => ({ priv: `${n}-private`, pub: n }));
}

/** Use one pair: handles for both repositories, and where the public one publishes. */
export async function open(parent, pair) {
  const priv = await parent.getDirectoryHandle(pair.priv), pub = await parent.getDirectoryHandle(pair.pub);
  let site = "";
  try {   // .git/config → remote "origin" → its GitHub Pages address
    const cfg = await (await (await (await pub.getDirectoryHandle(".git")).getFileHandle("config")).getFile()).text();
    const m = /\[remote "origin"\][^[]*?url\s*=\s*(\S+)/.exec(cfg);
    const r = m && /(?:github\.com[/:])([\w.-]+)\/([\w.-]+?)(?:\.git)?\/?$/.exec(m[1]);
    if (r) { const host = `${r[1].toLowerCase()}.github.io`; site = r[2].toLowerCase() === host ? `https://${host}/` : `https://${host}/${r[2]}/`; }
  } catch (_) {}
  await idb("put", parent);
  return { parent, priv, pub, site, name: parent.name, pair };
}

async function has(dir, name) { try { await dir.getFileHandle(name); return true; } catch (_) { return false; } }
async function* subdirs(d) { for await (const [n, h] of d.entries()) if (h.kind === "directory" && !n.startsWith(".") && !n.startsWith("_")) yield [n, h]; }

/** Every <course>/<term> in either repository, with what it has. */
export async function list(f, add) {
  for await (const [c, ch] of subdirs(f.pub)) for await (const [t, th] of subdirs(ch)) add(c, t, { page: await has(th, "info.html") });
  for await (const [c, ch] of subdirs(f.priv)) for await (const [t, th] of subdirs(ch)) {
    const exams = [];
    for await (const [e, eh] of subdirs(th)) if (await has(eh, "exam.json")) exams.push(e);
    add(c, t, { grades: await has(th, "grades.json"), exams });
  }
}

/** Delete a course offering's folder (<course>/<term>) from both repositories' folders. */
export async function removeOffering(f, c, t) {
  for (const repo of [f.pub, f.priv]) {
    let cd; try { cd = await repo.getDirectoryHandle(c); } catch (_) { continue; }
    try { await cd.removeEntry(t, { recursive: true }); } catch (e) { if (e.name !== "NotFoundError") throw e; }
    let empty = true; for await (const _ of cd.entries()) { empty = false; break; }
    if (empty) try { await repo.removeEntry(c); } catch (_) {}
  }
}
