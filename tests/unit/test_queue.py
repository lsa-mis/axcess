"""Unit tests for db.queue: enqueue/lease/complete/fail/reclaim."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from audit.db import queue


def _count_by_state(conn: sqlite3.Connection, state: str) -> int:
    cur = conn.execute("SELECT COUNT(*) AS n FROM jobs WHERE state = ?", (state,))
    row = cur.fetchone()
    return int(row["n"])


def test_enqueue_returns_id(tmp_db: sqlite3.Connection) -> None:
    job_id = queue.enqueue(tmp_db, "fetch", {"url": "https://example.com/"})
    assert isinstance(job_id, int) and job_id > 0
    assert queue.pending_count(tmp_db) == 1


def test_enqueue_dedupe_blocks_duplicate(tmp_db: sqlite3.Connection) -> None:
    first = queue.enqueue(tmp_db, "fetch", {"url": "a"}, dedupe_key="a")
    second = queue.enqueue(tmp_db, "fetch", {"url": "a"}, dedupe_key="a")
    assert first is not None
    assert second is None
    assert queue.pending_count(tmp_db) == 1


def test_enqueue_without_dedupe_allows_duplicates(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"url": "a"})
    queue.enqueue(tmp_db, "fetch", {"url": "a"})
    assert queue.pending_count(tmp_db) == 2


def test_lease_claims_pending_in_fifo_order(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"url": "a"})
    queue.enqueue(tmp_db, "fetch", {"url": "b"})
    first = queue.lease(tmp_db, "fetch", lease_secs=30)
    second = queue.lease(tmp_db, "fetch", lease_secs=30)
    assert first is not None and first.payload == {"url": "a"}
    assert second is not None and second.payload == {"url": "b"}
    assert first.attempts == 1
    assert queue.pending_count(tmp_db) == 0


def test_lease_returns_none_when_empty(tmp_db: sqlite3.Connection) -> None:
    assert queue.lease(tmp_db, "fetch", lease_secs=30) is None


def test_lease_filters_by_kind(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"u": "x"})
    queue.enqueue(tmp_db, "analyze", {"u": "y"})
    job = queue.lease(tmp_db, "analyze", lease_secs=30)
    assert job is not None and job.kind == "analyze"
    assert queue.pending_count(tmp_db, "fetch") == 1


def test_lease_and_pending_count_can_be_scoped_to_scan(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"url": "old", "scan_id": 12})
    queue.enqueue(tmp_db, "fetch", {"url": "current", "scan_id": 13})

    assert queue.pending_count(tmp_db, "fetch", scan_id=12) == 1
    assert queue.pending_count(tmp_db, "fetch", scan_id=13) == 1

    job = queue.lease(tmp_db, "fetch", lease_secs=30, scan_id=13)

    assert job is not None
    assert job.payload == {"url": "current", "scan_id": 13}
    assert queue.pending_count(tmp_db, "fetch", scan_id=13) == 0
    assert queue.pending_count(tmp_db, "fetch", scan_id=12) == 1


def test_complete_marks_done(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"u": "x"})
    job = queue.lease(tmp_db, "fetch", lease_secs=30)
    assert job is not None
    queue.complete(tmp_db, job.id)
    assert _count_by_state(tmp_db, "completed") == 1
    assert _count_by_state(tmp_db, "leased") == 0


def test_fail_returns_to_pending_under_max_attempts(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"u": "x"})
    job = queue.lease(tmp_db, "fetch", lease_secs=30)
    assert job is not None
    queue.fail(tmp_db, job.id, "boom", max_attempts=3)
    assert _count_by_state(tmp_db, "pending") == 1
    assert _count_by_state(tmp_db, "failed") == 0


def test_fail_marks_failed_when_attempts_exhausted(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"u": "x"})
    for _ in range(3):
        job = queue.lease(tmp_db, "fetch", lease_secs=30)
        assert job is not None
        queue.fail(tmp_db, job.id, "boom", max_attempts=3)
    assert _count_by_state(tmp_db, "failed") == 1
    assert _count_by_state(tmp_db, "pending") == 0


def test_reclaim_expired_reverts_stuck_leases(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"u": "x"})
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    claimed = queue.lease(tmp_db, "fetch", lease_secs=60, now=t0)
    assert claimed is not None
    later = t0 + timedelta(seconds=90)
    reclaimed = queue.reclaim_expired(tmp_db, now=later)
    assert reclaimed == 1
    assert _count_by_state(tmp_db, "pending") == 1


def test_reclaim_expired_ignores_live_leases(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"u": "x"})
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    queue.lease(tmp_db, "fetch", lease_secs=300, now=t0)
    later = t0 + timedelta(seconds=60)
    assert queue.reclaim_expired(tmp_db, now=later) == 0
    assert _count_by_state(tmp_db, "leased") == 1


def test_reclaim_allows_release(tmp_db: sqlite3.Connection) -> None:
    queue.enqueue(tmp_db, "fetch", {"u": "x"})
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    first = queue.lease(tmp_db, "fetch", lease_secs=10, now=t0)
    assert first is not None
    later = t0 + timedelta(seconds=30)
    assert queue.reclaim_expired(tmp_db, now=later) == 1
    retry = queue.lease(tmp_db, "fetch", lease_secs=10, now=later)
    assert retry is not None and retry.id == first.id
    assert retry.attempts == 2


def test_release_returns_a_leased_job_without_using_a_try(tmp_db: sqlite3.Connection) -> None:
    """A job that could not run through no fault of its page keeps its tries."""
    queue.enqueue(tmp_db, "fetch", {"u": "x"})
    for _ in range(5):
        job = queue.lease(tmp_db, "fetch", lease_secs=30)
        assert job is not None
        queue.release(tmp_db, job.id)
    row = tmp_db.execute("SELECT state, attempts FROM jobs").fetchone()
    assert row["state"] == "pending"
    assert row["attempts"] == 0


def test_release_leaves_a_job_that_is_not_leased_alone(tmp_db: sqlite3.Connection) -> None:
    job_id = queue.enqueue(tmp_db, "fetch", {"u": "x"})
    assert job_id is not None
    tmp_db.execute("UPDATE jobs SET state = 'completed', attempts = 1")
    queue.release(tmp_db, job_id)
    row = tmp_db.execute("SELECT state, attempts FROM jobs").fetchone()
    assert row["state"] == "completed"
    assert row["attempts"] == 1


def test_retry_failed_requeues_one_scans_failed_jobs_with_fresh_tries(
    tmp_db: sqlite3.Connection,
) -> None:
    for scan_id, url in ((1, "a"), (1, "b"), (2, "c")):
        queue.enqueue(tmp_db, "fetch", {"scan_id": scan_id, "url": url}, dedupe_key=url)
    queue.enqueue(tmp_db, "analyze", {"scan_id": 1, "url": "d"}, dedupe_key="d")
    tmp_db.execute("UPDATE jobs SET state = 'failed', attempts = 3")
    tmp_db.execute("UPDATE jobs SET state = 'completed' WHERE dedupe_key = 'b'")

    assert queue.retry_failed(tmp_db, "fetch", scan_id=1) == 1

    rows = {
        r["dedupe_key"]: (r["state"], r["attempts"])
        for r in tmp_db.execute("SELECT dedupe_key, state, attempts FROM jobs")
    }
    assert rows["a"] == ("pending", 0)
    assert rows["b"] == ("completed", 3), "finished work stays finished"
    assert rows["c"] == ("failed", 3), "another scan's jobs are untouched"
    assert rows["d"] == ("failed", 3), "another kind of job is untouched"
