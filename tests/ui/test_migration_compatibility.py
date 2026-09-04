"""Regression coverage for rolling upgrades of the local Axcess database."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.db.schema import connect
from audit.web import server

pytestmark = pytest.mark.ui

_MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"


def _legacy_database(tmp_path: Path, *, through: int = 10) -> tuple[Path, Path, int, int]:
    """Build a real pre-protected schema using migrations 0001..0010."""

    db_path = tmp_path / "legacy.db"
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir()
    conn = connect(db_path)
    try:
        for path in sorted(_MIGRATIONS.glob("*.sql")):
            if path.name.endswith(".rollback.sql"):
                continue
            migration_number = int(path.name.split("_", 1)[0])
            if migration_number > through:
                continue
            conn.executescript(path.read_text(encoding="utf-8"))
        first = conn.execute(
            "INSERT INTO scans "
            "(seed_url, status, page_count, finding_count, config_json, finished_at) "
            "VALUES ('https://legacy.example/first', 'completed', 1, 0, '{}', "
            "CURRENT_TIMESTAMP)"
        )
        second = conn.execute(
            "INSERT INTO scans "
            "(seed_url, status, page_count, finding_count, config_json, finished_at) "
            "VALUES ('https://legacy.example/second', 'completed', 2, 0, '{}', "
            "CURRENT_TIMESTAMP)"
        )
        return db_path, blob_dir, int(first.lastrowid or 0), int(second.lastrowid or 0)
    finally:
        conn.close()


def test_public_report_apis_survive_pre_protected_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """New server code must not make migration 0011 mandatory for public reports."""

    db_path, blob_dir, first_id, second_id = _legacy_database(tmp_path)

    async def no_op_crawl(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(server, "_run_background_crawl", no_op_crawl)
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    with TestClient(app, raise_server_exceptions=False) as client:
        listed = client.get("/api/scans")
        assert listed.status_code == 200
        assert {row["id"] for row in listed.json()} == {first_id, second_id}

        detail = client.get(f"/api/scans/{first_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == first_id

        evaluation = client.get(f"/api/scans/{first_id}/evaluation")
        assert evaluation.status_code == 200
        assert evaluation.json()["scan_id"] == first_id

        manual_checks = client.get(f"/api/scans/{first_id}/manual-checks")
        assert manual_checks.status_code == 200
        assert manual_checks.json()["evaluation"]["scan_id"] == first_id

        comparison = client.get(f"/api/scans/{second_id}/diff?compare_to={first_id}")
        assert comparison.status_code == 200

        exported = client.get(
            f"/api/scans/{first_id}/export/markdown",
            params={"draft": "acknowledged"},
        )
        assert exported.status_code == 200
        assert "text/markdown" in exported.headers["content-type"]
        assert f"scan_{first_id}_DRAFT.md" in exported.headers["content-disposition"]

        created = client.post(
            "/api/scans",
            json={
                "url": "https://new-public.example/",
                "scan_engine": "axe",
                "max_pages": 1,
            },
        )
        assert created.status_code == 201
        created_id = int(created.json()["scan_id"])
        assert created_id > second_id

        cancelled = client.post(f"/api/scans/{created_id}/cancel")
        assert cancelled.status_code == 200


def test_partial_protected_migration_still_lists_public_reports(tmp_path: Path) -> None:
    """A table created by 0011 must hide its rows before later migrations finish."""

    db_path, blob_dir, public_id, protected_id = _legacy_database(tmp_path, through=11)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO protected_scans ("
            "scan_id, target_owner, environment, data_classification, authorized_by, "
            "authorization_acknowledged, least_privilege_account_acknowledged, "
            "approved_target_origins_json, approved_auth_origins_json, "
            "approved_cdn_origins_json, local_ai_allowed, local_ai_acknowledged, "
            "protection_status, cleanup_at, wrapped_data_key, kms_key_id"
            ") VALUES (?, 'owner', 'staging', 'sensitive', 'auditor', 1, 1, "
            "'[\"https://protected.example\"]', '[]', '[]', 0, 0, 'interrupted', "
            "datetime('now', '+7 days'), X'01', 'test-kms')",
            (protected_id,),
        )
        conn.commit()
    finally:
        conn.close()

    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    with TestClient(app, raise_server_exceptions=False) as client:
        listed = client.get("/api/scans")
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [public_id]

        public_detail = client.get(f"/api/scans/{public_id}")
        assert public_detail.status_code == 200


def test_legacy_populated_alfa_report_still_exports_without_revealed_by(tmp_path: Path) -> None:
    """Missing later metadata must not prevent exporting existing evidence."""
    from audit.exports.collector import collect_scan
    from audit.exports.markdown_report import render_markdown

    db_path, _, scan_id, _ = _legacy_database(tmp_path)
    with connect(db_path) as conn:
        page_id = int(
            conn.execute(
                "INSERT INTO pages(scan_id,url_normalized,status_code,render_mode) VALUES (?, 'https://legacy.example/first',200,'js')",
                (scan_id,),
            ).lastrowid
        )
        conn.execute(
            "INSERT INTO page_a11y_findings(page_id,scan_id,rule_id,pipeline,target_selector,"
            "target_hash,engine_outcome,engine_evidence_json,help) "
            "VALUES (?,?,'sia-r69','alfa','p','legacy-hash','cant_tell',?, 'Contrast')",
            (page_id, scan_id, '{"diagnostic":{"message":"Could not resolve colors"}}'),
        )
        columns_before = [r[1] for r in conn.execute("PRAGMA table_info(page_a11y_findings)")]
        assert "revealed_by" not in columns_before
        report = collect_scan(conn, scan_id)
        assert report.a11y_findings[0].revealed_by is None
        assert report.a11y_findings[0].failure_summary == "Could not resolve colors"
        assert "**Diagnostic:** Could not resolve colors" in render_markdown(report)
        assert [
            r[1] for r in conn.execute("PRAGMA table_info(page_a11y_findings)")
        ] == columns_before
