"""An occurrence on the whole page (``<html>`` or ``<body>``) draws no box.

Some rules flag the page itself: axe's html-has-lang names ``html``, and
others name ``body``. The numbered box went around the whole document, with
the rest of the page dimmed (there is no rest), its label off the top, and
the frame scrolled to the middle of the page. Now there is no box, nothing is
dimmed, the frame stays where it is, and the table says it is the whole page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import BOX_RECT, DOC, fact, open_inspector, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

CAPTURE = (
    "<!doctype html><html><head><title>Whole page fixture</title></head>"
    "<body style='margin:0'>"
    + "".join(f"<p style='height:300px;margin:0'>Section {n}</p>" for n in range(12))
    + "</body></html>"
)

# Nothing in the saved copy draws the box or the dimming.
_NO_BOX = f"""() => {{
  const doc = {DOC};
  if (({BOX_RECT})() !== null) return false;
  const all = [doc.documentElement, doc.body, ...doc.body.querySelectorAll('*')];
  return !all.some((el) => getComputedStyle(el).boxShadow.includes('100vmax')
    || getComputedStyle(el).boxShadow.includes('rgba(0, 39, 76, 0.3)'));
}}"""


@pytest.mark.parametrize(
    ("selector", "snippet", "kind"),
    [
        ("html", "<html>", "The whole page (<html> element)"),
        ("body", '<body style="margin:0">', "The whole page (<body> element)"),
    ],
)
async def test_the_whole_page_gets_no_box(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
    selector: str,
    snippet: str,
    kind: str,
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(db_path, scan_id, CAPTURE, "html-has-lang", [(selector, snippet)])
    page = await open_inspector(new_page, base, scan_id, page_id, "html-has-lang")
    try:
        await playwright_async.expect(page.get_by_text("1 flagged element")).to_be_visible()
        await playwright_async.expect(fact(page, "What it is")).to_have_text(kind)
        await settled(page)
        assert await page.evaluate(_NO_BOX)
        # The frame was not scrolled to the middle of the page.
        assert await page.evaluate(f"{DOC}.defaultView.scrollY") == 0
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "No box, because it is the whole page. Nothing is dimmed."
        )
        # The line under the saved copy does not describe a box that is not there.
        await playwright_async.expect(
            page.get_by_text("A blue box with a yellow ring marks the flagged element.")
        ).to_have_count(0)
        await playwright_async.expect(
            page.get_by_text(
                "No box marks the flagged element. The table above the saved copy says why."
            )
        ).to_be_visible()
    finally:
        await page.context.close()
