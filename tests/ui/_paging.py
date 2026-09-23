"""Read every row of a paged table (see TablePagination.tsx) in a Playwright test."""

from __future__ import annotations

from typing import Any


async def all_pages_text(page: Any, cells: Any, label: str) -> list[str]:
    """The text of ``cells`` on every page of the table ``label`` names, in order.

    Tables show ten rows at a time. This goes back to the first page, reads
    the cells, and turns pages until "Next" is disabled or absent (one page).
    Each turn waits for the "Showing …" line to change, so it never reads or
    clicks against the page it is leaving.
    """
    previous = page.get_by_role("button", name=f"Previous page of {label.lower()}")
    next_button = page.get_by_role("button", name=f"Next page of {label.lower()}")
    status = page.get_by_role("navigation", name=f"{label} pagination").get_by_role("status")

    async def enabled(button: Any) -> bool:
        return bool(await button.count()) and await button.get_attribute("aria-disabled") != "true"

    async def turn(button: Any) -> None:
        before = await status.inner_text()
        await button.click()
        await page.wait_for_function(
            "([el, text]) => el.textContent !== text",
            arg=[await status.element_handle(), before],
        )

    # Whatever the caller just did (a sort, a filter) may still be rendering;
    # let it land before reading which page the table is on.
    await page.evaluate("new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    while await enabled(previous):
        await turn(previous)
    texts: list[str] = []
    while True:
        texts.extend(text.strip() for text in await cells.all_inner_texts())
        if not await enabled(next_button):
            return texts
        await turn(next_button)
