"""A table heading starts on the same line as the words under it.

The developer's report (2026-11-16): "Issue type" sat left of the issue
types, and "Site" on Reports left of the site's name (which follows the
row's expand arrow). SortHeader no longer adds its button's padding in
front of the words, Issues' first heading keeps its row header's padding,
and Reports indents "Site" by the arrow's width.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("playwright.async_api")

pytestmark = pytest.mark.asyncio(loop_scope="module")

_TEXT_LEFT = """el => {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.textContent.trim() || node.parentElement.closest('.sr-only, [popover]')) continue;
    range.selectNodeContents(node);
    const rect = range.getClientRects()[0];
    if (rect) return rect.left;
  }
  return null;
}"""


async def _first_column_lines_up(page: Any) -> tuple[float, float]:
    header = await page.locator("table thead th").first.evaluate(_TEXT_LEFT)
    cell = await page.locator("table tbody tr").first.locator("th, td").first.evaluate(_TEXT_LEFT)
    assert header is not None and cell is not None
    return header, cell


@pytest.mark.parametrize("width", [1280, 390])
async def test_issue_type_heading_starts_with_the_issue_types(
    live_server: tuple[str, int], new_page: Any, width: int
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": width, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    header, cell = await _first_column_lines_up(page)
    assert abs(header - cell) <= 1, (header, cell)


@pytest.mark.parametrize("width", [1280, 390])
async def test_site_heading_starts_with_the_site_name(
    live_server: tuple[str, int], new_page: Any, width: int
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": width, "height": 900})
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    header, cell = await _first_column_lines_up(page)
    assert abs(header - cell) <= 1, (header, cell)
