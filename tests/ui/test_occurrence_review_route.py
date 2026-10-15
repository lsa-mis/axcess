"""PUT /api/scans/{id}/pages/{page}/review: a person's review of one element."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support.rich_scan import dom_finding

from audit.db.schema import connect
from audit.web import server


def _page_and_image(db_path: Path, scan_id: int) -> tuple[int, int]:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT pi.page_id, pi.id FROM page_images pi JOIN pages p ON p.id = pi.page_id "
            "WHERE p.scan_id = ? ORDER BY pi.id LIMIT 1",
            (scan_id,),
        ).fetchone()
    finally:
        conn.close()
    return int(row[0]), int(row[1])


def _add_finding(db_path: Path, scan_id: int, page_id: int) -> int:
    conn = connect(db_path)
    try:
        dom_finding(
            conn,
            scan_id=scan_id,
            page_id=page_id,
            rule_id="color-contrast",
            help_text="Elements must meet minimum color contrast",
            target="p.muted",
            impact="serious",
            wcag_sc="1.4.3",
            wcag_level="AA",
        )
        conn.commit()
        return int(
            conn.execute(
                "SELECT id FROM page_a11y_findings WHERE scan_id = ? ORDER BY id DESC LIMIT 1",
                (scan_id,),
            ).fetchone()[0]
        )
    finally:
        conn.close()


def test_saves_a_review_and_the_inspector_reads_it_back(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    page_id, image_id = _page_and_image(db_path, scan_id)
    finding_id = _add_finding(db_path, scan_id, page_id)

    resp = client.put(
        f"/api/scans/{scan_id}/pages/{page_id}/review",
        json={
            "a11y_finding_ids": [finding_id],
            "page_image_ids": [image_id],
            "decision": "report",
            "notes": "  Grey text on white fails contrast. ",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "report"
    assert body["notes"] == "Grey text on white fails contrast."
    assert body["updated_at"]

    evidence = client.get(f"/api/scans/{scan_id}/pages/{page_id}").json()
    (finding,) = [f for f in evidence["a11y_findings"] if f["id"] == finding_id]
    assert finding["review"]["decision"] == "report"
    images = [i for i in evidence["image_occurrences"] if i["occurrence_id"] == image_id]
    assert images and images[0]["review"]["notes"] == body["notes"]


def test_any_report_can_be_reviewed_finished_or_not(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    page_id, image_id = _page_and_image(db_path, scan_id)
    conn = connect(db_path)
    conn.execute("UPDATE scans SET status = 'interrupted' WHERE id = ?", (scan_id,))
    conn.commit()
    conn.close()

    resp = client.put(
        f"/api/scans/{scan_id}/pages/{page_id}/review",
        json={"page_image_ids": [image_id], "decision": None, "notes": "Check later."},
    )
    assert resp.status_code == 200, resp.text


def test_refuses_occurrences_from_another_report(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    page_id, image_id = _page_and_image(db_path, scan_id)
    conn = connect(db_path)
    other = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES ('http://other.test/', "
        "'completed', '{}')"
    ).lastrowid
    conn.commit()
    conn.close()
    body = {"page_image_ids": [image_id], "decision": "report", "notes": ""}

    # The page belongs to the first report, not the second.
    assert client.put(f"/api/scans/{other}/pages/{page_id}/review", json=body).status_code == 404
    assert client.put(f"/api/scans/99999/pages/{page_id}/review", json=body).status_code == 404

    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT COUNT(*) FROM occurrence_reviews").fetchone()[0] == 0
    raw.close()


def test_rejects_requests_it_cannot_bound(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    page_id, image_id = _page_and_image(db_path, scan_id)
    url = f"/api/scans/{scan_id}/pages/{page_id}/review"

    too_long = {"page_image_ids": [image_id], "decision": "report", "notes": "x" * 2001}
    assert client.put(url, json=too_long).status_code == 422
    unknown_decision = {"page_image_ids": [image_id], "decision": "maybe", "notes": ""}
    assert client.put(url, json=unknown_decision).status_code == 422
    unknown_field = {"page_image_ids": [image_id], "decision": "report", "sql": "1"}
    assert client.put(url, json=unknown_field).status_code == 422
    nothing = {"decision": "report", "notes": ""}
    assert client.put(url, json=nothing).status_code == 400
    # Notes may be left out: the decision alone is saved, notes kept.
    decision_only = {"page_image_ids": [image_id], "decision": "repeat"}
    assert client.put(url, json=decision_only).status_code == 200


def test_refuses_protected_reports(
    client: TestClient, seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A protected report keeps only aliases; notes would be plaintext evidence."""
    db_path, _, scan_id = seeded_db
    page_id, image_id = _page_and_image(db_path, scan_id)
    monkeypatch.setattr(server, "_get_protected_scan_compat", lambda conn, scan_id: object())

    resp = client.put(
        f"/api/scans/{scan_id}/pages/{page_id}/review",
        json={"page_image_ids": [image_id], "decision": "report", "notes": ""},
    )
    assert resp.status_code == 403
