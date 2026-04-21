"""SQLite-backed job queue with lease/claim semantics.

Used by the crawler orchestrator (and later the analysis pipeline) to persist
pending work so a crash or Ctrl-C can resume where it left off. All operations
are synchronous; callers that need async can ``run_in_executor``.

State machine::

    pending -> leased -> completed
                       `-> failed
    leased  -> pending  (reclaim_expired)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class Job:
    """Leased unit of work returned by :func:`lease`."""

    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def enqueue(
    conn: sqlite3.Connection,
    kind: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
) -> int | None:
    """Insert a pending job. Returns row id, or ``None`` if ``dedupe_key`` collides."""
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO jobs (kind, payload_json, state, dedupe_key)
        VALUES (?, ?, 'pending', ?)
        """,
        (kind, payload_json, dedupe_key),
    )
    if cur.rowcount == 0:
        return None
    return int(cur.lastrowid) if cur.lastrowid is not None else None


def lease(
    conn: sqlite3.Connection,
    kind: str,
    lease_secs: float,
    *,
    now: datetime | None = None,
) -> Job | None:
    """Atomically claim one pending job of ``kind``. Returns ``None`` when queue is empty.

    The claim is expressed as a single ``UPDATE ... WHERE id = (SELECT ...) RETURNING``
    so concurrent callers cannot double-lease the same row.
    """
    current = _now(now)
    lease_until = current + timedelta(seconds=lease_secs)
    cur = conn.execute(
        """
        UPDATE jobs
           SET state       = 'leased',
               lease_until = ?,
               attempts    = attempts + 1,
               updated_at  = ?
         WHERE id = (
               SELECT id FROM jobs
                WHERE state = 'pending' AND kind = ?
                ORDER BY id
                LIMIT 1
         )
         RETURNING id, kind, payload_json, attempts
        """,
        (_iso(lease_until), _iso(current), kind),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return Job(
        id=int(row["id"]),
        kind=str(row["kind"]),
        payload=json.loads(row["payload_json"]),
        attempts=int(row["attempts"]),
    )


def complete(conn: sqlite3.Connection, job_id: int, *, now: datetime | None = None) -> None:
    """Mark a leased job completed."""
    conn.execute(
        """
        UPDATE jobs
           SET state = 'completed', updated_at = ?, lease_until = NULL, last_error = NULL
         WHERE id = ?
        """,
        (_iso(_now(now)), job_id),
    )


def fail(
    conn: sqlite3.Connection,
    job_id: int,
    error: str,
    *,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> None:
    """Record a failure. Returns the job to ``pending`` if retries remain, else ``failed``."""
    ts = _iso(_now(now))
    conn.execute(
        """
        UPDATE jobs
           SET state = CASE
                         WHEN attempts >= ? THEN 'failed'
                         ELSE 'pending'
                       END,
               last_error = ?,
               lease_until = NULL,
               updated_at = ?
         WHERE id = ?
        """,
        (max_attempts, error, ts, job_id),
    )


def reclaim_expired(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    """Move leased jobs whose lease has expired back to pending. Returns count reclaimed."""
    ts = _iso(_now(now))
    cur = conn.execute(
        """
        UPDATE jobs
           SET state = 'pending', lease_until = NULL, updated_at = ?
         WHERE state = 'leased' AND lease_until IS NOT NULL AND lease_until < ?
        """,
        (ts, ts),
    )
    return int(cur.rowcount)


def pending_count(conn: sqlite3.Connection, kind: str | None = None) -> int:
    """Count jobs currently in ``pending`` state."""
    if kind is None:
        cur = conn.execute("SELECT COUNT(*) AS n FROM jobs WHERE state = 'pending'")
    else:
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE state = 'pending' AND kind = ?",
            (kind,),
        )
    row = cur.fetchone()
    return int(row["n"]) if row is not None else 0
