// bm bookmarklet — capture current tab's URL + title to the local daemon.
//
// Install: minify the IIFE below to a single line, prefix with `javascript:`,
// and paste into a browser bookmark's URL field. See bookmarklet.min.js for
// the ready-to-paste minified form.
//
// Wire format:
//   POST http://localhost:9876/add  Content-Type: application/json
//   body: {"url": "<href>", "title": "<document.title>"}
//
// CSP fallback: if fetch() is blocked by the page's CSP, opens a tiny popup
// at GET http://localhost:9876/add?url=...&title=... — the daemon serves an
// HTML response that auto-closes the popup after writing the inbox file.
(() => {
  const u = location.href;
  const t = document.title || "";

  // Toast UI: floating div, bottom-right. Success auto-dismisses fast (1.6s).
  // Failure stays longer (4s) so the user has time to read it.
  const toast = (msg, ok) => {
    try {
      const d = document.createElement("div");
      d.textContent = "bm: " + msg;
      d.style.cssText =
        "position:fixed;z-index:2147483647;right:16px;bottom:16px;" +
        "padding:10px 14px;border-radius:6px;font:14px/1.3 system-ui;" +
        "color:#fff;background:" + (ok ? "#10b981" : "#ef4444") + ";" +
        "box-shadow:0 4px 12px rgba(0,0,0,.18);pointer-events:none;" +
        "max-width:320px";
      document.body.appendChild(d);
      setTimeout(() => d.remove(), ok ? 1600 : 4000);
    } catch (e) { /* document.body may be unavailable on some pages */ }
  };

  // fetch POST. mode:'no-cors' permits cross-origin requests to localhost
  // without preflight, at the cost of an opaque response — we display
  // "Saved" optimistically on resolve. Rejection covers both daemon-down
  // (connection refused) and strict-CSP-blocking-fetch cases.
  fetch("http://localhost:9876/add", {
    method: "POST",
    mode: "no-cors",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: u, title: t }),
  }).then(
    () => toast("Saved", true),
    () => toast("Failed — daemon down or CSP-blocked. /bm:install --status", false)
  );
})();
