"""Excel (.xlsx) audit report — structural assertions.

The xlsx renderer produces a binary workbook, so we parse it back with
openpyxl and pin the *structure* (two named sheets, the metadata header
block, the table headers, value mappings) rather than byte content. The
issue rows come from the same multi-pipeline fixture the Markdown audit
report uses, so both deliverables stay in lockstep.
"""

from __future__ import annotations

import io
import re
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
        "Page Hotspots",
        "Page References",
        "Who's Affected",
        "Coverage & Method",
        "Test Tracking",
        "Manual Review Evidence",
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
    assert "Likely barriers by severity" in labels  # a section header (col A, no value)
    assert "Likely-barrier issue groups" in labels
    assert "Review-only / informational groups" in labels
    assert "Manual only" in labels  # coverage-method rollup row
    assert {"Critical", "Serious", "Moderate", "Minor"} <= labels


def test_coverage_sheet(tmp_db: sqlite3.Connection) -> None:
    wb = load_workbook(io.BytesIO(_render(tmp_db)))

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
    header = tuple(ws.cell(row=8, column=c).value for c in range(1, len(_ISSUE_HEADERS)))
    assert header == _ISSUE_HEADERS[:-1]
    # Every grouped issue with page locations points to the dedicated
    # page-reference index with a true internal workbook destination.
    location_cells = [
        ws.cell(row=row, column=9)
        for row in range(9, ws.max_row + 1)
        if ws.cell(row=row, column=9).value
    ]
    assert location_cells
    assert all(cell.hyperlink is not None for cell in location_cells)
    assert all(cell.hyperlink.target is None for cell in location_cells if cell.hyperlink)
    assert all(
        cell.hyperlink.location == "'Page References'!A1"
        for cell in location_cells
        if cell.hyperlink
    )

    # At least one data row, and the conformance column is mapped to the
    # template's letters. The best-practice axe rule (no SC) → "S".
    conformance = {ws.cell(row=r, column=5).value for r in range(9, ws.max_row + 1)}
    assert "S" in conformance  # page-has-heading-one is best-practice → S
    assert conformance & {"A", "AA"}  # real SCs present too
    sources = {str(ws.cell(row=r, column=3).value or "") for r in range(9, ws.max_row + 1)}
    assert "axe-core (deterministic DOM rules)" in sources
    assert "per-criterion LLM analyzer" in sources
    decisions = {str(ws.cell(row=r, column=2).value or "") for r in range(9, ws.max_row + 1)}
    assert "Likely Barrier" in decisions
    assert "Expert Review" in decisions

    references = wb["Page References"]
    reference_headers = tuple(references.cell(row=4, column=c).value for c in range(1, 9))
    assert reference_headers == (
        "Issue",
        "Detection source",
        "Page",
        "Page title",
        "Location on page",
        "Technical target",
        "Occurrences",
        "Status",
    )
    descriptions = {
        str(references.cell(row=r, column=5).value or "") for r in range(5, references.max_row + 1)
    }
    assert any(
        "text element containing “low text” with class “muted”" in value for value in descriptions
    )
    technical_targets = {
        str(references.cell(row=r, column=6).value or "") for r in range(5, references.max_row + 1)
    }
    assert "p > span.muted" in technical_targets
    assert references.cell(row=5, column=3).hyperlink is not None


def test_xlsx_without_blob_store_omits_empty_evidence_column(
    tmp_db: sqlite3.Connection,
) -> None:
    """Without a blob store, do not waste workbook width on a blank column."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    data = render_xlsx(scan, conn=tmp_db, blob_store=None)
    assert data[:2] == b"PK"
    wb = load_workbook(io.BytesIO(data))
    ws = wb["Issues Overview"]
    header = tuple(ws.cell(row=8, column=c).value for c in range(1, len(_ISSUE_HEADERS)))
    assert header == _ISSUE_HEADERS[:-1]
    assert ws.cell(row=8, column=len(_ISSUE_HEADERS)).value is None


def test_page_references_summarizes_large_structured_engine_targets(
    tmp_db: sqlite3.Connection,
) -> None:
    """Alfa JSON evidence must not turn one workbook row thousands of pixels tall."""
    scan_id = _scan_with_real_findings(tmp_db)
    page_id = int(
        tmp_db.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1",
            (scan_id,),
        ).fetchone()["id"]
    )
    structured_target = '{"path":[' + ",".join(f'"node-{index}"' for index in range(150)) + "]}"
    tmp_db.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, pipeline, engine_outcome, rule_id, wcag_sc,
             wcag_scs, wcag_level, impact, help, help_url, target_selector,
             failure_summary, html_snippet, target_hash, status)
        VALUES (?, ?, 'alfa', 'failed', 'sia-r-test', '1.1.1', '1.1.1', 'A',
                NULL, 'Alfa structured target test',
                'https://alfa.siteimprove.com/rules/sia-r-test', ?,
                'The ACT rule failed for the stored target.', NULL,
                'structured-target-hash', 'new')
        """,
        (page_id, scan_id, structured_target),
    )
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    workbook = load_workbook(io.BytesIO(render_xlsx(scan, conn=tmp_db)))
    references = workbook["Page References"]
    alfa_rows = [
        row
        for row in range(5, references.max_row + 1)
        if "Siteimprove Alfa" in str(references.cell(row=row, column=2).value or "")
    ]
    assert alfa_rows
    row = alfa_rows[0]
    assert "structured target evidence" in str(references.cell(row=row, column=5).value)
    assert references.cell(row=row, column=6).value == (
        "Structured engine target recorded — open the issue evidence in Axcess."
    )


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


def test_every_web_url_in_workbook_is_a_clickable_excel_link(
    tmp_db: sqlite3.Connection,
) -> None:
    """No handoff recipient should need to copy and paste a visible web URL."""
    workbook = load_workbook(io.BytesIO(_render(tmp_db)))
    url_pattern = re.compile(r"https?://[^\s]+")

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                value = str(cell.value or "")
                if url_pattern.search(value):
                    assert cell.hyperlink is not None, (
                        f"{sheet.title}!{cell.coordinate} contains a plain-text URL: {value}"
                    )
