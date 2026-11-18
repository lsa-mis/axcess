"""Migration 0044 removes what the withdrawn veraPDF migration 0042 left.

0042 ran on real databases on 2026-11-17 before veraPDF was taken out of
Axcess. Those databases keep its two tables and ``linked_files.pdfua_outcome``;
a database created since never had them.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from unittest import mock

from yoyo import get_backend, read_migrations

MIGRATIONS = Path(__file__).parents[2] / "src/audit/db/migrations"
CLEANUP = MIGRATIONS / "0044_drop_verapdf_results.py"

# 0042's forward SQL as it ran, before the file was removed.
_OLD_0042 = """
ALTER TABLE linked_files ADD COLUMN pdfua_outcome TEXT
    CHECK (pdfua_outcome IS NULL OR pdfua_outcome IN ('checked', 'error', 'timed_out'));
CREATE TABLE linked_file_pdfua_failures (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES linked_files(id) ON DELETE CASCADE,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    failed_checks INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    UNIQUE (file_id, rule_id)
);
CREATE INDEX idx_linked_file_pdfua_failures_scan
    ON linked_file_pdfua_failures(scan_id, file_id);
CREATE TABLE linked_file_checkers (
    scan_id INTEGER PRIMARY KEY REFERENCES scans(id) ON DELETE CASCADE,
    verapdf_found INTEGER NOT NULL CHECK (verapdf_found IN (0, 1)),
    verapdf_version TEXT
);
"""


def _cleanup_step():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("migration_0044", CLEANUP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # The file registers its steps with yoyo as it loads (``step(...)``),
    # which works only inside yoyo's own loader; here only the step
    # functions are wanted, so registering is skipped.
    with mock.patch("yoyo.step", lambda *args, **kwargs: None):
        spec.loader.exec_module(module)
    return module.apply_step


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(linked_files)")}


def test_it_drops_what_0042_added(tmp_db: sqlite3.Connection) -> None:
    tmp_db.executescript(_OLD_0042)
    assert {"linked_file_pdfua_failures", "linked_file_checkers"} <= _tables(tmp_db)
    _cleanup_step()(tmp_db)
    assert not {"linked_file_pdfua_failures", "linked_file_checkers"} & _tables(tmp_db)
    assert "pdfua_outcome" not in _columns(tmp_db)


def test_it_leaves_a_database_that_never_ran_0042_alone(tmp_db: sqlite3.Connection) -> None:
    tables, columns = _tables(tmp_db), _columns(tmp_db)
    _cleanup_step()(tmp_db)
    assert _tables(tmp_db) == tables
    assert _columns(tmp_db) == columns


def test_the_apps_migration_path_runs_it(tmp_path: Path) -> None:
    """yoyo resolves every ``__depends__``: 0043 must no longer name 0042."""
    db = tmp_path / "audit.db"
    backend = get_backend(f"sqlite:///{db}")
    with backend.lock():
        backend.apply_migrations(backend.to_apply(read_migrations(str(MIGRATIONS))))
    with sqlite3.connect(db) as conn:
        applied = {row[0] for row in conn.execute("SELECT migration_id FROM _yoyo_migration")}
        assert {"0043_repair_linked_file_thumbnail_small", "0044_drop_verapdf_results"} <= applied
        assert "pdfua_outcome" not in _columns(conn)
