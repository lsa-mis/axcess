from __future__ import annotations

import ast
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


# --- What the packaged app ships ------------------------------------------------

_BACKEND_SPEC = Path(__file__).resolve().parents[2] / "desktop" / "backend.spec"


def _package_path(node: ast.expr) -> str | None:
    """``audit_source / "exports" / "x.py"`` as ``"exports/x.py"``, else ``None``."""
    parts: list[str] = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
            return None
        parts.append(node.right.value)
        node = node.left
    if not (isinstance(node, ast.Name) and node.id == "audit_source"):
        return None
    return "/".join(reversed(parts))


def _shipped_package_files() -> dict[str, str]:
    """What the PyInstaller spec copies out of ``src/audit``: source -> folder.

    The spec runs only inside PyInstaller, which the test environment does
    not install, so its ``datas`` entries are read from the code as written:
    every ``(str(audit_source / ...), "audit/...")`` pair.
    """
    shipped: dict[str, str] = {}
    for node in ast.walk(ast.parse(_BACKEND_SPEC.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Tuple) and len(node.elts) == 2):
            continue
        source, folder = node.elts
        if not (
            isinstance(source, ast.Call)
            and isinstance(source.func, ast.Name)
            and source.func.id == "str"
            and len(source.args) == 1
            and isinstance(folder, ast.Constant)
            and isinstance(folder.value, str)
        ):
            continue
        path = _package_path(source.args[0])
        if path is not None:
            shipped[path] = folder.value
    return shipped


def test_the_spec_reader_finds_the_folders_the_packaged_app_is_known_to_ship() -> None:
    # Guards the test below against passing or failing for the wrong reason.
    shipped = _shipped_package_files()

    assert shipped["db/migrations"] == "audit/db/migrations"
    assert shipped["web/static"] == "audit/web/static"


def test_the_packaged_app_ships_the_check_script_the_fix_brief_reads() -> None:
    # PyInstaller packs a module as compiled code and leaves no .py file on
    # disk. The fix brief copies the check script in word for word, so
    # fix_brief reads the script's source file when it is imported, and
    # audit.web.server imports fix_brief. The spec must copy the source file
    # to the folder the module lives in. Without it every desktop build
    # failed its packaged check with FileNotFoundError (10 November 2026),
    # and no pull request check had run the packaging, because a change
    # under src/ alone does not start the desktop build.
    import audit
    from audit.exports import axcess_check, fix_brief

    package_dir = Path(audit.__file__).resolve().parent
    script = Path(axcess_check.__file__).resolve().relative_to(package_dir)

    on_disk = Path(axcess_check.__file__).read_text(encoding="utf-8")
    assert on_disk == fix_brief.CHECK_SCRIPT
    assert _shipped_package_files().get(script.as_posix()) == f"audit/{script.parent.as_posix()}"
