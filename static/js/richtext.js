/* A rich text box: bold, italic, links and lists, kept as the Markdown the course page reads
   (hub-view.js's markdown: **bold**, *italic*, [text](url), "- " bullets, "1. " numbered, blank line = paragraph).

     richText(host, { value, placeholder, label, disabled, quiet, onChange(markdown) }) → { get, set, el }

   It grows with what's in it; it doesn't have a handle to drag it bigger. quiet: the toolbar shows only
   while it's being typed in (for a box that looks like the page's own text, e.g. a course's description). */

const ICONS = {
  bold: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 5h6a3.5 3.5 0 0 1 0 7H7zM7 12h7a3.5 3.5 0 0 1 0 7H7z"/></svg>',
  italic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M14 5h-4M14 19h-4M15 5l-6 14"/></svg>',
  link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>',
  ul: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1" fill="currentColor"/><circle cx="4.5" cy="12" r="1" fill="currentColor"/><circle cx="4.5" cy="18" r="1" fill="currentColor"/></svg>',
  ol: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M10 6h10M10 12h10M10 18h10"/><path d="M4 4.5h1.5V9M4 9h3M4 14.5c.4-.6 1-.9 1.6-.9.9 0 1.4.6 1.4 1.3 0 1.2-3 2.1-3 3.6h3" stroke-width="1.5"/></svg>',
};
const TOOLS = [["bold", "Bold (Ctrl+B)"], ["italic", "Italic (Ctrl+I)"], ["link", "Link (Ctrl+K)"], ["ul", "Bulleted list"], ["ol", "Numbered list"]];

// Markdown → what the box shows (the course page's own drawing of it).
function toHTML(md) {
  const HV = window.HubView;
  const h = HV && HV.markdown ? HV.markdown(md || "") : "";
  return h.replace(/^<div class="hb-md">/, "").replace(/<\/div>$/, "").replace(/<h5>/g, "<p><b>").replace(/<\/h5>/g, "</b></p>");
}

// What the box has → Markdown.
function inline(node) {
  let s = "";
  node.childNodes.forEach(n => {
    if (n.nodeType === 3) { s += n.nodeValue.replace(/ /g, " ").replace(/\s+/g, " "); return; }
    if (n.nodeType !== 1) return;
    const tag = n.tagName.toLowerCase(), inner = inline(n);
    if (tag === "br") s += "\n";
    else if (tag === "b" || tag === "strong") s += inner.trim() ? `**${inner.trim()}**${/\s$/.test(inner) ? " " : ""}` : inner;
    else if (tag === "i" || tag === "em") s += inner.trim() ? `*${inner.trim()}*${/\s$/.test(inner) ? " " : ""}` : inner;
    else if (tag === "a") { const href = n.getAttribute("href") || ""; s += href && !/^mailto:/.test(href) ? `[${inner.trim() || href}](${href})` : inner; }
    else if (tag === "code") s += `\`${inner}\``;
    else if (["p", "div", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6"].includes(tag)) s += "\n" + blocks(n) + "\n";
    else s += inner;
  });
  return s;
}
function blocks(root) {
  const out = []; let line = "";
  const flush = () => { if (line.trim()) out.push(line.trim().split("\n").map(x => x.trim()).filter(Boolean).join("\n\n")); line = ""; };
  root.childNodes.forEach(n => {
    const tag = n.nodeType === 1 ? n.tagName.toLowerCase() : "";
    if (tag === "ul" || tag === "ol") {
      flush();
      const items = [...n.children].filter(li => li.tagName.toLowerCase() === "li").map((li, k) => `${tag === "ol" ? `${k + 1}.` : "-"} ${inline(li).replace(/\s*\n\s*/g, " ").trim()}`).filter(x => !/^(-|\d+\.)\s*$/.test(x));
      if (items.length) out.push(items.join("\n"));
    } else if (["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"].includes(tag)) {
      flush();
      const b = blocks(n); if (b.trim()) out.push(b.trim());
    } else if (tag === "br") { flush(); }
    else line += n.nodeType === 3 ? n.nodeValue.replace(/ /g, " ") : inline({ childNodes: [n] });
  });
  flush();
  return out.join("\n\n");
}
export const toMarkdown = el => blocks(el).replace(/\n{3,}/g, "\n\n").trim();

export function richText(host, { value = "", placeholder = "", label = "", disabled = false, quiet = false, onChange = () => {} } = {}) {
  host.classList.add("rt"); if (quiet) host.classList.add("quiet"); if (disabled) host.classList.add("off");
  host.innerHTML = `${disabled ? "" : `<div class="rt-bar" role="toolbar" aria-label="Formatting">${TOOLS.map(([k, t]) => `<button type="button" data-rt="${k}" title="${t}" aria-label="${t}" tabindex="-1">${ICONS[k]}</button>`).join("")}</div>
      <div class="rt-link" hidden><input type="url" placeholder="https://…" aria-label="The link's address"><button type="button" data-rt-ok>Add Link</button><button type="button" data-rt-no>Cancel</button></div>`}
    <div class="rt-ed" ${disabled ? "" : 'contenteditable="true"'} role="textbox" aria-multiline="true"${label ? ` aria-label="${label.replace(/"/g, "&quot;")}"` : ""} data-ph="${placeholder.replace(/"/g, "&quot;")}"></div>`;
  const ed = host.querySelector(".rt-ed");
  let last = String(value || "");
  const empty = () => ed.classList.toggle("empty", !ed.textContent.trim() && !ed.querySelector("li"));
  const set = md => { last = String(md || ""); ed.innerHTML = toHTML(last); empty(); };
  set(value);
  if (disabled) return { get: () => last, set, el: ed };

  const changed = () => { empty(); const md = toMarkdown(ed); if (md !== last) { last = md; onChange(md); } };
  const cmd = (c, v = null) => { ed.focus(); document.execCommand(c, false, v); changed(); state(); };
  const state = () => host.querySelectorAll("[data-rt]").forEach(b => {
    const k = b.dataset.rt, q = { bold: "bold", italic: "italic", ul: "insertUnorderedList", ol: "insertOrderedList" }[k];
    let on = false; try { on = q ? document.queryCommandState(q) : !!(sel() && sel().closest("a")); } catch (_) {}
    b.setAttribute("aria-pressed", on && document.activeElement === ed ? "true" : "false");
  });
  const sel = () => { const s = getSelection(); if (!s.rangeCount || !ed.contains(s.anchorNode)) return null; const n = s.anchorNode; return n.nodeType === 1 ? n : n.parentElement; };

  // Links: a little box for the address, under the toolbar.
  const box = host.querySelector(".rt-link"), url = box.querySelector("input");
  let saved = null;
  const openLink = () => {
    const s = getSelection(); saved = s.rangeCount && ed.contains(s.anchorNode) ? s.getRangeAt(0).cloneRange() : null;
    const a = sel() && sel().closest("a"); url.value = a ? a.getAttribute("href") || "" : "";
    box.hidden = false; url.focus();
  };
  const addLink = () => {
    let u = url.value.trim(); box.hidden = true;
    if (!saved) return;
    ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(saved);
    if (!u) { document.execCommand("unlink"); changed(); return; }
    if (!/^(https?:|mailto:)/i.test(u)) u = /@/.test(u) && !/\//.test(u) ? `mailto:${u}` : `https://${u}`;
    if (saved.collapsed) document.execCommand("insertHTML", false, `<a href="${u.replace(/"/g, "%22")}">${u.replace(/^mailto:/, "").replace(/[<&]/g, m => (m === "<" ? "&lt;" : "&amp;"))}</a>&nbsp;`);
    else document.execCommand("createLink", false, u);
    changed();
  };
  box.querySelector("[data-rt-ok]").onclick = addLink;
  box.querySelector("[data-rt-no]").onclick = () => { box.hidden = true; ed.focus(); };
  url.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); addLink(); } if (e.key === "Escape") { e.preventDefault(); box.hidden = true; ed.focus(); } });

  host.querySelector(".rt-bar").addEventListener("mousedown", e => e.preventDefault());   // keep the selection in the box
  host.querySelectorAll("[data-rt]").forEach(b => { b.onclick = () => {
    const k = b.dataset.rt;
    if (k === "link") return openLink();
    cmd({ bold: "bold", italic: "italic", ul: "insertUnorderedList", ol: "insertOrderedList" }[k]);
  }; });
  ed.addEventListener("focus", () => { try { document.execCommand("defaultParagraphSeparator", false, "p"); } catch (_) {} });
  ed.addEventListener("input", changed);
  ed.addEventListener("keyup", state); ed.addEventListener("mouseup", state); ed.addEventListener("blur", () => { changed(); state(); });
  ed.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openLink(); }
  });
  // Pasting: its text only (formatting from elsewhere doesn't come along), lines kept.
  ed.addEventListener("paste", e => {
    e.preventDefault();
    const t = (e.clipboardData || window.clipboardData).getData("text/plain") || "";
    document.execCommand("insertText", false, t);
  });
  ed.addEventListener("drop", e => { if (e.dataTransfer && e.dataTransfer.files.length) e.preventDefault(); });
  return { get: () => last, set, el: ed };
}
