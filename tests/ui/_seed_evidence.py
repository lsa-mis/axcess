"""Seed a finding that has a stored location screenshot, for UI tests.

The shared ``seeded_db`` fixture has no finding screenshots, and the pages
that show them (an issue's screenshots page, and the stored-evidence links
it leads to) render nothing to test without one.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from PIL import Image

from audit.blob_store import BlobStore

SCREENSHOT_ISSUE_KEY = "axe:color-contrast"


def add_screenshot_finding(db_path: Path, blob_dir: Path, scan_id: int) -> int:
    """Store a screenshot and a color-contrast finding that cites it; returns its page id."""
    png = io.BytesIO()
    Image.new("RGB", (240, 120), (255, 255, 255)).save(png, format="PNG")
    screenshot_hash, _ = BlobStore(blob_dir).store(png.getvalue(), "image/png")
    with sqlite3.connect(db_path) as conn:
        (page_id,) = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        conn.execute(
            """
            INSERT INTO page_a11y_findings (
                page_id, scan_id, rule_id, help, target_selector, target_hash,
                status, created_at, updated_at, screenshot_hash, engine_outcome,
                pipeline
            ) VALUES (?, ?, 'color-contrast', 'Contrast (Minimum)', 'main p',
                      'seeded-screenshot', 'new', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                      ?, 'failed', 'axe')
            """,
            (page_id, scan_id, screenshot_hash),
        )
    return int(page_id)
