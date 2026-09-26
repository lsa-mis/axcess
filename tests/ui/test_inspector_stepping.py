"""Stepping through an issue's flagged elements on the inspector's rendered page.

The Loaded DOM tab has had Previous / Next for its flagged markup; the
Rendered page tab now has the same control. These tests pin the position
text, which element is set apart as current (blue on maize, the others
red), that each step brings its element into view, and the ends of the
range.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

# Three flagged inputs, far enough apart that each needs its own scroll.
CAPTURE = (
    "<!doctype html><html><head><title>Stepping fixture</title></head><body>"
    + "".join(
        f'<div style="height:1200px"><input id="field-{n}" aria-label=""></div>' for n in (1, 2, 3)
    )
    + "</body></html>"
)
ISSUE_KEY = "axe:aria-input-field-name"


def _seed(db_path: Path, scan_id: int) -> int:
    """Give a page the capture and one finding per input; returns the page id."""
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
        for n in (1, 2, 3):
            conn.execute(
                "INSERT INTO page_a11y_findings (page_id, scan_id, rule_id, wcag_sc, "
                "wcag_level, impact, help, target_selector, failure_summary, "
                "html_snippet, target_hash) "
                "VALUES (?, ?, 'aria-input-field-name', '4.1.2', 'A', 'serious', "
                "'ARIA input fields must have an accessible name', ?, 'no name', ?, ?)",
                (
                    page["id"],
                    scan_id,
                    f"#field-{n}",
                    f'<input id="field-{n}" aria-label="">',
                    f"step-{n}",
                ),
            )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


async def test_previous_and_next_step_through_the_rendered_page(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed(db_path, scan_id)
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(
            f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue={ISSUE_KEY}",
            wait_until="networkidle",
        )
        group = page.get_by_role("group", name="Flagged elements", exact=True)
        status = group.get_by_role("status")
        previous = group.get_by_role("button", name="Previous flagged element")
        following = group.get_by_role("button", name="Next flagged element")
        await playwright_async.expect(status).to_have_text("Flagged element 1 of 3")
        await playwright_async.expect(previous).to_be_disabled()

        frame = page.frame_locator("iframe[title^='Saved copy']")

        async def assert_on(n: int) -> None:
            await playwright_async.expect(status).to_have_text(f"Flagged element {n} of 3")
            # The current element is blue on a maize halo; the rest stay red,
            # so the one you are on is told apart by more than thickness.
            for other in (1, 2, 3):
                colour = "rgb(0, 39, 76)" if other == n else "rgb(190, 0, 30)"
                await playwright_async.expect(frame.locator(f"#field-{other}")).to_have_css(
                    "outline-color", colour
                )
            # And the step brought it into the frame's view.
            await playwright_async.expect(frame.locator(f"#field-{n}")).to_be_in_viewport()

        # The first is marked as current from the start, not only after a click.
        await assert_on(1)
        await following.click()
        await assert_on(2)
        await following.click()
        await assert_on(3)
        await playwright_async.expect(following).to_be_disabled()
        await previous.click()
        await assert_on(2)

        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()
