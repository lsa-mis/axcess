"""``migrate_db`` (tests/conftest.py) gives the database the scripts give.

It copies a template built once per session instead of running every
migration script for each test. A copy has to be indistinguishable from the
scripts run on a fresh ``connect()`` connection, including the connection
settings a script changes, which live on the connection and are not copied
with the file. It has to be independent of every other copy, and it must
refuse a database that already has a schema rather than overwrite it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"

Migrate = Callable[[sqlite3.Connection], None]

# Settings a test could observe, of the file and of the connection.
# schema_version is left out: it counts schema changes, which a copy makes
# differently from the scripts, and nothing reads it.
_PRAGMAS = (
    "application_id",
    "auto_vacuum",
    "automatic_index",
    "busy_timeout",
    "cache_size",
    "cache_spill",
    "cell_size_check",
    "checkpoint_fullfsync",
    "defer_foreign_keys",
    "encoding",
    "foreign_keys",
    "freelist_count",
    "fullfsync",
    "ignore_check_constraints",
    "journal_mode",
    "journal_size_limit",
    "legacy_alter_table",
    "locking_mode",
    "max_page_count",
    "mmap_size",
    "page_count",
    "page_size",
    "query_only",
    "read_uncommitted",
    "recursive_triggers",
    "reverse_unordered_selects",
    "secure_delete",
    "synchronous",
    "temp_store",
    "trusted_schema",
    "user_version",
    "wal_autocheckpoint",
)


def _run_scripts(conn: sqlite3.Connection) -> None:
    # The slow way, written out here rather than borrowed from the conftest,
    # so the comparison does not trust the code that builds the template.
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if not path.name.endswith(".rollback.sql"):
            conn.executescript(path.read_text())


def _rows(conn: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    query = f'SELECT * FROM "{table}"'  # noqa: S608 - a name read from sqlite_master
    return sorted((tuple(row) for row in conn.execute(query)), key=repr)


def _observe(conn: sqlite3.Connection) -> dict[str, Any]:
    tables = [
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    ]
    return {
        "schema": [
            tuple(row)
            for row in conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            )
        ],
        "rows": {table: _rows(conn, table) for table in tables},
        "pragmas": {name: conn.execute(f"PRAGMA {name}").fetchone()[0] for name in _PRAGMAS},
        "integrity_check": [tuple(row) for row in conn.execute("PRAGMA integrity_check")],
        "foreign_key_check": [tuple(row) for row in conn.execute("PRAGMA foreign_key_check")],
    }


def _count_scans(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0])


def test_a_copy_matches_running_the_scripts(tmp_path: Path, migrate_db: Migrate) -> None:
    scripted = connect(tmp_path / "scripted.db")
    copied = connect(tmp_path / "copied.db")
    try:
        _run_scripts(scripted)
        migrate_db(copied)
        expected = _observe(scripted)
        assert "scans" in expected["rows"], "the scripts built no schema to compare"
        assert _observe(copied) == expected
    finally:
        scripted.close()
        copied.close()


def test_copies_share_nothing(tmp_path: Path, migrate_db: Migrate) -> None:
    first = connect(tmp_path / "first.db")
    second = connect(tmp_path / "second.db")
    try:
        migrate_db(first)
        migrate_db(second)
        first.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
            "VALUES ('http://example.com/', 'completed', 0, 0, '{}')"
        )
        assert _count_scans(first) == 1
        assert _count_scans(second) == 0
    finally:
        first.close()
        second.close()
    # Nor did the write reach the template the next copy comes from.
    third = connect(tmp_path / "third.db")
    try:
        migrate_db(third)
        assert _count_scans(third) == 0
    finally:
        third.close()


def test_refuses_a_database_that_already_has_a_schema(tmp_path: Path, migrate_db: Migrate) -> None:
    conn = connect(tmp_path / "kept.db")
    try:
        conn.execute("CREATE TABLE kept (value TEXT)")
        conn.execute("INSERT INTO kept VALUES ('still here')")
        with pytest.raises(RuntimeError, match="empty database"):
            migrate_db(conn)
        assert [tuple(row) for row in conn.execute("SELECT value FROM kept")] == [("still here",)]
    finally:
        conn.close()

    migrated = connect(tmp_path / "migrated.db")
    try:
        migrate_db(migrated)
        with pytest.raises(RuntimeError, match="empty database"):
            migrate_db(migrated)
    finally:
        migrated.close()


def test_tmp_db_enforces_foreign_keys(tmp_db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        tmp_db.execute(
            "INSERT INTO pages (scan_id, url_normalized, render_mode) "
            "VALUES (999, 'http://example.com/', 'static')"
        )
