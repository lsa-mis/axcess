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
                    len(issues.list_issues(conn, int(latest_completed["id"])))
                    if latest_completed
                    else None
                ),
                scans=[ScanSummaryModel(**scan) for scan in scans],
            )
        )
    return groups
