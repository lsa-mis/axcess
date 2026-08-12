"""MCP must fail closed for reports with authenticated-site evidence."""

from __future__ import annotations

import sqlite3

import pytest

from audit.mcp_server import (
    compare_reports,
    get_coverage_and_limitations,
    get_finding_evidence,
    get_report_issue_detail,
    get_report_summary,
    list_report_issues,
)
from audit.protected.crypto import DeterministicLocalKms, ProtectedVault
from audit.protected.models import (
    ProtectedScanCreate,
    ProtectedScopeFingerprints,
    ProtectedWorkSpec,
)
from audit.protected.repository import create_protected_scan


def _completed_scan(conn: sqlite3.Connection, *, url: str) -> int:
    alias = "protected://report/" + ("a" * 64)
    cursor = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'completed', ?)",
        (alias, '{"protected_work_spec":"encrypted","seed_url":"' + alias + '"}'),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _protected_completed_scan(conn: sqlite3.Connection) -> int:
    scan_id = _completed_scan(conn, url="https://protected.example.test/")
    create_protected_scan(
        conn,
        scan_id=scan_id,
        protected_scan=ProtectedScanCreate(
            target_owner="U-M protected application owner",
            environment="staging",
            data_classification="sensitive",
            authorized_by="wolverineid:accessibility-auditor",
            authorization_acknowledged=True,
            least_privilege_account_acknowledged=True,
            approved_target_origins=("https://protected.example.test",),
        ),
        work_spec=ProtectedWorkSpec(
            seed_url="https://protected.example.test/",
            approved_target_origins=("https://protected.example.test",),
            index_hmac_key="d" * 64,
            config={},
        ),
        scope_fingerprints=ProtectedScopeFingerprints(
            target="a" * 64,
            auth="b" * 64,
            cdn="c" * 64,
        ),
        seed_locator="b" * 64,
        vault=ProtectedVault(DeterministicLocalKms(b"protected-mcp-test-kms")),
    )
    return scan_id


def test_every_read_only_mcp_tool_rejects_protected_reports(tmp_db: sqlite3.Connection) -> None:
    """No read-only tool may turn a future chat provider into data egress."""
    protected_scan_id = _protected_completed_scan(tmp_db)
    public_scan_id = _completed_scan(tmp_db, url="https://public.example.test/")

    with pytest.raises(ValueError, match="Protected reports"):
        get_report_summary(tmp_db, scan_id=protected_scan_id)
    with pytest.raises(ValueError, match="Protected reports"):
        list_report_issues(tmp_db, scan_id=protected_scan_id)
    with pytest.raises(ValueError, match="Protected reports"):
        get_report_issue_detail(tmp_db, scan_id=protected_scan_id, issue_key="img:example")
    with pytest.raises(ValueError, match="Protected reports"):
        get_finding_evidence(tmp_db, scan_id=protected_scan_id, finding_id=1)
    with pytest.raises(ValueError, match="Protected reports"):
        get_coverage_and_limitations(tmp_db, scan_id=protected_scan_id)
    with pytest.raises(ValueError, match="Protected reports"):
        compare_reports(
            tmp_db,
            current_scan_id=protected_scan_id,
            compare_to_scan_id=public_scan_id,
        )
