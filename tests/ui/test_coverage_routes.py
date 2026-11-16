"""Routes behind the Coverage page: /api/coverage/checks and /api/coverage/found.

The figures themselves are pinned in tests/unit/test_issue_share.py and
tests/unit/test_coverage_checks.py; these tests pin the HTTP edges, and that
the found figures change as soon as another scan completes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from audit.db.schema import connect


def test_checks_default_to_the_version_scans_use(client: TestClient) -> None:
    body = client.get("/api/coverage/checks").json()
    assert body["wcag_version"] == "2.1"
    assert len(body["criteria"]) == 50
    contrast = next(c for c in body["criteria"] if c["sc"] == "1.4.3")
    assert [rule["id"] for rule in contrast["rules"]] == ["color-contrast"]
    assert contrast["rules"][0]["description"].startswith("Ensure the contrast")
    assert contrast["rules"][0]["url"].startswith("https://dequeuniversity.com/rules/axe/")
    assert contrast["understanding_url"].endswith("/WCAG21/Understanding/contrast-minimum.html")


def test_checks_for_wcag_22_and_a_refused_version(client: TestClient) -> None:
    assert len(client.get("/api/coverage/checks?version=2.2").json()["criteria"]) == 55
    assert client.get("/api/coverage/checks?version=3.0").status_code == 422


def test_found_counts_completed_reports_and_updates_after_a_scan(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    before = client.get("/api/coverage/found").json()
    assert before["scans_included"] == 1
    assert before["scan_id"] is None

    conn = connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('http://second.test/', 'completed', '{}')"
        )
        second = int(cur.lastrowid or 0)
        page = conn.execute(
            "INSERT INTO pages (scan_id, url_normalized, status_code, title, render_mode, "
            "html_hash) VALUES (?, 'http://second.test/', 200, 'Home', 'js', ?)",
            (second, "f" * 64),
        ).lastrowid
        conn.execute(
            "INSERT INTO page_a11y_findings (page_id, scan_id, rule_id, wcag_sc, wcag_level, "
            "impact, help, target_selector, target_hash) "
            "VALUES (?, ?, 'image-alt', '1.1.1', 'A', 'critical', 'Images need alt', 'img', 'h1')",
            (page, second),
        )
        conn.commit()
    finally:
        conn.close()

    after = client.get("/api/coverage/found").json()
    assert after["scans_included"] == 2
    assert after["layers"]["total"] == before["layers"]["total"] + 1

    one = client.get(f"/api/coverage/found?scan_id={second}").json()
    assert one["scan_id"] == second
    assert one["layers"]["total"] == 1
    assert client.get(f"/api/coverage/found?scan_id={scan_id}").status_code == 200


def test_found_refuses_reports_it_cannot_count(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, _ = seeded_db
    conn: sqlite3.Connection = connect(db_path)
    try:
        running = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('http://run.test/', 'running', '{}')"
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    assert client.get(f"/api/coverage/found?scan_id={running}").status_code == 409
    assert client.get("/api/coverage/found?scan_id=99999").status_code == 404
    assert client.get("/api/coverage/found?scan_id=0").status_code == 422
