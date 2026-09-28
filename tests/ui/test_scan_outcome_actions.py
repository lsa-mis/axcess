"""A stopped scan's card offers its actions in one shape, with one primary.

"Review what the scan found" was added to a partial report as a bare button
of its own width with no description, beside rows that each had a fixed-width
button and a sentence, and "Change settings first" stayed the primary action
though the scan had saved pages to review. Every action is now the same row,
and the one primary button is the likeliest next step: reviewing a partial
report, or changing the settings when no report was made.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

WHITE = "rgb(255, 255, 255)"


def _stopped_scan(db_path: Path, from_scan: int, *, with_pages: bool) -> int:
    """A stopped (interrupted) public scan; with the seeded scan's pages if asked."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'interrupted', ?)",
            ("https://example.com/", json.dumps({"seed_url": "https://example.com/"})),
        )
        scan_id = int(cur.lastrowid)
        if with_pages:
            columns = [
                row["name"]
                for row in conn.execute("PRAGMA table_info(pages)")
                if row["name"] not in ("id", "scan_id")
            ]
            names = ", ".join(columns)
            conn.execute(
                f"INSERT INTO pages (scan_id, {names}) "
                f"SELECT ?, {names} FROM pages WHERE scan_id = ?",
                (scan_id, from_scan),
            )
            # The scan row carries its own count; the card reads that.
            conn.execute(
                "UPDATE scans SET page_count = (SELECT COUNT(*) FROM pages WHERE scan_id = ?) "
                "WHERE id = ?",
                (scan_id, scan_id),
            )
        conn.commit()
        return scan_id
    finally:
        conn.close()


async def _actions(page: Any) -> list[tuple[str, str, str]]:
    """(name, background colour, description) of each action, in order."""
    return await page.evaluate(
        """() => [...document.querySelectorAll('main ul > li')]
          .map((li) => li.querySelector('a[data-button], button[data-button]'))
          .filter(Boolean)
          .map((el) => {
            const id = el.getAttribute('aria-describedby');
            const hint = id ? document.getElementById(id) : null;
            return [el.textContent.trim(), getComputedStyle(el).backgroundColor,
                    hint ? hint.textContent.trim() : ''];
          })"""
    )


async def test_a_partial_report_leads_with_review_and_every_action_has_words(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, seeded = live_server
    scan_id = _stopped_scan(db_path, seeded, with_pages=True)
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
        await playwright_async.expect(
            page.get_by_role("heading", name="Partial report", exact=True)
        ).to_be_visible()
        actions = await _actions(page)
        names = [name for name, _, _ in actions]
        assert names[:2] == ["Review what the scan found", "Change settings first"], names
        # One primary: the first action is filled, the rest are not.
        assert actions[0][1] != WHITE, actions
        assert all(colour == WHITE for _, colour, _ in actions[1:]), actions
        # Every action says what it does.
        assert all(hint for _, _, hint in actions), actions
        assert actions[0][2].startswith("Opens the issues found on the "), actions
        # The same width for every action's button.
        widths = await page.evaluate(
            """() => [...document.querySelectorAll('main ul > li')]
              .map((li) => li.querySelector('a[data-button], button[data-button]'))
              .filter(Boolean).map((el) => Math.round(el.getBoundingClientRect().width))"""
        )
        assert len(set(widths)) == 1, widths
        review = page.get_by_role("link", name="Review what the scan found")
        await playwright_async.expect(review).to_have_attribute(
            "href", f"/app/scans/{scan_id}/issues"
        )
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_no_report_leads_with_changing_the_settings(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    db_path, _, _ = seeded_db
    base, seeded = live_server
    scan_id = _stopped_scan(db_path, seeded, with_pages=False)
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
        await playwright_async.expect(
            page.get_by_role("heading", name="No report was produced", exact=True)
        ).to_be_visible()
        actions = await _actions(page)
        names = [name for name, _, _ in actions]
        assert names[0] == "Change settings first", names
        assert "Review what the scan found" not in names, names
        assert actions[0][1] != WHITE, actions
        assert all(colour == WHITE for _, colour, _ in actions[1:]), actions
    finally:
        await page.context.close()
