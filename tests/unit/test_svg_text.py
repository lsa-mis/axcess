"""Unit tests for inline SVG text detection."""

from __future__ import annotations

from audit.extractor.svg_text import find_inline_svg_text


def _doc(body: str) -> bytes:
    return f"<!doctype html><html><body>{body}</body></html>".encode()


def test_svg_with_text_is_flagged() -> None:
    html = _doc(
        '<svg width="100" height="40" xmlns="http://www.w3.org/2000/svg">'
        '<text x="10" y="20">Buy now</text>'
        "</svg>"
    )
    hits = find_inline_svg_text(html)
    assert len(hits) == 1
    assert hits[0].visible_text == "Buy now"


def test_svg_with_empty_text_not_flagged() -> None:
    html = _doc("<svg><text></text></svg>")
    assert find_inline_svg_text(html) == []


def test_svg_without_any_text_not_flagged() -> None:
    html = _doc('<svg><rect width="10" height="10"></rect></svg>')
    assert find_inline_svg_text(html) == []


def test_svg_title_and_desc_ignored() -> None:
    """<title> and <desc> are accessible-name metadata, not visible text."""
    html = _doc("<svg><title>Chart icon</title><desc>A small chart</desc></svg>")
    assert find_inline_svg_text(html) == []


def test_multiple_text_children_joined() -> None:
    html = _doc("<svg><text>Sign</text><text>up</text></svg>")
    hits = find_inline_svg_text(html)
    assert len(hits) == 1
    assert hits[0].visible_text == "Sign up"


def test_accessible_name_from_aria_label() -> None:
    html = _doc('<svg aria-label="Button"><text>Go</text></svg>')
    hit = find_inline_svg_text(html)[0]
    assert hit.alt_context == "Button"


def test_accessible_name_from_title_fallback() -> None:
    html = _doc("<svg><title>Icon name</title><text>Go</text></svg>")
    hit = find_inline_svg_text(html)[0]
    assert hit.alt_context == "Icon name"


def test_accessible_name_absent() -> None:
    html = _doc("<svg><text>Go</text></svg>")
    hit = find_inline_svg_text(html)[0]
    assert hit.alt_context is None


def test_multiple_svgs_track_position() -> None:
    html = _doc(
        "<svg><text>One</text></svg>"
        "<svg><rect/></svg>"  # no text → skipped
        "<svg><text>Two</text></svg>"
    )
    hits = find_inline_svg_text(html)
    positions = [h.position for h in hits]
    visible = [h.visible_text for h in hits]
    assert positions == [0, 1]
    assert visible == ["One", "Two"]
