// Runs before first paint to avoid a theme flash. Lives in a static file
// (not inline in index.html) so the Content-Security-Policy in vercel.json
// can stay `script-src 'self'` without 'unsafe-inline'.
(function () {
  try {
    var stored = localStorage.getItem("theme");
    var theme = stored === "dark" || stored === "light"
      ? stored
      : (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    document.documentElement.dataset.theme = theme;
  } catch (e) {}
})();
