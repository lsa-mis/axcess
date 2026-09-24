"""Two-finger touchpad swipe back/forward, which only the desktop app handles.

Playwright's ``mouse.wheel`` sends the same pixel-mode wheel events a
touchpad's two-finger scroll does. The desktop app is recognised by its
Electron user agent, so these tests borrow one.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")

DESKTOP_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "axcess/0.1.0 Chrome/140.0.0.0 Electron/43.4.0 Safari/537.36"
)
# Longer than the hook's gap between gestures, so the next wheel starts anew.
GESTURE_GAP_MS = 400


async def _swipe(page: Any, dx: float, steps: int = 4) -> None:
    """One two-finger swipe: a quick burst of small horizontal wheel events."""
    for _ in range(steps):
        await page.mouse.wheel(dx / steps, 0)
    await page.wait_for_timeout(GESTURE_GAP_MS)


async def _open_issue_from_list(page: Any, base: str, scan_id: int) -> tuple[str, str]:
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    issues_url = page.url
    table = page.get_by_role("table", name="Accessibility issue groups")
    await table.get_by_role("rowheader").first.get_by_role("link").click()
    await page.wait_for_url("**/issues/**")
    await page.get_by_role("heading", level=1).wait_for()
    # Over the page title: nothing there scrolls sideways.
    box = await page.get_by_role("heading", level=1).bounding_box()
    assert box is not None
    await page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
    return issues_url, page.url


async def test_desktop_swipe_goes_back_and_forward(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900}, user_agent=DESKTOP_UA)
    issues_url, issue_url = await _open_issue_from_list(page, base, scan_id)

    # Vertical scrolling, and a nudge short of the threshold, stay put.
    await page.mouse.wheel(0, 300)
    await page.wait_for_timeout(GESTURE_GAP_MS)
    await _swipe(page, -60)
    assert page.url == issue_url

    await _swipe(page, -240)
    await page.wait_for_url(issues_url)

    box = await page.get_by_role("heading", level=1).bounding_box()
    assert box is not None
    await page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
    await _swipe(page, 240)
    await page.wait_for_url(issue_url)


async def test_browser_tab_leaves_swipes_to_the_browser(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """A Chromium tab already has this gesture; handling it too would go back twice."""
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    _issues_url, issue_url = await _open_issue_from_list(page, base, scan_id)
    await _swipe(page, -400)
    assert page.url == issue_url


async def test_swipe_over_a_wide_table_scrolls_it_instead(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """At phone width the issue table scrolls sideways, and a swipe over it
    scrolls it; a gesture that scrolled never turns into navigation."""
    base, scan_id = live_server
    page = await new_page(viewport={"width": 320, "height": 800}, user_agent=DESKTOP_UA)
    await page.goto(f"{base}/app/scans/{scan_id}/diff", wait_until="networkidle")
    await (
        page.get_by_role("navigation", name="Report workspace")
        .get_by_role("link", name="Issues", exact=True)
        .click()
    )
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")
    issues_url = page.url

    region = page.get_by_role("region", name="Issue table")
    await region.scroll_into_view_if_needed()
    box = await region.bounding_box()
    assert box is not None
    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    await _swipe(page, 200)
    scrolled = await region.evaluate("el => el.scrollLeft")
    assert scrolled > 0
    # Back to the table's left edge and past it, in one gesture: it scrolls
    # to the edge and stops there rather than going back a page.
    await _swipe(page, -(scrolled + 300), steps=8)
    assert await region.evaluate("el => el.scrollLeft") == 0
    assert page.url == issues_url
