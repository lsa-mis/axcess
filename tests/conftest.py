"""Pytest root configuration. Shared fixtures live here."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from audit.db.schema import connect

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "src" / "audit" / "db" / "migrations"


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Execute every forward migration .sql file in migrations/ in filename order.

    Avoids pulling in yoyo for unit tests — the queue tests only need the
    schema to exist, not yoyo's bookkeeping tables. Rollback files are
    skipped explicitly: the old 0001 rollback only ran ``DROP TABLE IF
    EXISTS`` (no-op pre-creation) so the previous glob happened to work,
    but rollbacks that drop columns can't be no-op-safe in SQLite.
    """
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name.endswith(".rollback.sql"):
            continue
        conn.executescript(path.read_text())


@pytest.fixture
def tmp_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Fresh SQLite DB with all migrations applied."""
    conn = connect(tmp_path / "audit.db")
    _apply_migrations(conn)
    try:
        yield conn
    finally:
        conn.close()
