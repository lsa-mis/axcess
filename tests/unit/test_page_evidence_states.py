"""Page evidence must distinguish load-state findings from revealed ones.

A finding that only exists after a control is operated cannot be told apart
from one present at page load when both sit in a flat list. The evidence page
was sending an auditor to look for a dialog that is not in the DOM until
something is clicked, with nothing on the page saying so.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from audit import evaluation
from audit.db import repo
from audit.db.schema import connect

_MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"


def _scan_with_findings(tmp_path: Path) -> tuple[sqlite3.Connection, int, int]:
    conn = connect(tmp_path / "audit.db")
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        if not path.name.endswith(".rollback.sql"):
            conn.executescript(path.read_text(encoding="utf-8"))
    scan_id = int(
        conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('https://app.example.edu/', 'completed', '{}')"
        ).lastrowid
        or 0
    )
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="https://app.example.edu/",
        status_code=200,
        title="Home",
        render_mode="js",
        html_hash="a" * 64,
    )

    def _finding(rule: str, selector: str, revealed_by: str | None) -> None:
        repo.upsert_axe_violation(
            conn,
            page_id=page_id,
            scan_id=scan_id,
            rule_id=rule,
            wcag_sc="4.1.2",
            wcag_scs="4.1.2",
            wcag_level="A",
            impact="serious",
            help=f"{rule} help",
            help_url="https://example.test/rule",
            target_selector=selector,
            failure_summary="summary",
            html_snippet=f"<div>{selector}</div>",
            target_hash=f"{rule}:{selector}",
            revealed_by=revealed_by,
        )

    _finding("region", "#main", None)
    _finding("aria-dialog-name", "#profile-menu", "Account Profile")
    _finding("aria-dialog-name", "#notifications-menu", "Notifications")
    return conn, scan_id, page_id


def test_page_evidence_reports_which_control_revealed_a_finding(tmp_path: Path) -> None:
    conn, scan_id, page_id = _scan_with_findings(tmp_path)
    try:
        evidence = evaluation.get_page_evidence(conn, scan_id=scan_id, page_id=page_id)
        assert evidence is not None
        by_selector = {f["target_selector"]: f for f in evidence["a11y_findings"]}

        # Present when the page loaded: nothing had to be operated.
        assert by_selector["#main"]["revealed_by"] is None
        # Only in the DOM after a control was used, and the page says which.
        assert by_selector["#profile-menu"]["revealed_by"] == "Account Profile"
        assert by_selector["#notifications-menu"]["revealed_by"] == "Notifications"
    finally:
        conn.close()


def test_findings_group_into_load_state_and_one_group_per_control(tmp_path: Path) -> None:
    """The grouping the evidence page renders, asserted on its source data.

    Load-state findings first, then one group per control in the order the
    probe reached them — the order an auditor reproduces them in.
    """
    conn, scan_id, page_id = _scan_with_findings(tmp_path)
    try:
        evidence = evaluation.get_page_evidence(conn, scan_id=scan_id, page_id=page_id)
        assert evidence is not None
        findings = evidence["a11y_findings"]

        at_load = [f for f in findings if not f["revealed_by"]]
        controls: list[str] = []
        for finding in findings:
            control = finding["revealed_by"]
            if control and control not in controls:
                controls.append(control)

        assert len(at_load) == 1
        assert controls == ["Account Profile", "Notifications"]
    finally:
        conn.close()
