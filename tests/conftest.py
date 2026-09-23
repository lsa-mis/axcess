"""Pytest root configuration. Shared fixtures live here."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
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


# Connection-level settings. They live on the connection, not in the file, so
# a copied schema does not carry the ones a migration script changed (0013,
# 0016 and 0018 turn on secure_delete) and they are replayed onto each copy.
_CONNECTION_PRAGMAS = (
    "automatic_index",
    "busy_timeout",
    "cache_size",
    "cell_size_check",
    "defer_foreign_keys",
    "foreign_keys",
    "ignore_check_constraints",
    "legacy_alter_table",
    "mmap_size",
    "query_only",
    "recursive_triggers",
    "reverse_unordered_selects",
    "secure_delete",
    "synchronous",
    "temp_store",
    "trusted_schema",
)


def _connection_pragmas(conn: sqlite3.Connection) -> dict[str, object]:
    return {name: conn.execute(f"PRAGMA {name}").fetchone()[0] for name in _CONNECTION_PRAGMAS}


@pytest.fixture(scope="session")
def migrate_db(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[sqlite3.Connection], None]:
    """Give an empty database every forward migration, the fast way.

    Running the migration scripts costs more than most tests that need the
    schema, so they run once per session into a template file and each call
    copies that file's pages into ``conn`` with the SQLite backup API. The
    result matches :func:`_apply_migrations` on a fresh ``connect()``
    connection: same schema and rows, and the same connection settings,
    because the ones the scripts changed are replayed onto ``conn``.

    The copy replaces whatever ``conn`` holds, so it refuses a database that
    already has a schema rather than silently discarding it.
    """
    template = tmp_path_factory.mktemp("schema") / "audit.db"
    build = connect(template)
    try:
        before = _connection_pragmas(build)
        _apply_migrations(build)
        after = _connection_pragmas(build)
    finally:
        build.close()
    changed = {name: value for name, value in after.items() if before[name] != value}

    def migrate(conn: sqlite3.Connection) -> None:
        if conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is not None:
            raise RuntimeError("migrate_db only fills an empty database")
        source = sqlite3.connect(template)
        try:
            source.backup(conn)
        finally:
            source.close()
        for name, value in changed.items():
            conn.execute(f"PRAGMA {name} = {value}")

    return migrate


@pytest.fixture
def tmp_db(
    tmp_path: Path, migrate_db: Callable[[sqlite3.Connection], None]
) -> Iterator[sqlite3.Connection]:
    """Fresh SQLite DB with all migrations applied."""
    conn = connect(tmp_path / "audit.db")
    migrate_db(conn)
    try:
        yield conn
    finally:
        conn.close()
