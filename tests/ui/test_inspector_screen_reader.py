"""A screen reader can find the flagged element in the Page inspector.

The box and label over the saved copy are drawn for the eye and hidden from
screen readers, so the inspector gives the same thing in words and a way
in. After each step, the stepper's status says what the element is.
Keyboard focus coming into the saved copy goes on to the element itself,
which then has "Flagged element N of M" as its description; Tab goes on from
it in the page's order, and Escape goes back to where the reader was. The
frame's name says both. A click in the copy is left where it landed. The
label also stays inside the frame for an element at the very top or side of
the page, where it used to be cut off.
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


# A flagged heading the page hides, then a link: focus cannot land on the
# heading, so focus coming in stays where Tab put it, on the first link.
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


async def test_tab_into_the_copy_goes_to_the_element_and_escape_goes_back(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    assert not await page.get_by_role("button", name="Go to element").count()
    await playwright_async.expect(_frame(page)).to_have_attribute(
        "title",
        re.compile(
            r"^Saved copy: .+\. Tab into it goes to the flagged element\. "
            r"Press Escape to go back to where you were\.$"
        ),
    )
    last = await _tab_into_copy(page)
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    heading = copy.locator("#status")
    await playwright_async.expect(heading).to_be_focused()
    await playwright_async.expect(heading).to_have_accessible_description("Flagged element 1 of 2")
    # Focusable from the move only: the page's own tab order is unchanged.
    assert await heading.get_attribute("tabindex") == "-1"
    await page.keyboard.press("Escape")
    assert await page.evaluate("() => document.activeElement.tagName") != "IFRAME"
    assert await page.evaluate("() => document.activeElement.textContent") == last
    await page.context.close()


async def test_focus_follows_the_reader_and_tab_goes_on_in_page_order(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    """After Next element, focus coming in lands on the new element; from
    the first, Tab goes on to the next stop in the page's own order."""
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    await _tab_into_copy(page)
    await playwright_async.expect(copy.locator("#status")).to_be_focused()
    await page.keyboard.press("Tab")
    await playwright_async.expect(copy.locator("#skip")).to_be_focused()
    await page.keyboard.press("Escape")
    await page.get_by_role("button", name="Next element").click()
    await _tab_into_copy(page)
    await playwright_async.expect(copy.locator("#skip")).to_be_focused()
    # A link takes focus already, so it is given no tab index.
    assert await copy.locator("#skip").get_attribute("tabindex") is None
    await page.context.close()


# A flagged heading between two links, to check both directions of Tab.
MIDDLE_CAPTURE = (
    "<!doctype html><html><head><title>Reader fixture</title></head>"
    "<body><a id='before' href='#a'>Before</a>"
    "<h2 id='middle'>Middle</h2>"
    "<a id='after' href='#b'>After</a></body></html>"
)
MIDDLE_FINDINGS = [("#middle", '<h2 id="middle">Middle</h2>')]


async def test_tab_and_shift_tab_go_on_from_the_element_in_page_order(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int]
) -> None:
    """From the flagged element, Tab goes to the stop after it on the page,
    and Shift+Tab to the stop before it, not to the top of the copy."""
    db_path, _, scan_id = seeded_db
    middle_page = seed(db_path, scan_id, MIDDLE_CAPTURE, RULE, MIDDLE_FINDINGS)
    base, _ = live_server
    page = await open_inspector(new_page, base, scan_id, middle_page, RULE)
    await page.get_by_role("button", name="Show element").wait_for()
    await settled(page)
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    await _tab_into_copy(page)
    await playwright_async.expect(copy.locator("#middle")).to_be_focused()
    await page.keyboard.press("Tab")
    await playwright_async.expect(copy.locator("#after")).to_be_focused()
    await page.keyboard.press("Escape")
    await _tab_into_copy(page)
    await playwright_async.expect(copy.locator("#middle")).to_be_focused()
    await page.keyboard.press("Shift+Tab")
    await playwright_async.expect(copy.locator("#before")).to_be_focused()
    await page.context.close()


async def test_a_click_in_the_copy_stays_where_it_landed(
    live_server: tuple[str, int], new_page: Any, seeded_db: tuple[Path, Path, int], page_id: int
) -> None:
    """A click on another link in the copy keeps focus on that link: only
    keyboard focus coming in is moved to the flagged element."""
    base, _ = live_server
    page = await _inspector(new_page, base, seeded_db[2], page_id)
    copy = page.frame_locator('iframe[title^="Saved copy"]')
    await copy.locator("#skip").click()
    await playwright_async.expect(copy.locator("#skip")).to_be_focused()
    await page.context.close()


async def test_a_hidden_element_is_not_promised(
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
    assert "flagged element" not in (await frame.get_attribute("title") or "")
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
    """On a short window the saved copy starts below the screen; after focus
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
