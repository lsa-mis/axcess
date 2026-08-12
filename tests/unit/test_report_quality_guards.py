"""Adversarial quality gates for the stakeholder audit report.

These cases model the ways a polished-looking report can become misleading:
an access-blocked seed that looks clean, manual evidence that vanishes at
handoff, or reviewer text that corrupts a Markdown table.
"""

from __future__ import annotations

import sqlite3

from test_audit_report import _scan_with_real_findings

from audit import evaluation
from audit.db import repo
from audit.exports.audit_report import render_audit_report
from audit.exports.collector import collect_scan


def test_blocked_seed_report_does_not_claim_a_clean_scope(
    tmp_db: sqlite3.Connection,
) -> None:
    """A Cloudflare/login wall is missing coverage, never a passing result."""
    cur = tmp_db.execute(
        "INSERT INTO scans (seed_url, status, page_count, config_json) "
        "VALUES (?, 'completed', 1, '{}')",
        ("https://protected.example/",),
    )
    scan_id = int(cur.lastrowid)
    repo.upsert_page(
        tmp_db,
        scan_id=scan_id,
        url_normalized="https://protected.example/",
        status_code=403,
        title="Just a moment...",
        render_mode="js",
        html_hash="0" * 64,
    )

    report = render_audit_report(collect_scan(tmp_db, scan_id), conn=tmp_db)

    assert "Coverage warning" in report
    assert "HTTP 403" in report
    assert "Just a moment" in report
    assert "scope is already clean" not in report
    assert "not a passing result" in report


def test_manual_evidence_is_exported_and_markdown_safe(
    tmp_db: sqlite3.Connection,
) -> None:
    """Evidence and hostile-looking prose stay attached to the right decision."""
    scan_id = _scan_with_real_findings(tmp_db)
    page_id = int(
        tmp_db.execute("SELECT id FROM pages WHERE scan_id = ?", (scan_id,)).fetchone()["id"]
    )
    evaluation.upsert_evaluation(
        tmp_db,
        scan_id,
        {
            "reviewer": "A. Expert",
            "limitations": "A representative sample only.",
            "status": "in_progress",
        },
    )
    evaluation.update_manual_check(
        tmp_db,
        scan_id=scan_id,
        criterion_sc="1.1.1",
        outcome="needs_follow_up",
        rationale="Hero review | needs content-owner confirmation\nbefore sign-off.",
    )
    evaluation.add_manual_evidence(
        tmp_db,
        scan_id=scan_id,
        criterion_sc="1.1.1",
        page_id=page_id,
        evidence_url="https://tracker.example/TICKET-42",
        note="Screenshot | reviewed with design\nteam.",
    )

    report = render_audit_report(collect_scan(tmp_db, scan_id), conn=tmp_db)
    expert = report.split("## Expert evaluation record", 1)[1].split("## Page hotspots", 1)[0]

    assert "| 1.1.1 | needs follow up | Hero review \\| needs content-owner" in expert
    assert "### Evidence references" in expert
    assert "http://example.com/" in expert
    assert "https://tracker.example/TICKET-42" in expert
    assert "Screenshot \\| reviewed with design team." in expert


def test_manual_evidence_never_crosses_report_boundaries(
    tmp_db: sqlite3.Connection,
) -> None:
    """A report export may not disclose another report's expert evidence."""
    first_scan = _scan_with_real_findings(tmp_db)
    first_page = int(
        tmp_db.execute("SELECT id FROM pages WHERE scan_id = ?", (first_scan,)).fetchone()["id"]
    )
    evaluation.add_manual_evidence(
        tmp_db,
        scan_id=first_scan,
        criterion_sc="1.1.1",
        page_id=first_page,
        evidence_url="https://private.example/first-report",
        note="First report only.",
    )

    second_scan = _scan_with_real_findings(tmp_db)
    report = render_audit_report(collect_scan(tmp_db, second_scan), conn=tmp_db)

    assert "https://private.example/first-report" not in report
    assert "First report only." not in report
