// Before anything draws: show the app straight away when this browser was signed in last time
// (a hint only: the server decides), so the splash doesn't flash. A file of its own, not inline,
// because Lectern's Content-Security-Policy runs no inline scripts.
try {
  if (localStorage.getItem("lectern.signedin") === "1" && !/[#&](invite|join|reset)=/.test(location.hash)) document.documentElement.classList.add("lt-has-session");
} catch (_) {}

// Installing Lectern as an app (the account menu's Install Lectern): the service worker, and the browser's
// install offer, which can arrive before lectern.js has loaded, so it's kept here for the menu to use.
window.LecternInstall = { prompt: null };
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); window.LecternInstall.prompt = e; });
window.addEventListener("appinstalled", () => { window.LecternInstall.prompt = null; });
if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/static/js/sw.js", { scope: "/" }).catch(() => {}));
}
