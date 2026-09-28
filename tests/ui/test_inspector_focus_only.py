"""A flagged element that shows only with keyboard focus is shown as it looks focused.

A skip link is often placed off the screen (``left: -9999px``) until it has
keyboard focus. The numbered box followed it off the screen, so the reader
saw no box at all. The inspector now shows the link where it appears when
focused, draws the box there, and says it shows only with keyboard focus.
It must not take the reader's own keyboard focus to do it: focus stays where
it was, on page load and after the reader asks for the element. An element
that focus does not bring back on screen gets no box, and the table says it
is off the screen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import BOX_RECT, DOC, fact, open_inspector, rect_of, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

CAPTURE = (
    "<!doctype html><html><head><title>Skip link fixture</title>"
    "<style>.skip{position:absolute;left:-9999px;top:0;padding:8px;background:#fff}"
    ".skip:focus{left:16px;top:16px}</style></head>"
    "<body style='margin:0'><a class='skip' id='skip' href='#main'>Skip to content</a>"
    "<header style='height:120px'>Site name</header>"
    "<main id='main' style='height:1600px'>Main content</main></body></html>"
)

# The box is around the link, and the link is where its focus style puts it.
_BOX_ON_LINK = f"""() => {{
  const b = ({BOX_RECT})();
  if (!b) return false;
  const e = {rect_of("#skip")};
  return e.left >= 0 && e.left < 100 && b.left <= e.left && b.top <= e.top
    && e.right <= b.right && e.bottom <= b.bottom;
}}"""

# Neither the inspector's focus nor the saved copy's is on the link.
_FOCUS = f"""() => {{
  const frame = document.querySelector('iframe[title^="Saved copy"]');
  return [document.activeElement === frame, {DOC}.activeElement?.id === 'skip'];
}}"""


async def test_a_skip_link_is_shown_where_it_appears_with_focus(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(
        db_path,
        scan_id,
        CAPTURE,
        "skip-link",
        [("#skip", '<a class="skip" id="skip" href="#main">Skip to content</a>')],
    )
    page = await open_inspector(new_page, base, scan_id, page_id, "skip-link")
    try:
        box = page.frame_locator("iframe[title^='Saved copy']").locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("Flagged element")
        await page.wait_for_function(_BOX_ON_LINK)
        await settled(page)
        assert await page.evaluate(_BOX_ON_LINK)
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "It shows only when it has keyboard focus. The box is where it shows then."
        )
        # Page load did not move the reader's focus into the saved copy.
        assert await page.evaluate(_FOCUS) == [False, False]

        # Asked for from the keyboard, the element is shown again and the
        # reader's focus stays on the button they used.
        jump = page.get_by_role("button", name="Jump to flagged element")
        await jump.focus()
        await page.keyboard.press("Enter")
        await settled(page)
        assert await page.evaluate(_BOX_ON_LINK)
        assert await page.evaluate(_FOCUS) == [False, False]
        await playwright_async.expect(jump).to_be_focused()
    finally:
        await page.context.close()


OFF_SCREEN = (
    "<!doctype html><html><head><title>Off-screen fixture</title></head>"
    "<body style='margin:0'><header style='height:120px'>Site name</header>"
    "<span id='note' style='position:absolute;left:-9999px'>Opens in a new window</span>"
    "<main style='height:1600px'>Main content</main></body></html>"
)


async def test_an_element_focus_does_not_bring_on_screen_gets_no_box(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(
        db_path,
        scan_id,
        OFF_SCREEN,
        "skip-link",
        [
            (
                "#note",
                '<span id="note" style="position:absolute;left:-9999px">'
                "Opens in a new window</span>",
            )
        ],
    )
    page = await open_inspector(new_page, base, scan_id, page_id, "skip-link")
    try:
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "No box. It is off the screen in this saved copy."
        )
        await settled(page)
        assert await page.evaluate(f"({BOX_RECT})()") is None
        assert await page.evaluate(_FOCUS) == [False, False]
    finally:
        await page.context.close()
