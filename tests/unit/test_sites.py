"""Reports grouped by site: the scan each headline number comes from."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from support.rich_scan import seed_rich_scan

from audit.web import sites
from audit.web.sites import group_scans


def _summary(scan_id: int, seed_url: str, status: str, pages: int = 1) -> dict[str, Any]:
    return {
        "id": scan_id,
        "seed_url": seed_url,
        "status": status,
        "page_count": pages,
        "dom_state_count": 0,
        "finding_count": 0,
        "started_at": None,
        "finished_at": None,
    }


def test_groups_by_normalized_scope_most_recent_site_first(tmp_db: sqlite3.Connection) -> None:
    groups = group_scans(
        tmp_db,
        [
            _summary(1, "https://a.example/", "completed"),
            _summary(2, "https://b.example/docs", "completed"),
            # Same scope as #2: the seed form adds the directory slash.
            _summary(3, "https://b.example/docs/", "completed"),
            _summary(4, "https://a.example/", "interrupted"),
        ],
    )
    assert [g.site_url for g in groups] == ["https://a.example/", "https://b.example/docs/"]
    assert [s.id for s in groups[0].scans] == [4, 1]
    assert [s.id for s in groups[1].scans] == [3, 2]
    assert (groups[0].scan_count, groups[0].completed_count) == (2, 1)


def test_headline_scan_is_most_recent_completed_not_most_recent(
    tmp_db: sqlite3.Connection,
) -> None:
    [group] = group_scans(
        tmp_db,
        [
            _summary(1, "https://a.example/", "completed", pages=40),
            _summary(2, "https://a.example/", "interrupted", pages=3),
            _summary(3, "https://a.example/", "running", pages=1),
        ],
    )
    assert group.most_recent.id == 3
    assert group.most_recent_completed is not None
    assert group.most_recent_completed.id == 1
    assert group.most_recent_completed.page_count == 40
    # No findings were stored for the seeded scan, so zero issue groups.
    assert group.most_recent_completed_issue_count == 0


def test_site_without_a_completed_scan_has_no_headline(tmp_db: sqlite3.Connection) -> None:
    [group] = group_scans(
        tmp_db,
        [
            _summary(1, "https://a.example/", "failed"),
            _summary(2, "https://a.example/", "interrupted"),
        ],
    )
    assert group.completed_count == 0
    assert group.most_recent_completed is None
    assert group.most_recent_completed_issue_count is None


def test_empty_input(tmp_db: sqlite3.Connection) -> None:
    assert group_scans(tmp_db, []) == []


def test_a_malformed_seed_is_a_site_of_its_own(tmp_db: sqlite3.Connection) -> None:
    """One unparseable older seed must not take the whole list down."""
    groups = group_scans(
        tmp_db,
        [
            _summary(1, "https://a.example/", "completed"),
            _summary(2, "http://[broken/", "completed"),
        ],
    )
    assert [g.site_url for g in groups] == ["http://[broken/", "https://a.example/"]


def test_a_completed_reports_issue_count_is_reused_until_its_evidence_changes(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real = sites.issues.list_issues

    def counting(conn: sqlite3.Connection, scan_id: int) -> list[Any]:
        calls.append(scan_id)
        return real(conn, scan_id)

    monkeypatch.setattr(sites.issues, "list_issues", counting)
    monkeypatch.setattr(sites, "_issue_counts", {})
    scan_id = seed_rich_scan(tmp_db)
    summaries = [_summary(scan_id, "https://a.example/", "completed")]

    [first] = group_scans(tmp_db, summaries)
    [again] = group_scans(tmp_db, summaries)
    assert calls == [scan_id]
    assert again.most_recent_completed_issue_count == first.most_recent_completed_issue_count

    # Changed evidence (``audit synthesize`` can rewrite a completed report's
    # image findings) is counted again.
    tmp_db.execute(
        "DELETE FROM findings WHERE id = (SELECT MAX(id) FROM findings WHERE scan_id = ?)",
        (scan_id,),
    )
    group_scans(tmp_db, summaries)
    assert calls == [scan_id, scan_id]
