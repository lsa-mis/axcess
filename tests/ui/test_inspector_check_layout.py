"""A zoom and layout issue opens the saved page the way the check saw it.

The check found reflow failures in a 320-pixel window, clipped text in a
640 by 450 window (its stand-in for 200% zoom), and text-spacing failures
with WCAG's spacing stylesheet applied. At the inspector's full width none
of those were visible, so the highlight pointed at an element that looked
fine. The inspector now recreates the condition from the issue's rule.
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

CAPTURE = (
    "<!doctype html><html><head><title>Layout fixture</title></head><body>"
    '<main><h1>Layout fixture</h1><div id="wide" style="width:900px">A banner 900px wide</div>'
    "<p>A paragraph of text.</p></main></body></html>"
)


def _seed(db_path: Path, scan_id: int, rule: str) -> int:
    """Give a page the capture and one zoom and layout finding; returns the page id."""
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
        conn.execute(
            "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
            "wcag_level, impact, help, target_selector, failure_summary, html_snippet, "
            "target_hash) VALUES (?, ?, 'responsive', ?, '1.4.10', 'AA', 'serious', "
            "'Content must reflow', '#wide', 'wider than the window', "
            "'<div id=\"wide\" style=\"width:900px\">A banner 900px wide</div>', 'wide-1')",
            (page["id"], scan_id, rule),
        )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


async def _open(new_page: Any, base: str, scan_id: int, page_id: int, rule: str) -> Any:
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?issue=responsive:{rule}",
        wait_until="networkidle",
    )
    await playwright_async.expect(page.get_by_text("1 flagged element")).to_be_visible()
    return page


async def test_a_reflow_issue_is_shown_320_pixels_wide(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    rule = "responsive-reflow-overflow"
    page = await _open(new_page, base, scan_id, _seed(db_path, scan_id, rule), rule)
    try:
        await playwright_async.expect(
            page.get_by_text("As the zoom and layout check saw it:")
        ).to_be_visible()
        await playwright_async.expect(
            page.get_by_text("320 pixels wide", exact=False)
        ).to_be_visible()
        frame_box = await page.locator("iframe[title^='Saved copy']").bounding_box()
        assert frame_box and round(frame_box["width"]) == 320
        # The flagged element is outlined, inside the narrow window.
        wide = page.frame_locator("iframe[title^='Saved copy']").locator("#wide")
        await playwright_async.expect(wide).to_have_css("outline-style", "solid")
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)

        full = page.get_by_role("button", name="Show at full width")
        await full.click()
        await playwright_async.expect(full).to_have_attribute("aria-pressed", "true")
        await playwright_async.expect(
            page.get_by_text("As the zoom and layout check saw it:")
        ).to_have_count(0)
        frame_box = await page.locator("iframe[title^='Saved copy']").bounding_box()
        assert frame_box and frame_box["width"] > 800
    finally:
        await page.context.close()


async def test_a_zoom_issue_is_shown_in_the_checks_640_by_450_window(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    rule = "responsive-text-clipped"
    page = await _open(new_page, base, scan_id, _seed(db_path, scan_id, rule), rule)
    try:
        await playwright_async.expect(page.get_by_text("200% zoom", exact=False)).to_be_visible()
        frame_box = await page.locator("iframe[title^='Saved copy']").bounding_box()
        assert frame_box and (round(frame_box["width"]), round(frame_box["height"])) == (640, 450)
    finally:
        await page.context.close()


async def test_a_text_spacing_issue_is_shown_with_wcags_spacing(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    rule = "responsive-text-spacing-clipped"
    page = await _open(new_page, base, scan_id, _seed(db_path, scan_id, rule), rule)
    try:
        await playwright_async.expect(
            page.get_by_text("text spacing", exact=False).first
        ).to_be_visible()
        paragraph = page.frame_locator("iframe[title^='Saved copy']").locator("p")
        # 0.12em of the default 16px text.
        await playwright_async.expect(paragraph).to_have_css("letter-spacing", "1.92px")
        await page.get_by_role("button", name="Show at full width").click()
        await playwright_async.expect(paragraph).to_have_css("letter-spacing", "normal")
    finally:
        await page.context.close()
