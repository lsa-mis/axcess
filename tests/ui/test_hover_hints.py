"""Words that need explaining say what they mean on hover.

The Issues table's Type and Found by tags carry the glossary's own sentences,
the column headers say what their column counts, the priority band says what
it ranks, a level badge names its level, and a status chip says whose
decision it is. The glossary, where each meaning is printed beside its tag,
adds no hint of its own.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

LANE_HELP = {
    "Barrier": (
        "A rule check (axe or Alfa) failed a fixed rule, so this is likely to block someone. "
        "Fix it, test the fix, then scan again to see if it is still found."
    ),
    "Needs review": (
        "A possible problem from a less certain check, such as the AI review or a rule check "
        "that cannot tell. A person must confirm it before you report it as a barrier."
    ),
    "Informational": (
        "Recorded for context, not a problem to fix, such as an image whose alt text already "
        "says the same words."
    ),
}
FOUND_BY_HELP = {
    "WCAG": (
        "Found at page load, by a rule check (axe or Alfa), a browser check such as the "
        "keyboard check, or the AI review."
    ),
    "Click-Through": (
        "Found only in a page state opened by clicking a control, such as a menu, tab, or "
        "dialog. Use that control first to see it."
    ),
    "Alt Text": (
        "Found by the image text check: text in an image, and whether its alt text (what a "
        "screen reader reads) says the same."
    ),
}


async def _hints(scope: Any, words: dict[str, str]) -> list[tuple[str, str | None]]:
    """``(word, title)`` for every span in ``scope`` whose text is one of ``words``."""
    return [
        (word, title)
        for word, title in await scope.evaluate(
            """(root, words) => [...root.querySelectorAll('span')]
                .filter((el) => words.includes(el.textContent.trim()) && !el.querySelector('span'))
                .map((el) => [el.textContent.trim(), el.getAttribute('title')])""",
            list(words),
        )
    ]


async def test_issue_tags_headers_and_bands_explain_themselves(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
        table = page.get_by_role("table", name="Accessibility issues")
        body = table.locator("tbody")

        lanes = await _hints(body, LANE_HELP)
        found_by = await _hints(body, FOUND_BY_HELP)
        assert lanes and found_by
        assert all(title == LANE_HELP[word] for word, title in lanes), lanes
        assert all(title == FOUND_BY_HELP[word] for word, title in found_by), found_by

        headers = {
            "Type": "How sure the evidence is: Barrier, Needs review, or Informational.",
            "Found by": "Which group of checks found the issue.",
        }
        # On the sort button, the header's focusable part, so a screen reader
        # reads it as the button's description.
        for name, hint in headers.items():
            button = table.get_by_role("columnheader", name=name, exact=False).get_by_role("button")
            await playwright_async.expect(button).to_have_attribute("title", hint)
            await playwright_async.expect(button).to_have_accessible_description(hint)
        await playwright_async.expect(
            table.get_by_role("columnheader", name="Priority", exact=False).get_by_role("button")
        ).to_have_attribute(
            "title", re.compile(r"^High, Medium, or Low, from the issue's impact rating")
        )

        bands = await _hints(body, {"High": "", "Medium": "", "Low": ""})
        assert bands, "no priority band in the seeded issues"
        assert all(title and title.startswith("Look at these") for _, title in bands), bands

        levels = await body.evaluate(
            """(root) => [...root.querySelectorAll('span[title^="Level "]')]
                .map((el) => [el.textContent.replace('Level', '').trim(), el.title])"""
        )
        assert levels, "no level badge in the seeded issues"
        for level, title in levels:
            assert title.startswith(f"Level {level}: "), (level, title)
            assert "Web Content Accessibility Guidelines (WCAG)" in title

        # The glossary prints each meaning beside its tag, so its tags add none,
        # and it spells out the priority bands for those who cannot hover.
        await page.get_by_role(
            "button", name="What Barrier, Needs review and the other labels mean", exact=True
        ).click()
        terms = page.get_by_role("term")
        await playwright_async.expect(terms.filter(has_text="Needs review")).to_be_visible()
        assert await terms.locator("[title]").count() == 0
        await playwright_async.expect(
            page.get_by_role("heading", name="Priority: which issues to look at first", level=3)
        ).to_be_visible()
        await playwright_async.expect(
            page.get_by_role("definition").filter(has_text="a critical problem on 1 page is Low")
        ).to_be_visible()
    finally:
        await page.context.close()


async def test_a_status_chip_says_whose_decision_it_is(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/findings", wait_until="networkidle")
        chip = page.locator("span[title]", has_text=re.compile(r"^New$")).first
        await playwright_async.expect(chip).to_have_attribute(
            "title", "No one has set a status for it in this report yet."
        )
    finally:
        await page.context.close()


async def test_keyboard_focus_keeps_the_hint_as_the_description(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    """In the "Always" setting a focused control shows its hint and keeps its title.

    The visible hint used to take the title away while it showed, so a screen
    reader lost the description exactly when the control had focus.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.add_init_script(
        "localStorage.setItem('axcess.preferences', JSON.stringify({hints: 'always'}))"
    )
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
        table = page.get_by_role("table", name="Accessibility issues")
        button = table.get_by_role("columnheader", name="Type", exact=False).get_by_role("button")
        hint = "How sure the evidence is: Barrier, Needs review, or Informational."
        await button.focus()
        await playwright_async.expect(page.get_by_text(hint, exact=True)).to_be_visible()
        await playwright_async.expect(button).to_have_attribute("title", hint)
        await playwright_async.expect(button).to_have_accessible_description(hint)
    finally:
        await page.context.close()


async def test_hovering_keeps_the_hint_as_the_description(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    """Under a pointer the title is parked (no double tooltip), but not the description.

    A screen reader user may also use a pointer: while the visible hint shows,
    the words stay the control's description, and the title comes back after.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.add_init_script(
        "localStorage.setItem('axcess.preferences', JSON.stringify({hints: 'always'}))"
    )
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
        table = page.get_by_role("table", name="Accessibility issues")
        button = table.get_by_role("columnheader", name="Type", exact=False).get_by_role("button")
        hint = "How sure the evidence is: Barrier, Needs review, or Informational."
        await button.hover()
        await playwright_async.expect(page.get_by_text(hint, exact=True)).to_be_visible()
        await playwright_async.expect(button).not_to_have_attribute("title", hint)
        await playwright_async.expect(button).to_have_accessible_description(hint)
        # Moving away puts the title back and removes the description it added.
        await page.mouse.move(5, 5)
        await playwright_async.expect(button).to_have_attribute("title", hint)
        assert await button.get_attribute("aria-description") is None
    finally:
        await page.context.close()
