"""The scroll bar over a wide table (TableRegion, components/table/Table.tsx)
follows the rules for a scroll bar (the developer's request, 2026-11-16).

A scroll bar is a pointer control, never a Tab stop: the keyboard way to
scroll is to focus the scrolling box and use the arrow keys (SC 2.1.1), and
the table's region is that box. So the top bar is hidden from screen readers
and out of the Tab order, a click on it sends focus to the region (focus
never rests on hidden content), it has no scrollbar role (no custom widget),
its grab area is 24px tall (SC 2.5.8), and it moves with the table both ways.
It shows only while the table is wider than its region.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

_SCROLLBAR_HEIGHT = r"""() => {
  const walk = (rules) => {
    for (const rule of rules) {
      if (rule.selectorText === '.ax-scrollbar::-webkit-scrollbar') return rule.style.height;
      if (rule.cssRules) {
        const found = walk(rule.cssRules);
        if (found) return found;
      }
    }
    return null;
  };
  for (const sheet of document.styleSheets) {
    const found = walk(sheet.cssRules);
    if (found) return found;
  }
  return null;
}"""

_BAR = "xpath=preceding-sibling::div[contains(@class, 'ax-scrollbar')][1]"


async def test_the_top_scroll_bar_is_a_pointer_aid_and_never_a_tab_stop(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 320, "height": 800})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    region = page.get_by_role("region", name="Issues table")
    assert await region.evaluate("el => el.scrollWidth > el.clientWidth")
    bar = region.locator(_BAR)
    await playwright_async.expect(bar).to_have_count(1)

    # Hidden from screen readers, out of the Tab order, no scrollbar role.
    await playwright_async.expect(bar).to_have_attribute("aria-hidden", "true")
    await playwright_async.expect(bar).to_have_attribute("tabindex", "-1")
    assert await page.get_by_role("scrollbar").count() == 0
    # The region is the keyboard way to scroll.
    await playwright_async.expect(region).to_have_attribute("tabindex", "0")

    # A 24px grab area. Read from the style rule: headless Chromium hides
    # scroll bars, so the drawn height cannot be measured here.
    height = await page.evaluate(_SCROLLBAR_HEIGHT)
    assert height == "24px", height

    # Moves with the table, both ways.
    await bar.evaluate("el => { el.scrollLeft = 120; el.dispatchEvent(new Event('scroll')); }")
    await page.wait_for_function(
        "el => Math.abs(el.scrollLeft - 120) < 1", arg=await region.element_handle()
    )
    await region.evaluate("el => { el.scrollLeft = 40; el.dispatchEvent(new Event('scroll')); }")
    await page.wait_for_function(
        "el => Math.abs(el.scrollLeft - 40) < 1", arg=await bar.element_handle()
    )

    # A click on it leaves focus on the region, never on the hidden bar.
    box = await bar.bounding_box()
    assert box is not None
    await page.mouse.click(box["x"] + box["width"] - 6, box["y"] + box["height"] / 2)
    assert await region.evaluate("el => document.activeElement === el")
    await page.keyboard.press("ArrowLeft")
    assert await bar.evaluate("el => document.activeElement !== el")
    await page.context.close()


async def test_no_top_scroll_bar_when_the_table_fits(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1600, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    region = page.get_by_role("region", name="Issues table")
    assert await region.evaluate("el => el.scrollWidth <= el.clientWidth")
    await playwright_async.expect(region.locator(_BAR)).to_have_count(0)
    await page.context.close()
