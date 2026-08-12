"""HTTP contracts for auditable finding-status decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
from fastapi.testclient import TestClient

from audit.db import repo
from audit.db.schema import connect
from audit.web.server import create_app

pytestmark = pytest.mark.ui

_MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"
FindingKind = Literal["image", "a11y"]


def _finding_id(db_path: Path, scan_id: int, kind: FindingKind) -> int:
    conn = connect(db_path)
    try:
        if kind == "image":
            row = conn.execute(
                "SELECT id FROM findings WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
            ).fetchone()
            assert row is not None
            return int(row["id"])

        page = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        assert page is not None
        return repo.upsert_axe_violation(
            conn,
            page_id=int(page["id"]),
            scan_id=scan_id,
            rule_id="label",
            wcag_sc="1.3.1",
            wcag_scs="1.3.1,3.3.2",
            wcag_level="A",
            impact="serious",
            help="Form elements must have labels",
            help_url="https://dequeuniversity.com/rules/axe/4.10/label",
            target_selector="#route-fixture",
            failure_summary="Fix the missing label.",
            html_snippet='<input id="route-fixture">',
            target_hash="route-status-history",
        )
    finally:
        conn.close()


def _route(kind: FindingKind, finding_id: int, bulk: bool) -> str:
    family = "a11y-findings" if kind == "a11y" else "findings"
    return f"/api/{family}/bulk-status" if bulk else f"/api/{family}/{finding_id}/status"


def _body(
    *, finding_id: int, status: str, bulk: bool, rationale: object | None = None
) -> dict[str, object]:
    body: dict[str, object] = {"status": status}
    if bulk:
        body["finding_ids"] = [finding_id]
    if rationale is not None:
        body["rationale"] = rationale
    return body


@pytest.mark.parametrize("kind", ["image", "a11y"])
@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize("status", ["in_progress", "remediated", "accepted_risk", "false_positive"])
def test_decisive_status_routes_require_and_redact_rationale(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    kind: FindingKind,
    bulk: bool,
    status: str,
) -> None:
    db_path, _, scan_id = seeded_db
    finding_id = _finding_id(db_path, scan_id, kind)
    route = _route(kind, finding_id, bulk)

    missing = client.post(
        route,
        json=_body(finding_id=finding_id, status=status, bulk=bulk),
    )
    assert missing.status_code == 400
    assert "rationale is required" in missing.json()["detail"]

    wrong_type = client.post(
        route,
        json=_body(finding_id=finding_id, status=status, bulk=bulk, rationale=["private"]),
    )
    assert wrong_type.status_code == 400
    assert wrong_type.json()["detail"] == "rationale must be text"

    too_long = client.post(
        route,
        json=_body(finding_id=finding_id, status=status, bulk=bulk, rationale="x" * 2001),
    )
    assert too_long.status_code == 400
    assert "at most 2000" in too_long.json()["detail"]

    sensitive_marker = "route-sensitive-value-must-not-persist"
    rationale = (
        f"Authorization: Bearer {sensitive_marker}\n"
        "Decision verified by auditor@example.edu using stored evidence."
    )
    changed = client.post(
        route,
        json=_body(finding_id=finding_id, status=status, bulk=bulk, rationale=rationale),
    )
    assert changed.status_code == 200
    assert changed.json() == {"status": status, "updated": 1}
    assert sensitive_marker not in changed.text
    assert rationale not in changed.text

    table = "a11y_finding_history" if kind == "a11y" else "finding_history"
    finding_table = "page_a11y_findings" if kind == "a11y" else "findings"
    conn = connect(db_path)
    try:
        persisted_status = conn.execute(
            f"SELECT status FROM {finding_table} WHERE id = ?",  # noqa: S608 - closed test enum
            (finding_id,),
        ).fetchone()["status"]
        history = conn.execute(
            f"SELECT scan_id, change_type, from_status, to_status, actor, "  # noqa: S608 - closed test enum
            f"CAST(changed_at AS TEXT) AS changed_at, note FROM {table} "
            "WHERE finding_id = ? AND change_type = 'status_change' ORDER BY id",
            (finding_id,),
        ).fetchall()
    finally:
        conn.close()
    assert persisted_status == status
    assert len(history) == 1
    row = history[0]
    assert row["scan_id"] == scan_id
    assert row["from_status"] == "new"
    assert row["to_status"] == status
    assert row["actor"] == "user"
    assert row["changed_at"]
    assert row["note"] == (
        "Authorization: <redacted>\nDecision verified by <redacted-email> using stored evidence."
    )
    assert sensitive_marker not in row["note"]

    repeated = client.post(
        route,
        json=_body(
            finding_id=finding_id,
            status=status,
            bulk=bulk,
            rationale="The same disposition remains valid.",
        ),
    )
    assert repeated.status_code == 200
    assert repeated.json()["updated"] == 0
    conn = connect(db_path)
    try:
        count = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} "  # noqa: S608 - closed test enum
            "WHERE finding_id = ? AND change_type = 'status_change'",
            (finding_id,),
        ).fetchone()["n"]
    finally:
        conn.close()
    assert count == 1


@pytest.mark.parametrize("kind", ["image", "a11y"])
def test_nondecisive_status_routes_remain_backward_compatible(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    kind: FindingKind,
) -> None:
    db_path, _, scan_id = seeded_db
    finding_id = _finding_id(db_path, scan_id, kind)
    response = client.post(
        _route(kind, finding_id, bulk=False),
        json={"status": "reviewing"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "reviewing", "updated": 1}

    table = "a11y_finding_history" if kind == "a11y" else "finding_history"
    conn = connect(db_path)
    try:
        note = conn.execute(
            f"SELECT note FROM {table} WHERE finding_id = ? "  # noqa: S608 - closed test enum
            "AND change_type = 'status_change' ORDER BY id DESC LIMIT 1",
            (finding_id,),
        ).fetchone()["note"]
    finally:
        conn.close()
    assert note is None


def test_pre_0019_a11y_status_route_fails_closed_without_partial_update(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "pre-0019.db"
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir()
    conn = connect(db_path)
    try:
        for path in sorted(_MIGRATIONS.glob("*.sql")):
            if path.name.endswith(".rollback.sql"):
                continue
            number = int(path.name.split("_", 1)[0])
            if number >= 19:
                continue
            conn.executescript(path.read_text(encoding="utf-8"))
        scan = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('https://pre-0019.example/', 'completed', '{}')"
        )
        scan_id = int(scan.lastrowid or 0)
        page_id = repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized="https://pre-0019.example/",
            status_code=200,
            title="Migration fixture",
            render_mode="static",
            html_hash="d" * 64,
        )
        finding_id = repo.upsert_axe_violation(
            conn,
            page_id=page_id,
            scan_id=scan_id,
            rule_id="label",
            wcag_sc="1.3.1",
            wcag_scs="1.3.1",
            wcag_level="A",
            impact="serious",
            help="Form elements must have labels",
            help_url="https://dequeuniversity.com/rules/axe/4.10/label",
            target_selector="#legacy",
            failure_summary="Fix the missing label.",
            html_snippet='<input id="legacy">',
            target_hash="pre-0019",
        )
    finally:
        conn.close()

    with TestClient(
        create_app(db_path=db_path, blob_dir=blob_dir), raise_server_exceptions=False
    ) as legacy_client:
        response = legacy_client.post(
            f"/api/a11y-findings/{finding_id}/status",
            json={"status": "reviewing"},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Database migrations are incomplete. Run `make migrate` and retry."
    )
    conn = connect(db_path)
    try:
        status = conn.execute(
            "SELECT status FROM page_a11y_findings WHERE id = ?", (finding_id,)
        ).fetchone()["status"]
    finally:
        conn.close()
    assert status == "new"
