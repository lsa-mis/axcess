"""Excel (.xlsx) audit report — structural assertions.

The xlsx renderer produces a binary workbook, so we parse it back with
openpyxl and pin the *structure* (two named sheets, the metadata header
block, the table headers, value mappings) rather than byte content. The
issue rows come from the same multi-pipeline fixture the Markdown audit
report uses, so both deliverables stay in lockstep.
"""

from __future__ import annotations

import io
import sqlite3

from openpyxl import load_workbook
from test_audit_report import _scan_with_real_findings  # tests/unit on sys.path

from audit import coverage_matrix
from audit.exports.collector import collect_scan
from audit.exports.xlsx_export import (
    _ISSUE_HEADERS,
    _TRACK_HEADERS,
    render_xlsx,
)


def _render(conn: sqlite3.Connection) -> bytes:
    scan_id = _scan_with_real_findings(conn)
    scan = collect_scan(conn, scan_id, ui_base_url="http://127.0.0.1:8765")
    return render_xlsx(scan, conn=conn)


def test_xlsx_is_a_valid_workbook_with_all_report_sheets(tmp_db: sqlite3.Connection) -> None:
    data = _render(tmp_db)
    assert data[:2] == b"PK"  # zip / OOXML signature
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == [
        "Summary",
        "Issues Overview",
        "Owner Worklist",
        "Page Hotspots",
        "Who's Affected",
        "Coverage & Method",
        "Test Tracking",
    ]


def test_summary_dashboard_has_metadata_and_rollups(tmp_db: sqlite3.Connection) -> None:
    wb = load_workbook(io.BytesIO(_render(tmp_db)))
    ws = wb["Summary"]
    # Flatten the label/value column-A/B grid into a lookup.
    cells = {
        str(ws.cell(row=r, column=1).value or ""): ws.cell(row=r, column=2).value
        for r in range(1, ws.max_row + 1)
    }
    assert cells.get("Audited against") == "WCAG 2.2 Level AA"
    assert cells.get("Pages crawled") == 2
    # Section bars + at least one severity + coverage-method row are present.
    labels = set(cells)
    assert "Open issues by severity" in labels  # a section header (col A, no value)
    assert "Manual only" in labels  # coverage-method rollup row
    assert {"Critical", "Serious", "Moderate", "Minor"} <= labels


def test_owner_worklist_and_coverage_sheets(tmp_db: sqlite3.Connection) -> None:
    wb = load_workbook(io.BytesIO(_render(tmp_db)))

    work = wb["Owner Worklist"]
    assert tuple(work.cell(row=4, column=c).value for c in range(1, 7)) == (
        "Owner",
        "Issue",
        "Severity",
        "Effort",
        "Pages",
        "WCAG",
    )
    owners = {str(work.cell(row=r, column=1).value or "") for r in range(5, work.max_row + 1)}
    assert owners & {"Developer", "Content editor", "Designer", "Content team"}

    cov = wb["Coverage & Method"]
    assert cov.cell(row=4, column=1).value == "SC"
    cov_rows = [r for r in range(5, cov.max_row + 1) if cov.cell(row=r, column=1).value]
    assert len(cov_rows) == len(coverage_matrix.load_matrix())
    methods = {str(cov.cell(row=r, column=4).value or "") for r in cov_rows}
    assert "Manual only" in methods


def test_issues_overview_header_block_and_table(tmp_db: sqlite3.Connection) -> None:
    wb = load_workbook(io.BytesIO(_render(tmp_db)))
    ws = wb["Issues Overview"]

    # Metadata block (rows 1-5), merged into column A.
    meta = [str(ws.cell(row=r, column=1).value or "") for r in range(1, 6)]
    assert meta[0].startswith("Page: http://example.com/")
    assert meta[1] == "Compliance Standard: WCAG 2.2 Level AA"
    assert meta[2].startswith("Audit Date:")
    assert meta[3] == "Auditor: Axcess"
    assert "Prioritization Guidance" in meta[4]

    # Table header on row 8.
    header = tuple(ws.cell(row=8, column=c).value for c in range(1, len(_ISSUE_HEADERS) + 1))
    assert header == _ISSUE_HEADERS

    # At least one data row, and the conformance column is mapped to the
    # template's letters. The best-practice axe rule (no SC) → "S".
    conformance = {ws.cell(row=r, column=2).value for r in range(9, ws.max_row + 1)}
    assert "S" in conformance  # page-has-heading-one is best-practice → S
    assert conformance & {"A", "AA"}  # real SCs present too


def test_test_tracking_is_the_full_manual_checklist(tmp_db: sqlite3.Connection) -> None:
    wb = load_workbook(io.BytesIO(_render(tmp_db)))
    ws = wb["Test Tracking"]

    header = tuple(ws.cell(row=4, column=c).value for c in range(1, len(_TRACK_HEADERS) + 1))
    assert header == _TRACK_HEADERS

    focus = [str(ws.cell(row=r, column=1).value or "") for r in range(5, ws.max_row + 1)]
    # One row per WCAG 2.2 A/AA criterion, sorted, each with a check.
    assert len(focus) == len(coverage_matrix.load_matrix())
    assert any(f.startswith("1.1.1 ") for f in focus)
    assert all("What to check" not in f for f in focus)
    # Every checklist row carries a non-empty "what to check" instruction.
    checks = [ws.cell(row=r, column=2).value for r in range(5, ws.max_row + 1)]
    assert all(str(c or "").strip() for c in checks)
