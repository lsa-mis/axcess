"""Route tests for the report workspace's expert-review APIs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from audit import coverage_matrix, evaluation
from audit.db.schema import connect
from audit.web import issues


def _prepare_completion_ready_evaluation(
    db_path: Path,
    scan_id: int,
    *,
    not_tested_sc: str | None = None,
) -> None:
    conn = connect(db_path)
    try:
        record = evaluation.upsert_evaluation(
            conn,
            scan_id,
            {
                "reviewer": "A. Expert",
                "purpose": "Prepare a defensible accessibility evaluation.",
                "scope_included": "Pages recorded in this report.",
                "methods_note": "Automated evidence and structured expert review.",
                "limitations": "The evaluation is limited to the documented scope and date.",
                "status": "in_progress",
            },
        )
        rows = []
        for criterion in coverage_matrix.load_matrix():
            is_not_tested = criterion.sc == not_tested_sc
            rows.append(
                (
                    int(record["id"]),
                    criterion.sc,
                    "not_tested" if is_not_tested else "pass",
                    (
                        "Authentication journey was outside the owner-approved test scope."
                        if is_not_tested
                        else f"Expert reviewed {criterion.sc} for the documented scope."
                    ),
                )
            )
        conn.executemany(
            "INSERT INTO manual_check_results "
            "(evaluation_report_id, criterion_sc, outcome, rationale, tested_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )
        for row in issues.list_issues(conn, scan_id, review_lane="expert_review"):
            for finding_id in row.finding_ids:
                if row.pipeline == "image":
                    conn.execute(
                        "UPDATE findings SET status = 'remediated' WHERE scan_id = ? AND id = ?",
                        (scan_id, finding_id),
                    )
                else:
                    conn.execute(
                        "UPDATE page_a11y_findings SET status = 'remediated' "
                        "WHERE scan_id = ? AND id = ?",
                        (scan_id, finding_id),
                    )
    finally:
        conn.close()


def test_issue_api_separates_barriers_review_leads_and_information(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    """The browser contract never collapses an adequate alt into a barrier."""
    _, _, scan_id = seeded_db
    response = client.get(f"/api/scans/{scan_id}/issues")
    assert response.status_code == 200
    payload = response.json()

    assert payload["review_lane_counts"] == {
        "likely_barrier": 0,
        "expert_review": 1,
        "informational": 1,
    }
    assert payload["occurrence_counts"]["high_confidence"] == 0
    assert payload["occurrence_counts"]["all_evidence"] == 3
    rows = {row["issue_key"]: row for row in payload["rows"]}
    assert rows["image:essential_missing"]["page_count"] == 2
    assert rows["image:essential_missing"]["review_lane"] == "expert_review"
    assert rows["image:logo_adequate"]["review_lane"] == "informational"


def test_evaluation_and_manual_check_routes(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    _, _, scan_id = seeded_db
    initial = client.get(f"/api/scans/{scan_id}/evaluation")
    assert initial.status_code == 200
    assert initial.json()["target_standard"] == "WCAG 2.2"
    assert initial.json()["exists"] is False

    saved = client.put(
        f"/api/scans/{scan_id}/evaluation",
        json={"reviewer": "A. Expert", "status": "in_progress", "limitations": "No login flow."},
    )
    assert saved.status_code == 200
    assert saved.json()["reviewer"] == "A. Expert"

    check = client.patch(
        f"/api/scans/{scan_id}/manual-checks/1.1.1",
        json={"outcome": "pass", "rationale": "Reviewed representative images."},
    )
    assert check.status_code == 200
    assert check.json()["outcome"] == "pass"

    evidence = client.post(
        f"/api/scans/{scan_id}/manual-checks/1.1.1/evidence",
        json={"note": "Reviewed home-page hero."},
    )
    assert evidence.status_code == 201

    matrix = client.get(f"/api/scans/{scan_id}/manual-checks")
    row = next(item for item in matrix.json()["checks"] if item["criterion"]["sc"] == "1.1.1")
    assert row["outcome"] == "pass"
    assert row["evidence"][0]["note"] == "Reviewed home-page hero."

    authentication = next(
        item for item in matrix.json()["checks"] if item["criterion"]["sc"] == "3.3.8"
    )
    assert authentication["criterion"]["method"] == "manual"
    assert "does not automatically" in authentication["criterion"]["manual_check"]


def test_evaluation_cannot_complete_without_context_and_terminal_manual_decisions(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    _, _, scan_id = seeded_db

    response = client.put(
        f"/api/scans/{scan_id}/evaluation",
        json={"status": "completed"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "evaluation_not_ready"
    assert any("Required context is missing" in blocker for blocker in detail["blockers"])
    assert any("not started" in blocker for blocker in detail["blockers"])
    assert client.get(f"/api/scans/{scan_id}/evaluation").json()["status"] == "draft"


def test_decided_manual_check_requires_a_nonempty_rationale(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    _, _, scan_id = seeded_db

    response = client.patch(
        f"/api/scans/{scan_id}/manual-checks/1.1.1",
        json={"outcome": "not_tested", "rationale": "   "},
    )

    assert response.status_code == 400
    assert "rationale is required" in response.json()["detail"]
    checks = client.get(f"/api/scans/{scan_id}/manual-checks").json()["checks"]
    result = next(check for check in checks if check["criterion"]["sc"] == "1.1.1")
    assert result["outcome"] == "not_started"


def test_needs_follow_up_blocks_completion_even_with_a_rationale(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    _prepare_completion_ready_evaluation(db_path, scan_id)
    changed = client.patch(
        f"/api/scans/{scan_id}/manual-checks/1.1.1",
        json={"outcome": "needs_follow_up", "rationale": "A second AT session is required."},
    )
    assert changed.status_code == 200

    response = client.put(
        f"/api/scans/{scan_id}/evaluation",
        json={"status": "completed"},
    )

    assert response.status_code == 409
    assert any(
        "still need follow-up" in blocker for blocker in response.json()["detail"]["blockers"]
    )


def test_not_tested_with_rationale_is_a_documented_export_limitation(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    _prepare_completion_ready_evaluation(db_path, scan_id, not_tested_sc="3.3.8")

    completed = client.put(
        f"/api/scans/{scan_id}/evaluation",
        json={"status": "completed"},
    )
    assert completed.status_code == 200, completed.text

    exported = client.get(f"/api/scans/{scan_id}/export/audit")
    assert exported.status_code == 200, exported.text
    assert f'filename="scan_{scan_id}.audit.md"' in exported.headers["content-disposition"]
    assert "DRAFT" not in exported.headers["content-disposition"]
    assert "### Not-tested criteria, documented evaluation limitations" in exported.text
    assert "| 3.3.8 |" in exported.text
    assert "Authentication journey was outside the owner-approved test scope." in exported.text


def test_completed_evaluation_must_be_reopened_before_becoming_incomplete(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    _prepare_completion_ready_evaluation(db_path, scan_id)
    completed = client.put(
        f"/api/scans/{scan_id}/evaluation",
        json={"status": "completed"},
    )
    assert completed.status_code == 200

    check = client.patch(
        f"/api/scans/{scan_id}/manual-checks/1.1.1",
        json={"outcome": "needs_follow_up", "rationale": "New uncertainty found."},
    )
    assert check.status_code == 409

    context = client.put(
        f"/api/scans/{scan_id}/evaluation",
        json={"limitations": "   "},
    )
    assert context.status_code == 409
    assert client.get(f"/api/scans/{scan_id}/evaluation").json()["status"] == "completed"


def test_legacy_invalid_completed_evaluation_is_not_export_ready(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO evaluation_reports "
            "(scan_id, reviewer, purpose, scope_included, methods_note, limitations, status) "
            "VALUES (?, 'Legacy Expert', 'Legacy review', 'Legacy scope', "
            "'Legacy methods', 'Legacy limitations', 'completed')",
            (scan_id,),
        )
    finally:
        conn.close()

    blocked = client.get(f"/api/scans/{scan_id}/export/markdown")
    assert blocked.status_code == 409

    draft = client.get(
        f"/api/scans/{scan_id}/export/markdown",
        params={"draft": "acknowledged"},
    )
    assert draft.status_code == 200
    assert f"scan_{scan_id}_DRAFT.md" in draft.headers["content-disposition"]
    assert draft.text.startswith("> **DRAFT, INCOMPLETE ACCESSIBILITY EVALUATION**")


def test_page_evidence_route_is_scan_scoped(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    conn = sqlite3.connect(db_path)
    try:
        page_id = int(
            conn.execute("SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)).fetchone()[0]
        )
    finally:
        conn.close()

    assert client.get(f"/api/scans/{scan_id}/pages/{page_id}").status_code == 200
    assert client.get(f"/api/scans/{scan_id + 999}/pages/{page_id}").status_code == 404


def test_structured_audit_export_includes_expert_context(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    """The Handoff report link stays a real downloadable expert report."""
    _, _, scan_id = seeded_db
    saved = client.put(
        f"/api/scans/{scan_id}/evaluation",
        json={
            "reviewer": "A. Expert",
            "scope_included": "Public landing pages",
            "limitations": "Authenticated journeys excluded.",
            "status": "in_progress",
        },
    )
    assert saved.status_code == 200
    check = client.patch(
        f"/api/scans/{scan_id}/manual-checks/2.1.1",
        json={"outcome": "not_tested", "rationale": "Needs keyboard test session."},
    )
    assert check.status_code == 200

    unacknowledged = client.get(f"/api/scans/{scan_id}/export/audit")
    assert unacknowledged.status_code == 409

    response = client.get(
        f"/api/scans/{scan_id}/export/audit",
        params={"draft": "acknowledged"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert f'filename="scan_{scan_id}_DRAFT.audit.md"' in response.headers["content-disposition"]
    assert response.text.startswith("> **DRAFT, INCOMPLETE ACCESSIBILITY EVALUATION**")
    assert "## Expert evaluation record" in response.text
    assert "Public landing pages" in response.text
    assert "Authenticated journeys excluded." in response.text
    assert "| 2.1.1 | not tested | Needs keyboard test session. |" in response.text
