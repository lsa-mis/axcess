"""Prove two checkouts render identical exports for every completed scan.

Dev-only tool for export refactors (``src/audit/exports/**``, the workbook
renderer, draft labeling in ``audit.web.export_readiness``). It renders every
export the web route can produce, under whichever ``audit`` package is on
``PYTHONPATH``, then compares two such renders.

Usage, from the checkout that has this script (the branch)::

    # 1. Render with the base code. BASE is another checkout or worktree.
    PYTHONPATH=BASE/src python scripts/export_diff.py render \\
        --db data/audit.db --out /tmp/exports-base

    # 2. Render with the branch code.
    PYTHONPATH=src python scripts/export_diff.py render \\
        --db data/audit.db --out /tmp/exports-branch

    # 3. Compare. Exit status 0 means identical, 1 means a difference.
    python scripts/export_diff.py compare /tmp/exports-base /tmp/exports-branch

``render --db PATH --out DIR [--blob-dir DIR] [--scan ID ...]``
    Takes a consistent snapshot of ``PATH`` through SQLite's backup API from
    a read-only connection into a temporary file, and renders from that copy
    only; the source database is never opened writable. For every completed,
    non-protected scan, every route format (csv, json, jira, markdown, audit,
    xlsx) is written as a final and as a draft, named like the route's
    download (``scan_7.csv``, ``scan_7_DRAFT.audit.md``). Each workbook is
    written as the raw ``.xlsx`` and as its semantic fingerprint
    (``.xlsx.json``) for reading diffs. The UI base URL, Markdown generation
    time and workbook audit date are pinned, so a render is reproducible.
    ``--blob-dir`` passes a read-only blob store, as the route does, so
    workbooks embed evidence screenshots. ``DIR`` must be new or empty. A
    render that raises is recorded as ``<name>.error.txt`` and makes the
    command exit 1 after every other export has been written.

``compare DIR_A DIR_B``
    Byte comparison for the text formats (with a short unified diff), and a
    fingerprint comparison for workbooks, recomputed from the raw ``.xlsx``
    files with this checkout's fingerprint code so both sides are measured
    the same way. Files present on one side only count as differences.
    ``manifest.json`` is informational and never compared; compare warns when
    both renders came from the same ``audit`` package.

Rendering goes through ``tests/support/export_render.py``, which calls the
route's own entry points (``collect_scan``, the per-format renderers,
``label_draft_export``) and does not import the FastAPI app. Both helpers
under ``tests/support`` are loaded from this script's checkout, so run the
script from the same checkout for both renders and switch only
``PYTHONPATH``.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# The shared helpers live in tests/support so the unit-test goldens and this
# tool render and fingerprint exports the same way. tests/ is not a package;
# put it on the path explicitly.
_TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"
sys.path.insert(0, str(_TESTS_DIR))

from support.xlsx_fingerprint import (  # noqa: E402
    dumps_fingerprint,
    fingerprint_diff,
    fingerprint_xlsx,
)

MANIFEST = "manifest.json"
_DIFF_LINES = 40


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def _snapshot(source: Path, destination: Path) -> None:
    """Copy ``source`` to ``destination`` without opening it writable.

    The backup API reads a consistent snapshot, including pages still in the
    write-ahead log, which a plain file copy of a live WAL database misses.
    """
    uri = source.resolve().as_uri() + "?mode=ro"
    reader = sqlite3.connect(uri, uri=True)
    try:
        writer = sqlite3.connect(destination)
        try:
            reader.backup(writer)
        finally:
            writer.close()
    finally:
        reader.close()


def _render(args: argparse.Namespace) -> int:
    # Imported here so `compare` needs neither `audit` nor a database.
    from support import export_render

    import audit
    from audit.blob_store import BlobStore
    from audit.db.schema import connect

    source = Path(args.db)
    if not source.is_file():
        print(f"error: database not found: {source}", file=sys.stderr)
        return 2
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        print(f"error: output directory is not empty: {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    blob_store = BlobStore(Path(args.blob_dir)) if args.blob_dir else None
    audit_package = str(Path(audit.__file__).resolve().parent)
    started = time.perf_counter()
    manifest: dict[str, Any] = {
        "audit_package": audit_package,
        "source_db": str(source.resolve()),
        "blob_dir": str(Path(args.blob_dir).resolve()) if args.blob_dir else None,
        "pinned": {
            "ui_base": export_render.UI_BASE,
            "generated_at": export_render.GENERATED_AT.isoformat(),
            "audit_date": export_render.AUDIT_DATE,
        },
        "scans": [],
    }
    failures = 0
    written = 0
    print(f"audit package: {audit_package}")

    with tempfile.TemporaryDirectory(prefix="export-diff-") as scratch:
        copy = Path(scratch) / "audit.db"
        copy_started = time.perf_counter()
        _snapshot(source, copy)
        copy_seconds = time.perf_counter() - copy_started
        print(f"snapshot of {source} taken in {copy_seconds:.2f} s")
        manifest["snapshot_seconds"] = round(copy_seconds, 3)

        conn = connect(copy)
        try:
            scan_ids = [
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM scans WHERE status = 'completed' ORDER BY id"
                ).fetchall()
            ]
            if args.scan:
                wanted = set(args.scan)
                scan_ids = [scan_id for scan_id in scan_ids if scan_id in wanted]
            for scan_id in scan_ids:
                entry, scan_failures, scan_written = _render_scan(
                    conn, scan_id, out, blob_store=blob_store, export_render=export_render
                )
                manifest["scans"].append(entry)
                failures += scan_failures
                written += scan_written
        finally:
            conn.close()

    total = time.perf_counter() - started
    manifest["total_seconds"] = round(total, 3)
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {written} file(s) for {len(manifest['scans'])} scan(s) to {out} in {total:.2f} s")
    if failures:
        print(f"error: {failures} export(s) failed; see *.error.txt in {out}", file=sys.stderr)
        return 1
    return 0


def _is_protected(conn: sqlite3.Connection, scan_id: int) -> bool:
    """The route refuses protected scans outright, so the harness skips them."""
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'protected_scans'"
    ).fetchone()
    if table is None:
        return False
    row = conn.execute("SELECT 1 FROM protected_scans WHERE scan_id = ?", (scan_id,)).fetchone()
    return row is not None


def _render_scan(
    conn: sqlite3.Connection,
    scan_id: int,
    out: Path,
    *,
    blob_store: Any,
    export_render: Any,
) -> tuple[dict[str, Any], int, int]:
    """Render one scan in every format, final and draft. Returns the manifest
    entry, the number of failed exports and the number of files written."""
    seed = conn.execute("SELECT seed_url FROM scans WHERE id = ?", (scan_id,)).fetchone()
    entry: dict[str, Any] = {"id": scan_id, "seed_url": seed["seed_url"] if seed else None}
    if _is_protected(conn, scan_id):
        entry["skipped"] = "protected scan; the export route refuses it"
        print(f"scan {scan_id}: skipped (protected)")
        return entry, 0, 0
    status, route_draft = export_render.evaluation_status(conn, scan_id)
    entry["evaluation_status"] = status
    entry["route_disposition"] = "draft" if route_draft else "final"
    timings: dict[str, float] = {}
    failures = 0
    written = 0
    stem = f"scan_{scan_id}"
    for export_format in export_render.EXPORT_FORMATS:
        render_started = time.perf_counter()
        rendered: str | bytes | None = None
        render_error: Exception | None = None
        try:
            rendered = export_render.render_unlabeled(
                conn, scan_id, export_format, blob_store=blob_store
            )
        except Exception as exc:  # recorded per file; the other exports still render
            render_error = exc
        timings[export_format] = round(time.perf_counter() - render_started, 3)
        for draft in (False, True):
            name = export_render.export_filename(stem, export_format, draft=draft)
            error = render_error
            if rendered is not None:
                try:
                    labeled = export_render.label(
                        rendered, export_format, status=status, draft=draft
                    )
                except Exception as exc:
                    error = exc
            if error is not None:
                # Type and message only: a traceback carries checkout paths
                # that would differ between two otherwise identical renders.
                (out / f"{name}.error.txt").write_text(f"{type(error).__name__}: {error}\n")
                failures += 1
                written += 1
                continue
            if isinstance(labeled, bytes):
                (out / name).write_bytes(labeled)
                fingerprint_started = time.perf_counter()
                text = dumps_fingerprint(fingerprint_xlsx(labeled))
                timings[f"{name} fingerprint"] = round(time.perf_counter() - fingerprint_started, 3)
                (out / f"{name}.json").write_bytes(text.encode("utf-8"))
                written += 2
            else:
                (out / name).write_bytes(labeled.encode("utf-8"))
                written += 1
    entry["seconds"] = timings
    rendered_total = sum(seconds for key, seconds in timings.items() if " " not in key)
    print(
        f"scan {scan_id}: {entry['route_disposition']} ({status}), "
        f"renders {rendered_total:.2f} s, xlsx {timings.get('xlsx', 0.0):.2f} s"
        + (f", {failures} failure(s)" if failures else "")
    )
    return entry, failures, written


# --------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------


def _compared_names(directory: Path) -> set[str]:
    """Files that carry export content. Fingerprint JSON is derived from the
    raw workbook, which is what gets compared."""
    return {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != MANIFEST and not path.name.endswith(".xlsx.json")
    }


def _text_diff(name: str, left: bytes, right: bytes) -> list[str]:
    lines = list(
        difflib.unified_diff(
            left.decode("utf-8", errors="replace").splitlines(),
            right.decode("utf-8", errors="replace").splitlines(),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
            lineterm="",
            n=1,
        )
    )
    if not lines:
        # Same lines, different bytes: line endings or a trailing newline.
        return [f"  bytes differ ({len(left)} vs {len(right)}) with identical text lines"]
    if len(lines) > _DIFF_LINES:
        lines = [*lines[:_DIFF_LINES], f"... {len(lines) - _DIFF_LINES} more diff line(s)"]
    return ["  " + line for line in lines]


def _warn_on_manifests(left: Path, right: Path) -> None:
    manifests = []
    for directory in (left, right):
        try:
            manifests.append(json.loads((directory / MANIFEST).read_text()))
        except (OSError, ValueError):
            print(f"warning: no readable {MANIFEST} in {directory}", file=sys.stderr)
            return
    left_package, right_package = (m.get("audit_package") for m in manifests)
    print(f"a: {left_package}\nb: {right_package}")
    if left_package == right_package:
        print(
            "warning: both renders used the same audit package; "
            "did PYTHONPATH change between them?",
            file=sys.stderr,
        )
    if manifests[0].get("pinned") != manifests[1].get("pinned"):
        print("warning: the two renders pinned different inputs", file=sys.stderr)


def _compare(args: argparse.Namespace) -> int:
    left, right = Path(args.dir_a), Path(args.dir_b)
    for directory in (left, right):
        if not directory.is_dir():
            print(f"error: not a directory: {directory}", file=sys.stderr)
            return 2
    _warn_on_manifests(left, right)
    left_names, right_names = _compared_names(left), _compared_names(right)
    identical = 0
    different: list[str] = []
    for name in sorted(left_names - right_names):
        different.append(name)
        print(f"ONLY IN A  {name}")
    for name in sorted(right_names - left_names):
        different.append(name)
        print(f"ONLY IN B  {name}")
    for name in sorted(left_names & right_names):
        left_bytes = (left / name).read_bytes()
        right_bytes = (right / name).read_bytes()
        if name.endswith(".xlsx"):
            diff = fingerprint_diff(
                fingerprint_xlsx(left_bytes),
                fingerprint_xlsx(right_bytes),
                labels=(f"a/{name}", f"b/{name}"),
                limit=_DIFF_LINES,
            )
            diff = ["  " + line for line in diff]
        elif left_bytes == right_bytes:
            diff = []
        else:
            diff = _text_diff(name, left_bytes, right_bytes)
        if diff:
            different.append(name)
            print(f"DIFFERS    {name}")
            print("\n".join(diff))
        else:
            identical += 1
    print(f"{identical} identical, {len(different)} different")
    return 1 if different else 0


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render every export for every completed scan, or compare two renders."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render", help="render all exports from a database copy")
    render.add_argument("--db", required=True, help="source audit.db (opened read-only)")
    render.add_argument("--out", required=True, help="new or empty output directory")
    render.add_argument("--blob-dir", help="blob store to embed workbook evidence from (read-only)")
    render.add_argument(
        "--scan", type=int, action="append", help="limit to this scan id (repeatable)"
    )
    render.set_defaults(handler=_render)

    compare = commands.add_parser("compare", help="compare two render directories")
    compare.add_argument("dir_a")
    compare.add_argument("dir_b")
    compare.set_defaults(handler=_compare)

    args = parser.parse_args(argv)
    handler = args.handler
    return int(handler(args))


if __name__ == "__main__":
    sys.exit(main())
