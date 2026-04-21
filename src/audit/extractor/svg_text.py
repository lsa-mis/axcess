"""Detect inline ``<svg>`` elements that contain visible ``<text>``.

Inline SVG text is rendered as a raster image by the browser — it's an
"image of text" even though there's no image file to download. Per the spec
we flag these as findings immediately and skip OCR.

Only rendered ``<text>`` counts. ``<title>`` and ``<desc>`` are part of the
SVG accessible-name algorithm, not visible text, so we ignore them.
"""

from __future__ import annotations

from dataclasses import dataclass

from selectolax.parser import HTMLParser, Node


@dataclass(frozen=True)
class InlineSvgTextHit:
    """One inline SVG on the page that contains rendered text."""

    position: int
    visible_text: str
    alt_context: str | None
    """Best-effort accessible name (``aria-label`` or first ``<title>``)."""


def find_inline_svg_text(body: bytes) -> list[InlineSvgTextHit]:
    """Return one hit per top-level inline ``<svg>`` with non-empty ``<text>`` content.

    Nested ``<svg>`` elements are ignored — we only report the outermost one
    so a single composition doesn't generate multiple findings.
    """
    tree = HTMLParser(body)
    body_node = tree.body
    if body_node is None:
        return []

    out: list[InlineSvgTextHit] = []
    position = 0
    for node in body_node.css("svg"):
        if _has_svg_ancestor(node):
            continue
        visible = _collect_text(node)
        if not visible:
            continue
        out.append(
            InlineSvgTextHit(
                position=position,
                visible_text=visible,
                alt_context=_accessible_name(node),
            )
        )
        position += 1
    return out


def _has_svg_ancestor(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.tag == "svg":
            return True
        parent = parent.parent
    return False


def _collect_text(svg_node: Node) -> str:
    parts: list[str] = []
    for child in svg_node.css("text"):
        raw = child.text() or ""
        text = " ".join(raw.split())
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def _accessible_name(svg_node: Node) -> str | None:
    aria = svg_node.attributes.get("aria-label")
    if aria:
        aria = aria.strip()
        if aria:
            return aria
    title = svg_node.css_first("title")
    if title is not None:
        text = (title.text() or "").strip()
        if text:
            return text
    return None
