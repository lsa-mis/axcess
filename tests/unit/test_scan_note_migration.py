"""Migration 0039: scans.scan_note, forward, rollback and forward again."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0039_scan_note"


def _scan_columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(scans)")}


def test_forward_rollback_forward(tmp_db: sqlite3.Connection) -> None:
    tmp_db.execute(
        "INSERT INTO scans (seed_url, status, config_json, scan_note) "
        "VALUES ('https://x.test/', 'completed', '{}', 'A note')"
    )

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    assert "scan_note" not in _scan_columns(tmp_db)
    assert tmp_db.execute("SELECT COUNT(*) FROM scans").fetchone()[0] == 1

    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())
    assert tmp_db.execute("SELECT scan_note FROM scans").fetchone()[0] is None
