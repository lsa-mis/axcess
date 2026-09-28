"""A flagged element taller than the view is scrolled to its top, not centred.

A flagged ``<main>`` or a long ``<form>`` is often taller than the saved
copy's view. Centring it put its middle in the view, so its top, where it
starts, and the box's numbered label above it were both scrolled out of
sight. Now an element taller than the view is scrolled so its top is in view
with a small margin, and the label shows. The same holds inside a panel that
scrolls on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import DOC, open_inspector, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

PAGE = (
    "<!doctype html><html><head><title>Tall fixture</title></head><body style='margin:0'>"
    "<div style='height:1500px'>Before</div>"
    "<main id='tall' style='height:2400px'>Main content</main>"
    "<div style='height:1500px'>After</div>"
    "</body></html>"
)

PANEL = (
    "<!doctype html><html style='height:100%;overflow:hidden'>"
    "<head><title>Tall panel fixture</title></head>"
    "<body style='height:100%;margin:0;overflow:hidden'>"
    "<aside id='panel' style='height:100%;overflow-y:auto'>"
    "<div style='height:1500px'>Before</div>"
    "<form id='tall' style='height:2400px'><label>Name <input></label></form>"
    "<div style='height:1500px'>After</div>"
    "</aside></body></html>"
)

# Where the element's top and the box's label are, from the top of what
# shows of the element's container (the frame's view, or the panel).
_TOPS = f"""(panel) => {{
  const doc = {DOC};
  const view = panel ? doc.getElementById('panel').getBoundingClientRect().top : 0;
  const tall = doc.getElementById('tall').getBoundingClientRect().top - view;
  const box = doc.getElementById('axcess-spotlight');
  const label = box.firstElementChild.getBoundingClientRect().top - view;
  return [tall, label];
}}"""


@pytest.mark.parametrize(
    ("capture", "selector", "snippet", "in_panel"),
    [
        (PAGE, "#tall", '<main id="tall" style="height:2400px">', False),
        (PANEL, "#tall", '<form id="tall" style="height:2400px">', True),
    ],
    ids=["page", "panel"],
)
async def test_a_tall_element_shows_its_top(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
    capture: str,
    selector: str,
    snippet: str,
    in_panel: bool,
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(db_path, scan_id, capture, "region", [(selector, snippet)])
    page = await open_inspector(new_page, base, scan_id, page_id, "region")
    try:
        box = page.frame_locator("iframe[title^='Saved copy']").locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("Flagged element")
        await settled(page)
        tall, label = await page.evaluate(_TOPS, in_panel)
        # Its top is in view, a little below the edge, with the label above it.
        assert 20 <= tall <= 80, tall
        assert 0 <= label < tall, (label, tall)
    finally:
        await page.context.close()
