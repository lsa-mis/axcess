// Shared fixture helpers. `fired` writes a visible record into #sink, which is
// the DOM-observable side effect the oracles look for.
window.__fired = [];
function fired(id) {
  window.__fired.push(id);
  var sink = document.getElementById('sink');
  if (sink) {
    var line = document.createElement('div');
    line.textContent = 'fired: ' + id;
    sink.appendChild(line);
  }
}
// Handlers that deliberately leave no DOM trace (see e-nodom.html).
function firedSilently(id) { window.__fired.push(id); }
