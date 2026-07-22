"""Route tests for the report workspace's expert-review APIs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


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
