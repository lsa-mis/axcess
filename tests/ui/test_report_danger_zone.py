"""Deleting a report from the end of its own page.

The delete section asks before it acts. Cancelling the prompt keeps the report;
accepting it deletes the scan and lands on Reports, where the report is gone.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")


async def test_delete_report_asks_first_and_then_deletes(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
        zone = page.get_by_role("region", name="Delete this report")
        await zone.scroll_into_view_if_needed()
        await playwright_async.expect(zone).to_contain_text(
            "Image files that other reports also use may stay in storage."
        )
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        delete = zone.get_by_role("button", name="Delete report")

        # Cancelled: nothing is deleted and the report stays open.
        prompts: list[str] = []

        async def dismiss(dialog: Any) -> None:
            prompts.append(dialog.message)
            await dialog.dismiss()

        page.once("dialog", dismiss)
        await delete.click()
        await playwright_async.expect(page).to_have_url(f"{base}/app/scans/{scan_id}/issues")
        assert prompts and f"Delete report #{scan_id}" in prompts[0], prompts
        assert (await page.request.get(f"{base}/api/scans/{scan_id}")).ok

        # Accepted: the scan is deleted and Reports opens.
        async def accept(dialog: Any) -> None:
            await dialog.accept()

        page.once("dialog", accept)
        await delete.click()
        await page.wait_for_url(f"{base}/app/scans")
        assert (await page.request.get(f"{base}/api/scans/{scan_id}")).status == 404
    finally:
        await page.context.close()


async def test_no_screen_or_prompt_shows_the_start_address_password(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """A start address can carry ``user:password@`` for the crawler; it never shows.

    The delete prompts used to repeat the stored address as it was typed.
    """
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE scans SET seed_url = ? WHERE id = ?",
            ("https://reviewer:hunter2@example.com/", scan_id),
        )
    page = await new_page(viewport={"width": 1280, "height": 900})
    prompts: list[str] = []

    async def dismiss(dialog: Any) -> None:
        prompts.append(dialog.message)
        await dialog.dismiss()

    page.on("dialog", dismiss)
    try:
        await page.goto(f"{base}/app/scans", wait_until="networkidle")
        await playwright_async.expect(page.get_by_text("example.com").first).to_be_visible()
        assert "hunter2" not in await page.content()

        await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
        zone = page.get_by_role("region", name="Delete this report")
        await zone.get_by_role("button", name="Delete report").click()
        # Dismissed, so the report stays open.
        await playwright_async.expect(page).to_have_url(f"{base}/app/scans/{scan_id}/issues")
        assert "hunter2" not in await page.content()
        assert prompts, "the delete prompt did not open"
        assert all("hunter2" not in prompt and "reviewer" not in prompt for prompt in prompts)
        assert f"Delete report #{scan_id} (example.com)" in prompts[0]
    finally:
        await page.context.close()
