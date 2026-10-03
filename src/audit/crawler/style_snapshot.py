"""Save a rendered page's CSS beside its saved copy, during the scan.

A saved copy (``pages.rendered_html``, ``page_dom_states.dom``) is HTML only.
Shown later in the Page inspector it used to fetch its CSS from the live site,
which fails in many ways: the site's CSP ``<meta>`` (where ``'self'`` becomes
the review UI), ``crossorigin``/``integrity`` links, CSS behind a sign-in (no
cookies at view time), CSS files deleted after a deploy, offline viewing, and
rules that scripts added through the CSSOM (JSS, emotion, styled-components),
which ``page.content()`` never serializes. This module reads the page's CSS in
the scan's own live page instead, so the inspector can serve it from the
review UI's own origin.

What is captured, in cascade (document) order:

* every sheet in ``document.styleSheets`` that is not disabled, with
  ``@import`` rules inlined in place of the rule (wrapped in the import's
  media, ``supports()`` and ``layer()`` conditions), then
  ``document.adoptedStyleSheets``;
* each sheet's rules as the browser holds them (``cssRules``), which includes
  rules scripts inserted; each top-level sheet keeps its own ``media`` text;
* a cross-origin sheet whose ``cssRules`` the page may not read is fetched
  again with the browser context's own request API, which carries the scan's
  cookies, so CSS behind a sign-in still works. :class:`SheetCache` keeps
  those results for the whole scan, so a site's shared CSS is fetched once.

Every relative ``url(...)`` is rewritten to an absolute URL against the sheet's
own URL (or the document base for inline sheets), so fonts and images keep
resolving to the live site. ``@charset`` and ``@import`` are dropped (imports
are already inlined).

Known limits:

* Shadow DOM content is not in ``page.content()``, so the styles inside shadow
  roots are out of scope here as well.
* ``cssRules`` is the browser's parsed view: declarations this Chromium does
  not understand (another engine's vendor prefixes) are not in it.
* ``@namespace`` rules only apply at the top of a sheet; one that ends up
  after other rules in the concatenated file is ignored by the browser.

Bounds (AGENTS.md rule 6): at most :data:`MAX_SHEET_BYTES` per sheet,
:data:`MAX_PAGE_BYTES` per page and :data:`MAX_SHEETS` sheets. Anything over a
bound is skipped and the snapshot records that it is incomplete. Nothing here
raises into the crawl: :func:`capture_styles` returns ``None`` on failure.

The same ``page.evaluate`` also records a small fingerprint of computed
styles (see :data:`_SNAPSHOT_JS`), so the inspector can check how closely its
rendering of the saved copy matches what the scan saw at that same moment.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit

from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import APIRequestContext, Page

log = get_logger(__name__)

MAX_SHEET_BYTES = 2_000_000
MAX_PAGE_BYTES = 8_000_000
MAX_SHEETS = 300
# Elements sampled for the fingerprint. The inspector reads the same count.
FINGERPRINT_SAMPLES = 40
# Elements walked when choosing the sample. Index order is still the full
# filtered order; this only bounds the time spent measuring boxes.
_FINGERPRINT_SCAN_LIMIT = 20_000
# Nested @import depth followed, in the page and in fetched text alike.
_MAX_IMPORT_DEPTH = 8
_FETCH_TIMEOUT_MS = 10_000
# Fetched sheet texts kept for the whole scan. Beyond this new results are
# still used, just not kept.
_MAX_CACHE_BYTES = 32_000_000


@dataclass(frozen=True)
class CapturedSheet:
    """One stylesheet's rules as text, ready to concatenate."""

    css: str
    #: The top-level sheet's own media text ('' for all media).
    media: str
    #: Where the rules came from; ``None`` for inline and constructed sheets.
    source_url: str | None


@dataclass(frozen=True)
class StyleSnapshot:
    """A page's CSS and fingerprint, taken at one moment."""

    sheets: tuple[CapturedSheet, ...]
    #: False when a bound was hit or a sheet could not be read or fetched.
    complete: bool
    #: ``{"scheme": "light"|"dark", "forced_colors": bool, "samples": [...]}``.
    fingerprint: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SheetRef:
    """One stored sheet: its blob hash, top-level media and origin."""

    sha256: str
    media: str
    source_url: str | None


@dataclass(frozen=True)
class StoredStyles:
    """What ``saved_copy_styles`` holds for one saved copy."""

    sheets: tuple[SheetRef, ...]
    complete: bool
    fingerprint: dict[str, Any] = field(default_factory=dict)


# One evaluate returns both the CSS parts and the fingerprint, so they describe
# the same moment. Parts are in cascade order. A "text" part is rules the page
# could read; a "fetch" part names a sheet the page could not read, for Python
# to fetch. ``wrappers`` are the conditions of the @import chain that led to a
# part, outermost first.
#
# The fingerprint filter (skipped tags, element order) must stay identical to
# ``fingerprintElements`` in src/audit/web/frontend/src/lib/styleFingerprint.ts:
# the inspector looks each sample up by its index in that same order.
_SNAPSHOT_JS = """
(opts) => {
  const parts = [];
  let total = 0;
  let incomplete = false;
  const docBase = document.baseURI;
  const push = (part) => {
    if (parts.length >= opts.maxSheets) { incomplete = true; return; }
    parts.push(part);
  };
  const importWrappers = (rule) => {
    const out = [];
    const media = rule.media ? rule.media.mediaText : '';
    if (media && media !== 'all') out.push({kind: 'media', text: media});
    if (rule.supportsText) out.push({kind: 'supports', text: rule.supportsText});
    if (rule.layerName !== null && rule.layerName !== undefined) {
      out.push({kind: 'layer', text: rule.layerName});
    }
    return out;
  };
  const walk = (sheet, media, wrappers, depth) => {
    const href = sheet.href || null;
    let rules = null;
    try { rules = sheet.cssRules; } catch (e) { rules = null; }
    if (rules === null) {
      if (href) push({kind: 'fetch', href, media, wrappers});
      else incomplete = true;
      return;
    }
    const base = href || docBase;
    let chunk = [];
    let size = 0;
    let over = false;
    const flush = () => {
      if (over) incomplete = true;
      else if (chunk.length) {
        if (total + size > opts.maxPageChars) incomplete = true;
        else {
          total += size;
          push({kind: 'text', text: chunk.join('\\n'), base, href, media, wrappers});
        }
      }
      chunk = []; size = 0; over = false;
    };
    for (const rule of rules) {
      if (rule.type === 3) {
        flush();
        if (depth >= opts.maxDepth) { incomplete = true; continue; }
        const inner = wrappers.concat(importWrappers(rule));
        if (rule.styleSheet) walk(rule.styleSheet, media, inner, depth + 1);
        else if (rule.href) {
          push({kind: 'fetch', href: new URL(rule.href, base).href, media, wrappers: inner});
        }
        else incomplete = true;
        continue;
      }
      if (rule.type === 2) continue;
      if (over) continue;
      const text = rule.cssText;
      size += text.length + 1;
      if (size > opts.maxSheetChars) { over = true; chunk = []; continue; }
      chunk.push(text);
    }
    flush();
  };
  for (const sheet of Array.from(document.styleSheets)) {
    if (sheet.disabled) continue;
    walk(sheet, sheet.media ? sheet.media.mediaText : '', [], 0);
  }
  for (const sheet of Array.from(document.adoptedStyleSheets || [])) {
    if (sheet.disabled) continue;
    walk(sheet, sheet.media ? sheet.media.mediaText : '', [], 0);
  }

  const SKIP = new Set(['noscript', 'script', 'style', 'template', 'link']);
  const elements = [];
  if (document.body) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, {
      acceptNode: (n) =>
        SKIP.has(n.localName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    let node;
    while ((node = walker.nextNode())) elements.push(node);
  }
  const tiers = [[], [], []];
  const limit = Math.min(elements.length, opts.scanLimit);
  for (let i = 0; i < limit; i++) {
    const el = elements[i];
    const box = el.getBoundingClientRect();
    const hasBox = box.width > 0 && box.height > 0;
    const hasText = Array.from(el.childNodes).some(
      (c) => c.nodeType === 3 && /\\S/.test(c.nodeValue || ''));
    tiers[hasBox && hasText ? 0 : hasBox ? 1 : 2].push(i);
  }
  const even = (list, n) => {
    if (list.length <= n) return list.slice();
    const out = [];
    for (let k = 0; k < n; k++) out.push(list[Math.floor(k * list.length / n)]);
    return out;
  };
  let picked = [];
  for (const tier of tiers) {
    if (picked.length >= opts.samples) break;
    picked = picked.concat(even(tier, opts.samples - picked.length));
  }
  picked.sort((a, b) => a - b);
  const firstFamily = (value) => {
    const first = (value || '').split(',')[0] || '';
    return first.trim().replace(/^["']|["']$/g, '').toLowerCase();
  };
  const samples = picked.map((index) => {
    const cs = getComputedStyle(elements[index]);
    return {
      index,
      fontFamily: firstFamily(cs.fontFamily),
      fontWeight: cs.fontWeight,
      color: cs.color,
      backgroundColor: cs.backgroundColor,
      textDecorationLine: cs.textDecorationLine,
    };
  });
  const fingerprint = {
    scheme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
    forced_colors: matchMedia('(forced-colors: active)').matches,
    samples,
  };
  return {parts, incomplete, fingerprint};
}
"""


# ---------------------------------------------------------------------------
# Pure CSS text helpers (unit tested)
# ---------------------------------------------------------------------------

_URL_RE = re.compile(
    r"""url\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|([^)"'\s]*))\s*\)""",
    re.IGNORECASE,
)
_CHARSET_RE = re.compile(r"""@charset\s+(?:"[^"]*"|'[^']*')\s*;""", re.IGNORECASE)
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_IMPORT_RE = re.compile(
    r"""@import\s+(?:url\(\s*(?:"([^"]*)"|'([^']*)'|([^)"'\s]*))\s*\)|"([^"]*)"|'([^']*)')"""
    r"""\s*([^;]*);""",
    re.IGNORECASE,
)
# Schemes an absolute url() may already carry; left untouched.
_ABSOLUTE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _css_string(value: str) -> str:
    """Quote ``value`` as a CSS string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\a ")
    return f'"{escaped}"'


def absolutize_urls(css: str, base: str | None) -> str:
    """Rewrite every relative ``url(...)`` in ``css`` against ``base``.

    Absolute URLs (any scheme, including ``data:``), protocol-relative ones
    resolved the same way a browser would, and fragment-only references such
    as ``url(#clip)`` (an SVG reference into the document itself) are handled
    so the result means exactly what the sheet meant where it was loaded.
    Without a usable http(s) ``base`` the text is returned unchanged.
    """
    if not base or urlsplit(base).scheme not in {"http", "https"}:
        return css

    def replace(match: re.Match[str]) -> str:
        raw = next((g for g in match.groups() if g is not None), "")
        value = re.sub(r"\\(.)", r"\1", raw).strip()
        if not value or value.startswith("#") or _ABSOLUTE_RE.match(value):
            return match.group(0)
        return f"url({_css_string(urljoin(base, value))})"

    return _URL_RE.sub(replace, css)


def strip_charset(css: str) -> str:
    """Drop ``@charset`` rules: only valid first in a file, and meaningless in text."""
    return _CHARSET_RE.sub("", css)


def wrap_conditions(css: str, wrappers: list[dict[str, str]]) -> str:
    """Wrap ``css`` in the conditions of an ``@import`` chain, outermost first.

    ``media`` becomes ``@media``, ``supports`` becomes ``@supports (...)`` and
    ``layer`` becomes ``@layer name`` (an empty name is an anonymous layer, as
    a bare ``layer`` keyword on the import is).
    """
    for wrapper in reversed(wrappers):
        kind = wrapper.get("kind")
        text = (wrapper.get("text") or "").strip()
        if kind == "media" and text and text.lower() != "all":
            css = f"@media {text} {{\n{css}\n}}"
        elif kind == "supports" and text:
            condition = text if text.startswith("(") else f"({text})"
            css = f"@supports {condition} {{\n{css}\n}}"
        elif kind == "layer":
            css = f"@layer {text} {{\n{css}\n}}" if text else f"@layer {{\n{css}\n}}"
    return css


def parse_import_conditions(tail: str) -> list[dict[str, str]]:
    """The conditions written after an ``@import`` URL, as wrappers.

    ``layer``, ``layer(name)``, ``supports(...)`` and a media query list, in
    the order :func:`wrap_conditions` expects (media outermost).
    """
    rest = tail.strip()
    layer: str | None = None
    supports: str | None = None
    match = re.match(r"layer(?:\(\s*([^)]*?)\s*\))?(?=\s|$)", rest, re.IGNORECASE)
    if match:
        layer = match.group(1) or ""
        rest = rest[match.end() :].strip()
    if rest.lower().startswith("supports("):
        depth = 0
        for index, char in enumerate(rest):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    supports = rest[len("supports(") : index].strip()
                    rest = rest[index + 1 :].strip()
                    break
    out: list[dict[str, str]] = []
    if rest and rest.lower() != "all":
        out.append({"kind": "media", "text": rest})
    if supports:
        out.append({"kind": "supports", "text": supports})
    if layer is not None:
        out.append({"kind": "layer", "text": layer})
    return out


def split_imports(css: str) -> tuple[list[tuple[str, list[dict[str, str]]]], str]:
    """Separate a raw sheet's leading ``@import`` rules from its other rules.

    Returns ``([(url, conditions), ...], rest)``. Only imports before the first
    other rule count, as in a browser; later ones are invalid and are dropped
    from ``rest`` all the same.
    """
    text = strip_charset(_COMMENT_RE.sub("", css))
    imports: list[tuple[str, list[dict[str, str]]]] = []
    position = 0
    while True:
        while position < len(text) and text[position].isspace():
            position += 1
        match = _IMPORT_RE.match(text, position)
        if match is None:
            break
        url = next((g for g in match.groups()[:5] if g is not None), "")
        imports.append((url, parse_import_conditions(match.group(6) or "")))
        position = match.end()
    rest = _IMPORT_RE.sub("", text[position:])
    return imports, rest


def concatenate(sheets: list[tuple[str, str]]) -> str:
    """Join ``(css, media)`` pairs in order, wrapping each one that has media."""
    out: list[str] = []
    for css, media in sheets:
        media = media.strip()
        if media and media.lower() != "all":
            out.append(f"@media {media} {{\n{css}\n}}")
        else:
            out.append(css)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Fetching sheets the page could not read
# ---------------------------------------------------------------------------


class SheetCache:
    """Cross-origin sheet texts fetched during one scan, keyed by URL.

    One instance per crawl. Results are processed text (imports inlined, URLs
    absolute) or ``None`` for an HTTP failure; a request that raised is not
    kept, because it may have failed only because its page closed. Concurrent
    callers asking for one URL share a single request.
    """

    def __init__(self, *, max_bytes: int = _MAX_CACHE_BYTES) -> None:
        self._done: dict[str, str | None] = {}
        self._pending: dict[str, asyncio.Future[str | None]] = {}
        self._bytes = 0
        self._max_bytes = max_bytes

    async def get(self, request: APIRequestContext, url: str, depth: int = 0) -> str | None:
        if url in self._done:
            return self._done[url]
        pending = self._pending.get(url)
        if pending is not None:
            return await asyncio.shield(pending)
        future: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        self._pending[url] = future
        keep = True
        try:
            text = await self._fetch(request, url, depth)
        except Exception as exc:
            keep = False
            text = None
            log.debug("styles.fetch_failed", error_type=type(exc).__name__)
        finally:
            self._pending.pop(url, None)
        if keep and (text is None or self._bytes + len(text) <= self._max_bytes):
            self._done[url] = text
            self._bytes += len(text or "")
        future.set_result(text)
        return text

    async def _fetch(self, request: APIRequestContext, url: str, depth: int) -> str | None:
        if urlsplit(url).scheme not in {"http", "https"}:
            return None
        response = await request.get(url, timeout=_FETCH_TIMEOUT_MS, max_redirects=5)
        try:
            if not response.ok:
                return None
            length = response.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_SHEET_BYTES:
                return None
            body = await response.body()
        finally:
            await response.dispose()
        if len(body) > MAX_SHEET_BYTES:
            return None
        raw = body.decode("utf-8", errors="replace")
        imports, rest = split_imports(raw)
        pieces: list[str] = []
        for href, conditions in imports:
            if depth >= _MAX_IMPORT_DEPTH:
                return None
            inner = await self.get(request, urljoin(url, href), depth + 1)
            if inner is None:
                return None
            pieces.append(wrap_conditions(inner, conditions))
        pieces.append(absolutize_urls(rest, url))
        text = "\n".join(piece for piece in pieces if piece.strip())
        if len(text.encode("utf-8")) > MAX_SHEET_BYTES:
            return None
        return text


# ---------------------------------------------------------------------------
# The capture
# ---------------------------------------------------------------------------


async def capture_styles(page: Page, cache: SheetCache) -> StyleSnapshot | None:
    """Read ``page``'s CSS and fingerprint. ``None`` when nothing could be read.

    Never raises. The caller decides whether this scan stores saved copies.
    """
    try:
        raw = await page.evaluate(
            _SNAPSHOT_JS,
            {
                "maxSheets": MAX_SHEETS,
                "maxSheetChars": MAX_SHEET_BYTES,
                "maxPageChars": MAX_PAGE_BYTES,
                "maxDepth": _MAX_IMPORT_DEPTH,
                "samples": FINGERPRINT_SAMPLES,
                "scanLimit": _FINGERPRINT_SCAN_LIMIT,
            },
        )
        return await build_snapshot(raw, lambda url: cache.get(page.context.request, url))
    except Exception as exc:
        log.warning("styles.capture_failed", error_type=type(exc).__name__)
        return None


async def build_snapshot(raw: Any, fetch: Any) -> StyleSnapshot | None:
    """Turn the evaluate result into a bounded :class:`StyleSnapshot`.

    ``fetch`` is an async ``url -> text | None`` for sheets the page could not
    read. Separate from :func:`capture_styles` so the bounds and ordering can
    be tested without a browser.
    """
    if not isinstance(raw, dict):
        return None
    complete = not raw.get("incomplete")
    sheets: list[CapturedSheet] = []
    total = 0
    for part in raw.get("parts") or []:
        if not isinstance(part, dict):
            complete = False
            continue
        if len(sheets) >= MAX_SHEETS:
            complete = False
            break
        wrappers = [w for w in part.get("wrappers") or [] if isinstance(w, dict)]
        href = part.get("href") or None
        if part.get("kind") == "fetch":
            if not href:
                complete = False
                continue
            fetched = await fetch(href)
            if fetched is None:
                complete = False
                continue
            css = fetched
        elif part.get("kind") == "text":
            css = absolutize_urls(strip_charset(str(part.get("text") or "")), part.get("base"))
        else:
            complete = False
            continue
        css = wrap_conditions(css, wrappers)
        size = len(css.encode("utf-8"))
        if size > MAX_SHEET_BYTES or total + size > MAX_PAGE_BYTES:
            complete = False
            continue
        total += size
        sheets.append(CapturedSheet(css=css, media=str(part.get("media") or ""), source_url=href))
    fingerprint = raw.get("fingerprint")
    return StyleSnapshot(
        sheets=tuple(sheets),
        complete=complete,
        fingerprint=fingerprint if isinstance(fingerprint, dict) else {},
    )
