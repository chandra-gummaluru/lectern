/* Announcements: written here, and the course page shows each one in the week its date falls in
   (Announcements, and This week).

     #/<course>/<term>/announcements          every announcement, newest first
     #/<course>/<term>/announcements/<id>     one: its title, date and time, and message

   Kept in the offering's private files, <course>/<term>/announcements.json:

     { "format": "lectern-announcements/1",
       "items": [ { "id", "title", "date": "Oct 24, 2026, 13:48", "at": 1792860000000, "body": "Markdown" } ] }

   An offering without one starts from its course page's announcements (course.json), and becomes an
   announcements.json with the first change. Changes save by themselves. Instructors write them; TAs see them. */

const uid = () => Math.random().toString(36).slice(2, 10);
const MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = n => String(n).padStart(2, "0");
const stampOf = d => `${MON3[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
function readStamp(t) {
  const m = /([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})(?:,?\s+(\d{1,2}):(\d\d))?/.exec(t || "");
  if (!m) return { date: "", time: "" };
  const d = new Date(`${m[1]} ${m[2]}, ${m[3]}`);
  return isNaN(d) ? { date: "", time: "" } : { date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, time: m[4] ? `${pad(m[4])}:${m[5]}` : "" };
}
const timeOf = a => { const t = Date.parse(String(a.date || "")); return isNaN(t) ? a.at || 0 : t; };

function fromCoursePage(page) {
  const items = [];
  ((page && page.sections) || []).filter(s => s && s.type === "schedule").forEach(s => (s.weeks || []).forEach(w => (w && w.announcements || []).forEach(a => {
    if (a && ((a.title || "").trim() || (a.body || "").trim())) items.push({ id: uid(), title: a.title || "", date: a.date || "", at: a.at || 0, body: a.body || "" });
  })));
  return { format: "lectern-announcements/1", items };
}

export function announcementsPage(ctx, r) {
  const { $, esc, pageHTML, toast, confirmBox, go, Store, area, canEdit, ICON, renderPath, steps, markdown } = ctx;
  const { c, t } = r, path = `${c}/${t}/announcements.json`, repo = area(Store.PRIV), edit = canEdit(c, t);
  const key = `${r.o || ""}/${c}/${t}`;
  const here = () => { const x = ctx.route(); return x.page === "announcements" && x.c === c && x.t === t; };
  const st = (announcementsPage.state = announcementsPage.state && announcementsPage.state.key === key ? announcementsPage.state : { key, data: null, sha: undefined });

  async function load() {
    pageHTML(`<div class="lt-in"><div class="lt-loading" style="min-height:200px">Reading the announcements…</div></div>`);
    try {
      const f = await Store.readFile(repo, path);
      if (f) { st.data = JSON.parse(f.text); st.sha = f.sha; }
      else {
        const pg = await Store.readText(area(Store.PUB), `${c}/${t}/course.json`).catch(() => null);
        let page = null; try { page = pg ? JSON.parse(pg).page : null; } catch (_) {}
        st.data = fromCoursePage(page); st.sha = null;
      }
      if (!Array.isArray(st.data.items)) st.data.items = [];
    } catch (e) { if (here()) pageHTML(`<div class="lt-in"><p class="lt-note err">Couldn't read the announcements. ${esc(e.message)}</p></div>`); return; }
    if (here()) draw();
  }

  let timer = 0, saving = null, again = false;
  function changed() { status("Saving…"); clearTimeout(timer); timer = setTimeout(save, 500); }
  async function save() {
    if (saving) { again = true; return; }
    saving = (async () => {
      try { st.sha = await Store.writeText(repo, path, JSON.stringify(st.data, null, 1) + "\n", "Announcements", st.sha); status("Saved"); }
      catch (e) { status("Not saved", true); toast(e.conflict ? "The announcements were changed somewhere else. Reload this page to see them; your last change wasn't saved." : `Couldn't save. ${e.message}`); }
      finally { saving = null; if (again) { again = false; save(); } }
    })();
  }
  function status(text, bad) { const el = $("#an-status"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }

  function draw() {
    const a = r.a && st.data.items.find(x => x.id === r.a);
    return a ? drawOne(a) : drawList();
  }

  function drawList() {
    renderPath([...steps, { label: "Announcements" }]);
    const empty = st.data.items.filter(x => !(x.title || "").trim() && !(x.body || "").trim());   // started and left blank: not kept
    if (empty.length && edit) { st.data.items = st.data.items.filter(x => !empty.includes(x)); changed(); }
    const list = st.data.items.slice().sort((x, y) => timeOf(y) - timeOf(x));
    pageHTML(`<div class="lt-in lt-lw">
      <div class="lt-off-head"><div><h1>Announcements</h1><p class="lt-lede">The course page shows each one in the week its date is in, newest first.</p></div>
        <div class="lt-off-acts">${edit ? `<span class="lw-status" id="an-status"></span><button type="button" class="lt-btn primary" id="an-new">${ICON.plus}New Announcement</button>` : ""}</div></div>
      ${edit ? "" : `<p class="lt-note">As a TA you can read the announcements; the instructors write them.</p>`}
      <div class="lw-list">${list.length ? list.map(x => `<article class="an-card" data-an="${esc(x.id)}" role="button" tabindex="0"><p class="an-date">${esc(x.date || "No date")}</p><h2>${esc(x.title || "Untitled")}</h2><div class="an-body">${markdown(x.body)}</div></article>`).join("") : `<p class="lt-hint">No announcements yet.</p>`}</div>
    </div>`);
    document.querySelectorAll("[data-an]").forEach(b => { b.onclick = e => { if (e.target.closest("a")) return; go({ page: "announcements", c, t, a: b.dataset.an }); }; });
    if (edit) $("#an-new").onclick = () => {
      const x = { id: uid(), title: "", date: stampOf(new Date()), at: Date.now(), body: "" };
      st.data.items.push(x); changed(); go({ page: "announcements", c, t, a: x.id });
    };
  }

  function drawOne(x) {
    const crumbs = () => renderPath([...steps, { label: "Announcements", go: () => go({ page: "announcements", c, t }) }, { label: x.title || "New announcement" }]);
    crumbs();
    const when = readStamp(x.date), dis = edit ? "" : " disabled";
    pageHTML(`<div class="lt-in lt-lw lw-page">
      <div class="lt-off-head"><h1 id="an-h">${esc(x.title || "New announcement")}</h1><div class="lt-off-acts">${edit ? `<span class="lw-status" id="an-status"></span><button type="button" class="lt-btn lt-trash" id="an-del" title="Delete this announcement" aria-label="Delete this announcement">${ICON.trash}</button>` : ""}</div></div>
      <div class="lw-card lt-form">
        <label>Title<input type="text" id="an-title" value="${esc(x.title)}" placeholder="e.g. Midterm rooms posted"${dis}></label>
        <div class="lw-two"><label>Date<input type="date" id="an-date" value="${esc(when.date)}"${dis}><small>It goes in the week this date is in.</small></label>
          <label>Time<input type="time" id="an-time" value="${esc(when.time)}"${dis}></label></div>
        <label>Message<textarea id="an-body" rows="10" placeholder="Write it here. A blank line starts a new paragraph; - for bullets; **bold**, *italic*, [a link](https://…)."${dis}>${esc(x.body)}</textarea></label>
      </div>
      <h2 class="lw-h2">As students see it</h2>
      <article class="an-card an-preview"><p class="an-date" id="an-pd">${esc(x.date)}</p><h2 id="an-pt">${esc(x.title || "Untitled")}</h2><div class="an-body" id="an-pb">${markdown(x.body)}</div></article>
    </div>`);
    if (!edit) return;
    let shown = x.title || "New announcement";
    const head = () => { $("#an-pt").textContent = x.title || "Untitled"; $("#an-pd").textContent = x.date; const now = x.title || "New announcement"; if (now === shown) return; shown = now; $("#an-h").textContent = now; crumbs(); };
    $("#an-title").oninput = $("#an-title").onchange = e => { x.title = e.target.value.trim(); head(); changed(); };
    const stamp = () => { const d = $("#an-date").value, tm = $("#an-time").value; if (d) { const [y, m, dd] = d.split("-").map(Number); x.date = `${MON3[m - 1]} ${dd}, ${y}${tm ? `, ${tm}` : ""}`; } else x.date = ""; head(); changed(); };
    $("#an-date").onchange = stamp; $("#an-time").onchange = stamp;
    $("#an-body").oninput = e => { x.body = e.target.value; $("#an-pb").innerHTML = markdown(x.body); changed(); };
    $("#an-del").onclick = async () => {
      if (!await confirmBox("Delete this announcement?", "It goes from the course page.", "Delete")) return;
      st.data.items = st.data.items.filter(y => y !== x); changed(); go({ page: "announcements", c, t });
    };
  }

  if (st.data) draw(); else load();
}
