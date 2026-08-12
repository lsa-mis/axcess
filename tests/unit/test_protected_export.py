"""Protected-export boundary tests that do not need a FastAPI app."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from audit import cli, evaluation
from audit.config import Settings
from audit.protected.crypto import DeterministicLocalKms, ProtectedVault
from audit.protected.export import render_redacted_protected_report
from audit.protected.models import (
    ProtectedScanCreate,
    ProtectedScanRecord,
    ProtectedScopeFingerprints,
    ProtectedWorkSpec,
)
from audit.protected.repository import create_protected_scan, get_protected_scan


def _completed_protected_scan(
    conn: sqlite3.Connection,
) -> tuple[int, ProtectedScanRecord]:
    """Create a completed protected report without adding crawl evidence."""

    seed_url = "https://app.example.test/secure/"
    alias = "protected://report/protected-export-manual-checks-0001"
    scan = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'completed', ?)",
        (alias, '{"protected_work_spec":"encrypted","seed_url":"' + alias + '"}'),
    )
    scan_id = int(scan.lastrowid or 0)
    create_protected_scan(
        conn,
        scan_id=scan_id,
        protected_scan=ProtectedScanCreate(
            target_owner="U-M Application Team",
            environment="staging",
            data_classification="sensitive",
            authorized_by="wolverineid:auditor",
            authorization_acknowledged=True,
            least_privilege_account_acknowledged=True,
            approved_target_origins=("https://app.example.test",),
        ),
        work_spec=ProtectedWorkSpec(
            seed_url=seed_url,
            approved_target_origins=("https://app.example.test",),
            index_hmac_key="d" * 64,
            config={"max_pages": 10},
        ),
        scope_fingerprints=ProtectedScopeFingerprints(
            target="a" * 64,
            auth="b" * 64,
            cdn="c" * 64,
        ),
        seed_locator="a" * 64,
        vault=ProtectedVault(DeterministicLocalKms(b"protected-export-manual-test")),
    )
    conn.execute(
        "UPDATE protected_scans SET protection_status = 'completed' WHERE scan_id = ?",
        (scan_id,),
    )
    record = get_protected_scan(conn, scan_id=scan_id)
    assert record is not None
    return scan_id, record


def test_cli_export_refuses_protected_scan_before_creating_an_output_file(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The ordinary filesystem export command is never a protected-data bypass."""

    seed_url = "https://app.example.test/secure/"
    alias = "protected://report/protected-export-test-alias-0001"
    scan = tmp_db.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'completed', ?)",
        (alias, '{"protected_work_spec":"encrypted","seed_url":"' + alias + '"}'),
    )
    scan_id = int(scan.lastrowid or 0)
    create_protected_scan(
        tmp_db,
        scan_id=scan_id,
        protected_scan=ProtectedScanCreate(
            target_owner="U-M Application Team",
            environment="staging",
            data_classification="sensitive",
            authorized_by="wolverineid:auditor",
            authorization_acknowledged=True,
            least_privilege_account_acknowledged=True,
            approved_target_origins=("https://app.example.test",),
        ),
        work_spec=ProtectedWorkSpec(
            seed_url=seed_url,
            approved_target_origins=("https://app.example.test",),
            index_hmac_key="d" * 64,
            config={"max_pages": 10},
        ),
        scope_fingerprints=ProtectedScopeFingerprints(
            target="a" * 64,
            auth="b" * 64,
            cdn="c" * 64,
        ),
        seed_locator="a" * 64,
        vault=ProtectedVault(DeterministicLocalKms(b"protected-cli-export-test")),
    )
    db_path = Path(str(tmp_db.execute("PRAGMA database_list").fetchone()[2]))
    data_dir = tmp_path / "data"
    settings = Settings(
        data_dir=data_dir,
        db_path=db_path,
        blob_dir=data_dir / "blobs",
        log_dir=data_dir / "logs",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    output = tmp_path / "ordinary-export-must-not-exist.csv"

    result = CliRunner().invoke(
        cli.app,
        ["export", str(scan_id), "--output", str(output)],
    )

    assert result.exit_code == 1
    assert "Protected scans cannot be exported from the CLI" in result.output
    assert not output.exists()


def test_redacted_export_includes_outcome_only_manual_checks_without_review_detail(
    tmp_db: sqlite3.Connection,
) -> None:
    """Protected handoff includes 3.3.8 but cannot leak review prose or evidence."""

    scan_id, record = _completed_protected_scan(tmp_db)
    evaluation.update_manual_check_outcome_only(
        tmp_db,
        scan_id=scan_id,
        criterion_sc="3.3.8",
        outcome="needs_follow_up",
    )
    # Deliberately contaminate the public manual-review tables. The protected
    # renderer must not query or reproduce these values.
    sensitive_rationale = "Sensitive sign-in review rationale"
    sensitive_note = "Sensitive MFA evidence note"
    sensitive_url = "https://app.example.test/account?token=manual-export-secret"
    tmp_db.execute(
        """
        UPDATE manual_check_results
           SET rationale = ?
         WHERE evaluation_report_id = (
                   SELECT id FROM evaluation_reports WHERE scan_id = ?
               )
           AND criterion_sc = '3.3.8'
        """,
        (sensitive_rationale, scan_id),
    )
    evaluation.add_manual_evidence(
        tmp_db,
        scan_id=scan_id,
        criterion_sc="3.3.8",
        note=sensitive_note,
        page_id=None,
        evidence_url=sensitive_url,
    )

    statements: list[str] = []
    tmp_db.set_trace_callback(statements.append)
    try:
        rendered = render_redacted_protected_report(
            tmp_db,
            scan_id=scan_id,
            record=record,
        )
    finally:
        tmp_db.set_trace_callback(None)

    assert "## Manually documented WCAG check outcomes" in rendered
    assert "manually documented" in rendered
    assert "not automated test results" in rendered
    assert "| 3.3.8 | Accessible Authentication (Minimum) | AA | Needs follow-up |" in rendered
    assert "| 1.1.1 | Non-text Content | A | Not started |" in rendered
    for prohibited in (sensitive_rationale, sensitive_note, sensitive_url, "manual-export-secret"):
        assert prohibited not in rendered
    observed_sql = "\n".join(statements).lower()
    assert "manual_check_evidence" not in observed_sql
    assert "rationale" not in observed_sql
