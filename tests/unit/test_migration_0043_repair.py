"""Migration 0043 repairs databases that ran 0041 before it was edited.

0041's first version (run on 2026-11-16 by at least one real database) added
only ``linked_files.thumbnail_hash``; the committed one also adds
``thumbnail_small_hash``. Without that column every finished PDF check failed
to save, and a completed scan's PDFs all read "not checked".
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from unittest import mock

from yoyo import get_backend, read_migrations

MIGRATIONS = Path(__file__).parents[2] / "src/audit/db/migrations"
REPAIR = MIGRATIONS / "0043_repair_linked_file_thumbnail_small.py"


def _repair_step():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("migration_0043", REPAIR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # The file registers its steps with yoyo as it loads (``step(...)``),
    # which works only inside yoyo's own loader; here only the step
    # functions are wanted, so registering is skipped.
    with mock.patch("yoyo.step", lambda *args, **kwargs: None):
        spec.loader.exec_module(module)
    return module.apply_step


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(linked_files)")}


def test_it_adds_the_column_a_database_is_missing(tmp_db: sqlite3.Connection) -> None:
    tmp_db.execute("ALTER TABLE linked_files DROP COLUMN thumbnail_small_hash")
    assert "thumbnail_small_hash" not in _columns(tmp_db)
    _repair_step()(tmp_db)
    assert "thumbnail_small_hash" in _columns(tmp_db)


def test_it_leaves_a_database_that_has_the_column_alone(tmp_db: sqlite3.Connection) -> None:
    before = _columns(tmp_db)
    assert "thumbnail_small_hash" in before
    _repair_step()(tmp_db)
    assert _columns(tmp_db) == before


def test_the_apps_migration_path_runs_it(tmp_path: Path) -> None:
    """The app migrates with yoyo, which runs Python migrations as well as
    SQL ones; the test schema helper applies only the .sql files, which a new
    database needs (0041 as committed already adds the column)."""
    db = tmp_path / "audit.db"
    backend = get_backend(f"sqlite:///{db}")
    with backend.lock():
        backend.apply_migrations(backend.to_apply(read_migrations(str(MIGRATIONS))))
    with sqlite3.connect(db) as conn:
        applied = {row[0] for row in conn.execute("SELECT migration_id FROM _yoyo_migration")}
        assert "0043_repair_linked_file_thumbnail_small" in applied
        assert "thumbnail_small_hash" in _columns(conn)
