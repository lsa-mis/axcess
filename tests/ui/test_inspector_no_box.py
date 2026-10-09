"""The numbered box is drawn on an element that has no box of its own.

Three kinds of element are never drawn themselves: one styled
``display: contents`` (its children are drawn, it is not), an ``<option>``
inside a closed ``<select>``, and an ``<area>`` of an image map. The first two
report an empty rectangle at the frame's top-left, and the box jumped there,
over whatever the page had in that corner; the area reports an empty point at
its image's corner, so the box was a small square there. The box now goes
around what the reader sees for each: the children, the list box, or the part
of the image the area covers, and the table under the toolbar says which.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import BOX_RECT, DOC, fact, open_inspector, rect_of, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

IMAGE = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='120'%3E"
    "%3Crect width='240' height='120' fill='%23ccc'/%3E%3C/svg%3E"
)
CAPTURE = (
    "<!doctype html><html><head><title>No box fixture</title></head>"
    "<body style='margin:0'>"
    "<p style='margin:0;height:40px'>Top of the page</p>"
    "<div style='height:500px'></div>"
    "<div id='wrap' style='margin-left:200px'>"
    "<div id='contents' style='display:contents'>"
    "<button type='button'>One</button> <button type='button'>Two</button></div></div>"
    "<div style='height:500px'></div>"
    "<p style='margin-left:300px'><select id='pick' aria-label='Fruit'>"
    "<option>Pear</option><option id='opt'>Apple</option></select></p>"
    "<div style='height:500px'></div>"
    f"<p style='margin-left:400px'><img id='pic' usemap='#map' src=\"{IMAGE}\" "
    "alt='Floor plan' width='240' height='120' style='display:block'>"
    "<map name='map'><area id='spot' shape='rect' coords='0,0,120,120' href='/room'></map></p>"
    "<div style='height:500px'></div>"
    "</body></html>"
)

FINDINGS = [
    ("#contents", '<div id="contents" style="display:contents">'),
    ("#opt", '<option id="opt">Apple</option>'),
    ("#spot", '<area id="spot" shape="rect" coords="0,0,120,120" href="/room">'),
]


def _around(stand_in: str) -> str:
    """True when the drawn box is around the stand-in's rectangle."""
    return f"""() => {{
  const b = ({BOX_RECT})();
  if (!b) return false;
  const e = {stand_in};
  return e.width > 0 && b.left <= e.left && b.top <= e.top
    && e.right <= b.right && e.bottom <= b.bottom
    && b.right - b.left < e.width + 30 && b.bottom - b.top < e.height + 30;
}}"""


# The union of the two buttons, the display: contents element's children.
_BUTTONS = f"""(() => {{
  const [a, b] = Array.from({DOC}.querySelectorAll('#contents > button'))
    .map((el) => el.getBoundingClientRect());
  const top = Math.min(a.top, b.top), bottom = Math.max(a.bottom, b.bottom);
  return {{left: a.left, top, right: b.right, bottom,
    width: b.right - a.left, height: bottom - top}};
}})()"""


# The area's shape, ``coords='0,0,120,120'``, on the image.
_AREA = f"""(() => {{
  const r = {rect_of("#pic")};
  return {{left: r.left, top: r.top, right: r.left + 120, bottom: r.top + 120,
    width: 120, height: 120}};
}})()"""


async def test_the_box_goes_on_what_shows_for_an_element_without_a_box(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(db_path, scan_id, CAPTURE, "aria-allowed-attr", FINDINGS)
    page = await open_inspector(new_page, base, scan_id, page_id, "aria-allowed-attr")
    try:
        group = page.get_by_role("group", name="Flagged elements", exact=True)
        box = page.frame_locator("iframe[title^='Saved copy']").locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("1 of 3")

        # display: contents: around its two buttons.
        await page.wait_for_function(_around(_BUTTONS))
        await settled(page)
        assert await page.evaluate(_around(_BUTTONS))
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "Around what it holds. It has no box of its own (display: contents)."
        )

        # An option: on its list box.
        await group.get_by_role("button", name="Next element").click()
        await playwright_async.expect(box).to_have_text("2 of 3")
        await page.wait_for_function(_around(rect_of("#pick")))
        await settled(page)
        assert await page.evaluate(_around(rect_of("#pick")))
        await playwright_async.expect(fact(page, "What it is")).to_have_text("<option> element")
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "On its list box. An option has no box of its own."
        )
        # The size is the option's own; the row above says where the box is,
        # so the "no visible size" hint does not contradict it.
        await playwright_async.expect(fact(page, "Size")).not_to_contain_text("marks where it sits")

        # An image map area: on the part of its image it covers, the left
        # 120 by 120 pixels of a 240 by 120 image.
        await group.get_by_role("button", name="Next element").click()
        await playwright_async.expect(box).to_have_text("3 of 3")
        await page.wait_for_function(_around(_AREA))
        await settled(page)
        assert await page.evaluate(_around(_AREA))
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "On the part of its image it covers. An area of an image map (<area>) has no "
            "box of its own."
        )
    finally:
        await page.context.close()
