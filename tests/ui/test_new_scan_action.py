"""The New scan button looks and works the same on every screen.

On the New scan form it used to turn grey and leave the tab order, which
read as broken rather than "you are here". It now stays as it is, marked as
a link to the current page (aria-current="page"); see NewScanAction in
components/AppShell.tsx.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")


@pytest.mark.parametrize("path", ["/app/scans", "/app/scans/new"])
async def test_new_scan_stays_the_same_control(
    live_server: tuple[str, int], new_page: Any, path: str
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}{path}", wait_until="networkidle")
        action = (
            page.get_by_role("link", name="Start a new scan", exact=True).filter(visible=True).first
        )
        await playwright_async.expect(action).to_be_visible()
        assert await action.get_attribute("aria-disabled") is None
        assert await action.get_attribute("tabindex") is None
        assert await action.evaluate("el => getComputedStyle(el).opacity") == "1"
        current = await action.get_attribute("aria-current")
        assert current == ("page" if path == "/app/scans/new" else None)
        # Reachable by keyboard on the form too.
        await action.focus()
        await playwright_async.expect(action).to_be_focused()
    finally:
        await page.context.close()
