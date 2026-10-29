"""Flagged elements the saved copy cannot hold are said, never guessed.

axe names an element inside a component's own page code (shadow DOM) with a
list of locators, one per component, and the scan stores that list as text
(``['#host', 'button']``). The saved copy does not keep shadow DOM, so no
locator can find it, and the inspector fell back to the element's code and
outlined a different element that happened to look the same. An element in
another page shown within this one (an iframe) is named with one locator per
frame, joined with " > ", and fell back the same way. Both are now counted
and said, not outlined. A page that draws on a drawing area (``<canvas>``)
does so with scripts, and the saved copy runs none: a browser shows the
canvas's backup content instead of the drawing. Nothing said so, and a
flagged canvas was boxed with no word on why it looked empty. Both are said
now.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import BOX_RECT, fact, open_inspector, rect_of, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

# The component's shadow DOM is not in the saved copy; a button outside it
# has the same code as the flagged one inside it.
SHADOW = (
    "<!doctype html><html><head><title>Shadow fixture</title></head><body>"
    "<fancy-checkout id='host'></fancy-checkout>"
    "<p><button>Buy</button></p></body></html>"
)

# The payment frame's page is not in the saved copy; a field outside it has
# the same code as the flagged one inside it.
FRAME = (
    "<!doctype html><html><head><title>Frame fixture</title></head><body>"
    "<iframe id='pay' title='Payment'></iframe>"
    "<p><input id='card'></p></body></html>"
)

CANVAS = (
    "<!doctype html><html><head><title>Canvas fixture</title></head>"
    "<body style='margin:0'><canvas id='app' width='900' height='600'>"
    "<button id='play' type='button'>Play</button></canvas></body></html>"
)


async def _no_outline(page: Any) -> None:
    frame = page.frame_locator("iframe[title^='Saved copy']")
    await playwright_async.expect(frame.locator(".axcess-inspect-highlight")).to_have_count(0)
    assert await page.evaluate(f"({BOX_RECT})()") is None


async def test_an_element_in_shadow_dom_is_said_not_guessed(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    finding = ("['#host', 'button']", "<button>Buy</button>")
    page_id = seed(db_path, scan_id, SHADOW, "button-name", [finding])
    page = await open_inspector(new_page, base, scan_id, page_id, "button-name")
    try:
        await playwright_async.expect(
            page.get_by_text(
                "1 occurrence is not outlined: it is inside a part of the page that keeps its "
                "own page code (shadow DOM). The saved copy does not keep that code."
            )
        ).to_be_visible()
        await _no_outline(page)
        await playwright_async.expect(
            page.get_by_text("Axcess could not find the flagged element in this copy.")
        ).to_have_count(0)
    finally:
        await page.context.close()


async def test_an_element_in_an_iframe_is_said_not_guessed(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(db_path, scan_id, FRAME, "label", [("#pay > #card", '<input id="card">')])
    page = await open_inspector(new_page, base, scan_id, page_id, "label")
    try:
        await playwright_async.expect(
            page.get_by_text(
                "1 occurrence is not outlined: it is inside another page shown within this one "
                "(an iframe). The saved copy does not keep that page."
            )
        ).to_be_visible()
        await _no_outline(page)
    finally:
        await page.context.close()


async def test_a_page_drawn_on_a_canvas_is_said(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = seed(
        db_path,
        scan_id,
        CANVAS,
        "button-name",
        [
            ("#app", '<canvas id="app" width="900" height="600">'),
            ("#play", '<button id="play" type="button">Play</button>'),
        ],
    )
    page = await open_inspector(new_page, base, scan_id, page_id, "button-name")
    try:
        await playwright_async.expect(
            page.get_by_text(
                "This page draws on a drawing area (canvas). The saved copy runs no scripts, so "
                "it does not show the drawing, only any backup content the page gave. Nothing "
                "drawn on it can be outlined."
            )
        ).to_be_visible()
        box = page.frame_locator("iframe[title^='Saved copy']").locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("1 of 2")
        await playwright_async.expect(fact(page, "Where the box is")).to_have_text(
            "Around a drawing area (canvas). The saved copy runs no scripts, so it shows the "
            "area's backup content, not the drawing."
        )
        # The backup content shows in the saved copy, so the button inside the
        # drawing area is boxed as itself.
        group = page.get_by_role("group", name="Flagged elements", exact=True)
        await group.get_by_role("button", name="Next element").click()
        await playwright_async.expect(box).to_have_text("2 of 2")
        await settled(page)
        button = await page.evaluate(
            f"(() => {{ const r = {rect_of('#play')}; "
            "return [r.left, r.top, r.right, r.bottom]; })()"
        )
        drawn = await page.evaluate(f"({BOX_RECT})()")
        assert drawn is not None
        assert drawn["left"] <= button[0] and button[2] <= drawn["right"], (drawn, button)
        assert drawn["top"] <= button[1] and button[3] <= drawn["bottom"], (drawn, button)
        await playwright_async.expect(fact(page, "Where the box is")).to_have_count(0)
    finally:
        await page.context.close()
