"""Offline replay of a mitmproxy capture through Playwright request routing.

No listening socket and no origin contact. Every request the page makes is
resolved against the capture; anything unmatched is aborted and counted. That
default-deny is the property that makes an observation attributable to the
capture rather than to today's live web.

Two things this module deliberately does *not* do:

* It does not score anything. It produces coverage and denial counts.
* It does not touch the frozen detectors. The neutral census below assigns a
  stable id to every element in the page, independent of any label, so that
  candidate output can be referred to at all on a page that carries no
  `data-probe` attributes. Whether that census is stable and side-effect-free
  is a hypothesis this experiment tests, not an assumption it relies on.
"""

from __future__ import annotations

import gzip
import zlib
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from tools.flowfile import Exchange, ExchangeIndex

# Namespaced so it cannot collide with a captured page's own attributes, and
# named for this experiment so it is obvious in a DOM dump where it came from.
CENSUS_ATTR = "data-litrep-eid"

# Hosts whose absence changes telemetry, not behaviour. Denying these is the
# intended outcome of egress blocking and must not be reported as a broken
# capture (manager finding G4).
_TRACKING_HINTS = (
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "facebook.net",
    "facebook.com/tr",
    "hotjar.com",
    "segment.io",
    "newrelic.com",
    "nr-data.net",
    "scorecardresearch.com",
    "quantserve.com",
    "adservice.",
    "/collect",
    "/beacon",
    "/pixel",
)

# Extensions whose absence degrades appearance but not keyboard behaviour.
_MEDIA_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".webm",
)

# Resource kinds whose absence can change scripted behaviour, and therefore
# whether a keyboard observation means anything.
_ESSENTIAL_SUFFIXES = (".js", ".mjs", ".css", ".json", ".html", ".htm")


def normalize(url: str) -> str:
    """Drop the fragment; keep scheme, host, port, path and query."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def classify_denial(url: str) -> str:
    lowered = url.lower()
    if any(hint in lowered for hint in _TRACKING_HINTS):
        return "benign_tracking"
    path = urlsplit(lowered).path
    if path.endswith(_MEDIA_SUFFIXES):
        return "benign_media"
    if path.endswith(_ESSENTIAL_SUFFIXES):
        return "essential"
    # Unknown shape: treat as essential rather than quietly excusing it.
    return "essential"


def prepare_response(exchange: Exchange) -> tuple[bytes, dict[str, str]]:
    """Return the body and headers to fulfil a route with.

    mitmproxy serializes the *raw* body, so a gzip or brotli response is stored
    compressed. Verified on all three authorized captures. gzip and deflate are
    decoded here, because the standard library can; brotli is passed through
    with its header intact for Chromium to decode, because the standard library
    cannot and installing a decoder is out of scope.

    A body that claims an encoding but does not decode is passed through
    unchanged rather than raising: a malformed entry should degrade one
    resource, not abort the run.
    """
    headers = dict(exchange.headers)
    # Always stale once the body is rewritten, and wrong even when it is not,
    # because Playwright recomputes it.
    headers.pop("content-length", None)

    encoding = headers.get("content-encoding", "").strip().lower()
    body = exchange.body

    if encoding in ("gzip", "x-gzip"):
        try:
            body = gzip.decompress(body)
            headers.pop("content-encoding", None)
        except (OSError, zlib.error, EOFError):
            pass
    elif encoding == "deflate":
        try:
            body = zlib.decompress(body)
            headers.pop("content-encoding", None)
        except zlib.error:
            try:
                body = zlib.decompress(body, -zlib.MAX_WBITS)
                headers.pop("content-encoding", None)
            except zlib.error:
                pass
    elif encoding == "":
        headers.pop("content-encoding", None)
    # "br" and anything else: leave body and header alone for the browser.

    return body, headers


@dataclass
class ReplayRouter:
    """Resolve browser requests against a capture, denying everything else."""

    index: ExchangeIndex
    served: int = 0
    denied: int = 0
    denied_urls: dict[str, int] = field(default_factory=dict)
    _cursor: dict[tuple[str, str], int] = field(default_factory=dict)

    def resolve(self, url: str, method: str = "GET") -> Exchange | None:
        """Return the captured response for this request, or None to deny it.

        Method participates in matching. Answering a POST with a GET's captured
        body would fabricate a page state the capture never observed, which is
        worse than denying: a denial is visible in the counts, a wrong 200 is
        not.
        """
        key = normalize(url)
        verb = method.upper()
        candidates = [e for e in self.index.by_url.get(key, ()) if e.method == verb]
        if not candidates:
            self.denied += 1
            self.denied_urls[key] = self.denied_urls.get(key, 0) + 1
            return None

        # Serve repeated requests in capture order, then hold on the last
        # response: browsers re-request, and denying a re-request would look
        # like a capture defect that is not there. Ordering is per (url,
        # method) so a POST cannot advance the GET cursor.
        cursor_key = (key, verb)
        position = min(self._cursor.get(cursor_key, 0), len(candidates) - 1)
        self._cursor[cursor_key] = position + 1
        self.served += 1
        return candidates[position]

    def denial_report(self) -> dict[str, list[str]]:
        report: dict[str, list[str]] = {
            "essential": [],
            "benign_tracking": [],
            "benign_media": [],
        }
        for url in self.denied_urls:
            report[classify_denial(url)].append(url)
        for bucket in report.values():
            bucket.sort()
        return report

    def is_functionally_degraded(self) -> bool:
        """True only if something that can change behaviour went missing."""
        return bool(self.denial_report()["essential"])

    async def attach(self, context) -> None:
        """Bind to a Playwright context. Every route is handled here."""

        async def handler(route):
            request = route.request
            exchange = self.resolve(request.url, request.method)
            if exchange is None:
                await route.abort()
                return
            body, headers = prepare_response(exchange)
            await route.fulfill(status=exchange.status, headers=headers, body=body)

        await context.route("**/*", handler)


# ---------------------------------------------------------------------------
# Neutral element census (manager finding G1)
# ---------------------------------------------------------------------------

# Assigns every element a stable, label-independent id derived only from its
# position in the tree. Nothing about the experiment's labels, targets or
# vocabulary enters this script: it cannot prefer a "known" element because it
# has no notion of one. Whether adding the attribute perturbs the page is
# exactly what the tagged/untagged controls measure.
NEUTRAL_CENSUS_JS = """
(attr) => {
  let n = 0;
  const walk = (root, prefix) => {
    let els;
    try { els = root.querySelectorAll('*'); } catch (e) { return; }
    let i = 0;
    for (const el of els) {
      const id = prefix + '/' + (i++) + ':' + el.tagName.toLowerCase();
      try { el.setAttribute(attr, id); n++; } catch (e) {}
      if (el.shadowRoot) walk(el.shadowRoot, id + '#s');
    }
  };
  walk(document, '');
  return n;
}
"""

# Reads the same census without writing anything, so a tagged run and an
# untagged run can be compared on identical terms.
DOM_SIGNATURE_JS = """
() => {
  const counts = {};
  let total = 0;
  const walk = (root) => {
    let els;
    try { els = root.querySelectorAll('*'); } catch (e) { return; }
    for (const el of els) {
      const tag = el.tagName.toLowerCase();
      counts[tag] = (counts[tag] || 0) + 1;
      total++;
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  let visible = 0;
  try {
    for (const el of document.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) visible++;
    }
  } catch (e) {}
  return { total, visible, tags: counts, frames: window.frames.length };
}
"""

# Identifies the focused element by structural path alone.
#
# The earlier probe read CENSUS_ATTR and fell back to `tagName` when it was
# missing, so tagged runs reported per-element ids while untagged runs reported
# tag names -- 15 stops versus 1 on the same page, from the probe, not the page.
# That made the tagged/untagged comparison meaningless for focus order, which is
# the dimension that matters for a keyboard detector.
#
# The path here is derived only from tree position, so both arms are measured on
# identical terms and the census attribute's effect on focus order becomes
# observable rather than assumed.
# Emitted in place of an identity for a scope the probe cannot enter (a frame
# this context may not read). Every stop inside such a scope shares this string,
# so it is named, exported and checked for rather than counted as a focus stop.
OPAQUE_SCOPE = "#frame-opaque:UNSUPPORTED"

FOCUS_PROBE_JS = """
() => {
  const path = (el) => {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node.tagName !== 'HTML') {
      const parent = node.parentElement;
      if (!parent) {
        const root = node.getRootNode();
        if (root && root.host) {
          // The child's own position inside the shadow root has to be recorded
          // before crossing to the host, or every direct child of one root
          // collapses onto the host's path.
          const j = Array.prototype.indexOf.call(root.children, node);
          parts.push('#s' + j + ':' + node.tagName.toLowerCase());
          node = root.host;
          continue;
        }
        break;
      }
      const i = Array.prototype.indexOf.call(parent.children, node);
      parts.push(i + ':' + node.tagName.toLowerCase());
      node = parent;
    }
    return parts.reverse().join('/');
  };
  // Focus inside a shadow root or frame surfaces at the host; descend to the
  // element that actually holds it, and keep the crossing in the identity.
  const describe = (doc) => {
    let el = doc.activeElement;
    if (!el) return 'NONE';
    while (el.shadowRoot && el.shadowRoot.activeElement) el = el.shadowRoot.activeElement;
    if (el.tagName === 'IFRAME' || el.tagName === 'FRAME') {
      let inner = null;
      try { inner = el.contentDocument; } catch (e) { inner = null; }
      // A frame this context may not read is an unsupported scope. Say so:
      // returning the frame's own path would give every stop inside it one
      // identity and hide the loss as an ordinary result.
      if (!inner) return path(el) + '/#frame-opaque:UNSUPPORTED';
      return path(el) + '/#f/' + describe(inner);
    }
    if (el === doc.body) return 'BODY';
    return path(el) || 'NONE';
  };
  return describe(document);
}
"""
