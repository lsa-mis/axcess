"""A screen reader can find the flagged element in the Page inspector.

The box and label over the saved copy are drawn for the eye and hidden from
screen readers, so the inspector gives the same thing in words and a way
in. After each step, the stepper's status says what the element is.
"Go to this element in the saved copy" moves focus onto the element itself,
which then has "Flagged element N of M" as its description, and Escape comes
back. The label also stays inside the frame for an element at the very top
or side of the page, where it used to be cut off.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import DOC, open_inspector, seed, settled

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

# A one-pixel heading at the top right corner, as on the page the developer
# found the cut-off label on, then a link at the top left.
CAPTURE = (
    "<!doctype html><html><head><title>Reader fixture</title></head>"
    "<body style='margin:0;font:16px/24px sans-serif'>"
    "<h5 id='status' style='position:absolute;top:0;right:0;width:1px;height:24px;"
    "overflow:hidden;margin:0'>Status messages</h5>"
    "<a id='skip' href='#main' style='position:absolute;top:0;left:0'>Skip to main content</a>"
    "<main id='main' style='padding-top:80px'><p>Some text.</p></main></body></html>"
)
RULE = "aria-valid-attr"
FINDINGS = [
    (
        "#status",
        '<h5 id="status" style="position:absolute;top:0;right:0;width:1px;height:24px;'
        'overflow:hidden;margin:0">Status messages</h5>',
    ),
    (
        "#skip",
        '<a id="skip" href="#main" style="position:absolute;top:0;left:0">Skip to main content</a>',
    ),
]


@pytest.fixture
def page_id(seeded_db: tuple[Path, Path, int]) -> int:
    db_path, _, scan_id = seeded_db
    return seed(db_path, scan_id, CAPTURE, RULE, FINDINGS)


async def _inspector(new_page: Any, base: str, scan_id: int, page_id: int) -> Any:
    page = await open_inspector(new_page, base, scan_id, page_id, RULE)
    await page.get_by_role("button", name="Go to this element in the saved copy").wait_for()
    await settled(page)
    return page


def _status(page: Any) -> Any:
    return page.get_by_role("group", name="Flagged elements").get_by_role("status")


async def test_each_step_says_what_the_element_is(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    status = _status(page)
    await playwright_async.expect(status).to_have_text(
        "Flagged element 1 of 2: Heading level 5, “Status messages”"
    )
    await page.get_by_role("button", name="Next flagged element").click()
    await playwright_async.expect(status).to_have_text(
        "Flagged element 2 of 2: Link, “Skip to main content”"
    )
    await page.context.close()


async def test_go_to_moves_focus_onto_the_element_and_escape_comes_back(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    go = page.get_by_role("button", name="Go to this element in the saved copy")
    await playwright_async.expect(go).to_have_accessible_description(
        "Moves keyboard focus onto it. Press Escape to come back here."
    )
    await go.focus()
    await page.keyboard.press("Enter")
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    heading = copy.locator("#status")
    await playwright_async.expect(heading).to_be_focused()
    await playwright_async.expect(heading).to_have_accessible_description("Flagged element 1 of 2")
    # The heading is reached from here only, not by Tab.
    assert await heading.get_attribute("tabindex") == "-1"
    await page.keyboard.press("Escape")
    await playwright_async.expect(go).to_be_focused()
    await page.context.close()


async def test_only_the_current_element_is_described(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    await page.get_by_role("button", name="Next flagged element").click()
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    await playwright_async.expect(copy.locator("#skip")).to_have_accessible_description(
        "Flagged element 2 of 2"
    )
    await playwright_async.expect(copy.locator("#status")).to_have_accessible_description("")
    described = await page.evaluate(
        f"() => {DOC}.querySelectorAll('[aria-describedby~=\"axcess-flagged-note\"]').length"
    )
    assert described == 1
    await page.get_by_role("button", name="Go to this element in the saved copy").click()
    await playwright_async.expect(copy.locator("#skip")).to_be_focused()
    await page.context.close()


@pytest.mark.parametrize("step", [0, 1], ids=["top-right heading", "top-left link"])
async def test_the_label_stays_inside_the_frame(
    live_server: tuple[str, int],
    new_page: Any,
    seeded_db: tuple[Path, Path, int],
    page_id: int,
    step: int,
) -> None:
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    for _ in range(step):
        await page.get_by_role("button", name="Next flagged element").click()
    await settled(page)
    label = await page.evaluate(
        f"""() => {{
          const doc = {DOC};
          const r = doc.querySelector('#axcess-spotlight > div').getBoundingClientRect();
          const view = doc.documentElement;
          return [r.left, r.top, view.clientWidth - r.right, view.clientHeight - r.bottom];
        }}"""
    )
    assert all(edge >= 0 for edge in label), label
    text = await page.evaluate(f"() => {DOC}.querySelector('#axcess-spotlight > div').textContent")
    assert re.fullmatch(r"\d of 2", text)
    await page.context.close()
