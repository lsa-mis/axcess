"""The location outline drawn onto per-finding element screenshots.

The marker must frame the reported element without painting over it, so
a reviewer can still read what was flagged. These tests pin that contract
on synthetic images; the Playwright capture path is covered in
``tests/integration/test_screenshot_capture.py``.
"""

from __future__ import annotations

import io

from PIL import Image

from audit.crawler.js_fetcher import _draw_issue_outline

RED = (190, 0, 30)
WHITE = (255, 255, 255)


def _png(width: int, height: int, color: tuple[int, int, int] = WHITE) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return output.getvalue()


def _red_pixels(png: bytes) -> list[tuple[int, int]]:
    image = Image.open(io.BytesIO(png)).convert("RGB")
    return [
        (x, y)
        for y in range(image.height)
        for x in range(image.width)
        if image.getpixel((x, y)) == RED
    ]


def test_outline_frames_the_element_without_covering_it() -> None:
    marked = _draw_issue_outline(_png(200, 120), left=60, top=40, width=80, height=30)

    red = _red_pixels(marked)
    assert red
    assert not [(x, y) for x, y in red if 60 <= x < 140 and 40 <= y < 70]
    xs = [x for x, _ in red]
    ys = [y for _, y in red]
    # All four sides are drawn, each within a few pixels of the element.
    assert 60 - 12 <= min(xs) < 60
    assert 140 <= max(xs) <= 140 + 12
    assert 40 - 12 <= min(ys) < 40
    assert 70 <= max(ys) <= 70 + 12


def test_outline_follows_the_element_extent_not_a_fixed_size() -> None:
    marked = _draw_issue_outline(_png(900, 120), left=60, top=40, width=700, height=30)

    xs = [x for x, _ in _red_pixels(marked)]
    assert min(xs) < 60
    assert max(xs) >= 760


def test_white_halo_keeps_the_outline_visible_on_a_dark_page() -> None:
    marked = _draw_issue_outline(_png(200, 120, (0, 0, 0)), left=60, top=40, width=80, height=30)

    image = Image.open(io.BytesIO(marked)).convert("RGB")
    row = [image.getpixel((x, 55)) for x in range(40, 60)]
    red_at = row.index(RED)
    assert WHITE in row[:red_at]
    assert WHITE in row[red_at:]


def test_element_at_the_image_edge_is_clamped_not_dropped() -> None:
    marked = _draw_issue_outline(_png(100, 60), left=0, top=0, width=50, height=20)

    red = _red_pixels(marked)
    assert any(x > 50 for x, _ in red)
    assert any(y > 20 for _, y in red)


def test_element_larger_than_the_capture_is_framed_by_the_border() -> None:
    marked = _draw_issue_outline(_png(100, 60), left=-10, top=-10, width=300, height=300)

    assert _red_pixels(marked)


def test_element_outside_the_image_leaves_the_capture_unmarked() -> None:
    original = _png(100, 60)

    assert _draw_issue_outline(original, left=500, top=0, width=40, height=20) == original
    assert _draw_issue_outline(original, left=0, top=-50, width=40, height=20) == original
