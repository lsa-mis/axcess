"""The app's dropdown, operated by keyboard alone.

``Select`` is a custom select-only combobox (WAI-ARIA APG), not a native
``<select>``: the native list is drawn by the OS, so it could neither match
the Export panel nor carry a status chip on an option. Owning the widget
means owning everything the platform used to do. These tests pin it on the
Issues page's "Type" filter, whose options are, in order: All, Barrier,
Needs review, Informational.
"""

from __future__ import annotations

from typing import Any

import pytest

from .test_accessibility_axe import _render_violations, _run_axe, playwright_async

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

expect = playwright_async.expect


async def _type_filter(new_page: Any, base: str, scan_id: int) -> tuple[Any, Any]:
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    box = page.get_by_role("combobox", name="Type", exact=True)
    await box.focus()
    return page, box


async def _active_value(page: Any, box: Any) -> str | None:
    active = await box.get_attribute("aria-activedescendant")
    if not active:
        return None
    return await page.locator(f'[id="{active}"]').get_attribute("data-value")


async def test_arrows_move_and_enter_chooses_without_moving_focus(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page, box = await _type_filter(new_page, base, scan_id)

    await page.keyboard.press("ArrowDown")
    await expect(box).to_have_attribute("aria-expanded", "true")
    # Opens on the chosen option, and focus never leaves the trigger.
    assert await _active_value(page, box) == ""
    await expect(box).to_be_focused()

    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    assert await _active_value(page, box) == "expert_review"
    await page.keyboard.press("Enter")

    await expect(box).to_have_attribute("aria-expanded", "false")
    await page.wait_for_url("**type=expert_review*")
    await expect(box).to_have_attribute("data-value", "expert_review")
    await expect(box).to_be_focused()
    await page.context.close()


async def test_escape_closes_without_choosing(live_server: tuple[str, int], new_page: Any) -> None:
    base, scan_id = live_server
    page, box = await _type_filter(new_page, base, scan_id)

    await page.keyboard.press("Enter")
    await page.keyboard.press("End")
    assert await _active_value(page, box) == "informational"
    await page.keyboard.press("Escape")

    await expect(box).to_have_attribute("aria-expanded", "false")
    await expect(box).to_have_attribute("data-value", "")
    assert "type=" not in page.url
    await expect(box).to_be_focused()
    await page.context.close()


async def test_typing_finds_an_option_and_home_returns_to_the_first(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page, box = await _type_filter(new_page, base, scan_id)

    # Typing on the closed box opens it on the match.
    await page.keyboard.press("n")
    await expect(box).to_have_attribute("aria-expanded", "true")
    assert await _active_value(page, box) == "expert_review"
    await page.keyboard.press("Home")
    assert await _active_value(page, box) == ""
    await page.keyboard.press("i")
    assert await _active_value(page, box) == "informational"
    # Enter, not Space: a space typed straight after letters is part of the
    # text being searched for, as in the APG pattern.
    await page.keyboard.press("Enter")

    await page.wait_for_url("**type=informational*")
    await page.context.close()


async def test_tab_chooses_the_highlighted_option_and_moves_on(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page, box = await _type_filter(new_page, base, scan_id)

    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Tab")

    await page.wait_for_url("**type=likely_barrier*")
    await expect(box).to_have_attribute("aria-expanded", "false")
    await expect(box).not_to_be_focused()
    await page.context.close()


async def test_the_open_list_passes_axe(live_server: tuple[str, int], new_page: Any) -> None:
    base, scan_id = live_server
    page, _ = await _type_filter(new_page, base, scan_id)

    await page.keyboard.press("ArrowDown")
    await expect(page.get_by_role("listbox", name="Type")).to_be_visible()
    violations = await _run_axe(page)

    assert not violations, _render_violations(violations)
    await page.context.close()


async def test_screen_readers_get_name_value_state_and_the_highlighted_option(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """What assistive technology reads, from the browser's accessibility tree.

    Focus stays on the combobox, so a screen reader follows the highlighted
    option only through ``aria-activedescendant``; if that pointed nowhere,
    arrowing through the list would be silent.
    """
    base, scan_id = live_server
    page, box = await _type_filter(new_page, base, scan_id)

    await expect(box).to_have_accessible_name("Type")
    await expect(box).to_have_attribute("aria-expanded", "false")
    await expect(box).to_have_attribute("aria-haspopup", "listbox")
    # The closed list is out of the accessibility tree entirely.
    await expect(page.get_by_role("listbox", name="Type")).to_be_hidden()

    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    listbox = page.get_by_role("listbox", name="Type")
    await expect(listbox).to_be_visible()
    active = page.locator(f'[id="{await box.get_attribute("aria-activedescendant")}"]')
    await expect(active).to_have_role("option")
    await expect(active).to_have_accessible_name("Barrier (0)")
    await expect(listbox.get_by_role("option", selected=True)).to_have_accessible_name("All (2)")
    await page.context.close()
