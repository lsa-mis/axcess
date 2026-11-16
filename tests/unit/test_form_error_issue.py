"""A stored form error finding shows up as an issue like any other check's.

The form error check (WCAG 3.3.1) stores one occurrence per form in
page_a11y_findings with pipeline 'forms'. The issue list groups it like the
other browser checks: its own title and guidance card, WCAG 3.3.1 Level A,
and "After clicking", because the error exists only after the submit control
is pressed.

How sure (the developer's decision, 2026-11-05): a clear failure is Mostly
sure; one with an undecided sign (a "Required" hint turning red, text only
screen readers get, a changed placeholder, a picture with alt text) is Not
sure. Reports made before the split keep their rule and read as they did.
"""

from __future__ import annotations

import hashlib
import sqlite3
from types import SimpleNamespace
from typing import Any

from audit.analyzer.forms import FormFinding
from audit.analyzer.forms import base as forms_base
from audit.db import repo
from audit.web import comparison, issues


def _finding(*, unclear: bool = False) -> FormFinding:
    return FormFinding(
        target_selector="#contact",
        html_snippet='<form id="contact" novalidate>...</form>',
        failure_summary="Fields were marked in error, but no text describes the error.",
        submit="Send message",
        unclear=unclear,
    )


def _scan_with(conn: sqlite3.Connection, **kwargs: Any) -> int:
    cursor = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://x.test/', 'completed', ?)",
        ('{"form_error_checks_enabled": true}',),
    )
    scan_id = int(cursor.lastrowid or 0)
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="https://x.test/contact",
        status_code=200,
        title="Contact",
        render_mode="js",
        html_hash="0" * 64,
    )
    repo.upsert_keyboard_finding(conn, page_id=page_id, scan_id=scan_id, **kwargs)
    conn.commit()
    return scan_id


def _form_row(conn: sqlite3.Connection, scan_id: int) -> issues.IssueRow:
    rows = [r for r in issues.list_issues(conn, scan_id) if r.pipeline == "forms"]
    assert len(rows) == 1, rows
    return rows[0]


def test_a_clear_failure_is_mostly_sure(tmp_db: sqlite3.Connection) -> None:
    row = _form_row(tmp_db, _scan_with(tmp_db, **_finding().to_repo_kwargs()))

    assert row.issue_key == "forms:form-error-identification"
    assert row.title == "Form shows an error without describing it in text"
    assert row.wcag_sc == "3.3.1"
    assert row.wcag_name == "Error Identification"
    assert row.conformance == "A"
    assert row.review_lane == "likely_barrier"
    assert row.evidence_confidence == "high"
    assert row.finding_types == ("click_through",)
    assert row.occurrence_count == 1


def test_an_unclear_failure_is_not_sure(tmp_db: sqlite3.Connection) -> None:
    row = _form_row(tmp_db, _scan_with(tmp_db, **_finding(unclear=True).to_repo_kwargs()))

    assert row.issue_key == "forms:form-error-identification-unclear"
    assert row.title == "Form may show an error without describing it in text"
    assert row.review_lane == "expert_review"


def test_a_report_from_before_the_split_reads_as_it_did(tmp_db: sqlite3.Connection) -> None:
    kwargs = _finding().to_repo_kwargs() | {"rule_id": forms_base.RULE_LEGACY}
    row = _form_row(tmp_db, _scan_with(tmp_db, **kwargs))

    assert row.issue_key == "forms:form-error-not-described"
    assert row.title == "Form shows an error without describing it in text"
    assert row.review_lane == "expert_review"


def test_a_clear_failure_keeps_the_identity_it_had_before_the_split() -> None:
    """Reviews and history follow ``target_hash``; it hashes the old rule."""
    h = hashlib.sha256()
    snippet = '<form id="contact" novalidate>...</form>'
    for part in ("form-error-not-described", "", "#contact", snippet):
        h.update(part.encode())
        h.update(b"\x00")
    assert _finding().target_hash == h.hexdigest()
    assert _finding(unclear=True).target_hash != h.hexdigest()


def test_comparison_treats_the_old_rule_and_the_clear_rule_as_one_issue() -> None:
    def key(issue_key: str) -> str:
        return comparison._group_key(SimpleNamespace(pipeline="forms", issue_key=issue_key))  # type: ignore[arg-type]

    assert key("forms:form-error-not-described") == key("forms:form-error-identification")
    assert key("forms:form-error-identification-unclear") != key("forms:form-error-identification")


def test_its_detail_has_the_guidance_card_and_the_page(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan_with(tmp_db, **_finding().to_repo_kwargs())

    detail = issues.get_issue_detail(tmp_db, scan_id, "forms:form-error-identification")

    assert detail is not None
    assert [p.page_url for p in detail.pages] == ["https://x.test/contact"]
    text = repr(detail)
    assert "Error Identification" in text
    assert "aria-describedby" in text
