"""Public reports grouped by site, for the Reports list.

A site is a normalized seed scope, the same key that decides which earlier
report a scan is compared with, so the list and "compare to previous" never
disagree about whether two reports cover the same site.

Each group names two scans that can differ: the most recent scan of any
status, and the most recent *completed* one. The headline numbers come only
from the completed one; an interrupted or failed crawl has partial evidence
and must not stand in for the site. Issue counts use the canonical issue
projection, so they match the total the Issues page shows for that report.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from audit.web import issues
from audit.web.comparison import site_scope


class ScanSummaryModel(BaseModel):
    """The ``ScanSummary`` shape ``GET /api/scans`` returns per row."""

    id: int
    seed_url: str
    status: str
    page_count: int
    dom_state_count: int
    finding_count: int
    started_at: str | None
    finished_at: str | None


class SiteGroup(BaseModel):
    """Every public report of one site, newest first."""

    site_url: str
    scan_count: int
    completed_count: int
    most_recent: ScanSummaryModel
    most_recent_completed: ScanSummaryModel | None
    # Unified issue groups in ``most_recent_completed``; null when there is none.
    most_recent_completed_issue_count: int | None
    scans: list[ScanSummaryModel]


def group_scans(conn: sqlite3.Connection, summaries: Iterable[dict[str, Any]]) -> list[SiteGroup]:
    """Group scan summaries by site, most recently scanned site first.

    "Most recent" is by report id, which increases with creation and never
    ties, so a scan without a start time still has a defined place.
    """
    by_site: dict[str, list[dict[str, Any]]] = {}
    for summary in sorted(summaries, key=lambda s: int(s["id"]), reverse=True):
        by_site.setdefault(site_scope(str(summary["seed_url"])), []).append(summary)

    groups: list[SiteGroup] = []
    for site_url, scans in by_site.items():
        completed = [scan for scan in scans if scan["status"] == "completed"]
        latest_completed = completed[0] if completed else None
        groups.append(
            SiteGroup(
                site_url=site_url,
                scan_count=len(scans),
                completed_count=len(completed),
                most_recent=ScanSummaryModel(**scans[0]),
                most_recent_completed=(
                    ScanSummaryModel(**latest_completed) if latest_completed else None
                ),
                most_recent_completed_issue_count=(
                    _issue_count(conn, int(latest_completed["id"])) if latest_completed else None
                ),
                scans=[ScanSummaryModel(**scan) for scan in scans],
            )
        )
    return groups


# Issue counts of completed reports, by database file and report id, with the
# evidence they were counted from. Reports polls every few seconds while a scan runs, and
# building the full issue list for every site on every poll grew with the
# number of sites times their evidence. A completed report's count changes
# only if its evidence does (``audit synthesize`` rewrites image findings),
# so the cheap fingerprint below decides when to count again.
_issue_counts: dict[tuple[str, int], tuple[tuple[int, ...], int]] = {}
_issue_counts_lock = threading.Lock()


def _evidence_fingerprint(conn: sqlite3.Connection, scan_id: int) -> tuple[int, ...]:
    """How many evidence rows the report has, and its newest row ids."""
    row = conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM page_a11y_findings WHERE scan_id = ?), "
        "(SELECT COALESCE(MAX(id), 0) FROM page_a11y_findings WHERE scan_id = ?), "
        "(SELECT COUNT(*) FROM findings WHERE scan_id = ?), "
        "(SELECT COALESCE(MAX(id), 0) FROM findings WHERE scan_id = ?)",
        (scan_id, scan_id, scan_id, scan_id),
    ).fetchone()
    return tuple(int(value) for value in row)


def _issue_count(conn: sqlite3.Connection, scan_id: int) -> int:
    """Issues in a completed report, as the Issues page counts them."""
    # The file as well as the id: report ids start at 1 in every database.
    key = (str(conn.execute("PRAGMA database_list").fetchone()[2]), scan_id)
    fingerprint = _evidence_fingerprint(conn, scan_id)
    with _issue_counts_lock:
        cached = _issue_counts.get(key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    count = len(issues.list_issues(conn, scan_id))
    with _issue_counts_lock:
        _issue_counts[key] = (fingerprint, count)
    return count
