/* ============================================================
   Lectern: the three builders on one page, each in its own scope.

   A builder arrives from the server in three parts (see server/tools.py):
   its markup, its CSS (every rule already scoped to [data-lt-tool="name"])
   and its script, wrapped as

       Lectern.define("grades", function (document, window, fetch) { …the builder… });

   Inside that function `document` and `window` are stand-ins that keep the
   builder to its own element:

   - document.getElementById / querySelector(All) look only inside the tool's
     element, so the three can all have #stage, #home, #save, #modal-root…
   - document.body and document.documentElement are the tool's element, so
     body classes, menus appended to the body and --tbh land in its scope.
   - listeners on document and window only hear events while that builder is
     the one showing (except beforeunload, so unsaved work is always guarded).
   - document.title is kept per builder instead of renaming the tab.
   - fetch goes to the network, except calls to GitHub for a repository Lectern serves from a folder
     on this computer (Lectern.local; see localgh.js), which never leave the browser.

   Everything else (createElement, activeElement, scrollTo, fetch…) is the
   real thing. The builder's own variables already live in its IIFE.
   ============================================================ */
(() => {
"use strict";

const realDoc = document, realWin = window;
const tools = {};                        // name → { name, root, doc, win, api, ready, title }
let active = null;                       // the builder that's showing, or null for Lectern's own pages
const ALWAYS = new Set(["beforeunload", "unload", "pagehide"]);
const styleOnce = new Map(), scriptOnce = new Map();
const lower = p => typeof p === "string" && /^[a-z]/.test(p);   // methods, not constructors (URL, Image…)

// The same wrapper every time for the same handler and event, so removeEventListener finds it.
const wraps = new WeakMap();
function gated(name, type, h) {
  if (!h || (typeof h !== "function" && typeof h.handleEvent !== "function")) return h;
  let m = wraps.get(h);
  if (!m) wraps.set(h, m = new Map());
  const key = `${name}:${type}`;
  if (!m.has(key)) m.set(key, function (e) {
    if (active !== name && !ALWAYS.has(type)) return;
    return typeof h === "function" ? h.call(this, e) : h.handleEvent(e);
  });
  return m.get(key);
}

function forward(target, cache, p) {
  const v = Reflect.get(target, p, target);
  if (typeof v !== "function" || !lower(p)) return v;
  if (!cache.has(p) || cache.get(p).src !== v) { const b = v.bind(target); b.src = v; cache.set(p, b); }
  return cache.get(p);
}

function makeDocument(name, root) {
  const t = tools[name], cache = new Map();
  const own = {
    getElementById: id => root.querySelector(`#${CSS.escape(id)}`),
    querySelector: s => root.querySelector(s),
    querySelectorAll: s => root.querySelectorAll(s),
    getElementsByClassName: c => root.getElementsByClassName(c),
    getElementsByTagName: n => root.getElementsByTagName(n),
    contains: n => root.contains(n),
    addEventListener: (type, h, o) => realDoc.addEventListener(type, gated(name, type, h), o),
    removeEventListener: (type, h, o) => realDoc.removeEventListener(type, gated(name, type, h), o),
  };
  return new Proxy(realDoc, {
    get(target, p) {
      if (p === "body" || p === "documentElement") return root;
      if (p === "title") return t.title || "";
      if (Object.prototype.hasOwnProperty.call(own, p)) return own[p];
      return forward(target, cache, p);
    },
    set(target, p, v) {
      if (p === "title") { t.title = String(v); if (t.onTitle) t.onTitle(t.title); return true; }
      return Reflect.set(target, p, v, target);
    },
  });
}

function makeWindow(name, doc) {
  const cache = new Map();
  const own = {
    document: doc,
    addEventListener(type, h, o) {
      // A builder that waits for "load" was written for a page that is still loading; this one isn't.
      if (type === "load" && realDoc.readyState === "complete") setTimeout(() => (typeof h === "function" ? h : h.handleEvent.bind(h))(new Event("load")), 0);
      return realWin.addEventListener(type, gated(name, type, h), o);
    },
    removeEventListener: (type, h, o) => realWin.removeEventListener(type, gated(name, type, h), o),
  };
  return new Proxy(realWin, {
    get(target, p) {
      if (Object.prototype.hasOwnProperty.call(own, p)) return own[p];
      return forward(target, cache, p);
    },
    set(target, p, v) { return Reflect.set(target, p, v, target); },
  });
}

function addStyle(href) {
  if (!styleOnce.has(href)) styleOnce.set(href, new Promise(res => {
    const l = realDoc.createElement("link");
    l.rel = "stylesheet"; l.href = href;
    l.onload = l.onerror = () => res();       // a missing web font mustn't stop the builder
    realDoc.head.append(l);
  }));
  return styleOnce.get(href);
}
function addScript(src) {
  if (!scriptOnce.has(src)) scriptOnce.set(src, new Promise((res, rej) => {
    const s = realDoc.createElement("script");
    s.src = src;
    s.onload = () => res();
    s.onerror = () => rej(new Error(`Couldn't load ${src}`));
    realDoc.body.append(s);
  }));
  return scriptOnce.get(src);
}

// GitHub calls for a repository kept in a folder are answered from the folder (folder mode).
function scopedFetch(url, opts) {
  const m = /^https:\/\/api\.github\.com\/repos\/([^/]+\/[^/?#]+)/.exec(String(url));
  const local = m && realWin.Lectern.local && realWin.Lectern.local[decodeURIComponent(m[1])];
  return local ? local(String(url), opts) : realWin.fetch(url, opts);
}

const Lectern = realWin.Lectern = {
  local: {},   // "local/<repo>" → a fetch that answers GitHub's API from a folder
  hosting: true,
  tools,
  get active() { return active; },

  // Called by /tools/<name>.js: run the builder inside its scope.
  define(name, fn) {
    const t = tools[name];
    if (!t || !t.root) throw new Error(`Lectern: ${name} arrived before its markup`);
    try { fn.call(undefined, t.doc, t.win, scopedFetch); }
    catch (e) { t.error = e; console.error(`[Lectern] ${name} failed to start`, e); }
  },

  // Called by each builder at the end of its script (its "Lectern" section).
  register(name, api) { if (tools[name]) tools[name].api = api; },

  // Fetch a builder's parts, put its markup in place and start it. The builder
  // is shown (and active) while it starts, so its first layout measures right.
  mount(name, container) {
    if (tools[name] && tools[name].ready) return tools[name].ready;
    const t = tools[name] = { name };
    t.ready = (async () => {
      const res = await fetch(`/tools/${name}.json`);
      if (!res.ok) throw new Error(`Couldn't load the ${name} builder (${res.status}).`);
      const meta = await res.json();
      t.title = meta.title;
      await Promise.all([...meta.styles.map(addStyle), addStyle(`/tools/${name}.css`)]);
      // A library from a CDN that doesn't load (offline, say) mustn't stop the builder: on its own it wouldn't either.
      for (const src of meta.scripts) await addScript(src).catch(e => console.warn(`[Lectern] ${e.message}`));
      const root = t.root = realDoc.createElement("div");
      root.className = "lt-tool";
      root.dataset.ltTool = name;
      root.innerHTML = meta.markup;
      container.append(root);
      t.doc = makeDocument(name, root);
      t.win = makeWindow(name, t.doc);
      const prev = active;
      active = name;
      await addScript(`/tools/${name}.js`);
      if (t.error) throw t.error;
      if (!t.api) throw new Error(`The ${name} builder didn't connect to Lectern.`);
      active = prev;
      return t;
    })();
    t.ready.catch(() => { delete tools[name]; });
    return t.ready;
  },

  // Show one builder (or none) and let only its listeners hear events.
  show(name) {
    active = name || null;
    Object.values(tools).forEach(t => { if (t.root) t.root.hidden = t.name !== active; });
    if (active) realWin.dispatchEvent(new Event("resize"));   // let it re-measure now that it's visible
  },
};
})();
