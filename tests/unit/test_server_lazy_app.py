"""The module-level ``app`` in ``audit.web.server`` is built on first access.

Importing the module used to run ``create_app()`` against the configured
database, which swept its running scans to "interrupted" and purged
protected data. Every check runs in a fresh interpreter: in-process, other
tests have already imported the module, so an import-side-effect check
would pass without proving anything.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def _run(code: str, *, tmp_path: Path, db_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "AUDIT_DB_PATH": str(db_path),
        "AUDIT_DATA_DIR": str(tmp_path / "data"),
        "AUDIT_BLOB_DIR": str(tmp_path / "blobs"),
        "AUDIT_LOG_DIR": str(tmp_path / "logs"),
    }
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture
def db(tmp_db: sqlite3.Connection, tmp_path: Path) -> Path:
    """The migrated ``tmp_db`` file, holding one running scan."""
    tmp_db.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('http://example.com/', 'running', '{}')"
    )
    return tmp_path / "audit.db"


def _scan_status(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return str(conn.execute("SELECT status FROM scans").fetchone()[0])
    finally:
        conn.close()


def test_import_touches_no_database(tmp_path: Path) -> None:
    missing = tmp_path / "absent" / "audit.db"
    result = _run(
        """
        import audit.web.server as server
        assert callable(server.create_app)
        """,
        tmp_path=tmp_path,
        db_path=missing,
    )
    assert result.returncode == 0, result.stderr
    assert not missing.parent.exists()


def test_import_leaves_running_scans_alone(tmp_path: Path, db: Path) -> None:
    result = _run("import audit.web.server", tmp_path=tmp_path, db_path=db)
    assert result.returncode == 0, result.stderr
    assert _scan_status(db) == "running"


def test_every_entry_point_gets_one_app_built_once(tmp_path: Path, db: Path) -> None:
    result = _run(
        """
        import audit.web.server as server

        calls = []
        original = server.create_app

        def counting_create_app(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        server.create_app = counting_create_app

        from uvicorn.importer import import_from_string

        loaded = import_from_string("audit.web.server:app")
        from audit.web.server import app as imported

        assert loaded is imported is server.app
        assert loaded.title == "Axcess"
        assert len(calls) == 1, calls
        """,
        tmp_path=tmp_path,
        db_path=db,
    )
    assert result.returncode == 0, result.stderr
    # The startup sweep still runs, exactly as it did when the module built
    # the app at import time.
    assert _scan_status(db) == "interrupted"


def test_concurrent_first_access_builds_once(tmp_path: Path, db: Path) -> None:
    result = _run(
        """
        import threading

        import audit.web.server as server

        calls = []
        original = server.create_app

        def counting_create_app(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        server.create_app = counting_create_app
        barrier = threading.Barrier(8)
        seen = []

        def worker():
            barrier.wait()
            seen.append(server.app)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(calls) == 1, calls
        assert len({id(app) for app in seen}) == 1
        """,
        tmp_path=tmp_path,
        db_path=db,
    )
    assert result.returncode == 0, result.stderr


def test_attribute_error_inside_create_app_keeps_its_cause(tmp_path: Path, db: Path) -> None:
    result = _run(
        """
        import audit.web.server as server

        def broken_create_app(*args, **kwargs):
            raise AttributeError("real cause")

        server.create_app = broken_create_app
        try:
            server.app
        except RuntimeError as exc:
            assert isinstance(exc.__cause__, AttributeError), exc.__cause__
            assert str(exc.__cause__) == "real cause"
        else:
            raise AssertionError("expected RuntimeError")
        """,
        tmp_path=tmp_path,
        db_path=db,
    )
    assert result.returncode == 0, result.stderr


def test_unknown_attribute_still_raises_attribute_error(tmp_path: Path) -> None:
    result = _run(
        """
        import audit.web.server as server

        try:
            server.not_a_real_name
        except AttributeError:
            pass
        else:
            raise AssertionError("expected AttributeError")
        assert not hasattr(server, "also_missing")
        """,
        tmp_path=tmp_path,
        db_path=tmp_path / "absent" / "audit.db",
    )
    assert result.returncode == 0, result.stderr
