"""How much of the site one scan covered, as facts rather than a label.

How a scan ended does not decide whether it is a report: a scan stopped
after 100 pages covers more of a site than one that completed at a 10-page
limit, and calling the first "partial" and the second "full" told the reader
the opposite of the truth. Coverage is said with numbers instead
(``ScanCoverage``): the pages found, the pages visited, the page limit
chosen, and how the scan ended.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel

#: Every address the crawl added to its list for one scan. Jobs are kept
#: after they run, so this counts pages visited, skipped and still waiting.
_FOUND_SQL = (
    "SELECT COUNT(*) FROM jobs WHERE kind = 'fetch' AND json_extract(payload_json, '$.scan_id') = ?"
)

EndReason = Literal["running", "all_found", "page_limit", "stopped", "failed"]


def count_pages_found(conn: sqlite3.Connection, scan_id: int) -> int:
    """Pages found so far: every address queued for ``scan_id``."""
    return int(conn.execute(_FOUND_SQL, (scan_id,)).fetchone()[0])


def record_pages_found(conn: sqlite3.Connection, scan_id: int) -> None:
    """Store the pages found, never lowering a count already stored.

    Stop empties the queue of waiting addresses, so it records the count
    first; the crawl's own finish runs after that and must not overwrite it
    with the smaller number left. A database from before migration 0040 has
    no column to store it in; the scan still ends, without the count.
    """
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute(
            "UPDATE scans SET pages_found = MAX(COALESCE(pages_found, 0), ("  # noqa: S608
            + _FOUND_SQL
            + ")) WHERE id = ?",
            (scan_id, scan_id),
        )


class ScanCoverage(BaseModel):
    """How much of the site one scan covered, as facts rather than a label."""

    #: How the scan ended, or ``running``.
    ended: EndReason
    #: Pages the scan found (queued to visit). None for a scan stopped
    #: before this was recorded. Never less than ``pages_visited``.
    pages_found: int | None
    pages_visited: int
    #: The page limit chosen for the scan; None means no limit.
    page_limit: int | None
    #: The link depth limit chosen for the scan, when recorded.
    depth_limit: int | None


def _config(scan: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(scan.get("config_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def scan_coverage(
    conn: sqlite3.Connection, scan: Mapping[str, Any], *, page_count: int
) -> ScanCoverage:
    """Coverage facts for one ``scans`` row.

    ``page_count`` is the caller's count of saved pages (the live count for a
    scan that has not completed; see ``api_scan_detail``).
    """
    config = _config(scan)
    page_limit = _int_or_none(config.get("max_pages"))
    status = str(scan["status"])
    if status == "running":
        found: int | None = count_pages_found(conn, int(scan["id"]))
    else:
        stored = scan.get("pages_found")
        found = int(stored) if stored is not None else None
    if found is not None:
        found = max(found, page_count)
    ended: EndReason
    if status == "running":
        ended = "running"
    elif status == "failed":
        ended = "failed"
    elif status == "interrupted":
        ended = "stopped"
    elif page_limit is not None and page_count >= page_limit:
        ended = "page_limit"
    else:
        ended = "all_found"
    return ScanCoverage(
        ended=ended,
        pages_found=found,
        pages_visited=page_count,
        page_limit=page_limit,
        depth_limit=_int_or_none(config.get("max_depth")),
    )
