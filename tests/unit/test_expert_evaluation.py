"""Expert-review persistence, exports, and read-only report-tool boundaries."""

from __future__ import annotations

import sqlite3
from io import BytesIO

from openpyxl import load_workbook

from audit import evaluation
from audit.exports.audit_report import render_audit_report
from audit.exports.collector import collect_scan
from audit.exports.xlsx_export import render_xlsx
from audit.mcp_server import get_finding_evidence, get_report_summary, list_report_issues


def _scan(conn: sqlite3.Connection, *, url: str = "https://example.test/") -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'completed', '{}')",
        (url,),
    )
    return int(cur.lastrowid)


def test_evaluation_and_manual_check_are_persisted_without_mutating_scan(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _scan(tmp_db)
    initial = evaluation.get_evaluation(tmp_db, scan_id)
    assert initial["exists"] is False
    assert initial["target_standard"] == "WCAG 2.2"

    record = evaluation.upsert_evaluation(
        tmp_db,
        scan_id,
        {
            "reviewer": "A. Expert",
            "scope_included": "Homepage and admissions",
            "status": "in_progress",
        },
    )
    assert record["exists"] is True
    assert record["reviewer"] == "A. Expert"
    assert (
        tmp_db.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone()["status"]
        == "completed"
    )

    result = evaluation.update_manual_check(
        tmp_db,
        scan_id=scan_id,
        criterion_sc="2.1.1",
        outcome="fail",
        rationale="Keyboard-only menu cannot reach the search control.",
    )
    assert result["outcome"] == "fail"
    assert result["rationale"].startswith("Keyboard-only")


def test_manual_evidence_rejects_page_from_another_report(tmp_db: sqlite3.Connection) -> None:
    scan_a = _scan(tmp_db, url="https://a.test/")
    scan_b = _scan(tmp_db, url="https://b.test/")
    page_b = tmp_db.execute(
        "INSERT INTO pages (scan_id, url_normalized, render_mode) "
        "VALUES (?, ?, 'static') RETURNING id",
        (scan_b, "https://b.test/"),
    ).fetchone()["id"]

    try:
        evaluation.add_manual_evidence(
            tmp_db,
            scan_id=scan_a,
            criterion_sc="1.1.1",
            note="Wrong report page",
            page_id=int(page_b),
            evidence_url="",
        )
    except ValueError as exc:
        assert "not part" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("cross-report evidence must be rejected")


def test_expert_record_is_rendered_in_report_and_tracking_sheet(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    evaluation.upsert_evaluation(
        tmp_db,
        scan_id,
        {"reviewer": "A. Expert", "limitations": "No authenticated flows were reviewed."},
    )
    evaluation.update_manual_check(
        tmp_db,
        scan_id=scan_id,
        criterion_sc="1.1.1",
        outcome="pass",
        rationale="Representative meaningful images have text alternatives.",
    )
    scan = collect_scan(tmp_db, scan_id)
    markdown = render_audit_report(scan, conn=tmp_db)
    assert "## Expert evaluation record" in markdown
    assert "A. Expert" in markdown
    assert "No authenticated flows" in markdown
    assert "| 1.1.1 | pass |" in markdown

    book = load_workbook(BytesIO(render_xlsx(scan, conn=tmp_db)))
    tracking = book["Test Tracking"]
    first_row = next(
        row
        for row in tracking.iter_rows(min_row=5, values_only=True)
        if str(row[0]).startswith("1.1.1")
    )
    assert first_row[2] == "Pass"


def test_read_only_report_tools_reject_cross_report_finding(tmp_db: sqlite3.Connection) -> None:
    scan_a = _scan(tmp_db, url="https://a.test/")
    scan_b = _scan(tmp_db, url="https://b.test/")
    assert get_report_summary(tmp_db, scan_id=scan_a)["report"]["id"] == scan_a
    assert list_report_issues(tmp_db, scan_id=scan_a) == []
    assert get_finding_evidence(tmp_db, scan_id=scan_a, finding_id=9999) is None
    assert get_finding_evidence(tmp_db, scan_id=scan_b, finding_id=9999) is None
