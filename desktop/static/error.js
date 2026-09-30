// Fills the startup-failure page from the query string the launcher passes.
// Everything is assigned through textContent, so the backend's output is shown
// verbatim and never interpreted as markup.
(function renderFailure() {
  const params = new URLSearchParams(window.location.search);
  const reason = params.get("reason");
  const output = params.get("output");
  const log = params.get("log");

  if (reason) document.getElementById("reason").textContent = reason;
  if (params.get("packaged") !== "1") document.getElementById("dev-hint").hidden = false;
  if (output) {
    document.getElementById("output").textContent = output;
    document.getElementById("output-section").hidden = false;
  }
  if (log) {
    document.getElementById("log").textContent = log;
    document.getElementById("log-section").hidden = false;
  }
})();
