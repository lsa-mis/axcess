"""A flagged link that wraps onto two lines gets one box per line.

The box went around the link's bounding rectangle: for a link that starts
late on one line and ends early on the next, that is one big rectangle over
both lines and all the text beside them, so the reader could not see which
words are the link. Now each line of the link has its own ring, the rest of
the page is dimmed once around them, and the number label sits on the first
line.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import DOC, open_inspector, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

CAPTURE = (
    "<!doctype html><html><head><title>Wrapped link fixture</title></head>"
    "<body style='margin:0'><div style='height:300px'></div>"
    "<p style='width:320px;margin-left:100px;font:16px/24px sans-serif'>"
    "Our opening hours change in winter, so please "
    "<a id='wrapped' href='/hours'>read the full list of opening hours for every branch</a> "
    "before you visit the library.</p>"
    "<div style='height:1200px'></div></body></html>"
)

# Each line of the link and each drawn ring, and where the label is.
_LINES = f"""() => {{
  const doc = {DOC};
  const lines = Array.from(doc.getElementById('wrapped').getClientRects())
    .filter((r) => r.width > 0);
  const box = doc.getElementById('axcess-spotlight');
  const rings = Array.from(box.querySelectorAll('[data-axcess-line]'))
    .map((el) => el.getBoundingClientRect());
  const label = box.firstElementChild.getBoundingClientRect();
  const plain = (r) => ({{left: r.left, top: r.top, right: r.right, bottom: r.bottom}});
  return {{lines: lines.map(plain), rings: rings.map(plain), label: plain(label)}};
}}"""


async def test_each_line_of_a_wrapped_link_gets_its_own_box(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(
        db_path,
        scan_id,
        CAPTURE,
        "link-name",
        [
            (
                "#wrapped",
                '<a id="wrapped" href="/hours">'
                "read the full list of opening hours for every branch</a>",
            )
        ],
    )
    page = await open_inspector(new_page, base, scan_id, page_id, "link-name")
    try:
        box = page.frame_locator("iframe[title^='Saved copy']").locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("Flagged element")
        await settled(page)
        found = await page.evaluate(_LINES)
        lines, rings, label = found["lines"], found["rings"], found["label"]
        assert len(lines) == 2, lines
        # One ring per line, each around its line and not much bigger.
        assert len(rings) == len(lines), found
        for line, ring in zip(lines, rings, strict=True):
            assert ring["left"] <= line["left"] and line["right"] <= ring["right"], found
            assert ring["top"] <= line["top"] and line["bottom"] <= ring["bottom"], found
            assert ring["right"] - ring["left"] <= line["right"] - line["left"] + 16, found
        # The label is on the first line, not at the left of the paragraph.
        assert abs(label["left"] - lines[0]["left"]) <= 12, found
        assert label["bottom"] <= lines[0]["top"] + 4, found
    finally:
        await page.context.close()
