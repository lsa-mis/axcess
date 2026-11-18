"""Migration 0045 adds ``linked_files.checked_as``, and its rollback removes it."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from yoyo import get_backend, read_migrations

MIGRATIONS = Path(__file__).parents[2] / "src/audit/db/migrations"


def _columns(db: Path) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(linked_files)")}


def test_forward_and_rollback(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    backend = get_backend(f"sqlite:///{db}")
    migrations = read_migrations(str(MIGRATIONS))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
    assert "checked_as" in _columns(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('https://a.test/', 'completed', '{}')"
        )
        conn.execute(
            "INSERT INTO linked_files (scan_id, url, file_type, found_by, checked_as) "
            "VALUES (1, 'https://a.test/a.docx', 'docx', 'extension', 'docx')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO linked_files (scan_id, url, file_type, found_by, checked_as) "
                "VALUES (1, 'https://a.test/b.xlsx', 'xlsx', 'extension', 'xlsx')"
            )
    with backend.lock():
        backend.rollback_migrations(
            backend.to_rollback(migrations.filter(lambda m: m.id == "0045_linked_file_checked_as"))
        )
    assert "checked_as" not in _columns(db)
