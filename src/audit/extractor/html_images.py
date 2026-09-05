"""Pull image references out of a rendered HTML body.

Covers ``<img>`` (including ``srcset``) and ``<picture><source>`` (both ``src``
and ``srcset``). Every candidate is kept, e.g. all four entries in
``srcset="a.png 1x, b.png 2x"`` become separate refs, because art-direction
``<picture>`` setups really can swap in completely different images. Bytes-level
dedupe happens later against the blob store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from selectolax.parser import HTMLParser, Node


@dataclass(frozen=True)
class ImageRef:
    """One image reference found while walking a page's DOM."""

    url: str
    position: int
    alt: str | None
    role: str | None
    aria_label: str | None
    aria_labelledby: str | None
    figcaption: str | None
    context_snippet: str | None
    via_srcset: bool
    via_picture: bool


def extract_image_refs(body: bytes, base_url: str) -> list[ImageRef]:
    """Return every image reference on the page, in document order."""
    tree = HTMLParser(body)
    refs: list[ImageRef] = []
    position = 0

    for node in _ordered_image_sources(tree):
        for url, via_srcset in _urls_from_node(node):
            resolved = _safe_urljoin(base_url, url)
            if resolved is None:
                continue
            refs.append(
                ImageRef(
                    url=resolved,
                    position=position,
                    alt=_alt_text(node),
                    role=_attr(node, "role"),
                    aria_label=_attr(node, "aria-label"),
                    aria_labelledby=_attr(node, "aria-labelledby"),
                    figcaption=_figcaption_for(node),
                    context_snippet=_snippet_for(node),
                    via_srcset=via_srcset,
                    via_picture=_inside_picture(node),
                )
            )
            position += 1
    return refs


def _ordered_image_sources(tree: HTMLParser) -> list[Node]:
    """Walk ``img`` + ``source`` (inside picture) elements in document order."""
    body = tree.body
    if body is None:
        return []
    nodes = body.css("img, picture > source")
    return list(nodes)


def _urls_from_node(node: Node) -> list[tuple[str, bool]]:
    """Return ``[(url, via_srcset)]`` for all image URLs on a single node."""
    out: list[tuple[str, bool]] = []
    src = _attr(node, "src")
    if src:
        out.append((src, False))
    for candidate in _parse_srcset(_attr(node, "srcset")):
        out.append((candidate, True))
    return out


_SRCSET_SEP = re.compile(r",\s*")


def _parse_srcset(raw: str | None) -> list[str]:
    """Return just the URL portion of each srcset candidate."""
    if not raw:
        return []
    urls: list[str] = []
    for part in _SRCSET_SEP.split(raw.strip()):
        if not part:
            continue
        # A candidate is "url [descriptor]"; the URL is whitespace-delimited.
        url = part.strip().split(None, 1)[0]
        if url:
            urls.append(url)
    return urls


def _attr(node: Node, name: str) -> str | None:
    value = node.attributes.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _alt_text(node: Node) -> str | None:
    # <source> elements have no alt; only <img> does.
    if node.tag != "img":
        return None
    # selectolax maps alt="" to a None value, while a missing attribute is
    # absent from the dict entirely. That distinction matters for WCAG:
    # missing alt is a failure, alt="" is a decorative image declaration.
    if "alt" not in node.attributes:
        return None
    value = node.attributes.get("alt")
    return value if value is not None else ""


def _inside_picture(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.tag == "picture":
            return True
        parent = parent.parent
    return False


def _figcaption_for(node: Node) -> str | None:
    parent = node.parent
    while parent is not None:
        if parent.tag == "figure":
            cap = parent.css_first("figcaption")
            if cap is None:
                return None
            text = (cap.text() or "").strip()
            return text or None
        parent = parent.parent
    return None


_SNIPPET_CHARS = 200


def _snippet_for(node: Node) -> str | None:
    parent = node.parent
    if parent is None:
        return None
    text = (parent.text() or "").strip()
    if not text:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= _SNIPPET_CHARS:
        return collapsed
    return collapsed[:_SNIPPET_CHARS].rstrip() + "…"


def _safe_urljoin(base: str, url: str) -> str | None:
    url = url.strip()
    if not url or url.startswith("data:") or url.startswith("javascript:"):
        return None
    try:
        return urljoin(base, url)
    except ValueError:
        return None
