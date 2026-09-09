// Each probe gets its OWN named function on purpose. Upstream's fixtures routed
// every handler through one shared fired() helper, which inflates the overlap
// between unrelated handlers in V8 coverage sets and makes any coverage-based
// equivalence test look more similar than it is. Their own STUDY.md lists that
// as a threat to validity. Distinct functions remove it.
//
// The written value is DETERMINISTIC. An earlier version appended
// Math.random(), which meant a correct control produced a different DOM payload
// under the mouse than under the keyboard, and an oracle comparing payloads
// called every native <button> a keyboard defect. That was a defect in this
// fixture, not in the detector -- but it exposed a real limit of payload
// equality, which is recorded in the study rather than hidden by this fix.
function mark(id) {
  const out = document.getElementById('out');
  if (out) out.textContent = 'fired:' + id;
}
