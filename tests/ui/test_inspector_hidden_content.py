"""A flagged element the saved copy hides: in a closed section, or not displayed.

A link inside a closed ``<details>`` section, and a button in a tab that was
not open (``display: none``), have no box in the saved copy. The numbered box
jumped to the top left of the frame, and the frame scrolled to the top. Now
the closed section is opened in the saved copy (it is a copy, so nothing on
the site changes) and the link is boxed, and the table says so. The button
that is not displayed gets no box, the view stays where it was, and the table
says it was hidden in this saved copy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import BOX_RECT, DOC, fact, open_inspector, rect_of, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

CAPTURE = (
    "<!doctype html><html><head><title>Hidden content fixture</title></head>"
    "<body style='margin:0;font:16px/24px sans-serif'>"
    "<div style='height:600px'>Top</div>"
    "<details id='more' style='margin-left:120px'><summary>Opening hours</summary>"
    "<p><a id='inside' href='/hours'>See every branch</a></p></details>"
    "<div style='height:600px'></div>"
    "<div role='tablist'><button role='tab' aria-selected='true'>Books</button>"
    "<button role='tab' aria-selected='false'>Films</button></div>"
    "<div role='tabpanel'>Books panel</div>"
    "<div role='tabpanel' id='films' style='display:none'>"
    "<button id='intab' type='button'></button></div>"
    "<div style='height:900px'></div></body></html>"
)

FINDINGS = [
    ("#inside", '<a id="inside" href="/hours">See every branch</a>'),
    ("#intab", '<button id="intab" type="button"></button>'),
]


async def test_hidden_content_is_opened_or_said(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(db_path, scan_id, CAPTURE, "link-name", FINDINGS)
    page = await open_inspector(new_page, base, scan_id, page_id, "link-name")
    try:
        group = page.get_by_role("group", name="Flagged elements", exact=True)
        box = page.frame_locator("iframe[title^='Saved copy']").locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("1 of 2")

        # The closed section is opened in the saved copy, and the link boxed.
        await settled(page)
        assert await page.evaluate(f"{DOC}.getElementById('more').open")
        drawn = await page.evaluate(f"({BOX_RECT})()")
        link = await page.evaluate(
            f"(() => {{ const r = {rect_of('#inside')}; "
            "return [r.left, r.top, r.right, r.bottom]; })()"
        )
        assert link[2] > link[0], link
        assert drawn is not None, drawn
        assert drawn["left"] <= link[0] and link[2] <= drawn["right"], (drawn, link)
        assert drawn["top"] <= link[1] and link[3] <= drawn["bottom"], (drawn, link)
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "Around it. Axcess opened the closed section it is in (<details>) in this saved copy."
        )

        # Not displayed: no box, and the view is not moved to the top.
        before = await page.evaluate(f"{DOC}.defaultView.scrollY")
        await group.get_by_role("button", name="Next flagged element").click()
        await playwright_async.expect(box).to_have_text("2 of 2")
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "No box. It was hidden in this saved copy (display: none)."
        )
        await settled(page)
        assert await page.evaluate(f"({BOX_RECT})()") is None
        assert await page.evaluate(f"{DOC}.defaultView.scrollY") == before
    finally:
        await page.context.close()
