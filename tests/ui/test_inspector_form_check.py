"""A form error check occurrence is outlined in the page-load copy.

The check presses a form's submit control, so its occurrence records the
control ("revealed by Submit"). But the occurrence is the form itself, which
is on the page from the start. On Accessible University's "before" page the
inspector said the form "may not appear here" and outlined nothing: the
check keeps the first 600 characters of the form's code, and the inspector
did not know that cut, so a longer form's code matched nothing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

from ._inspector_case import DOC, seed

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

# As on Accessible University's "before" page, and longer than 600 characters.
_FIELDS = "".join(
    f'<div class="required">{name}: <input type="text" name="{name.lower()}"></div>\n'
    for name in ("Name", "Email", "Phone", "Street", "City", "Postcode", "Country", "Course")
)
_FORM = (
    '<form action="#" method="post">\n<div id="error"></div>\n'
    + _FIELDS
    + '<input type="submit" value="Submit">\n</form>'
)
_PAGE = (
    "<!doctype html><html><head><title>Apply</title></head><body>"
    '<div id="appForm"><div class="heading">Apply Now!</div>' + _FORM + "</div></body></html>"
)


def _seed_form_occurrence(db_path: Path, scan_id: int) -> int:
    page_id = seed(db_path, scan_id, _PAGE, "unused", [])
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
            "wcag_level, impact, help, target_selector, failure_summary, html_snippet, "
            "target_hash, revealed_by) VALUES (?, ?, 'forms', 'form-error-not-described', "
            "'3.3.1', 'A', 'serious', 'Form error', ?, 'no text', ?, 'form-au', 'Submit')",
            # The check's own cut: ``r.outerHTML.slice(0, 600)`` in forms/probe.py.
            (page_id, scan_id, "#appForm > form:nth-of-type(1)", _FORM[:600]),
        )
        conn.commit()
    finally:
        conn.close()
    return page_id


async def test_a_long_form_is_outlined_at_page_load(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    assert len(_FORM) > 600, "the form must be longer than the check's cut"
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    page_id = _seed_form_occurrence(db_path, scan_id)
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(
            f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect"
            "?issue=forms:form-error-not-described",
            wait_until="networkidle",
        )
        box = page.frame_locator("iframe[title^='Saved copy']").locator("#axcess-spotlight")
        await playwright_async.expect(box).to_have_text("Flagged element")
        outlined = await page.evaluate(
            f"() => {DOC}.querySelector('#appForm > form').classList"
            ".contains('axcess-inspect-highlight')"
        )
        assert outlined
        assert "may not appear here" not in await page.locator("body").inner_text()
    finally:
        await page.context.close()
