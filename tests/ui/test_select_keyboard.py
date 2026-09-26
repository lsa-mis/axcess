"""The app's dropdown, operated by keyboard alone.

``Select`` is a custom select-only combobox (WAI-ARIA APG), not a native
``<select>``: the native list is drawn by the OS, so it could neither match
the Export panel nor carry a status chip on an option. Owning the widget
means owning everything the platform used to do. These tests pin it on the
finding detail page's "Status:" control, whose options are, in order: new,
reviewing, in progress, remediated, accepted risk, false positive. The
seeded finding starts at "new".

Choosing an option only stages the status; the Save button beside it
persists it. Each test gets a fresh database, so a save in one test never
leaks into another.
"""

from __future__ import annotations

from typing import Any

import pytest

from .test_accessibility_axe import _render_violations, _run_axe, playwright_async

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

expect = playwright_async.expect

LABEL = "Status:"


async def _status_select(new_page: Any, base: str) -> tuple[Any, Any]:
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/findings/1", wait_until="networkidle")
    box = page.get_by_role("combobox", name=LABEL, exact=True)
    await expect(box).to_have_attribute("data-value", "new")
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
    base, _ = live_server
    page, box = await _status_select(new_page, base)

    await page.keyboard.press("ArrowDown")
    await expect(box).to_have_attribute("aria-expanded", "true")
    # Opens on the chosen option, and focus never leaves the trigger.
    assert await _active_value(page, box) == "new"
    await expect(box).to_be_focused()

    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    assert await _active_value(page, box) == "in_progress"
    await page.keyboard.press("Enter")

    await expect(box).to_have_attribute("aria-expanded", "false")
    await expect(box).to_have_attribute("data-value", "in_progress")
    await expect(box).to_be_focused()
    await page.context.close()


async def test_escape_closes_without_choosing(live_server: tuple[str, int], new_page: Any) -> None:
    base, _ = live_server
    page, box = await _status_select(new_page, base)

    await page.keyboard.press("Enter")
    await page.keyboard.press("End")
    assert await _active_value(page, box) == "false_positive"
    await page.keyboard.press("Escape")

    await expect(box).to_have_attribute("aria-expanded", "false")
    await expect(box).to_have_attribute("data-value", "new")
    # Nothing was staged, so there is nothing to save.
    await expect(page.get_by_role("button", name="Save", exact=True)).to_be_disabled()
    await expect(box).to_be_focused()
    await page.context.close()


async def test_typing_finds_an_option_and_home_returns_to_the_first(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page, box = await _status_select(new_page, base)

    # Typing on the closed box opens it on the match.
    await page.keyboard.press("f")
    await expect(box).to_have_attribute("aria-expanded", "true")
    assert await _active_value(page, box) == "false_positive"
    await page.keyboard.press("Home")
    assert await _active_value(page, box) == "new"
    await page.keyboard.press("i")
    assert await _active_value(page, box) == "in_progress"
    # Enter, not Space: a space typed straight after letters is part of the
    # text being searched for, as in the APG pattern.
    await page.keyboard.press("Enter")

    await expect(box).to_have_attribute("aria-expanded", "false")
    await expect(box).to_have_attribute("data-value", "in_progress")
    await page.context.close()


async def test_tab_chooses_the_highlighted_option_and_moves_on(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    page, box = await _status_select(new_page, base)

    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    assert await _active_value(page, box) == "reviewing"
    await page.keyboard.press("Tab")

    await expect(box).to_have_attribute("aria-expanded", "false")
    await expect(box).to_have_attribute("data-value", "reviewing")
    await expect(box).not_to_be_focused()
    # "Moves on" means to the next control, Save, which the choice enabled;
    # "reviewing" needs no rationale, so Enter saves it straight away.
    save = page.get_by_role("button", name="Save", exact=True)
    await expect(save).to_be_focused()
    await page.keyboard.press("Enter")
    await expect(page.get_by_text("Status updated to reviewing", exact=True)).to_be_visible()
    await expect(save).to_be_disabled()
    await page.context.close()


async def test_the_open_list_passes_axe(live_server: tuple[str, int], new_page: Any) -> None:
    base, _ = live_server
    page, _ = await _status_select(new_page, base)

    await page.keyboard.press("ArrowDown")
    await expect(page.get_by_role("listbox", name=LABEL)).to_be_visible()
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
    base, _ = live_server
    page, box = await _status_select(new_page, base)

    await expect(box).to_have_accessible_name(LABEL)
    await expect(box).to_have_attribute("aria-expanded", "false")
    await expect(box).to_have_attribute("aria-haspopup", "listbox")
    # The closed list is out of the accessibility tree entirely.
    await expect(page.get_by_role("listbox", name=LABEL)).to_be_hidden()

    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    listbox = page.get_by_role("listbox", name=LABEL)
    await expect(listbox).to_be_visible()
    active = page.locator(f'[id="{await box.get_attribute("aria-activedescendant")}"]')
    await expect(active).to_have_role("option")
    await expect(active).to_have_accessible_name("reviewing")
    await expect(listbox.get_by_role("option", selected=True)).to_have_accessible_name("new")
    await page.context.close()
