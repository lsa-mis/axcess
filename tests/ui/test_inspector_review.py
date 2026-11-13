"""A person's review in the page inspector, driven by keyboard alone.

Beside the element facts, "Your review: …" says the circled element's review
in words, and "Review this element" opens a modal dialog: "Checked by a
person" (three radios), Issue notes, "Save review" (saves and closes) and
"Close without saving". Previous / Next change which element it is for. An
unsaved edit is kept while the reader steps between elements, and leaving
the page discards it.
"""

from __future__ import annotations

import gzip
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ._inspector_case import open_inspector, seed
from .test_accessibility_axe import _AXE_TAGS, _AXE_TEXT, _render_violations

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect

RULE = "review-case"
CAPTURE = (
    "<!doctype html><html><body><main>"
    '<button id="one"></button><p>Some text between.</p><button id="two"></button>'
    "</main></body></html>"
)
FINDINGS = [("#one", '<button id="one"></button>'), ("#two", '<button id="two"></button>')]


def _reviews(db_path: Path) -> list[tuple[str, str | None, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT f.target_selector, r.decision, r.notes FROM occurrence_reviews r "
            "JOIN page_a11y_findings f ON f.id = r.a11y_finding_id ORDER BY f.id"
        ).fetchall()
    finally:
        conn.close()


async def _tab_to(page: Any, locator: Any, limit: int = 80) -> None:
    """Press Tab until ``locator`` has focus, as a keyboard user would."""
    for _ in range(limit):
        if await locator.evaluate("el => el === document.activeElement"):
            return
        await page.keyboard.press("Tab")
    raise AssertionError("Tab never reached the control")


async def _axe(page: Any, selector: str) -> list[dict[str, Any]]:
    await page.add_script_tag(content=_AXE_TEXT)
    violations: list[dict[str, Any]] = await page.evaluate(
        """async ([selector, tags]) => (await window.axe.run(
            document.querySelector(selector),
            { runOnly: { type: 'tag', values: tags } },
        )).violations""",
        [selector, _AXE_TAGS],
    )
    return violations


async def test_review_by_keyboard_alone(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    base, scan_id = live_server
    db_path = seeded_db[0]
    page_id = seed(db_path, scan_id, CAPTURE, RULE, FINDINGS)
    page = await open_inspector(new_page, base, scan_id, page_id, RULE)

    panel = page.get_by_role("group", name="The flagged element you are on")
    opener = panel.get_by_role("button", name="Review this element")
    # The review's own status message, beside its decision chip.
    status = panel.locator(
        "xpath=.//p[@role='status'][preceding-sibling::p[contains(@id, '-summary-label')]]"
    )
    dialog = page.get_by_role("dialog", name="Review this element")
    checked = dialog.get_by_role("group", name="Checked by a person")
    not_yet = checked.get_by_role("radio", name="Not checked yet")
    report = checked.get_by_role("radio", name="Checked: a problem to report")
    repeat = checked.get_by_role("radio", name="Checked: a repeat of one already reported")
    notes = dialog.get_by_role("textbox", name="Issue notes")
    save = dialog.get_by_role("button", name="Save review")

    # The review is said in words beside the facts, and on the button.
    await expect(panel).to_contain_text("Issue notes: None yet")
    await expect(opener).to_have_accessible_description("Your review: Not checked yet")
    await expect(dialog).to_be_hidden()

    # Open by keyboard: focus goes to the chosen radio in a named dialog.
    await _tab_to(page, opener)
    await page.keyboard.press("Enter")
    await expect(dialog).to_be_visible()
    await expect(dialog).to_have_accessible_description("Button")
    await expect(not_yet).to_be_focused()
    # The notes start as a suggestion from the scan, said so in the hint.
    await expect(notes).to_have_value("The button: Edge case.")
    await expect(notes).to_have_accessible_description(
        re.compile(r"^Suggested from the scan\. Read and edit it before you save\.")
    )

    # Choose with the arrow keys, write over the suggestion, save.
    await page.keyboard.press("ArrowDown")
    await expect(report).to_be_checked()
    await page.keyboard.press("Tab")
    await expect(notes).to_be_focused()
    await page.keyboard.press("ControlOrMeta+a")
    await page.keyboard.type("The first button has no accessible name.")
    await _tab_to(page, save, limit=3)
    await page.keyboard.press("Enter")

    # Saving closes the dialog, returns focus, and says so.
    await expect(dialog).to_be_hidden()
    await expect(opener).to_be_focused()
    await expect(status).to_have_text("Saved.")
    await expect(opener).to_have_accessible_description("Your review: Checked: a problem to report")
    await expect(panel).to_contain_text("Issue notes: The first button has no accessible name.")
    assert _reviews(db_path) == [("#one", "report", "The first button has no accessible name.")]

    # Reopening shows the saved review, and focus is on the chosen radio.
    # Saved notes are never replaced by a suggestion.
    await page.keyboard.press("Enter")
    await expect(report).to_be_focused()
    await expect(notes).to_have_value("The first button has no accessible name.")
    await expect(dialog).not_to_contain_text("Suggested from the scan")
    # Escape closes without saving and returns focus.
    await page.keyboard.press("Escape")
    await expect(dialog).to_be_hidden()
    await expect(opener).to_be_focused()

    # Next: the second element, with no review yet.
    await page.get_by_role("button", name="Next element").click()
    await expect(opener).to_have_accessible_description("Your review: Not checked yet")
    await expect(status).to_have_text("")
    # An unedited suggestion is not an unsaved change.
    await opener.click()
    await expect(notes).to_have_value("The button: Edge case.")
    await page.keyboard.press("Escape")
    await expect(panel).to_contain_text("Issue notes: None yet")
    await expect(panel).not_to_contain_text("Not saved yet")

    # An unsaved edit is kept when the dialog is closed without saving and
    # while stepping, and the line says it is not saved.
    await opener.click()
    await repeat.check()
    await notes.fill("Draft for the second button.")
    await dialog.get_by_role("button", name="Close without saving").click()
    await expect(dialog).to_be_hidden()
    await expect(opener).to_have_accessible_description(
        "Your review: Checked: a repeat of one already reported Not saved yet"
    )
    await expect(panel).to_contain_text("Issue notes: Draft for the second button.")
    await page.get_by_role("button", name="Previous element").click()
    await expect(opener).to_have_accessible_description("Your review: Checked: a problem to report")
    await page.get_by_role("button", name="Next element").click()
    await opener.click()
    await expect(repeat).to_be_checked()
    await expect(notes).to_have_value("Draft for the second button.")
    await page.keyboard.press("Escape")
    assert len(_reviews(db_path)) == 1  # the draft was never saved

    # Leaving the page discards the unsaved edit; the saved review stays.
    await page.reload(wait_until="networkidle")
    await expect(opener).to_have_accessible_description("Your review: Checked: a problem to report")
    await page.get_by_role("button", name="Next element").click()
    await expect(opener).to_have_accessible_description("Your review: Not checked yet")


async def test_review_passes_axe_and_fits_narrow_screens(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page_id = seed(seeded_db[0], scan_id, CAPTURE, RULE, FINDINGS)
    page = await open_inspector(new_page, base, scan_id, page_id, RULE)
    opener = page.get_by_role("button", name="Review this element")
    await expect(opener).to_be_visible()

    violations = await _axe(page, '[aria-label="The flagged element you are on"]')
    assert not violations, _render_violations(violations)
    await opener.click()
    violations = await _axe(page, "dialog[open]")
    assert not violations, _render_violations(violations)
    await page.keyboard.press("Escape")

    await page.set_viewport_size({"width": 320, "height": 640})
    await opener.click()
    dialog = page.get_by_role("dialog", name="Review this element")
    box = await dialog.bounding_box()
    assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 320
    assert box["y"] >= 0 and box["y"] + box["height"] <= 640
    assert await page.evaluate("document.documentElement.scrollWidth") <= 320
    # The dialog scrolls itself, so its buttons are reachable on a short screen.
    save = dialog.get_by_role("button", name="Save review")
    await save.scroll_into_view_if_needed()
    await expect(save).to_be_in_viewport()


async def test_inspector_still_outlines_when_reviews_cannot_be_read(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    """A database whose review table is out of date still shows the elements.

    This is the failure a reviewer hit: 0032 applied, 0033 not, so the page
    evidence failed and the inspector said the issue had no element to mark.
    """
    base, scan_id = live_server
    db_path = seeded_db[0]
    page_id = seed(db_path, scan_id, CAPTURE, RULE, FINDINGS)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE occurrence_reviews")
    conn.commit()
    conn.close()

    page = await open_inspector(new_page, base, scan_id, page_id, RULE)
    await expect(page.get_by_text("Flagged element 1 of 2")).to_be_visible()
    await expect(page.get_by_text("This issue has no element to mark")).to_have_count(0)


def _seed_finding(
    db_path: Path,
    scan_id: int,
    capture: str,
    *,
    rule: str,
    target: str,
    snippet: str,
    summary: str,
    state: tuple[str, str, str] | None = None,
) -> int:
    """One rule-check occurrence with the check's own sentence, as axe stores it.

    ``state`` is ``(state_key, control label, saved document)`` for an
    occurrence found only after clicking that control.
    """
    conn = sqlite3.connect(db_path)
    try:
        page_id = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(capture.encode()), page_id),
        )
        key = label = None
        if state:
            key, label, dom = state
            conn.execute(
                "INSERT INTO page_dom_states (page_id, scan_id, state_key, revealed_by, "
                "path_labels, encoding, dom) VALUES (?, ?, ?, ?, ?, 'gzip', ?)",
                (page_id, scan_id, key, label, f'["{label}"]', gzip.compress(dom.encode())),
            )
        conn.execute(
            "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
            "wcag_level, impact, help, target_selector, failure_summary, html_snippet, "
            "target_hash, revealed_by, revealed_state_key) "
            "VALUES (?, ?, 'axe', ?, '1.4.3', 'AA', 'serious', 'Rule help', ?, ?, ?, ?, ?, ?)",
            (page_id, scan_id, rule, target, summary, snippet, f"suggest-{rule}", label, key),
        )
        conn.commit()
        return int(page_id)
    finally:
        conn.close()


async def _suggestion(new_page: Any, base: str, scan_id: int, page_id: int, rule: str) -> str:
    page = await open_inspector(new_page, base, scan_id, page_id, rule)
    await page.get_by_role("button", name="Review this element").click()
    notes = page.get_by_role("dialog").get_by_role("textbox", name="Issue notes")
    await expect(notes).not_to_have_value("")
    value: str = await notes.input_value()
    await page.context.close()
    return value


async def test_suggested_notes_use_the_checks_own_contrast_sentence(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    """The ITS team's contrast notes are this sentence, with the element as its subject."""
    base, scan_id = live_server
    page_id = _seed_finding(
        seeded_db[0],
        scan_id,
        '<!doctype html><html><body><p id="low">Low text</p></body></html>',
        rule="color-contrast",
        target="#low",
        snippet='<p id="low">Low text</p>',
        summary=(
            "Fix any of the following:\n  Element has insufficient color contrast of 2.81 "
            "(foreground color: #555555, background color: #000000, font size: 13.2pt "
            "(17.6px), font weight: normal). Expected contrast ratio of 4.5:1"
        ),
    )
    assert await _suggestion(new_page, base, scan_id, page_id, "color-contrast") == (
        "“Low text” <p> element has insufficient color contrast of 2.81 (foreground color: "
        "#555555, background color: #000000, font size: 13.2pt (17.6px), font weight: "
        "normal). Expected contrast ratio of 4.5:1."
    )


async def test_suggested_notes_start_with_the_page_state(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    """An element found after a click: the click, the element, the problem, the detail."""
    base, scan_id = live_server
    dom = (
        '<!doctype html><html><body><div id="acc" tabindex="0" aria-expanded="true">'
        "Bonus Points</div></body></html>"
    )
    page_id = _seed_finding(
        seeded_db[0],
        scan_id,
        "<!doctype html><html><body><p>Before clicking.</p></body></html>",
        rule="aria-allowed-attr",
        target="#acc",
        snippet='<div id="acc" tabindex="0" aria-expanded="true">',
        summary='Fix all of the following:\n  ARIA attribute is not allowed: aria-expanded="true"',
        state=("click:bonus", "Bonus Points", dom),
    )
    assert await _suggestion(new_page, base, scan_id, page_id, "aria-allowed-attr") == (
        "After clicking “Bonus Points”, “Bonus Points” <div> element has an ARIA attribute "
        'its role does not support. ARIA attribute is not allowed: aria-expanded="true".'
    )


async def test_suggested_notes_leave_out_axes_other_ways_to_fix(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    """ "Fix any of the following" lists other ways to fix it, not the problem.

    A link with no name fails every way a link can get one; listing them all,
    or taking "Element has no title attribute" as the problem, misleads.
    """
    base, scan_id = live_server
    page_id = _seed_finding(
        seeded_db[0],
        scan_id,
        '<!doctype html><html><body><a id="x" href="/next"></a></body></html>',
        rule="link-name",
        target="#x",
        snippet='<a id="x" href="/next"></a>',
        summary="\n".join(
            [
                "Fix all of the following:",
                "  Element is in tab order and does not have accessible text",
                "",
                "Fix any of the following:",
                "  Element does not have text that is visible to screen readers",
                "  aria-label attribute does not exist or is empty",
                "  Element has no title attribute",
            ]
        ),
    )
    assert await _suggestion(new_page, base, scan_id, page_id, "link-name") == (
        "The link: Links have no name for screen readers."
    )


async def test_mark_not_checked_as_repeats_in_one_press(
    live_server: tuple[str, int], seeded_db: tuple[Path, Path, int], new_page: Any
) -> None:
    """Report the first, step through the rest, mark them all as repeats; undo."""
    base, scan_id = live_server
    db_path = seeded_db[0]
    capture = (
        "<!doctype html><html><body><main>"
        '<button id="one"></button><p>A</p><button id="two"></button>'
        '<p>B</p><button id="three"></button></main></body></html>'
    )
    findings = [*FINDINGS, ("#three", '<button id="three"></button>')]
    page_id = seed(db_path, scan_id, capture, RULE, findings)
    page = await open_inspector(new_page, base, scan_id, page_id, RULE)
    panel = page.get_by_role("group", name="The flagged element you are on")
    opener = panel.get_by_role("button", name="Review this element")
    dialog = page.get_by_role("dialog", name="Review this element")
    bulk = panel.get_by_role("button", name=re.compile(r"^Mark \d+ not checked as"))

    # Nothing reported in this issue yet: a repeat would be a repeat of
    # nothing, so the bulk button is not offered.
    await expect(opener).to_be_visible()
    await expect(bulk).to_have_count(0)

    # Report the first element; then the other two can be marked.
    await opener.click()
    await dialog.get_by_role("radio", name="Checked: a problem to report").check()
    await dialog.get_by_role("textbox", name="Issue notes").fill("No name on the button.")
    await dialog.get_by_role("button", name="Save review").click()
    # A note on the second, with no decision, must survive the bulk save.
    await page.get_by_role("button", name="Next element").click()
    await opener.click()
    await dialog.get_by_role("textbox", name="Issue notes").fill("Looked at it.")
    await dialog.get_by_role("button", name="Save review").click()

    await expect(bulk).to_have_text("Mark 2 not checked as repeats")
    await expect(bulk).to_have_accessible_description(
        re.compile(r"^Every flagged element in this page state with no review yet")
    )
    # Its own row, under "Review this element": the full label does not fit
    # beside it, and the label names exactly what it changes.
    opener_box, bulk_box = await opener.bounding_box(), await bulk.bounding_box()
    assert opener_box and bulk_box and bulk_box["y"] > opener_box["y"]

    # By keyboard: one press, said in words, focus on its undo.
    await _tab_to(page, bulk)
    await page.keyboard.press("Enter")
    undo = panel.get_by_role("button", name="Undo 2 repeats")
    await expect(undo).to_be_focused()
    await expect(panel).to_contain_text("2 elements marked as repeats.")
    await expect(opener).to_have_accessible_description(
        "Your review: Checked: a repeat of one already reported"
    )
    assert _reviews(db_path) == [
        ("#one", "report", "No name on the button."),
        ("#two", "repeat", "Looked at it."),
        ("#three", "repeat", ""),
    ]

    # Undo puts exactly those back, notes kept, and focus returns.
    await page.keyboard.press("Enter")
    await expect(panel).to_contain_text("2 elements set back to not checked yet.")
    await expect(bulk).to_be_focused()
    assert _reviews(db_path) == [
        ("#one", "report", "No name on the button."),
        ("#two", None, "Looked at it."),
        ("#three", None, ""),
    ]
    await expect(page.get_by_role("button", name="Mark as repeat")).to_have_count(0)
