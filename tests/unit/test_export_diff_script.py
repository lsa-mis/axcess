"""scripts/export_diff.py: the render/compare gate for export refactors.

Exercised end to end against the rich golden scan in a temporary database:
two renders of the same code must compare identical, a changed export must
be reported, rendering must leave the source database untouched, and the
gate must refuse to pass when it compared nothing.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import ModuleType

import pytest
from support.rich_scan import database_path, seed_rich_scan, write_evidence_blobs

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_diff.py"


@pytest.fixture(scope="module")
def tool() -> ModuleType:
    """The script, loaded once as a module so its ``main`` can be called."""
    spec = importlib.util.spec_from_file_location("export_diff", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_render_twice_compares_identical_and_changes_are_caught(
    tool: ModuleType,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scan_id = seed_rich_scan(tmp_db)
    blobs = write_evidence_blobs(tmp_path / "blobs").root
    # Everything the seed wrote is still in the WAL: the snapshot must see it
    # through a read-only connection, and must neither write the database nor
    # checkpoint the log. (The -shm index is shared reader state, not data.)
    source = database_path(tmp_db)
    wal = source.with_name(source.name + "-wal")
    before = (_digest(source), _digest(wal))
    left, right = tmp_path / "a", tmp_path / "b"
    render = ["render", "--db", str(source), "--blob-dir", str(blobs), "--out"]

    assert tool.main([*render, str(left)]) == 0
    assert tool.main([*render, str(right)]) == 0
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
    # The blob store reached the workbook: its evidence screenshots are in.
    fingerprint = json.loads((left / f"{stem}.xlsx.json").read_text())
    assert sum(len(sheet["images"]) for sheet in fingerprint["sheets"]) == 2
    manifest = json.loads((left / "manifest.json").read_text())
    assert manifest["blob_dir"] == str(blobs.resolve())
    assert len(manifest["snapshot"]["sha256"]) == 64
    capsys.readouterr()
    assert tool.main(["compare", str(left), str(right)]) == 0
    captured = capsys.readouterr()
    assert "0 different, 0 failed" in captured.out
    # Same code on both sides is expected here; a snapshot or blob mismatch
    # would not be.
    assert "different database snapshots" not in captured.err
    assert "--blob-dir" not in captured.err

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
    tool: ModuleType, tmp_db: sqlite3.Connection, tmp_path: Path
) -> None:
    seed_rich_scan(tmp_db)
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("not ours")
    assert tool.main(["render", "--db", str(database_path(tmp_db)), "--out", str(out)]) == 2
    assert [path.name for path in out.iterdir()] == ["keep.txt"]


def test_render_refuses_to_render_nothing(
    tool: ModuleType,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A gate that renders no scan must not hand compare two empty directories."""
    scan_id = seed_rich_scan(tmp_db)
    source = str(database_path(tmp_db))
    outs = iter(tmp_path / f"out-{index}" for index in range(10))

    # A scan id that does not exist, and a mistyped blob directory.
    for extra in (["--scan", str(scan_id + 1)], ["--blob-dir", str(tmp_path / "nope")]):
        out = next(outs)
        assert tool.main(["render", "--db", source, "--out", str(out), *extra]) == 2
        assert not out.exists()
    errors = capsys.readouterr().err
    assert f"not a completed, non-protected scan: {scan_id + 1}" in errors
    assert "blob directory not found" in errors

    # A scan that did not complete, asked for by id and implicitly.
    tmp_db.execute("UPDATE scans SET status = 'interrupted' WHERE id = ?", (scan_id,))
    tmp_db.commit()
    for extra in (["--scan", str(scan_id)], []):
        out = next(outs)
        assert tool.main(["render", "--db", source, "--out", str(out), *extra]) == 2
        assert not out.exists()
    assert "no completed, non-protected scan" in capsys.readouterr().err


def test_render_skips_protected_scans(
    tool: ModuleType,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
) -> None:
    """The route refuses protected scans, so the gate neither renders nor asks for them."""
    scan_id = seed_rich_scan(tmp_db)
    protected = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('https://private.example.org/', 'completed', '{}')"
        ).lastrowid
        or 0
    )
    # The real table demands vault metadata; the gate only asks whether a
    # scan id is listed (tests/ui/test_report_comparison_routes.py does the same).
    tmp_db.execute("ALTER TABLE protected_scans RENAME TO saved_protected_scans")
    tmp_db.execute("CREATE TABLE protected_scans (scan_id INTEGER PRIMARY KEY)")
    tmp_db.execute("INSERT INTO protected_scans VALUES (?)", (protected,))
    tmp_db.commit()
    source = str(database_path(tmp_db))

    asked = tmp_path / "asked"
    assert tool.main(["render", "--db", source, "--out", str(asked), "--scan", str(protected)]) == 2
    assert not asked.exists()

    out = tmp_path / "out"
    assert tool.main(["render", "--db", source, "--out", str(out)]) == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert [entry["id"] for entry in manifest["scans"]] == [scan_id]
    assert manifest["skipped_protected"] == [protected]
    assert not list(out.glob(f"scan_{protected}*"))


def test_compare_fails_on_nothing_compared_and_on_failed_renders(
    tool: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    left, right = tmp_path / "a", tmp_path / "b"
    for directory in (left, right):
        directory.mkdir()
        (directory / "manifest.json").write_text('{"scans": []}\n')
    assert tool.main(["compare", str(left), str(right)]) == 2
    assert "no exports to compare" in capsys.readouterr().err

    # The same failure on both sides is not equivalence: nothing was compared.
    for directory in (left, right):
        (directory / "scan_1.csv").write_text("a,b\n")
        (directory / "scan_1.xlsx.error.txt").write_text("ValueError: boom\n")
    assert tool.main(["compare", str(left), str(right)]) == 1
    report = capsys.readouterr().out
    assert "FAILED     scan_1.xlsx.error.txt (a+b)" in report
    assert "1 identical, 0 different, 1 failed render(s)" in report


def test_compare_warns_when_the_renders_are_not_comparable(
    tool: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Different snapshots, or evidence left out, weaken what "identical" means."""
    left, right = tmp_path / "a", tmp_path / "b"
    for directory, sha, blobs in ((left, "1" * 64, None), (right, "2" * 64, "/blobs")):
        directory.mkdir()
        manifest = {
            "audit_package": str(directory),
            "blob_dir": blobs,
            "snapshot": {"sha256": sha},
        }
        (directory / "manifest.json").write_text(json.dumps(manifest))
        (directory / "scan_1.csv").write_text("a,b\n")
    assert tool.main(["compare", str(left), str(right)]) == 0
    warnings = capsys.readouterr().err
    assert "different database snapshots" in warnings
    assert "render a ran without --blob-dir" in warnings
