"""Cmd/Ctrl+B shows and hides the sidebar, and says so."""

from __future__ import annotations

import json
from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect


async def test_shortcut_toggles_the_sidebar_and_announces_it(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    toggle = page.get_by_role("button", name="Collapse navigation sidebar")
    await expect(toggle).to_have_attribute("aria-keyshortcuts", "Meta+B Control+B")

    await page.keyboard.press("ControlOrMeta+b")
    await expect(page.get_by_role("button", name="Expand navigation sidebar")).to_have_attribute(
        "aria-expanded", "false"
    )
    await expect(page.get_by_role("status").filter(has_text="Sidebar")).to_have_text(
        "Sidebar hidden"
    )

    await page.keyboard.press("ControlOrMeta+b")
    await expect(toggle).to_have_attribute("aria-expanded", "true")
    await expect(page.get_by_role("status").filter(has_text="Sidebar")).to_have_text(
        "Sidebar shown"
    )

    await page.keyboard.press("Shift+?")
    await expect(page.get_by_role("dialog", name="Keyboard shortcuts")).to_contain_text(
        "Show or hide the sidebar"
    )


async def test_shortcut_is_off_when_keyboard_shortcuts_are_off(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page()
    stored = json.dumps(json.dumps({"shortcuts": "off"}))
    await page.add_init_script(f"localStorage.setItem('axcess.preferences', {stored})")
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    toggle = page.get_by_role("button", name="Collapse navigation sidebar")
    assert await toggle.get_attribute("aria-keyshortcuts") is None

    await page.keyboard.press("ControlOrMeta+b")

    await expect(toggle).to_have_attribute("aria-expanded", "true")
