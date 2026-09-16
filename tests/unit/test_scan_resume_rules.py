"""When a later crawl of the same seed may take over an earlier scan's row.

Resuming is the point of the SQLite-backed queue: a crawl killed mid-flight
leaves its work in ``jobs``, and the next run of the same seed picks it up
rather than starting the site again. A scan the operator *stopped* is a
different thing wearing the same status, and taking that one over silently
folds a finished-with reportinto whatever runs next.
"""

from __future__ import annotations

import json
import sqlite3

from audit.crawler.orchestrator import CrawlConfig, _ensure_scan
from audit.db import queue

SEED = "https://app.example.test/"


def _scan(conn: sqlite3.Connection, status: str, seed: str = SEED) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES (?, ?, 249, 0, '{}')",
        (seed, status),
    )
    return int(cur.lastrowid or 0)


def _queue_work(conn: sqlite3.Connection, scan_id: int, *, url: str = SEED) -> None:
    queue.enqueue(
        conn,
        "fetch",
        {"scan_id": scan_id, "url": url, "depth": 0},
        dedupe_key=f"{scan_id}:{url}",
    )


def _config() -> CrawlConfig:
    return CrawlConfig(seed_url=SEED)


def test_a_crawl_killed_mid_flight_is_resumed(tmp_db: sqlite3.Connection) -> None:
    """The behaviour that must survive: work left in the queue is picked up."""
    scan_id = _scan(tmp_db, "interrupted")
    _queue_work(tmp_db, scan_id)

    assert _ensure_scan(tmp_db, SEED, _config()) == scan_id
    status = tmp_db.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone()
    assert status["status"] == "running"


def test_a_stopped_scan_is_not_taken_over_by_the_next_crawl(
    tmp_db: sqlite3.Connection,
) -> None:
    """Stopping empties the queue, so there is nothing left to resume.

    Reproduces the report where a stopped scan said "No report was produced",
    and pressing Retry silently flipped that same scan to completed instead of
    starting a new one: its 249 pages and their findings were absorbed into a
    run the operator thought was fresh.
    """
    stopped = _scan(tmp_db, "interrupted")  # what a stop leaves behind
    # No queued work: the stop cleared it.

    resumed = _ensure_scan(tmp_db, SEED, _config())

    assert resumed != stopped, "a stopped scan must not be resumed"
    remaining = tmp_db.execute("SELECT status FROM scans WHERE id = ?", (stopped,)).fetchone()
    assert remaining["status"] == "interrupted", "the stopped scan keeps its own record"


def test_a_scan_with_only_finished_jobs_is_not_resumed(
    tmp_db: sqlite3.Connection,
) -> None:
    """Done work is not outstanding work."""
    scan_id = _scan(tmp_db, "interrupted")
    _queue_work(tmp_db, scan_id)
    tmp_db.execute("UPDATE jobs SET state = 'completed'")

    assert _ensure_scan(tmp_db, SEED, _config()) != scan_id


def test_another_seed_never_shares_a_scan(tmp_db: sqlite3.Connection) -> None:
    other = _scan(tmp_db, "interrupted", seed="https://other.example.test/")
    _queue_work(tmp_db, other, url="https://other.example.test/")

    assert _ensure_scan(tmp_db, SEED, _config()) != other


def test_resuming_keeps_the_queued_work_addressed_to_that_scan(
    tmp_db: sqlite3.Connection,
) -> None:
    """The job payload names the scan, so a resume must not orphan it."""
    scan_id = _scan(tmp_db, "interrupted")
    _queue_work(tmp_db, scan_id)

    _ensure_scan(tmp_db, SEED, _config())

    row = tmp_db.execute("SELECT payload_json FROM jobs WHERE state = 'pending'").fetchone()
    assert json.loads(row["payload_json"])["scan_id"] == scan_id


def test_a_freshly_prepared_row_is_adopted_before_any_work_is_queued(
    tmp_db: sqlite3.Connection,
) -> None:
    """The web layer creates the scan row first, so the progress view has
    something to poll; the crawler then adopts it. That row has no jobs yet, so
    a rule keyed purely on outstanding work split one scan into two: the row
    the UI was watching, and the one actually being crawled.
    """
    prepared = _scan(tmp_db, "running")

    assert _ensure_scan(tmp_db, SEED, _config()) == prepared
    assert tmp_db.execute("SELECT COUNT(*) c FROM scans").fetchone()["c"] == 1


def test_a_crawl_whose_process_died_is_still_adopted(
    tmp_db: sqlite3.Connection,
) -> None:
    """A hard kill never gets to write a status, so the row stays 'running'."""
    crashed = _scan(tmp_db, "running")
    _queue_work(tmp_db, crashed)

    assert _ensure_scan(tmp_db, SEED, _config()) == crashed
