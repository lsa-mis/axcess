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
