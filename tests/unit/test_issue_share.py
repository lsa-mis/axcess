"""Unit tests for the Coverage page's "What Axcess found" figures (`audit.web.issue_share`).

They pin what is counted (status filter, records, layers), scan isolation, the
completed-scan guard, the estimate's sample gate, and the manual-review match.
"""

from __future__ import annotations

import sqlite3
from collections import Counter

import pytest

from audit.db import repo
from audit.protected.crypto import DeterministicLocalKms, ProtectedVault
from audit.protected.models import (
    ProtectedScanCreate,
    ProtectedScopeFingerprints,
    ProtectedWorkSpec,
)
from audit.protected.repository import create_protected_scan
from audit.web import issue_share as share


def _scan(conn: sqlite3.Connection, status: str = "completed", url: str = "http://a.test/") -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, ?, '{}')", (url, status)
    )
    return int(cur.lastrowid or 0)


def _page(conn: sqlite3.Connection, scan_id: int, path: str = "/") -> int:
    return repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized=f"http://a.test{path}",
        status_code=200,
        title="Page",
        render_mode="js",
        html_hash=f"{scan_id}{path}".ljust(64, "0")[:64],
    )


def _finding(
    conn: sqlite3.Connection,
    scan_id: int,
    page_id: int,
    *,
    rule: str = "color-contrast",
    sc: str = "1.4.3",
    level: str = "AA",
    pipeline: str = "axe",
    status: str = "new",
    revealed_by: str | None = None,
    n: int = 0,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level, impact, help,
             target_selector, html_snippet, target_hash, status, pipeline, revealed_by)
        VALUES (?, ?, ?, ?, ?, ?, 'serious', 'help', ?, ?, ?, ?, ?, ?)
        """,
        (
            page_id,
            scan_id,
            rule,
            sc,
            sc,
            level,
            f"#el-{rule}-{n}",
            f"<p id=el-{n}>{rule}</p>",
            f"hash-{rule}-{n}",
            status,
            pipeline,
            revealed_by,
        ),
    )
    return int(cur.lastrowid or 0)


def _mark_protected(conn: sqlite3.Connection, scan_id: int) -> None:
    """Record ``scan_id`` as a sign-in (protected) scan, as the protected workflow does."""
    create_protected_scan(
        conn,
        scan_id=scan_id,
        protected_scan=ProtectedScanCreate(
            target_owner="Owner",
            environment="staging",
            data_classification="sensitive",
            authorized_by="auditor",
            authorization_acknowledged=True,
            least_privilege_account_acknowledged=True,
            approved_target_origins=("https://private.test",),
        ),
        work_spec=ProtectedWorkSpec(
            seed_url="https://private.test/",
            approved_target_origins=("https://private.test",),
            index_hmac_key="d" * 64,
            config={"max_pages": 1},
        ),
        scope_fingerprints=ProtectedScopeFingerprints(target="a" * 64, auth="b" * 64, cdn="c" * 64),
        seed_locator="a" * 64,
        vault=ProtectedVault(DeterministicLocalKms(b"issue-share-test")),
    )


def _layer(result: share.IssueShareResponse, layer: str) -> int:
    return next(row.count for row in result.layers.layers if row.layer == layer)


def test_empty_database_has_no_figures(tmp_db: sqlite3.Connection) -> None:
    result = share.issue_share(tmp_db)
    assert result.scans == []
    assert result.scans_included == 0
    assert result.layers.total == 0
    assert all(row.share is None for row in result.layers.layers)
    assert result.axe_rules == []
    assert result.estimate.available is False
    assert result.estimate.share is None
    assert result.manual_review.failed == 0
    assert result.manual_review.share is None


def test_single_scan_counts_each_layer_and_click_through(tmp_db: sqlite3.Connection) -> None:
    scan = _scan(tmp_db)
    page = _page(tmp_db, scan)
    _finding(tmp_db, scan, page, n=1)
    _finding(tmp_db, scan, page, n=2, revealed_by="menu button")
    _finding(tmp_db, scan, page, rule="image-alt", sc="1.1.1", level="A", n=3)
    _finding(tmp_db, scan, page, rule="1.4.10", sc="1.4.10", pipeline="responsive", n=4)

    result = share.issue_share(tmp_db)

    assert result.layers.total == 4
    assert _layer(result, "axe_loaded") == 2
    assert _layer(result, "axe_click_through") == 1
    assert _layer(result, "probes") == 1
    contrast = next(rule for rule in result.axe_rules if rule.rule_id == "color-contrast")
    assert (contrast.loaded, contrast.click_through) == (1, 1)
    assert contrast.category == "color"
    found = {row.sc: row.count for row in result.found_by_criterion}
    assert found == {"1.1.1": 1, "1.4.3": 2, "1.4.10": 1}


def test_not_a_problem_is_left_out_but_fixed_is_kept(tmp_db: sqlite3.Connection) -> None:
    scan = _scan(tmp_db)
    page = _page(tmp_db, scan)
    _finding(tmp_db, scan, page, n=1, status="false_positive")
    _finding(tmp_db, scan, page, n=2, status="remediated")
    _finding(tmp_db, scan, page, n=3, status="accepted_risk")

    result = share.issue_share(tmp_db)

    assert result.layers.total == 2
    assert result.layers.excluded_not_a_problem == 1


def test_one_report_reads_only_that_report(tmp_db: sqlite3.Connection) -> None:
    first = _scan(tmp_db, url="http://a.test/")
    second = _scan(tmp_db, url="http://b.test/")
    _finding(tmp_db, first, _page(tmp_db, first), n=1)
    page = _page(tmp_db, second)
    for n in range(3):
        _finding(tmp_db, second, page, rule="image-alt", sc="1.1.1", level="A", n=n)

    only_first = share.issue_share(tmp_db, first)
    assert only_first.scans_included == 1
    assert only_first.layers.total == 1
    assert {row.sc for row in only_first.found_by_criterion} == {"1.4.3"}

    both = share.issue_share(tmp_db)
    assert both.scans_included == 2
    assert both.layers.total == 4


def test_running_failed_and_missing_reports_are_not_counted(tmp_db: sqlite3.Connection) -> None:
    done = _scan(tmp_db)
    running = _scan(tmp_db, status="running")
    failed = _scan(tmp_db, status="failed")
    _finding(tmp_db, done, _page(tmp_db, done), n=1)
    _finding(tmp_db, running, _page(tmp_db, running), n=2)
    _finding(tmp_db, failed, _page(tmp_db, failed), n=3)

    result = share.issue_share(tmp_db)
    assert [option.id for option in result.scans] == [done]
    assert result.layers.total == 1

    with pytest.raises(share.IssueShareError) as not_done:
        share.issue_share(tmp_db, running)
    assert not_done.value.status_code == 409
    with pytest.raises(share.IssueShareError) as missing:
        share.issue_share(tmp_db, 999)
    assert missing.value.status_code == 404


def test_sign_in_scans_are_left_out(tmp_db: sqlite3.Connection) -> None:
    public = _scan(tmp_db)
    alias = "protected://report/issue-share-test-0001"
    protected = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'completed', ?)",
            (alias, '{"protected_work_spec":"encrypted","seed_url":"' + alias + '"}'),
        ).lastrowid
        or 0
    )
    _finding(tmp_db, public, _page(tmp_db, public), n=1)
    _finding(tmp_db, protected, _page(tmp_db, protected), n=2)
    _mark_protected(tmp_db, protected)

    result = share.issue_share(tmp_db)
    assert [option.id for option in result.scans] == [public]
    with pytest.raises(share.IssueShareError):
        share.issue_share(tmp_db, protected)


def test_no_evaluation_records_gives_no_manual_review_figure(tmp_db: sqlite3.Connection) -> None:
    scan = _scan(tmp_db)
    _finding(tmp_db, scan, _page(tmp_db, scan), n=1)
    review = share.issue_share(tmp_db).manual_review
    assert (review.evaluations, review.failed, review.found, review.share) == (0, 0, 0, None)


def test_failed_criteria_match_occurrences_in_the_same_report(tmp_db: sqlite3.Connection) -> None:
    reviewed = _scan(tmp_db)
    other = _scan(tmp_db, url="http://b.test/")
    _finding(tmp_db, reviewed, _page(tmp_db, reviewed), n=1)
    # 2.4.7 is found only in the other report, so it must not count as a match.
    _finding(tmp_db, other, _page(tmp_db, other), rule="focus", sc="2.4.7", n=2)
    cur = tmp_db.execute("INSERT INTO evaluation_reports (scan_id) VALUES (?)", (reviewed,))
    report_id = int(cur.lastrowid or 0)
    for sc, outcome in (("1.4.3", "fail"), ("2.4.7", "fail"), ("1.1.1", "pass")):
        tmp_db.execute(
            "INSERT INTO manual_check_results (evaluation_report_id, criterion_sc, outcome) "
            "VALUES (?, ?, ?)",
            (report_id, sc, outcome),
        )

    review = share.issue_share(tmp_db).manual_review
    assert (review.evaluations, review.failed, review.found) == (1, 2, 1)
    assert review.share == pytest.approx(0.5)
    assert review.scans[0].scan_id == reviewed
    assert review.scans[0].seed_url == "http://a.test/"


def test_estimate_waits_for_a_big_enough_sample() -> None:
    small = share.estimate_share(Counter({"1.4.3": 10}), Counter({"1.4.3": 10}))
    assert small.available is False
    assert small.share is None
    assert small.axe_sample == 10

    big = share.estimate_share(
        Counter({"1.4.3": 83, "4.1.2": 54}), Counter({"1.4.3": 90, "4.1.2": 60, "2.4.7": 5})
    )
    assert big.available is True
    assert big.share is not None
    assert 0 < big.share <= 1
    # Each row counts Axcess's occurrences only up to its own estimate.
    contrast = next(row for row in big.criteria if row.sc == "1.4.3")
    assert contrast.estimated_total == pytest.approx(100, rel=0.01)
    assert contrast.found == 90


def test_criteria_of_reads_every_number() -> None:
    assert share.criteria_of("1.3.1, 4.1.2") == ["1.3.1", "4.1.2"]
    assert share.criteria_of(None) == []
