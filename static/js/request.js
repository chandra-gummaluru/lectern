/* The students' accommodation request form (/request?r=…&o=…&e=…).
   1. What can be asked for this evaluation (and whether the deadline has passed).
   2. Who you are: email, identifier, first and last name, checked against the class list.
   3. What you need: the standard accommodation, or an alternate one (said in your own words).
   4. Sent: a copy goes to your email; another request starts again from step 3. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var q = new URLSearchParams(location.search);
  var where = { r: q.get("r") || "", o: q.get("o") || "", e: q.get("e") || "" };
  var card = $("#rq-card");
  var info = null, who = null, first = "";

  function api(path, body) {
    var opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.assign({}, where, body)) } : {};
    var url = "/api/accommodations/" + path + (body ? "" : "?" + new URLSearchParams(where));
    return fetch(url, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (d) {
        if (!res.ok) { var err = new Error(d.error || "Something went wrong. Try again in a moment."); err.status = res.status; err.code = d.code; throw err; }
        return d;
      });
    }, function () { throw new Error("Couldn't reach Lectern. Check your connection and try again."); });
  }

  function whenText(ev) {
    if (!ev.date) return "";
    var d = new Date(ev.date + "T" + (ev.time || "12:00"));
    if (isNaN(d)) return "";
    var day = d.toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric" });
    return (ev.type === "assignment" || ev.type === "project" || !ev.type ? "Due " : "") + day + (ev.time ? ", " + ev.time : "");
  }

  function header() {
    $("#rq-course").textContent = [info.course.code, info.course.term].filter(Boolean).join(" · ") || " ";
    $("#rq-eval").textContent = [info.evaluation.name, whenText(info.evaluation)].filter(Boolean).join(" — ");
    document.title = "Request an Accommodation · " + info.evaluation.name;
  }

  function stop(title, text) {
    card.innerHTML = "<h2>" + esc(title) + "</h2><p>" + text + "</p>";
  }

  function deadlineLine() {
    var d = info.deadline;
    return d && !d.passed ? '<p class="rq-lede">Requests close <b>' + esc(d.text) + "</b>.</p>" : "";
  }

  function closed() {
    stop("The deadline has passed", "Requests for an accommodation for " + esc(info.evaluation.name) + " closed " + esc(info.deadline.text) + ". If you still need one, contact your instructor.");
  }

  // ── 2. Who you are ──
  function identity(err) {
    var v = who || {};
    card.innerHTML =
      "<h2>First, who are you?</h2>" +
      '<p>Use the details your instructor has for you, so we can find you in the class list.</p>' + deadlineLine() +
      '<form class="rq-form" id="f-who" novalidate>' +
      '<label>Email<input type="email" name="email" autocomplete="email" required value="' + esc(v.email) + '"><small>The address your instructor has for you, e.g. your university email.</small></label>' +
      "<label>" + esc(info.idLabel) + '<input type="text" name="id" autocomplete="off" required value="' + esc(v.id) + '"></label>' +
      '<div class="rq-two"><label>First name<input type="text" name="first" autocomplete="given-name" required value="' + esc(v.first) + '"></label>' +
      '<label>Last name<input type="text" name="last" autocomplete="family-name" required value="' + esc(v.last) + '"></label></div>' +
      '<p class="rq-err" id="rq-err">' + esc(err || "") + "</p>" +
      '<div class="rq-acts"><span class="sp"></span><button type="submit" class="rq-btn primary">Continue</button></div></form>';
    var f = $("#f-who");
    if (!err) f.email.focus();
    f.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var d = { email: f.email.value.trim(), id: f.id.value.trim(), first: f.first.value.trim(), last: f.last.value.trim() };
      if (!d.email || !d.id || !d.first || !d.last) { $("#rq-err").textContent = "Fill in all four."; return; }
      var b = f.querySelector("button[type=submit]"); b.disabled = true; b.textContent = "Checking…";
      api("verify", d).then(function (res) {
        who = d; first = res.first || d.first;
        info = Object.assign(info, { standard: res.standard, alternate: res.alternate, deadline: res.deadline });
        choose();
      }, function (e) {
        who = d;
        if (e.code === "closed") return refresh();
        identity(e.message);
      });
    });
  }

  // ── 3. What you need ──
  function choose(err, keep) {
    var s = info.standard, canStd = !!(s && s.approval), alt = !!info.alternate;
    var k = keep || {};
    var opts = "";
    if (canStd) opts += '<label class="rq-opt"><input type="radio" name="kind" value="standard"' + (k.kind === "standard" || (!k.kind && !alt) ? " checked" : "") + "><b>Request approval for the standard accommodation</b><span>" + esc(s.text) + "</span></label>";
    opts += '<label class="rq-opt' + (alt ? "" : " off") + '"><input type="radio" name="kind" value="alternate"' + (alt ? "" : " disabled") + (alt && (k.kind === "alternate" || (!k.kind && !canStd)) ? " checked" : "") + "><b>Request an alternate accommodation</b><span>" + (alt ? "Something other than the standard accommodation: say what you need." : "Not available for this evaluation.") + "</span></label>";
    card.innerHTML =
      "<h2>Hi " + esc(first) + ". What do you need?</h2>" +
      (s && !s.approval ? '<p class="rq-std">The standard accommodation for this evaluation is <b>' + esc(s.text) + "</b>. It doesn't need a request.</p>" : "<p>Choose one. For something else as well, make another request after this one.</p>") +
      '<form class="rq-form" id="f-what" novalidate><div class="rq-opts">' + opts + "</div>" +
      '<label class="rq-more" id="rq-more" hidden>What do you need?<textarea name="details" maxlength="4000" placeholder="e.g. Writing it on a different day, because…">' + esc(k.details || "") + "</textarea></label>" +
      '<p class="rq-err" id="rq-err">' + esc(err || "") + "</p>" +
      '<div class="rq-acts"><button type="button" class="rq-btn" id="rq-back">Back</button><span class="sp"></span><button type="submit" class="rq-btn primary">Send Request</button></div></form>';
    var f = $("#f-what"), more = $("#rq-more");
    var sync = function () { var v = (f.querySelector("input[name=kind]:checked") || {}).value; more.hidden = v !== "alternate"; };
    f.querySelectorAll("input[name=kind]").forEach(function (x) { x.addEventListener("change", function () { sync(); if (x.value === "alternate") f.details.focus(); }); });
    sync();
    $("#rq-back").onclick = function () { identity(); };
    f.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var kind = (f.querySelector("input[name=kind]:checked") || {}).value, details = f.details.value.trim();
      if (!kind) { $("#rq-err").textContent = "Choose what you're asking for."; return; }
      if (kind === "alternate" && !details) { $("#rq-err").textContent = "Say what you need."; f.details.focus(); return; }
      var b = f.querySelector("button[type=submit]"); b.disabled = true; b.textContent = "Sending…";
      api("submit", Object.assign({}, who, { kind: kind, details: kind === "alternate" ? details : "" })).then(done, function (e) {
        if (e.code === "closed") return refresh();
        choose(e.message, { kind: kind, details: details });
      });
    });
  }

  // ── 4. Sent ──
  function done(res) {
    card.innerHTML = '<div class="rq-done"><span class="rq-tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span>' +
      "<h2>Request sent</h2>" +
      "<p>Your instructor will review it, and you'll get an email at <b>" + esc(res.email) + "</b> when it's approved or rejected." + (res.emailed ? " We've emailed you a copy of your request." : "") + "</p>" +
      '<p class="rq-ref">Reference ' + esc(res.id) + "</p>" +
      '<div class="rq-acts"><button type="button" class="rq-btn" id="rq-again">Make Another Request</button></div></div>';
    $("#rq-again").onclick = function () { choose(); };
  }

  // ── 1. What can be asked for ──
  function refresh() {
    return api("evaluation").then(function (d) {
      info = d; header();
      if (d.deadline && d.deadline.passed) return closed();
      identity();
    }, function (e) {
      if (e.status === 400) return stop("This link doesn't work", "It's missing its course or evaluation. Go back to the course page and use its Request Accommodation button.");
      if (e.status === 404) return stop("No requests for this evaluation", esc(e.message) + " If you need an accommodation, contact your instructor.");
      stop("Something went wrong", esc(e.message));
    });
  }
  refresh();
})();
