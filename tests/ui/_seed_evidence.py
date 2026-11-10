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


FORM_ERROR_ISSUE_KEY = "forms:form-error-not-described"


def add_form_error_finding(db_path: Path, blob_dir: Path, scan_id: int) -> tuple[int, str, str]:
    """A form error check occurrence with its form before and after the press.

    Returns ``(page_id, before_hash, after_hash)``. The two pictures differ,
    as the press changed the form (the after one has a red field).
    """
    store = BlobStore(blob_dir)
    hashes = []
    for colour in ((255, 255, 255), (255, 220, 220)):
        png = io.BytesIO()
        Image.new("RGB", (240, 120), colour).save(png, format="PNG")
        hashes.append(store.store(png.getvalue(), "image/png")[0])
    before_hash, after_hash = hashes
    with sqlite3.connect(db_path) as conn:
        (page_id,) = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        conn.execute(
            """
            INSERT INTO page_a11y_findings (
                page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level, impact, help,
                target_selector, target_hash, failure_summary, status, created_at,
                updated_at, screenshot_hash, before_screenshot_hash, pipeline, revealed_by
            ) VALUES (?, ?, 'form-error-not-described', '3.3.1', '3.3.1', 'A', 'serious',
                      'Form shows an error without describing it in text', 'form#contact',
                      'seeded-form-error', 'Fields marked in error: Name.', 'new',
                      CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?, 'forms', 'Send message')
            """,
            (page_id, scan_id, after_hash, before_hash),
        )
    return int(page_id), before_hash, after_hash
