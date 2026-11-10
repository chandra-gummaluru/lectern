// Lectern's service worker: what makes Lectern installable as an app (Install Lectern, in the account menu).
// It keeps nothing: Lectern's pages and answers are never cached (they carry grades and sign-in secrets), so
// everything still comes from the server. All it adds is a plain "You're offline" page when Lectern's page
// can't be reached, instead of the browser's error. Served from /static/js/ (Lectern's scripts may only come
// from there) with Service-Worker-Allowed: / so that it covers the whole site.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

const OFFLINE = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lectern — offline</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#fcfcfc;color:#333;
font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px;box-sizing:border-box}h1{font:500 30px Georgia,serif;margin:0 0 8px}
p{margin:0 0 20px;color:#666}a{display:inline-block;padding:9px 18px;border-radius:8px;background:#333;color:#fcfcfc;text-decoration:none}</style></head>
<body><main><h1>You're offline</h1><p>Lectern can't reach its server. Your work is kept there, so nothing is lost.</p>
<a href="">Try again</a></main></body></html>`;

self.addEventListener("fetch", e => {
  if (e.request.mode !== "navigate") return;           // everything but opening a page: straight to the server
  e.respondWith(fetch(e.request).catch(() =>
    new Response(OFFLINE, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } })));
});
