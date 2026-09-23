"""Pytest root configuration. Shared fixtures live here."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from audit.db.schema import connect

TESTS_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = TESTS_DIR.parent / "src" / "audit" / "db" / "migrations"

# Markers follow the directory a test lives in. The Makefile selects suites
# with `-m integration` / `-m ui`, and a file that forgot its `pytestmark`
# used to drop out of those runs without anyone noticing.
_DIRECTORY_MARKERS = {"integration": "integration", "ui": "ui"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    imports_playwright: dict[Path, bool] = {}
    for item in items:
        path = Path(str(item.path))
        try:
            top = path.relative_to(TESTS_DIR).parts[0]
        except (ValueError, IndexError):
            continue
        marker = _DIRECTORY_MARKERS.get(top)
        if marker is None:
            continue
        item.add_marker(marker)
        if path not in imports_playwright:
            imports_playwright[path] = "playwright" in path.read_text(encoding="utf-8")
        if imports_playwright[path]:
            item.add_marker("browser")


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
