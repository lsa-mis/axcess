"""API regressions for Alfa failed/cantTell evidence isolation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.ui


def test_mixed_alfa_outcomes_have_distinct_api_groups_and_details(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    conn = sqlite3.connect(db_path)
    try:
        page_ids = [
            int(row[0])
            for row in conn.execute(
                "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 2",
                (scan_id,),
            ).fetchall()
        ]
        assert len(page_ids) == 2
        finding_ids: dict[str, int] = {}
        for page_id, outcome, status in (
            (page_ids[0], "failed", "new"),
            (page_ids[1], "cant_tell", "reviewing"),
        ):
            cursor = conn.execute(
                """
                INSERT INTO page_a11y_findings
                    (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
                     impact, help, help_url, target_selector, failure_summary,
                     html_snippet, target_hash, status, pipeline, engine_outcome)
                VALUES (?, ?, 'sia-r-api-mixed', '1.1.1', '1.1.1', 'A', NULL,
                        'Non-text content needs an expert decision.',
                        'https://alfa.siteimprove.com/rules/sia-r-api-mixed',
                        ?, ?, '<img>', ?, ?, 'alfa', ?)
                """,
                (
                    page_id,
                    scan_id,
                    f"img.{outcome}",
                    f"diagnostic-{outcome}",
                    f"api-mixed-{outcome}",
                    status,
                    outcome,
                ),
            )
            finding_ids[outcome] = int(cursor.lastrowid or 0)
        conn.commit()
    finally:
        conn.close()

    by_rule = client.get(f"/api/scans/{scan_id}/a11y/by-rule")
    assert by_rule.status_code == 200
    groups = [
        group
        for group in by_rule.json()["groups"]
        if group["pipeline"] == "alfa" and group["rule_id"] == "sia-r-api-mixed"
    ]
    assert [group["outcome_group"] for group in groups] == ["failed", "cant_tell"]
    assert [finding["id"] for finding in groups[0]["findings"]] == [finding_ids["failed"]]
    assert [finding["id"] for finding in groups[1]["findings"]] == [finding_ids["cant_tell"]]

    issue_response = client.get(f"/api/scans/{scan_id}/issues")
    assert issue_response.status_code == 200
    issue_rows = {
        row["issue_key"]: row for row in issue_response.json()["rows"] if row["pipeline"] == "alfa"
    }
    failed = issue_rows["alfa:sia-r-api-mixed:failed"]
    review = issue_rows["alfa:sia-r-api-mixed:cant_tell"]
    assert (failed["review_lane"], failed["evidence_confidence"]) == (
        "likely_barrier",
        "high",
    )
    assert failed["finding_ids"] == [finding_ids["failed"]]
    assert "strong automated evidence" in failed["why_matters"]
    assert "not a conformance verdict" in failed["why_matters"]
    assert (review["review_lane"], review["evidence_confidence"]) == (
        "expert_review",
        "medium",
    )
    assert review["high_confidence_occurrence_count"] == 0
    assert review["finding_ids"] == [finding_ids["cant_tell"]]
    assert "not a failure" in review["why_matters"]

    failed_detail = client.get(f"/api/scans/{scan_id}/issues/alfa:sia-r-api-mixed:failed")
    review_detail = client.get(f"/api/scans/{scan_id}/issues/alfa:sia-r-api-mixed:cant_tell")
    assert failed_detail.status_code == 200
    assert review_detail.status_code == 200
    assert failed_detail.json()["pages"][0]["status_summary"] == {"new": 1}
    assert review_detail.json()["pages"][0]["status_summary"] == {"reviewing": 1}

    # The former aggregate key is intentionally unavailable when it would
    # combine incompatible evidence meanings.
    legacy = client.get(f"/api/scans/{scan_id}/issues/alfa:sia-r-api-mixed")
    assert legacy.status_code == 404
