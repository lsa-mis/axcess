"""Reports grouped by site: the scan each headline number comes from."""

from __future__ import annotations

import sqlite3
from typing import Any

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
