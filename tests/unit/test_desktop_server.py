from __future__ import annotations

from pathlib import Path

import pytest

from audit.desktop_server import apply_desktop_migrations, build_parser


def test_desktop_server_applies_bundled_migrations(tmp_path: Path) -> None:
    db_path = tmp_path / "Axcess Data" / "audit.db"

    apply_desktop_migrations(db_path)

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "scans" in tables
        assert "evaluation_reports" in tables
        assert "a11y_finding_history" in tables


def test_desktop_server_migrations_are_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"

    apply_desktop_migrations(db_path)
    apply_desktop_migrations(db_path)


def test_desktop_server_requires_a_port() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_desktop_server_runtime_verification_does_not_require_a_port() -> None:
    args = build_parser().parse_args(["--verify-runtime"])

    assert args.verify_runtime is True
    assert args.port is None


def _hold_migration_lock(db_path: Path, pid: int) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO yoyo_lock (locked, ctime, pid) VALUES (1, CURRENT_TIMESTAMP, ?)",
            (pid,),
        )


def test_desktop_server_releases_lock_left_by_exited_process(tmp_path: Path) -> None:
    import subprocess
    import sys

    db_path = tmp_path / "audit.db"
    apply_desktop_migrations(db_path)
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    _hold_migration_lock(db_path, finished.pid)

    apply_desktop_migrations(db_path)

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM yoyo_lock").fetchone()[0] == 0


def test_desktop_server_keeps_lock_held_by_running_process(tmp_path: Path) -> None:
    import os

    from yoyo import get_backend

    from audit.desktop_server import release_abandoned_migration_lock

    db_path = tmp_path / "audit.db"
    apply_desktop_migrations(db_path)
    _hold_migration_lock(db_path, os.getppid())

    release_abandoned_migration_lock(get_backend(f"sqlite:///{db_path.as_posix()}"))

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT pid FROM yoyo_lock").fetchone()[0] == os.getppid()
