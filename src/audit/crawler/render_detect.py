"""Cheap heuristic for deciding whether a page needs Playwright rendering.

Only the static HTML body is inspected. If any of these hold we upgrade to JS:
  * the document has fewer than :data:`MIN_BODY_NODE_COUNT` DOM nodes
  * a ``<noscript>`` tag contains a ``<meta http-equiv="refresh">`` redirect
  * the page exposes a known SPA bootstrap hint (``__NEXT_DATA__``,
    ``__NUXT__``, ``window.__INITIAL_STATE__``) but shows an effectively-empty
    mount point (``<div id="root">``/``<div id="app">`` with no children)
"""

from __future__ import annotations

from selectolax.parser import HTMLParser

MIN_BODY_NODE_COUNT = 15

_SPA_SIGNALS = (
    b"__NEXT_DATA__",
    b"__NUXT__",
    b"window.__INITIAL_STATE__",
    b"ng-version=",
)
_SPA_MOUNT_IDS = ("root", "app", "__next", "__nuxt")


def is_js_only(body: bytes) -> bool:
    """Return True if the static body is unlikely to carry final content."""
    if not body:
        return False
    tree = HTMLParser(body)
    body_node = tree.body
    if body_node is None:
        return False

    node_count = sum(1 for _ in body_node.traverse(include_text=False))
    if node_count < MIN_BODY_NODE_COUNT:
        return True

    if _has_noscript_meta_refresh(tree):
        return True

    has_signal = any(sig in body for sig in _SPA_SIGNALS)
    return bool(has_signal and _mount_is_empty(tree))


def _has_noscript_meta_refresh(tree: HTMLParser) -> bool:
    for ns in tree.css("noscript"):
        for meta in ns.css("meta"):
            if (meta.attributes.get("http-equiv") or "").lower() == "refresh":
                return True
    return False


def _mount_is_empty(tree: HTMLParser) -> bool:
    for mount_id in _SPA_MOUNT_IDS:
        node = tree.css_first(f"#{mount_id}")
        if node is None:
            continue
        children = [c for c in node.iter() if c.tag != "-text"]
        if not children:
            return True
    return False
