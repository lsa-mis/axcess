"""Migration 0035: a finding can keep a second screenshot, from before it showed.

Forward, rollback and forward again, keeping every row and its screenshot.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from audit.db import repo

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0035_finding_before_screenshot"


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(page_a11y_findings)")}


def _finding(conn: sqlite3.Connection) -> int:
    scan = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://x.test/', 'completed', '{}')"
    ).lastrowid
    page = conn.execute(
        "INSERT INTO pages (scan_id, url_normalized, render_mode) "
        "VALUES (?, 'https://x.test/', 'js')",
        (scan,),
    ).lastrowid
    return repo.upsert_keyboard_finding(
        conn,
        page_id=int(page or 0),
        scan_id=int(scan or 0),
        rule_id="form-error-not-described",
        wcag_sc="3.3.1",
        wcag_scs="3.3.1",
        wcag_level="A",
        impact="serious",
        help="Form shows an error without describing it in text",
        help_url="",
        target_selector="form",
        failure_summary="",
        html_snippet="<form>",
        target_hash="t",
        criterion_sc="3.3.1",
        pipeline="forms",
        screenshot_hash="after",
        before_screenshot_hash="before",
    )


def test_forward_rollback_forward(tmp_db: sqlite3.Connection) -> None:
    finding = _finding(tmp_db)
    row = tmp_db.execute(
        "SELECT screenshot_hash, before_screenshot_hash FROM page_a11y_findings WHERE id = ?",
        (finding,),
    ).fetchone()
    assert (row[0], row[1]) == ("after", "before")

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    assert "before_screenshot_hash" not in _columns(tmp_db)
    assert (
        tmp_db.execute(
            "SELECT screenshot_hash FROM page_a11y_findings WHERE id = ?", (finding,)
        ).fetchone()[0]
        == "after"
    )

    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())
    assert "before_screenshot_hash" in _columns(tmp_db)
    assert (
        tmp_db.execute(
            "SELECT before_screenshot_hash FROM page_a11y_findings WHERE id = ?", (finding,)
        ).fetchone()[0]
        is None
    )
