"""Migration 0038: page_a11y_findings accepts the page code check's rows.

Forward, rollback and forward again, keeping every other row (the form error
check's included), both indexes that cover the pipeline column, and the
scan's page count for the check.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from audit.db import repo

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0038_markup_pipeline"


def _page(conn: sqlite3.Connection) -> tuple[int, int]:
    scan = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://x.test/', 'completed', '{}')"
    ).lastrowid
    page = conn.execute(
        "INSERT INTO pages (scan_id, url_normalized, render_mode) "
        "VALUES (?, 'https://x.test/', 'js')",
        (scan,),
    ).lastrowid
    return int(scan or 0), int(page or 0)


def _insert(conn: sqlite3.Connection, scan: int, page: int, pipeline: str, key: str) -> None:
    conn.execute(
        "INSERT INTO page_a11y_findings (page_id, scan_id, rule_id, help, target_selector, "
        "target_hash, pipeline) VALUES (?, ?, 'r', 'h', 'input', ?, ?)",
        (page, scan, key, pipeline),
    )


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}


def _scan_columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(scans)")}


def test_forward_rollback_forward(tmp_db: sqlite3.Connection) -> None:
    scan, page = _page(tmp_db)
    _insert(tmp_db, scan, page, "markup", "a")
    _insert(tmp_db, scan, page, "forms", "b")
    repo.increment_scan_method_coverage(tmp_db, scan_id=scan, method="markup")
    assert tmp_db.execute("SELECT markup_pages_checked FROM scans").fetchone()[0] == 1

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    pipelines = [r[0] for r in tmp_db.execute("SELECT pipeline FROM page_a11y_findings")]
    assert pipelines == ["forms"]
    assert "markup_pages_checked" not in _scan_columns(tmp_db)
    with pytest.raises(sqlite3.IntegrityError):
        _insert(tmp_db, scan, page, "markup", "c")
    assert {"idx_a11y_pipeline", "idx_a11y_rule_lookup"} <= _indexes(tmp_db)

    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())
    _insert(tmp_db, scan, page, "markup", "d")
    pipelines = sorted(r[0] for r in tmp_db.execute("SELECT pipeline FROM page_a11y_findings"))
    assert pipelines == ["forms", "markup"]
    assert {"idx_a11y_pipeline", "idx_a11y_rule_lookup"} <= _indexes(tmp_db)
    assert tmp_db.execute("SELECT markup_pages_checked FROM scans").fetchone()[0] == 0
