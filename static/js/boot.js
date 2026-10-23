// Before anything draws: show the app straight away when this browser was signed in last time
// (a hint only: the server decides), so the splash doesn't flash. A file of its own, not inline,
// because Lectern's Content-Security-Policy runs no inline scripts.
try {
  if (localStorage.getItem("lectern.signedin") === "1" && !/[#&](invite|join|reset)=/.test(location.hash)) document.documentElement.classList.add("lt-has-session");
} catch (_) {}
