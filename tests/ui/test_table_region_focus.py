"""A table's scroll region takes a tab stop only when it scrolls, and focus shows its top.

Every table sat in a focusable scroll region, so a table that fit had a tab
stop that did nothing. And a browser brings a focused element into view by
centring it when it is off the screen, so tabbing to a table taller than the
window dropped the reader in its middle, away from the header row. Now the
region is in the tab order only while it scrolls sideways (still focusable
from code), and keyboard focus brings its top into view under the top bar.
"""

from __future__ import annotations

from typing import Any

import pytest

from .test_reports_table import DIST, _site

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

TOPBAR = 72


async def _open(new_page: Any, width: int, height: int, count: int) -> Any:
    sites = [_site(index, 1) for index in reversed(range(count))]
    page = await new_page(viewport={"width": width, "height": height})

    async def respond(route: Any) -> None:
        path = route.request.url.split("reports.test", 1)[-1].split("?", 1)[0]
        if path == "/api/sites":
            await route.fulfill(json=sites)
        elif path.startswith("/api/"):
            await route.fulfill(status=404, json={"detail": "Unavailable"})
        elif path.startswith("/app/assets/"):
            await route.fulfill(path=str(DIST / path.removeprefix("/app/")))
        else:
            await route.fulfill(path=str(DIST / "index.html"))

    await page.route("**/*", respond)
    await page.goto("http://reports.test/app/scans", wait_until="networkidle")
    return page


async def test_a_table_that_fits_has_no_tab_stop(new_page: Any) -> None:
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    page = await _open(new_page, 1400, 900, 3)
    try:
        region = page.get_by_role("region", name="Public reports table")
        await playwright_async.expect(region).to_have_attribute("tabindex", "-1")
        # From the search box, Tab goes into the table's first control, not
        # onto the region around it.
        await page.get_by_role("searchbox", name="Search sites").focus()
        await page.keyboard.press("Tab")
        assert await region.evaluate("(el) => document.activeElement !== el")
        assert await region.evaluate("(el) => el.contains(document.activeElement)")
    finally:
        await page.context.close()


async def test_keyboard_focus_shows_the_top_of_a_scrolling_table(new_page: Any) -> None:
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    page = await _open(new_page, 320, 480, 10)
    try:
        region = page.get_by_role("region", name="Public reports table")
        # Wider than a phone: it scrolls sideways, so it takes a tab stop.
        await playwright_async.expect(region).to_have_attribute("tabindex", "0")
        # Out of view below the window, as when a reader tabs to it from above.
        await page.evaluate("window.scrollTo(0, 0)")
        top = await region.evaluate("(el) => el.getBoundingClientRect().top")
        assert top > 480, top
        await page.keyboard.press("Shift")  # keyboard modality, so focus is :focus-visible
        await region.evaluate("(el) => el.focus({ focusVisible: true })")
        await playwright_async.expect(region).to_be_focused()
        top = await region.evaluate("(el) => el.getBoundingClientRect().top")
        # Its top, and the header row under it, just under the top bar; not
        # the middle of the table.
        assert TOPBAR <= top <= TOPBAR + 32, top
        header = await region.locator("thead").evaluate("(el) => el.getBoundingClientRect().top")
        assert header < 480, header
    finally:
        await page.context.close()
