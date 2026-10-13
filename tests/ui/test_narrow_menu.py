"""The narrow-screen menu opens where the reader is, over the page.

Below 768 px the sidebar is hidden and the menu button in the sticky top bar
opens the same navigation. It used to open in the page's flow, at the very
top of the page, so after scrolling down the button seemed to do nothing.
It now lies over the page just under the bar, and closes like an overlay:
Escape (focus back on the button), a click outside, or focus leaving it.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")


async def _scrolled_down(new_page: Any, base: str) -> Any:
    page = await new_page(viewport={"width": 390, "height": 640})
    # New scan is several screens tall at this width.
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    assert await page.evaluate("scrollY") > 400, (
        "the page must be scrolled for this test to mean anything"
    )
    return page


async def test_the_menu_opens_in_view_after_scrolling(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await _scrolled_down(new_page, base)
    await page.get_by_role("button", name="Open menu").click()

    nav = page.locator("#mobile-primary-nav")
    await playwright_async.expect(nav).to_be_visible()
    box = await nav.bounding_box()
    assert box is not None
    # Just under the 72 px bar, on screen, not at the top of the page.
    assert abs(box["y"] - 72) <= 2, box
    reports = nav.get_by_role("link", name="Reports")
    await playwright_async.expect(reports).to_be_in_viewport()
    # Its last row is reachable even on a short screen: the menu scrolls.
    settings = nav.get_by_role("link", name="Settings")
    await settings.scroll_into_view_if_needed()
    await playwright_async.expect(settings).to_be_in_viewport()
    await page.context.close()


async def test_escape_closes_the_menu_and_returns_focus(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await _scrolled_down(new_page, base)
    await page.get_by_role("button", name="Open menu").click()
    await page.locator("#mobile-primary-nav").get_by_role("link", name="Reports").focus()

    await page.keyboard.press("Escape")

    await playwright_async.expect(page.locator("#mobile-primary-nav")).to_have_count(0)
    await playwright_async.expect(page.get_by_role("button", name="Open menu")).to_be_focused()
    await page.context.close()


async def test_tabbing_out_or_clicking_outside_closes_the_menu(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """Focus must never move to a link the open menu is covering."""
    base, _ = live_server
    page = await _scrolled_down(new_page, base)
    menu = page.locator("#mobile-primary-nav")

    await page.get_by_role("button", name="Open menu").click()
    await menu.get_by_role("link", name="Settings").focus()
    await page.keyboard.press("Tab")
    await playwright_async.expect(menu).to_have_count(0)

    await page.get_by_role("button", name="Open menu").click()
    await playwright_async.expect(menu).to_be_visible()
    await page.mouse.click(200, 600)
    await playwright_async.expect(menu).to_have_count(0)
    await page.context.close()
