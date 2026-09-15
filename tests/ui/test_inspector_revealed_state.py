"""The inspector must not blame drift for interaction-revealed findings.

The highlight pass searches the *load-state* capture. An element the interaction
probe only reached by operating a control was never in that capture, so failing
to find it is the expected result, not evidence the site changed. These tests
pin the two explanations apart: they are both real, and telling them apart is
the whole point.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from playwright import async_api as playwright_async

from audit.db.schema import connect

pytestmark = pytest.mark.ui

#: A selector that cannot match the stored capture, so the highlight pass
#: always misses — which is the branch under test.
MISSING_SELECTOR = "#never-present-at-load"
REVEALING_CONTROL = "Open booking dialog"


def _seed_finding(db_path: Path, scan_id: int, revealed_by: str | None) -> int:
    """Add one a11y finding whose target is absent from the capture."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)
        ).fetchone()
        assert page is not None, "seeded scan has no pages"
        conn.execute(
            "INSERT INTO page_a11y_findings (page_id, scan_id, rule_id, wcag_sc, "
            "wcag_level, impact, help, target_selector, failure_summary, "
            "html_snippet, target_hash, revealed_by) "
            "VALUES (?, ?, 'aria-dialog-name', '4.1.2', 'A', 'serious', "
            "'ARIA dialog nodes should have an accessible name', ?, 'no name', "
            "'<div role=\"dialog\"></div>', 'hash-revealed', ?)",
            (page["id"], scan_id, MISSING_SELECTOR, revealed_by),
        )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


async def _inspector_text(base: str, scan_id: int, page_id: int) -> str:
    """Open the inspector on the unmatchable finding and return its text."""
    url = (
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect"
        f"?selector={MISSING_SELECTOR.replace('#', '%23')}"
    )
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(url, wait_until="networkidle")
            # The highlight pass runs in requestIdleCallback, so the status
            # line settles a beat after the document is ready.
            await page.wait_for_timeout(1500)
            return await page.locator("body").inner_text()
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_revealed_finding_names_its_control_instead_of_blaming_drift(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
) -> None:
    db_path, _, scan_id = seeded_db
    page_id = _seed_finding(db_path, scan_id, REVEALING_CONTROL)

    text = await _inspector_text(live_server[0], scan_id, page_id)

    assert REVEALING_CONTROL in text
    assert "the page as it loaded" in text
    # The load capture is not stale, and saying so blames the site for a fact
    # about how the scan works.
    assert "changed since the scan" not in text


@pytest.mark.asyncio
async def test_load_state_finding_still_reports_a_possible_change(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
) -> None:
    db_path, _, scan_id = seeded_db
    page_id = _seed_finding(db_path, scan_id, None)

    text = await _inspector_text(live_server[0], scan_id, page_id)

    # Nothing revealed this one, so it genuinely should have been in the
    # capture and drift is the honest explanation.
    assert "changed since the scan" in text
    assert "the page as it loaded" not in text
