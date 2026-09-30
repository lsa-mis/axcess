"""The queries behind the hot paths must reach their indexes.

These assert query *plans*, not results, and they exist because the failure
they guard is silent. An index on an expression is matched against the text
of the predicate, so re-spelling ``json_extract(payload_json, '$.scan_id')``
anywhere in the queue or the progress endpoints puts the queue back on a
full index scan with every test still green. The same goes for reordering
the columns of a covering index: nothing breaks, the work just comes back.

If one of these fails, the fix is either to restore the predicate's spelling
or to update migration 0029 to match the new one.
"""

from __future__ import annotations

import sqlite3

from audit.db import queue


def _plan(conn: sqlite3.Connection, sql: str, args: tuple[object, ...] = ()) -> str:
    """The query plan for ``sql``, as one lowercase string."""
    rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", args).fetchall()
    return " | ".join(str(row[-1]) for row in rows).lower()


def test_queue_lease_uses_the_scan_index(tmp_db: sqlite3.Connection) -> None:
    """Leasing the next page must not scan the pending frontier."""
    plan = _plan(
        tmp_db,
        """
        SELECT id FROM jobs
         WHERE state = 'pending' AND kind = 'fetch'
           AND json_extract(payload_json, '$.scan_id') = ?
         ORDER BY id LIMIT 1
        """,
        (1,),
    )
    assert "idx_jobs_scan" in plan
    assert "scan jobs" not in plan


def test_queue_pending_count_uses_the_scan_index(tmp_db: sqlite3.Connection) -> None:
    """The between-lease frontier count runs once per idle worker tick."""
    queue.enqueue(tmp_db, "fetch", {"url": "https://example.com/", "scan_id": 1})
    assert queue.pending_count(tmp_db, kind="fetch", scan_id=1) == 1
    plan = _plan(
        tmp_db,
        "SELECT COUNT(*) FROM jobs WHERE state = 'pending' AND kind = ? "
        "AND json_extract(payload_json, '$.scan_id') = ?",
        ("fetch", 1),
    )
    assert "idx_jobs_scan" in plan


def test_screenshot_hash_lookup_is_indexed(tmp_db: sqlite3.Connection) -> None:
    """serve_blob resolves a hash to its finding once per evidence thumbnail."""
    plan = _plan(
        tmp_db,
        "SELECT scan_id FROM page_a11y_findings WHERE screenshot_hash = ? LIMIT 1",
        ("deadbeef",),
    )
    assert "idx_a11y_screenshot" in plan
    assert "scan page_a11y_findings" not in plan


def test_findings_grouped_by_rule_is_covered(tmp_db: sqlite3.Connection) -> None:
    """The Issues projection groups a whole scan's findings by rule."""
    plan = _plan(
        tmp_db,
        "SELECT rule_id, COUNT(*) FROM page_a11y_findings WHERE scan_id = ? GROUP BY rule_id",
        (1,),
    )
    assert "idx_a11y_rule_lookup" in plan


def test_pages_for_one_rule_is_covered(tmp_db: sqlite3.Connection) -> None:
    """The per-issue detail lists the pages carrying one rule's findings."""
    plan = _plan(
        tmp_db,
        "SELECT page_id, COUNT(*) FROM page_a11y_findings "
        "WHERE scan_id = ? AND pipeline = ? AND rule_id = ? GROUP BY page_id",
        (1, "axe", "color-contrast"),
    )
    assert "idx_a11y_rule_lookup" in plan
    # The index carries page_id, so the grouping needs no temporary B-tree.
    assert "temp b-tree" not in plan
