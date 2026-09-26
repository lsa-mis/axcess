"""Times the server sends are UTC, whatever the reader's time zone.

The database stores times as SQLite's CURRENT_TIMESTAMP writes them,
"2026-09-26 21:53:46": UTC with no zone. Read as local time, a scan that
had just finished showed "in 4 hours" in US Eastern daylight time, and
anything under four hours old showed "just now".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")


async def test_reports_say_two_hours_ago_in_new_york(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE scans SET status = 'completed', started_at = datetime('now', '-3 hours'), "
            "finished_at = datetime('now', '-2 hours') WHERE id = ?",
            (scan_id,),
        )
    page = await new_page(timezone_id="America/New_York")
    try:
        await page.goto(f"{base}/app/scans", wait_until="networkidle")
        card = page.get_by_role("region", name="Last scanned site")
        await playwright_async.expect(card).to_contain_text("2 hours ago")
        await playwright_async.expect(card).not_to_contain_text("in 2 hours")
        table = page.get_by_role("region", name="Public reports table")
        await playwright_async.expect(table).to_contain_text("2 hours ago")
        await playwright_async.expect(table).not_to_contain_text("just now")
    finally:
        await page.context.close()
