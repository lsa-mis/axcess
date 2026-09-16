"""When a later crawl of the same seed may take over an earlier scan's row.

Resuming is the point of the SQLite-backed queue: a crawl killed mid-flight
leaves its work in ``jobs``, and the next run of the same seed picks it up
rather than starting the site again. A scan the operator *stopped* is a
different thing wearing the same status, and taking that one over silently
folds a finished-with reportinto whatever runs next.

A signed-in scan is a third case. Its browser context lives in one process's
memory, so there is no session for a later crawl to resume with -- only the row
and the queue, which an anonymous crawl would happily continue under its own
identity. Those rows say ``resumable: false`` in their stored config and are
invisible to seed-based discovery, including their own run's, which is why
``CrawlConfig.scan_id`` exists.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from audit.crawler.orchestrator import CrawlConfig, _ensure_scan, config_json_for_scan
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


def _signed_in_scan(conn: sqlite3.Connection, status: str) -> int:
    """A row written by the manual-login path: real work, unrepeatable session."""
    scan_id = _scan(conn, status)
    conn.execute(
        "UPDATE scans SET config_json = ? WHERE id = ?",
        (config_json_for_scan(CrawlConfig(seed_url=SEED, resumable=False)), scan_id),
    )
    return scan_id


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


def test_an_anonymous_crawl_does_not_take_over_a_running_signed_in_scan(
    tmp_db: sqlite3.Connection,
) -> None:
    """The reported bug: two scans' evidence merged into one report.

    An authenticated scan was still crawling when an ordinary scan of the same
    seed started. The ordinary run adopted the signed-in row, appended pages
    fetched with no session to it, and overwrote the stored config -- erasing
    the ``browser_only`` and ``start_url`` values that were the only record the
    scan had ever been authenticated.
    """
    signed_in = _signed_in_scan(tmp_db, "running")
    _queue_work(tmp_db, signed_in)

    adopted = _ensure_scan(tmp_db, SEED, _config())

    assert adopted != signed_in, "an anonymous crawl must not continue a signed-in scan"
    row = tmp_db.execute(
        "SELECT status, config_json FROM scans WHERE id = ?", (signed_in,)
    ).fetchone()
    assert row["status"] == "running", "the signed-in scan keeps its own status"
    assert json.loads(row["config_json"])["resumable"] is False, "and its own config"


def test_an_anonymous_crawl_does_not_resume_an_interrupted_signed_in_scan(
    tmp_db: sqlite3.Connection,
) -> None:
    """Queued work is not an invitation when the session behind it is gone."""
    signed_in = _signed_in_scan(tmp_db, "interrupted")
    _queue_work(tmp_db, signed_in)

    assert _ensure_scan(tmp_db, SEED, _config()) != signed_in


def test_a_signed_in_scan_crawls_the_row_it_was_given(
    tmp_db: sqlite3.Connection,
) -> None:
    """Its own run must still reach it, and discovery can no longer find it."""
    signed_in = _signed_in_scan(tmp_db, "running")
    config = CrawlConfig(seed_url=SEED, resumable=False, scan_id=signed_in)

    assert _ensure_scan(tmp_db, SEED, config) == signed_in
    assert tmp_db.execute("SELECT COUNT(*) c FROM scans").fetchone()["c"] == 1


def test_naming_a_row_that_does_not_exist_is_refused(tmp_db: sqlite3.Connection) -> None:
    """Better to fail the scan than to write findings against no report."""
    config = CrawlConfig(seed_url=SEED, scan_id=4321)

    with pytest.raises(ValueError, match="4321"):
        _ensure_scan(tmp_db, SEED, config)


def test_a_row_predating_the_flag_is_still_resumable(tmp_db: sqlite3.Connection) -> None:
    """Config written before ``resumable`` existed omits the key entirely."""
    legacy = _scan(tmp_db, "interrupted")  # config_json is '{}'
    _queue_work(tmp_db, legacy)

    assert _ensure_scan(tmp_db, SEED, _config()) == legacy


def test_an_unreadable_config_does_not_break_row_discovery(
    tmp_db: sqlite3.Connection,
) -> None:
    """A row nobody can parse must not make every later crawl fail."""
    broken = _scan(tmp_db, "interrupted")
    tmp_db.execute("UPDATE scans SET config_json = 'not json' WHERE id = ?", (broken,))
    _queue_work(tmp_db, broken)

    assert _ensure_scan(tmp_db, SEED, _config()) == broken
