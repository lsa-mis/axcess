"""A flagged element cut off by a part of the page that does not scroll.

A carousel shows one slide and hides the rest with ``overflow: hidden``; a
menu bar cuts off an item that does not fit. The box was drawn around the
whole element, over the slide or the items beside it, so it marked what the
reader could see instead of the flagged element. Now the box covers only the
part that shows, and the table says the part of the page around it hides the
rest; when none of it shows there is no box. An element the browser does
not cut off (a menu placed by a positioned ancestor outside the clipping
part) keeps its whole box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import BOX_RECT, fact, open_inspector, rect_of, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

CAPTURE = (
    "<!doctype html><html><head><title>Clipped fixture</title></head>"
    "<body style='margin:0;font:16px/24px sans-serif'>"
    "<div style='height:200px'></div>"
    # A carousel: three 300 pixel slides in a 300 pixel window.
    "<div id='carousel' style='width:300px;overflow:hidden;margin-left:100px'>"
    "<div style='display:flex;width:900px'>"
    "<div style='width:300px;height:150px'>Slide one</div>"
    "<div style='width:300px;height:150px'>Slide two</div>"
    "<div style='width:300px;height:150px'><a id='slide' href='/three'>Slide three</a></div>"
    "</div></div>"
    "<div style='height:300px'></div>"
    # A menu bar that cuts off its last item.
    "<nav id='bar' style='width:260px;overflow:hidden;white-space:nowrap;margin-left:100px'>"
    "<a href='/a' style='display:inline-block;width:120px'>Home</a>"
    "<a id='cut' href='/b' style='display:inline-block;width:200px'>Opening hours</a></nav>"
    "<div style='height:300px'></div>"
    # A dropdown placed by a positioned ancestor outside its clipping parent:
    # the browser does not cut it off.
    "<div style='position:relative;margin-left:100px'>"
    "<div style='height:40px;overflow:hidden'>Menu"
    "<ul id='drop' style='position:absolute;top:60px;left:0;margin:0;width:200px'>"
    "<li>Open</li><li>Save</li></ul></div></div>"
    "<div style='height:900px'></div></body></html>"
)

FINDINGS = [
    ("#slide", '<a id="slide" href="/three">Slide three</a>'),
    ("#cut", '<a id="cut" href="/b" style="display:inline-block;width:200px">Opening hours</a>'),
    ("#drop", '<ul id="drop" style="position:absolute;top:60px;left:0;margin:0;width:200px">'),
]


def _box_within(container: str, element: str) -> str:
    """True when the box is drawn, and fits the element's shown part."""
    return f"""() => {{
  const b = ({BOX_RECT})();
  if (!b) return false;
  const c = {container};
  const e = {element};
  const left = Math.max(c.left, e.left), right = Math.min(c.right, e.right);
  return b.left <= left && right <= b.right && b.right <= right + 8 && b.top <= e.top;
}}"""


async def test_the_box_covers_only_what_a_clipping_part_shows(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(db_path, scan_id, CAPTURE, "link-name", FINDINGS)
    page = await open_inspector(new_page, base, scan_id, page_id, "link-name")
    try:
        group = page.get_by_role("group", name="Flagged elements", exact=True)
        box = page.frame_locator("iframe[title^='Saved copy']").locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("1 of 3")

        # The third slide: hidden by the carousel, so no box.
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "No box. The part of the page around it hides it (overflow: hidden)."
        )
        await settled(page)
        assert await page.evaluate(f"({BOX_RECT})()") is None

        # The cut-off menu item: the box ends where the menu bar does.
        await group.get_by_role("button", name="Next flagged element").click()
        await playwright_async.expect(box).to_have_text("2 of 3")
        await settled(page)
        assert await page.evaluate(_box_within(rect_of("#bar"), rect_of("#cut")))
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "Around the part that shows. The part of the page around it hides the rest "
            "(overflow: hidden)."
        )

        # The dropdown the browser does not cut off: its whole box.
        await group.get_by_role("button", name="Next flagged element").click()
        await playwright_async.expect(box).to_have_text("3 of 3")
        await settled(page)
        assert await page.evaluate(_box_within(rect_of("#drop"), rect_of("#drop")))
        await playwright_async.expect(fact(page, "Where the box is")).to_have_count(0)
    finally:
        await page.context.close()
