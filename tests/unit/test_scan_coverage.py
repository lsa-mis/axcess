"""Coverage facts for a report (audit.db.reports) and migration 0040.

A report says how much of the site it covered with numbers (pages found,
pages visited, the limits chosen, how it ended), not with a "partial" label.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from audit.db.reports import record_pages_found, scan_coverage

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0040_pages_found"


def _scan(conn: sqlite3.Connection, status: str, config: dict[str, object]) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES ('https://x.test/', ?, ?)",
        (status, json.dumps(config)),
    )
    return int(cur.lastrowid or 0)


def _jobs(conn: sqlite3.Connection, scan_id: int, states: list[str]) -> None:
    for i, state in enumerate(states):
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state, dedupe_key) VALUES ('fetch', ?, ?, ?)",
            (
                json.dumps({"scan_id": scan_id, "url": f"https://x.test/{i}"}),
                state,
                f"{scan_id}:{i}",
            ),
        )


def _row(conn: sqlite3.Connection, scan_id: int) -> dict[str, object]:
    return dict(conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone())


def test_stopped_scan_keeps_pages_found_after_stop_empties_the_queue(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _scan(tmp_db, "interrupted", {"max_pages": None, "max_depth": 10})
    _jobs(tmp_db, scan_id, ["completed"] * 100 + ["pending"] * 40)
    record_pages_found(tmp_db, scan_id)  # Stop records first ...
    tmp_db.execute("DELETE FROM jobs WHERE state = 'pending'")  # ... then empties the queue
    record_pages_found(tmp_db, scan_id)  # the crawl's own finish must not lower it
    coverage = scan_coverage(tmp_db, _row(tmp_db, scan_id), page_count=100)
    assert coverage.model_dump() == {
        "ended": "stopped",
        "pages_found": 140,
        "pages_visited": 100,
        "page_limit": None,
        "depth_limit": 10,
    }


def test_completed_scan_at_its_page_limit_says_so(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db, "completed", {"max_pages": 10, "max_depth": 3})
    _jobs(tmp_db, scan_id, ["completed"] * 10 + ["pending"] * 25)
    record_pages_found(tmp_db, scan_id)
    coverage = scan_coverage(tmp_db, _row(tmp_db, scan_id), page_count=10)
    assert (coverage.ended, coverage.pages_found, coverage.page_limit) == ("page_limit", 35, 10)


def test_completed_scan_under_its_limit_visited_every_page_found(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _scan(tmp_db, "completed", {"max_pages": 5000})
    coverage = scan_coverage(tmp_db, _row(tmp_db, scan_id), page_count=42)
    assert coverage.ended == "all_found"
    # Not recorded, never guessed.
    assert coverage.pages_found is None


def test_running_scan_counts_pages_found_live(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db, "running", {"max_pages": 5000})
    _jobs(tmp_db, scan_id, ["completed", "leased", "pending"])
    coverage = scan_coverage(tmp_db, _row(tmp_db, scan_id), page_count=1)
    assert (coverage.ended, coverage.pages_found) == ("running", 3)


def test_failed_scan_and_found_never_below_visited(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db, "failed", {})
    tmp_db.execute("UPDATE scans SET pages_found = 2 WHERE id = ?", (scan_id,))
    coverage = scan_coverage(tmp_db, _row(tmp_db, scan_id), page_count=7)
    assert (coverage.ended, coverage.pages_found, coverage.page_limit) == ("failed", 7, None)


def test_migration_backfills_whole_queues_and_rolls_back(tmp_db: sqlite3.Connection) -> None:
    completed = _scan(tmp_db, "completed", {})
    stopped = _scan(tmp_db, "interrupted", {})  # Stop emptied its queue
    crashed = _scan(tmp_db, "interrupted", {})  # a crash left its queue
    tmp_db.execute("UPDATE scans SET page_count = 2")
    _jobs(tmp_db, completed, ["completed"] * 3)
    _jobs(tmp_db, stopped, ["completed"] * 2)
    _jobs(tmp_db, crashed, ["completed", "completed", "pending"])

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    assert "pages_found" not in {r[1] for r in tmp_db.execute("PRAGMA table_info(scans)")}
    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())

    found = dict(tmp_db.execute("SELECT id, pages_found FROM scans").fetchall())
    assert found == {completed: 3, stopped: None, crashed: 3}
