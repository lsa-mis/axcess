"""A stored form error finding shows up as an issue like any other check's.

The form error check (WCAG 3.3.1) stores one occurrence per form in
page_a11y_findings with pipeline 'forms'. The issue list groups it like the
other browser checks: its own title and guidance card, WCAG 3.3.1 Level A,
in the Not sure lane (expert review), and "After clicking", because the
error exists only after the submit control is pressed.
"""

from __future__ import annotations

import sqlite3

from audit.analyzer.forms import FormFinding
from audit.db import repo
from audit.web import issues


def _scan_with_form_error(conn: sqlite3.Connection) -> int:
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
    finding = FormFinding(
        target_selector="#contact",
        html_snippet='<form id="contact" novalidate>...</form>',
        failure_summary="Fields were marked in error, but no text describes the error.",
        submit="Send message",
    )
    repo.upsert_keyboard_finding(conn, page_id=page_id, scan_id=scan_id, **finding.to_repo_kwargs())
    conn.commit()
    return scan_id


def test_the_form_error_is_an_ordinary_issue(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan_with_form_error(tmp_db)

    rows = [r for r in issues.list_issues(tmp_db, scan_id) if r.pipeline == "forms"]

    assert len(rows) == 1
    row = rows[0]
    assert row.issue_key == "forms:form-error-not-described"
    assert row.title == "Form shows an error without describing it in text"
    assert row.wcag_sc == "3.3.1"
    assert row.wcag_name == "Error Identification"
    assert row.conformance == "A"
    assert row.review_lane == "expert_review"
    assert row.finding_types == ("click_through",)
    assert row.occurrence_count == 1


def test_its_detail_has_the_guidance_card_and_the_page(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan_with_form_error(tmp_db)

    detail = issues.get_issue_detail(tmp_db, scan_id, "forms:form-error-not-described")

    assert detail is not None
    assert [p.page_url for p in detail.pages] == ["https://x.test/contact"]
    text = repr(detail)
    assert "Error Identification" in text
    assert "aria-describedby" in text
