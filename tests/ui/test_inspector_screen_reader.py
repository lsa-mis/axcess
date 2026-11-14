"""A screen reader can find the flagged element in the Page inspector.

The box and label over the saved copy are drawn for the eye and hidden from
screen readers, so the inspector gives the same thing in words and a way
in. After each step, the stepper's status says what the element is. Tab
into the saved copy starts on the element itself, which then has "Flagged
element N of M" as its description, and Escape goes back to where the reader
was; the frame's name says both. A click in the copy is left where it
landed. The label also stays inside the frame for an element at the very top
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


# A flagged heading the page hides, then a link: Tab cannot stop on the
# heading, so the copy's tab order starts at the top as the page has it.
HIDDEN_CAPTURE = (
    "<!doctype html><html><head><title>Reader fixture</title></head>"
    "<body><h5 id='gone' style='display:none'>Gone</h5>"
    "<a id='first' href='#main'>First link</a><main id='main'><p>Text.</p></main>"
    "</body></html>"
)
HIDDEN_FINDINGS = [("#gone", '<h5 id="gone" style="display:none">Gone</h5>')]


async def _inspector(new_page: Any, base: str, scan_id: int, page_id: int) -> Any:
    page = await open_inspector(new_page, base, scan_id, page_id, RULE)
    await page.get_by_role("button", name="Next element").wait_for()
    await settled(page)
    return page


def _frame(page: Any) -> Any:
    return page.locator('iframe[title^="Saved copy"]')


async def _tab_into_copy(page: Any) -> str:
    """From the toolbar, press Tab until focus is inside the saved copy.

    Returns the text of the last control outside the copy that had focus,
    where Escape should go back to.
    """
    await page.get_by_role("button", name="Hide highlights").focus()
    for _ in range(20):
        last = await page.evaluate("() => document.activeElement.textContent")
        await page.keyboard.press("Tab")
        if await page.evaluate("() => document.activeElement.tagName === 'IFRAME'"):
            return str(last)
    raise AssertionError("Tab never reached the saved copy")


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
    await page.get_by_role("button", name="Next element").click()
    await playwright_async.expect(status).to_have_text(
        "Flagged element 2 of 2: Link, “Skip to main content”"
    )
    await page.context.close()


async def test_tab_starts_on_the_element_and_escape_goes_back(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    assert not await page.get_by_role("button", name="Go to element").count()
    await playwright_async.expect(_frame(page)).to_have_attribute(
        "title",
        re.compile(
            r"^Saved copy: .+\. Tab starts on the flagged element\. "
            r"Press Escape to go back to where you were\.$"
        ),
    )
    last = await _tab_into_copy(page)
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    heading = copy.locator("#status")
    await playwright_async.expect(heading).to_be_focused()
    await playwright_async.expect(heading).to_have_accessible_description("Flagged element 1 of 2")
    # The tab start, and only on the element the reader is on.
    assert await heading.get_attribute("tabindex") == "1"
    await page.keyboard.press("Escape")
    assert await page.evaluate("() => document.activeElement.tagName") != "IFRAME"
    assert await page.evaluate("() => document.activeElement.textContent") == last
    await page.context.close()


async def test_the_tab_start_moves_with_the_reader(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    """Next element moves the tab start, and gives the last element back the
    tab index the page gave it (none)."""
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    await page.get_by_role("button", name="Next element").click()
    await playwright_async.expect(copy.locator("#skip")).to_have_attribute("tabindex", "1")
    assert await copy.locator("#status").get_attribute("tabindex") is None
    await _tab_into_copy(page)
    await playwright_async.expect(copy.locator("#skip")).to_be_focused()
    await page.context.close()


async def test_a_click_in_the_copy_stays_where_it_landed(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    """Nothing moves focus when it enters the copy: a click elsewhere in the
    copy does not land on the flagged element (SC 3.2.1 On Focus)."""
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    await copy.locator("main p").click()
    focused = await page.evaluate(f"() => {DOC}.activeElement.id")
    assert focused != "status"
    await page.context.close()


async def test_a_hidden_element_is_not_promised_as_the_tab_start(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    hidden_page = seed(db_path, scan_id, HIDDEN_CAPTURE, RULE, HIDDEN_FINDINGS)
    base, _ = live_server
    page = await open_inspector(new_page, base, scan_id, hidden_page, RULE)
    await page.get_by_role("button", name="Show element").wait_for()
    await settled(page)
    frame = _frame(page)
    await playwright_async.expect(frame).to_have_attribute(
        "title", re.compile(r"Press Escape to go back to where you were\.$")
    )
    assert "Tab starts" not in (await frame.get_attribute("title") or "")
    await _tab_into_copy(page)
    await playwright_async.expect(
        page.frame_locator('iframe[title^="Saved copy"]').locator("#first")
    ).to_be_focused()
    await page.context.close()


@pytest.mark.parametrize("size", [(1280, 500), (320, 640)], ids=["short window", "phone"])
async def test_tab_brings_the_element_into_view(
    live_server: tuple[str, int],
    new_page: Any,
    seeded_db: tuple[Path, Path, int],
    page_id: int,
    size: tuple[int, int],
) -> None:
    """On a short window the saved copy starts below the screen; after Tab
    lands on the element, it is fully on screen, below the sticky top bar."""
    base, _ = live_server
    width, height = size
    page = await new_page(viewport={"width": width, "height": height})
    await page.goto(
        f"{base}/app/scans/{seeded_db[2]}/pages/{page_id}/inspect?issue=axe:{RULE}",
        wait_until="networkidle",
    )
    await page.get_by_role("button", name="Next element").wait_for()
    await settled(page)
    await _tab_into_copy(page)
    await playwright_async.expect(
        page.frame_locator('iframe[title^="Saved copy"]').locator("#status")
    ).to_be_focused()
    top, bottom, bar, screen = await page.evaluate(
        f"""() => {{
          const frame = document.querySelector('iframe[title^="Saved copy"]')
            .getBoundingClientRect();
          const r = {DOC}.activeElement.getBoundingClientRect();
          const bar = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop);
          return [frame.top + r.top, frame.top + r.bottom, bar, innerHeight];
        }}"""
    )
    assert bar <= top and bottom <= screen, (top, bottom, bar, screen)
    await page.context.close()


async def test_only_the_current_element_is_described(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    await page.get_by_role("button", name="Next element").click()
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    await playwright_async.expect(copy.locator("#skip")).to_have_accessible_description(
        "Flagged element 2 of 2"
    )
    await playwright_async.expect(copy.locator("#status")).to_have_accessible_description("")
    described = await page.evaluate(
        f"() => {DOC}.querySelectorAll('[aria-describedby~=\"axcess-flagged-note\"]').length"
    )
    assert described == 1
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
        await page.get_by_role("button", name="Next element").click()
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
