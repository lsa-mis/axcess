"""A running scan's stage: a scan at its page limit is preparing its report.

The crawler stops taking pages at the limit and leaves the other pages it
found waiting in the queue (report 78: 5 visited, 71 still waiting), so
"nothing waiting" alone never marked such a scan as preparing its report,
and its progress bar could not reach 100%.
"""

from __future__ import annotations

import sqlite3

from audit.db import queue
from audit.web.server import _scan_progress


def _scan_with_jobs(conn: sqlite3.Connection, *, completed: int, pending: int) -> int:
    scan_id = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', '{}')",
        ("https://site.test/",),
    ).lastrowid
    assert scan_id is not None
    for n in range(completed + pending):
        queue.enqueue(conn, "fetch", {"url": f"https://site.test/{n}", "scan_id": scan_id})
    conn.execute(
        "UPDATE jobs SET state = 'completed' WHERE id IN "
        "(SELECT id FROM jobs WHERE json_extract(payload_json, '$.scan_id') = ? "
        "ORDER BY id LIMIT ?)",
        (scan_id, completed),
    )
    return int(scan_id)


def test_a_scan_at_its_page_limit_is_preparing_its_report(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan_with_jobs(tmp_db, completed=5, pending=71)

    progress = _scan_progress(tmp_db, scan_id, page_limit=5, pages_saved=5)

    assert progress["stage"] == "preparing_report"
    assert progress["eta"]["state"] == "finalizing"


def test_a_scan_below_its_page_limit_is_still_scanning(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan_with_jobs(tmp_db, completed=3, pending=71)

    assert _scan_progress(tmp_db, scan_id, page_limit=5, pages_saved=3)["stage"] == "scanning"
    # Without a limit, waiting pages keep it scanning, as before.
    assert _scan_progress(tmp_db, scan_id, pages_saved=5)["stage"] == "scanning"
