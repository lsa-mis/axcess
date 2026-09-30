"""The saved copy outlines only elements the evidence names, and says which one you are on.

The inspector used to take the first element whose markup looked the same
whenever an occurrence's locator did not verify, so a row of identical cards
could have the wrong one outlined. It also drew the current element's outline
on the element itself, which vanished on a tiny or empty element. Now an
occurrence is outlined only when its locator (checked against its markup) or
its markup alone names one element; the current one gets a numbered box over
it; and a short table under the toolbar says what the box is on, with its
element locator, which can be shown in full and copied.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

CAPTURE = (
    "<!doctype html><html><head><title>Strict fixture</title></head><body><main>"
    '<div style="height:600px"><a id="big" href="/big">Read the big story</a></div>'
    # Two identical links: a generic locator cannot say which one is meant.
    '<p><a class="more" href="/more">More</a></p><p><a class="more" href="/more">More</a></p>'
    '<div style="height:600px"><a id="tiny" href="/tiny" style="font-size:2px">x</a></div>'
    '<div style="height:600px"><span id="empty" class="icon"></span></div>'
    '<nav><button type="button" class="px-4 py-2 rounded-full text-sm font-medium">'
    "Tab one</button></nav>"
    "<footer><span>Powered by the fixture</span></footer>"
    "</main></body></html>"
)


def _seed(db_path: Path, scan_id: int, findings: list[tuple[str, str, str, str]]) -> int:
    """(pipeline, rule, selector, snippet) findings on a page with the capture."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(CAPTURE.encode()), page["id"]),
        )
        for n, (pipeline, rule, selector, snippet) in enumerate(findings):
            conn.execute(
                "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
                "wcag_level, impact, help, target_selector, failure_summary, html_snippet, "
                "target_hash) VALUES (?, ?, ?, ?, '2.4.4', 'A', 'serious', 'Link purpose', "
                "?, 'unclear', ?, ?)",
                (page["id"], scan_id, pipeline, rule, selector, snippet, f"strict-{n}"),
            )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


def _fact(page: Any, term: str) -> Any:
    """The value (dd) beside one label (dt) in the table under the inspector toolbar."""
    return (
        page.get_by_role("group", name="The flagged element you are on", exact=True)
        .locator("dl > div")
        .filter(has=page.locator("dt").get_by_text(term, exact=True))
        .locator("dd")
    )


async def _open(new_page: Any, base: str, scan_id: int, page_id: int, issue: str) -> Any:
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue={issue}",
        wait_until="networkidle",
    )
    return page


async def test_identical_markup_is_not_guessed(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(
        db_path,
        scan_id,
        [
            ("axe", "link-name", "#big", '<a id="big" href="/big">Read the big story</a>'),
            # Matches both identical links; the markup cannot tell them apart.
            ("axe", "link-name", "a.more", '<a class="more" href="/more">More</a>'),
        ],
    )
    page = await _open(new_page, base, scan_id, page_id, "axe:link-name")
    try:
        await playwright_async.expect(page.get_by_text("1 flagged element")).to_be_visible()
        frame = page.frame_locator("iframe[title^='Saved copy']")
        await playwright_async.expect(frame.locator(".axcess-inspect-highlight")).to_have_count(1)
        await playwright_async.expect(
            frame.locator("a.more.axcess-inspect-highlight")
        ).to_have_count(0)
        await playwright_async.expect(
            page.get_by_text(
                "1 occurrence is not outlined: its markup appears in more than one place in "
                "this saved copy, and Axcess does not guess which."
            )
        ).to_be_visible()
    finally:
        await page.context.close()


async def test_the_current_element_gets_a_numbered_box_and_a_description(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(
        db_path,
        scan_id,
        [
            ("axe", "link-name", "#big", '<a id="big" href="/big">Read the big story</a>'),
            (
                "axe",
                "link-name",
                "#tiny",
                '<a id="tiny" href="/tiny" style="font-size:2px">x</a>',
            ),
            ("axe", "link-name", "#empty", '<span id="empty" class="icon"></span>'),
        ],
    )
    page = await _open(new_page, base, scan_id, page_id, "axe:link-name")
    try:
        group = page.get_by_role("group", name="Flagged elements", exact=True)
        await playwright_async.expect(group.get_by_role("status")).to_have_text(
            "Flagged element 1 of 3"
        )
        frame = page.frame_locator("iframe[title^='Saved copy']")
        box = frame.locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("1 of 3")
        # The same labels in the same places for every element; the toolbar
        # status above says which one it is, so the table does not repeat it.
        facts = page.get_by_role("group", name="The flagged element you are on", exact=True)
        labels = ["What it is", "Text or label", "Size", "Element locator (CSS selector)"]
        await playwright_async.expect(facts.locator("dt")).to_have_text(labels)
        await playwright_async.expect(page.get_by_text("Flagged element 1:")).to_have_count(0)
        await playwright_async.expect(_fact(page, "What it is")).to_have_text("Link")
        await playwright_async.expect(_fact(page, "Text or label")).to_have_text(
            "“Read the big story”"
        )
        locator = _fact(page, "Element locator (CSS selector)").locator("code")
        await playwright_async.expect(locator).to_have_text("#big")
        await playwright_async.expect(
            page.get_by_role("button", name="Copy element locator", exact=True)
        ).to_be_visible()

        # A tiny link: the box is still big enough to see, and labelled.
        await group.get_by_role("button", name="Next flagged element").click()
        await playwright_async.expect(box).to_have_text("2 of 3")
        size = await box.evaluate("el => [el.offsetWidth, el.offsetHeight]")
        assert size[0] >= 26 and size[1] >= 26, size
        await playwright_async.expect(locator).to_have_text("#tiny")
        await playwright_async.expect(_fact(page, "Text or label")).to_have_text("“x”")
        await playwright_async.expect(facts.locator("dt")).to_have_text(labels)

        # An empty element: said to have no visible size.
        await group.get_by_role("button", name="Next flagged element").click()
        await playwright_async.expect(box).to_have_text("3 of 3")
        await playwright_async.expect(_fact(page, "What it is")).to_have_text("<span> element")
        await playwright_async.expect(_fact(page, "Text or label")).to_have_text("None found")
        await playwright_async.expect(_fact(page, "Size")).to_contain_text("0 pixels wide")
        await playwright_async.expect(_fact(page, "Size")).to_contain_text(
            "It has no visible size in this saved copy, so the box marks where it sits."
        )
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_alfa_records_are_matched_by_tag_attributes_and_text(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    button = json.dumps(
        {
            "type": "element",
            "path": "/html[1]/body[1]/main[1]/nav[1]/button[1]",
            "name": "button",
            # Alfa shortens a long value and ends it with an ellipsis.
            "attributes": [
                {"name": "type", "value": "button"},
                {"name": "class", "value": "px-4 py-2 rounded-f…"},
            ],
        }
    )
    text = json.dumps(
        {
            "type": "text",
            "path": "/html[1]/body[1]/main[1]/footer[1]/span[1]/text()[1]",
            "data": "Powered by the fixture",
        }
    )
    page_id = _seed(
        db_path, scan_id, [("alfa", "sia-r111", button, button), ("alfa", "sia-r111", text, text)]
    )
    page = await _open(new_page, base, scan_id, page_id, "alfa:sia-r111")
    try:
        await playwright_async.expect(page.get_by_text("2 places highlighted")).to_be_visible()
        frame = page.frame_locator("iframe[title^='Saved copy']")
        await playwright_async.expect(
            frame.locator("nav button.axcess-inspect-highlight")
        ).to_have_count(1)
        await playwright_async.expect(
            frame.locator("footer span.axcess-inspect-highlight")
        ).to_have_count(1)
        # An Alfa record's locator is an XPath, and is named as one.
        await playwright_async.expect(
            _fact(page, "Element locator (XPath)").locator("code")
        ).to_have_text("/html[1]/body[1]/main[1]/nav[1]/button[1]")
    finally:
        await page.context.close()


_LONG_SELECTOR = 'html > body > main > div:nth-child(1) > a#big[href="/big"]'
_FAKE_CLIPBOARD = """
Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: { writeText: async (text) => { window.__copied = text; } },
});
"""


async def test_a_long_locator_shows_its_end_and_copies_whole(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(
        db_path,
        scan_id,
        [("axe", "link-name", _LONG_SELECTOR, '<a id="big" href="/big">Read the big story</a>')],
    )
    page = await new_page(viewport={"width": 320, "height": 900})
    await page.add_init_script(_FAKE_CLIPBOARD)
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:link-name",
        wait_until="networkidle",
    )
    try:
        code = _fact(page, "Element locator (CSS selector)").locator("code")
        # The whole locator is the text, whatever is cut on screen.
        await playwright_async.expect(code).to_have_text(_LONG_SELECTOR)
        assert await page.evaluate("document.documentElement.scrollWidth") <= 320

        show = page.get_by_role("button", name="Show all", exact=True)
        await playwright_async.expect(show).to_have_attribute("aria-expanded", "false")
        await show.click()
        less = page.get_by_role("button", name="Show less", exact=True)
        await playwright_async.expect(less).to_have_attribute("aria-expanded", "true")
        await playwright_async.expect(code).to_have_text(_LONG_SELECTOR)
        await less.click()
        assert await page.evaluate("document.activeElement.tagName") == "BUTTON"

        copy = page.get_by_role("button", name="Copy element locator", exact=True)
        await copy.click()
        await playwright_async.expect(
            page.get_by_role("status").filter(has_text="Copied")
        ).to_be_visible()
        assert await page.evaluate("window.__copied") == _LONG_SELECTOR
        await playwright_async.expect(copy).to_have_accessible_name("Copy element locator")

        # No clipboard (plain http on a network address): shown and selected.
        await page.evaluate(
            "() => { navigator.clipboard.writeText = () => Promise.reject(new Error('blocked')); }"
        )
        await copy.click()
        await playwright_async.expect(
            page.get_by_text("Not copied. Your browser did not allow it.", exact=False)
        ).to_be_visible()
        await playwright_async.expect(less).to_have_attribute("aria-expanded", "true")
        selected = await page.evaluate("String(getSelection())")
        assert " ".join(selected.split()) == _LONG_SELECTOR
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


@pytest.mark.parametrize("width", [430, 460, 480, 520, 800])
async def test_the_locator_toggle_holds_still_at_every_width(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any, width: int
) -> None:
    """The Show all button stays put, whatever the width.

    It used to appear only when the locator was cut, which narrowed the
    locator's box, which changed whether it was cut: at widths where one state
    wrapped and the other did not, the button came and went every frame.
    """
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(
        db_path,
        scan_id,
        [
            (
                "axe",
                "link-name",
                "html > body > main > div:nth-child(1) > a#big",
                '<a id="big" href="/big">Read the big story</a>',
            )
        ],
    )
    page = await new_page(viewport={"width": width, "height": 900})
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue=axe:link-name",
        wait_until="networkidle",
    )
    try:
        toggle = page.locator("button[aria-controls='inspect-locator']")
        await playwright_async.expect(toggle).to_have_count(1)
        seen = await toggle.evaluate(
            """async (el) => {
                const states = new Set();
                for (let i = 0; i < 30; i++) {
                    await new Promise((resolve) => requestAnimationFrame(resolve));
                    states.add(getComputedStyle(el).visibility + ":" + el.isConnected);
                }
                return [...states];
            }"""
        )
        assert len(seen) == 1, seen
        assert await page.evaluate("document.documentElement.scrollWidth") <= width
    finally:
        await page.context.close()
