"""Page instrumentation and state snapshots for the keyboard differential.

Upstream observed seven channels but reduced most of them to **counters**
(``a.net > b.net``). A counter answers "did something happen?"; it cannot
answer "did the *same* thing happen?", and the second question is the one the
oracle actually needs. Every channel here carries a normalized payload instead,
so :meth:`Effect.same_as` can compare a keyboard press against a mouse click
rather than merely observing that both were non-empty.

The init script is installed with ``add_init_script`` so it runs at
document-start, before any page script. Two traps, both of which upstream's
pilot caught the hard way and documented:

* ``document.documentElement`` is ``null`` at document-start, before the parser
  has built ``<html>``. Touching it throws and kills every channel silently.
  Nothing here dereferences the DOM until first use.
* ``requestAnimationFrame`` is throttled in backgrounded headless tabs, so a
  MutationObserver that defers through it drops records intermittently. The
  observer below increments synchronously in its callback.
"""

from __future__ import annotations

import re
from typing import Any

from audit.analyzer.keyboard.kbdiff.model import Effect

# Installed at document-start in every fresh page. Everything hangs off one
# global so a snapshot is a single round-trip, and every hook is wrapped in
# try/catch: an instrumentation failure must never change page behaviour, or we
# would be measuring our own probe.
INIT_SCRIPT = r"""
(() => {
  if (window.__kbdiff) return;
  const S = { net: [], console: [], canvas: 0, mutations: 0, storage: [] };
  window.__kbdiff = S;

  const note = (bucket, value) => {
    try { if (bucket.length < 500) bucket.push(String(value)); } catch (e) {}
  };

  // --- network ------------------------------------------------------------
  try {
    const origFetch = window.fetch;
    if (origFetch) {
      window.fetch = function (...args) {
        try {
          note(S.net, (args[0] && args[0].url) || args[0]);
        } catch (e) {}
        return origFetch.apply(this, args);
      };
    }
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
      try { note(S.net, url); } catch (e) {}
      return origOpen.call(this, method, url, ...rest);
    };
    const origSend = navigator.sendBeacon;
    if (origSend) {
      navigator.sendBeacon = function (url, ...rest) {
        try { note(S.net, url); } catch (e) {}
        return origSend.call(this, url, ...rest);
      };
    }
  } catch (e) {}

  // --- console ------------------------------------------------------------
  try {
    for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
      const orig = console[level];
      if (!orig) continue;
      console[level] = function (...args) {
        try {
          const parts = args.map(a => {
            try {
              return typeof a === 'object' ? JSON.stringify(a) : String(a);
            } catch (e) { return '?'; }
          });
          note(S.console, level + ':' + parts.join(' '));
        } catch (e) {}
        return orig.apply(this, args);
      };
    }
  } catch (e) {}

  // --- storage ------------------------------------------------------------
  // Recorded as an ordered write log, not a count. An idempotent write (same
  // key, same value, written twice) leaves the store identical, so comparing
  // stores after a reload would show nothing; the log still shows the write.
  try {
    const stores = [['local', localStorage], ['session', sessionStorage]];
    for (const [name, store] of stores) {
      const setItem = store.setItem.bind(store);
      const removeItem = store.removeItem.bind(store);
      const clear = store.clear.bind(store);
      store.setItem = function (k, v) {
        note(S.storage, name + ':set:' + k + '=' + v);
        return setItem(k, v);
      };
      store.removeItem = function (k) {
        note(S.storage, name + ':del:' + k);
        return removeItem(k);
      };
      store.clear = function () {
        note(S.storage, name + ':clear');
        return clear();
      };
    }
  } catch (e) {}

  // --- canvas -------------------------------------------------------------
  try {
    const proto = CanvasRenderingContext2D && CanvasRenderingContext2D.prototype;
    if (proto) {
      const ops = ['fillRect', 'strokeRect', 'drawImage', 'fillText',
                   'strokeText', 'stroke', 'fill'];
      for (const op of ops) {
        const orig = proto[op];
        if (!orig) continue;
        proto[op] = function (...args) {
          try { S.canvas++; } catch (e) {}
          return orig.apply(this, args);
        };
      }
    }
  } catch (e) {}

  // --- mutations ----------------------------------------------------------
  // Synchronous increment. No requestAnimationFrame: it is throttled when the
  // tab is backgrounded, which makes this channel intermittently dead.
  try {
    const start = () => {
      try {
        const obs = new MutationObserver((records) => {
          S.mutations += records.length;
        });
        obs.observe(document.documentElement, {
          childList: true, subtree: true, attributes: true, characterData: true,
        });
      } catch (e) {}
    };
    if (document.documentElement) start();
    else document.addEventListener('readystatechange', start, { once: true });
  } catch (e) {}
})();
"""

# One round-trip returning the current value of every channel. Digest channels
# (dom, geometry) are hashed here rather than shipped whole: a page's innerHTML
# can be megabytes, and we only ever compare it for equality.
SNAPSHOT_JS = r"""
() => {
  const S = window.__kbdiff || { net: [], console: [], canvas: 0, mutations: 0, storage: [] };
  const digest = (s) => {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    return String(h);
  };

  // Exact content, deliberately un-normalised. An earlier version collapsed
  // long digit and hex runs to absorb timestamps, but a 6-digit run is just as
  // likely to be an order number, an account id or a monetary amount -- and
  // collapsing those makes two genuinely DIFFERENT outcomes compare equal,
  // which silently dismisses real defects. Losing precision to hide
  // nondeterminism is the worse trade: a nondeterministic handler produces a
  // visible false positive we can explain, while an over-normalised comparison
  // produces a false negative nobody ever sees.
  let dom = '';
  try { dom = document.body ? document.body.innerHTML : ''; } catch (e) {}

  // Geometry: the visible-element set with rounded boxes, in DOCUMENT
  // coordinates. This is what catches a pure-CSS :hover reveal, which touches no
  // JavaScript and leaves innerHTML byte-identical.
  //
  // The scroll offset is added deliberately. getBoundingClientRect() is
  // viewport-relative, so the same unchanged layout hashes differently at
  // different scroll positions — and the mouse trial (which scrolls its target
  // into view) sits at a different offset from the keyboard trial (which lands
  // wherever Tab auto-scrolls). Comparing viewport coordinates therefore made
  // every effect look different across modalities, and reported plain <button>
  // elements as keyboard defects. Layout is the thing being measured here;
  // where the user happens to be scrolled is not.
  let geometry = '';
  try {
    const parts = [];
    const sx = window.scrollX || 0, sy = window.scrollY || 0;
    const els = document.querySelectorAll('*');
    const cap = Math.min(els.length, 4000);
    for (let i = 0; i < cap; i++) {
      const el = els[i];
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      parts.push(i + ':' + Math.round(r.x + sx) + ',' + Math.round(r.y + sy) +
                 ',' + Math.round(r.width) + ',' + Math.round(r.height));
    }
    geometry = parts.join('|');
  } catch (e) {}

  return {
    dom: digest(dom),
    geometry: digest(geometry),
    net: S.net.slice(),
    console: S.console.slice(),
    storage: S.storage.slice(),
    canvas: S.canvas,
    mutations: S.mutations,
    nav: location.href,
  };
}
"""

# Only an explicit cache-busting query parameter is treated as noise. These are
# named parameters whose whole purpose is to differ per request, so collapsing
# them cannot erase meaning.
#
# Nothing else is normalised. Blanket digit/hex collapsing was tried and removed:
# it absorbed timestamps, but it equally absorbed order numbers, account ids and
# amounts, so two different outcomes could compare equal and a real defect would
# be dismissed with no trace. Non-determinism is therefore a **disclosed
# limitation** of payload comparison rather than something papered over — a
# handler that writes a random token on every activation will produce a false
# positive, and the evidence in the report will show exactly why.
_NONCE = re.compile(
    r"([?&](?:_|t|ts|time|cb|cachebust|nonce|rand|r|v)=)[^&]*",
    re.IGNORECASE,
)


def normalize(value: str) -> str:
    """Collapse named cache-busting query parameters. Nothing else is touched.

    A keyboard press hitting the same endpoint as the mouse click compares equal
    even when the URL carries ``?t=<epoch>``; a press hitting ``/api/delete``
    instead of ``/api/save`` still compares different, and so does one carrying
    a different order id.
    """
    return _NONCE.sub(r"\1X", value)


def _added(before: list[str], after: list[str]) -> tuple[str, ...]:
    """The entries appended to an append-only log between two snapshots.

    The hooks only ever push, so the new entries are the tail. Slicing by length
    rather than diffing by value keeps a repeated identical call (two fetches to
    the same URL) visible as two events.
    """
    return tuple(sorted(normalize(v) for v in after[len(before) :]))


def diff(before: dict[str, Any], after: dict[str, Any]) -> Effect:
    """Compute the :class:`Effect` between two snapshots.

    A channel is "changed" only when it carries a payload the before-state did
    not have. ``dom`` and ``geometry`` compare digests; the rest compare their
    appended entries.
    """
    changed: set[str] = set()
    payloads: dict[str, tuple[str, ...]] = {}

    for channel in ("dom", "geometry", "nav"):
        if before.get(channel) != after.get(channel):
            changed.add(channel)
            payloads[channel] = (str(after.get(channel, "")),)

    for channel in ("net", "console", "storage"):
        entries = _added(before.get(channel, []), after.get(channel, []))
        if entries:
            changed.add(channel)
            payloads[channel] = entries

    drawn = int(after.get("canvas", 0)) - int(before.get("canvas", 0))
    if drawn > 0:
        changed.add("canvas")
        # The count, not the pixels: reading canvas back can taint it and can
        # throw cross-origin. Two different draws of the same op-count will
        # compare equal, which is a known and disclosed limitation.
        payloads["canvas"] = (f"draws={drawn}",)

    return Effect(frozenset(changed), payloads)
