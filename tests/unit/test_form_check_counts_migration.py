"""Migration 0036: a scan keeps the form error check's counts.

Forward, rollback and forward again; the counts start at zero.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from audit.db import repo

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0036_form_check_counts"
COLUMNS = {"forms_pages_checked", "forms_pressed", "forms_skipped", "forms_not_checked"}


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(scans)")}


def test_forward_rollback_forward_and_counting(tmp_db: sqlite3.Connection) -> None:
    scan = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('https://x.test/', 'completed', '{}')"
        ).lastrowid
        or 0
    )
    repo.record_form_check(tmp_db, scan_id=scan, pressed=2, skipped=1, not_checked=1)
    repo.record_form_check(tmp_db, scan_id=scan, pressed=0, skipped=0, not_checked=0)
    row = tmp_db.execute(
        "SELECT forms_pages_checked, forms_pressed, forms_skipped, forms_not_checked "
        "FROM scans WHERE id = ?",
        (scan,),
    ).fetchone()
    assert tuple(row) == (2, 2, 1, 1)

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    assert not COLUMNS & _columns(tmp_db)
    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())
    assert _columns(tmp_db) >= COLUMNS
    row = tmp_db.execute("SELECT forms_pressed FROM scans WHERE id = ?", (scan,)).fetchone()
    assert row[0] == 0
