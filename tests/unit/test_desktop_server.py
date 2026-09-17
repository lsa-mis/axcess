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


def test_desktop_server_waits_for_a_backend_that_is_still_migrating(tmp_path: Path) -> None:
    from audit.desktop_server import exclusive_migration_lock

    db_path = tmp_path / "audit.db"
    apply_desktop_migrations(db_path)

    with exclusive_migration_lock(db_path), pytest.raises(RuntimeError, match="still updating"):
        apply_desktop_migrations(db_path, lock_timeout=0.1)

    apply_desktop_migrations(db_path)


def test_desktop_server_releases_lock_when_terminated_during_migration(tmp_path: Path) -> None:
    import os
    import signal
    import subprocess
    import sys

    if sys.platform == "win32":
        pytest.skip("SIGTERM cannot be handled on Windows")

    db_path = tmp_path / "audit.db"
    apply_desktop_migrations(db_path)
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os, time\n"
            "from yoyo import get_backend\n"
            "from audit.desktop_server import exit_cleanly_on_terminate\n"
            "exit_cleanly_on_terminate()\n"
            "backend = get_backend('sqlite:///' + os.environ['LOCK_TEST_DB'])\n"
            "with backend.lock():\n"
            "    print('locked', flush=True)\n"
            "    time.sleep(30)\n",
        ],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "LOCK_TEST_DB": db_path.as_posix()},
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "locked"
    child.send_signal(signal.SIGTERM)
    assert child.wait(timeout=10) == 143

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM yoyo_lock").fetchone()[0] == 0
