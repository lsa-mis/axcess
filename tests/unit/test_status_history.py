"""Defensible status decisions for image and page-scoped findings."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from audit.db import repo
from audit.db.schema import connect

_MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"


def _seed_findings(conn: sqlite3.Connection) -> tuple[int, int, int]:
    scan = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://status.example/', 'completed', '{}')"
    )
    scan_id = int(scan.lastrowid or 0)
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="https://status.example/",
        status_code=200,
        title="Status fixture",
        render_mode="static",
        html_hash="a" * 64,
    )
    image_id = repo.upsert_image(
        conn,
        content_hash="b" * 64,
        src_url="https://status.example/image.png",
        mime="image/png",
        bytes_len=12,
        width=10,
        height=10,
        blob_path=None,
        has_svg_text=False,
        scan_id=scan_id,
    )
    image_finding_id = repo.upsert_finding(
        conn,
        image_id=image_id,
        scan_id=scan_id,
        severity="major",
        priority_score=9.0,
        remediation_hint="Replace the image text.",
    )
    a11y_finding_id = repo.upsert_axe_violation(
        conn,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="label",
        wcag_sc="1.3.1",
        wcag_scs="1.3.1,3.3.2",
        wcag_level="A",
        impact="serious",
        help="Form elements must have labels",
        help_url="https://dequeuniversity.com/rules/axe/4.10/label",
        target_selector="#email",
        failure_summary="Fix the missing label.",
        html_snippet='<input id="email">',
        target_hash="c" * 64,
    )
    return scan_id, image_finding_id, a11y_finding_id


def test_image_status_history_is_atomic_bounded_and_redacted(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id, finding_id, _ = _seed_findings(tmp_db)

    with pytest.raises(ValueError, match="rationale is required"):
        repo.bulk_set_findings_status(
            tmp_db,
            finding_ids=[finding_id],
            status="remediated",
        )
    assert (
        tmp_db.execute("SELECT status FROM findings WHERE id = ?", (finding_id,)).fetchone()[
            "status"
        ]
        == "new"
    )
    assert (
        tmp_db.execute(
            "SELECT COUNT(*) AS n FROM finding_history WHERE finding_id = ?", (finding_id,)
        ).fetchone()["n"]
        == 0
    )

    rationale = (
        "Authorization: Bearer never-persist-this-token\n"
        "Confirmed by reviewer@example.edu after keyboard verification."
    )
    assert (
        repo.bulk_set_findings_status(
            tmp_db,
            finding_ids=[finding_id],
            status="remediated",
            actor="user",
            rationale=rationale,
        )
        == 1
    )
    row = tmp_db.execute(
        "SELECT scan_id, change_type, from_status, to_status, actor, "
        "CAST(changed_at AS TEXT) AS changed_at, note "
        "FROM finding_history WHERE finding_id = ?",
        (finding_id,),
    ).fetchone()
    assert dict(row) == {
        "scan_id": scan_id,
        "change_type": "status_change",
        "from_status": "new",
        "to_status": "remediated",
        "actor": "user",
        "changed_at": row["changed_at"],
        "note": "Authorization: <redacted>\n"
        "Confirmed by <redacted-email> after keyboard verification.",
    }
    assert row["changed_at"] is not None
    assert "never-persist" not in row["note"]
    assert "reviewer@example.edu" not in row["note"]

    # A no-op is not a second decision and must not manufacture history.
    assert (
        repo.bulk_set_findings_status(
            tmp_db,
            finding_ids=[finding_id],
            status="remediated",
            rationale="Still verified.",
        )
        == 0
    )
    assert (
        tmp_db.execute(
            "SELECT COUNT(*) AS n FROM finding_history WHERE finding_id = ?", (finding_id,)
        ).fetchone()["n"]
        == 1
    )


def test_a11y_status_history_supports_workflow_notes_and_decisions(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id, _, finding_id = _seed_findings(tmp_db)

    # Workflow transitions stay compatible with callers that do not send a rationale.
    assert (
        repo.bulk_set_a11y_findings_status(
            tmp_db,
            finding_ids=[finding_id],
            status="reviewing",
        )
        == 1
    )
    first = tmp_db.execute(
        "SELECT scan_id, from_status, to_status, actor, note, "
        "CAST(changed_at AS TEXT) AS changed_at "
        "FROM a11y_finding_history WHERE finding_id = ? ORDER BY id",
        (finding_id,),
    ).fetchone()
    assert first["scan_id"] == scan_id
    assert first["from_status"] == "new"
    assert first["to_status"] == "reviewing"
    assert first["actor"] == "user"
    assert first["note"] is None
    assert first["changed_at"] is not None

    with pytest.raises(ValueError, match="at most 2000"):
        repo.bulk_set_a11y_findings_status(
            tmp_db,
            finding_ids=[finding_id],
            status="false_positive",
            rationale="x" * 2001,
        )
    assert (
        tmp_db.execute(
            "SELECT status FROM page_a11y_findings WHERE id = ?", (finding_id,)
        ).fetchone()["status"]
        == "reviewing"
    )

    assert (
        repo.bulk_set_a11y_findings_status(
            tmp_db,
            finding_ids=[finding_id],
            status="false_positive",
            rationale="Cookie: session=never-persist-this\nConfirmed against rendered DOM.",
        )
        == 1
    )
    second = tmp_db.execute(
        "SELECT from_status, to_status, actor, note FROM a11y_finding_history "
        "WHERE finding_id = ? ORDER BY id DESC LIMIT 1",
        (finding_id,),
    ).fetchone()
    assert dict(second) == {
        "from_status": "reviewing",
        "to_status": "false_positive",
        "actor": "user",
        "note": "Cookie: <redacted>\nConfirmed against rendered DOM.",
    }


def test_a11y_history_migration_forward_and_rollback(tmp_path: Path) -> None:
    db_path = tmp_path / "pre-0019.db"
    conn = connect(db_path)
    try:
        for path in sorted(_MIGRATIONS.glob("*.sql")):
            if path.name.endswith(".rollback.sql"):
                continue
            number = int(path.name.split("_", 1)[0])
            if number >= 19:
                continue
            conn.executescript(path.read_text(encoding="utf-8"))

        assert (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'a11y_finding_history'"
            ).fetchone()
            is None
        )
        _, _, finding_id = _seed_findings(conn)

        conn.executescript(
            (_MIGRATIONS / "0019_a11y_finding_history.sql").read_text(encoding="utf-8")
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(a11y_finding_history)")}
        assert {
            "finding_id",
            "scan_id",
            "change_type",
            "from_status",
            "to_status",
            "actor",
            "changed_at",
            "note",
        } <= columns
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(a11y_finding_history)")}
        assert indexes == {
            "idx_a11y_finding_history_finding",
            "idx_a11y_finding_history_scan",
        }
        assert (
            repo.bulk_set_a11y_findings_status(
                conn,
                finding_ids=[finding_id],
                status="accepted_risk",
                rationale="Target owner documented the approved exception.",
            )
            == 1
        )

        conn.executescript(
            (_MIGRATIONS / "0019_a11y_finding_history.rollback.sql").read_text(encoding="utf-8")
        )
        assert (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'a11y_finding_history'"
            ).fetchone()
            is None
        )
        # Rollback removes the audit table, not the finding's current disposition.
        status = conn.execute(
            "SELECT status FROM page_a11y_findings WHERE id = ?", (finding_id,)
        ).fetchone()["status"]
        assert status == "accepted_risk"
    finally:
        conn.close()
