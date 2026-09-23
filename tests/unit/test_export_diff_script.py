"""scripts/export_diff.py: the render/compare gate for export refactors.

Exercised end to end against the rich golden scan in a temporary database:
two renders of the same code must compare identical, a changed export must
be reported, and rendering must leave the source database untouched.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
from pathlib import Path
from types import ModuleType

import pytest
from test_export_goldens import seed_rich_scan

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_diff.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_diff", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_render_twice_compares_identical_and_changes_are_caught(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scan_id = seed_rich_scan(tmp_db)
    # Everything the seed wrote is still in the WAL: the snapshot must see it
    # through a read-only connection, and must neither write the database nor
    # checkpoint the log. (The -shm index is shared reader state, not data.)
    source = tmp_path / "audit.db"
    wal = tmp_path / "audit.db-wal"
    before = (_digest(source), _digest(wal))
    tool = _load_script()
    left, right = tmp_path / "a", tmp_path / "b"

    assert tool.main(["render", "--db", str(source), "--out", str(left)]) == 0
    assert tool.main(["render", "--db", str(source), "--out", str(right)]) == 0
    assert (_digest(source), _digest(wal)) == before

    names = {path.name for path in left.iterdir()}
    stem = f"scan_{scan_id}"
    assert {
        f"{stem}.csv",
        f"{stem}_DRAFT.jira.csv",
        f"{stem}.audit.md",
        f"{stem}_DRAFT.xlsx",
        f"{stem}_DRAFT.xlsx.json",
        "manifest.json",
    } <= names
    capsys.readouterr()
    assert tool.main(["compare", str(left), str(right)]) == 0
    assert "0 different" in capsys.readouterr().out

    # A one-byte change to a text export and a changed workbook are both caught;
    # a missing file counts as a difference too.
    csv_path = right / f"{stem}_DRAFT.csv"
    csv_path.write_bytes(csv_path.read_bytes() + b"\n")
    (right / f"{stem}.xlsx").write_bytes((left / f"{stem}_DRAFT.xlsx").read_bytes())
    (right / f"{stem}.md").unlink()
    assert tool.main(["compare", str(left), str(right)]) == 1
    report = capsys.readouterr().out
    assert f"DIFFERS    {stem}_DRAFT.csv" in report
    assert f"DIFFERS    {stem}.xlsx" in report
    assert "sheet 'DRAFT NOTICE'" in report
    assert f"ONLY IN A  {stem}.md" in report


def test_render_refuses_a_non_empty_output_directory(
    tmp_db: sqlite3.Connection, tmp_path: Path
) -> None:
    seed_rich_scan(tmp_db)
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("not ours")
    tool = _load_script()
    assert tool.main(["render", "--db", str(tmp_path / "audit.db"), "--out", str(out)]) == 2
    assert [path.name for path in out.iterdir()] == ["keep.txt"]
