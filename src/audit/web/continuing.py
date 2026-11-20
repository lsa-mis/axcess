"""Continuing a report that was not finished.

A scan ends ``interrupted`` in two ways, and they mean different things:

- **Stopped.** A person pressed Stop. Stopping is not pausing: the queue of
  waiting addresses is emptied and the report stays as it is.
- **Not finished.** Axcess closed (or crashed) mid-scan. The addresses it
  had still to visit stay in the queue, so the same report can carry on.

The queue is what tells them apart (``WORK_WAITING_SQL``). Only a report
that is not finished can be continued, and only when someone asks for it
with **Continue scan** (``POST /api/scans/{id}/continue``). Until
2026-11-20, starting any new scan of the same address quietly continued
the last unfinished report instead of making a new one: "Scan again" from
report #70 gave back report #71, three days old and made by an older
build. A new scan now always makes a new report (the developer's decision,
2026-11-20).

A report cut off by Axcess closing during a sign-in scan cannot be
continued: its signed-in browser died with the process (``resumable:
false`` in its settings, and the protected workflow's own reports).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from typing import Any

from audit.crawler.orchestrator import RESUMABLE_SCAN_SQL, WORK_WAITING_SQL, CrawlConfig

_CONTINUABLE_SQL = f"status = 'interrupted' AND {RESUMABLE_SCAN_SQL} AND {WORK_WAITING_SQL}"


def _has_protected_scans(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'protected_scans'"
    ).fetchone()
    return row is not None


def _query(conn: sqlite3.Connection, extra: str = "") -> str:
    protected = (
        " AND NOT EXISTS (SELECT 1 FROM protected_scans p WHERE p.scan_id = scans.id)"
        if _has_protected_scans(conn)
        else ""
    )
    return f"SELECT id FROM scans WHERE {_CONTINUABLE_SQL}{protected}{extra}"  # noqa: S608


def continuable_ids(conn: sqlite3.Connection) -> set[int]:
    """Every report that is not finished and can be continued."""
    return {int(row[0]) for row in conn.execute(_query(conn))}


def can_continue(conn: sqlite3.Connection, scan_id: int) -> bool:
    """Whether ``scan_id`` is a report that is not finished and can be continued."""
    return conn.execute(_query(conn, " AND id = ?"), (scan_id,)).fetchone() is not None


def stored_user_agent(config_json: str | bytes | None) -> tuple[str | None, str | None]:
    """The browser name a scan sent, and the choice it came from, as stored.

    Continuing keeps the exact string the report started with, including one
    the person typed, which New scan never fills back in (``scan_settings``).
    It stays on the server.
    """
    try:
        stored: Any = json.loads(config_json or "{}")
    except (TypeError, ValueError):
        return None, None
    if not isinstance(stored, dict):
        return None, None
    agent = stored.get("user_agent")
    choice = stored.get("user_agent_choice")
    return (
        agent if isinstance(agent, str) and agent else None,
        choice if isinstance(choice, str) and choice else None,
    )


def with_stored_user_agent(
    config: CrawlConfig, config_json: str | bytes | None, *, server_user_agent: str
) -> CrawlConfig:
    """``config`` sending the same browser name the report started with."""
    agent, choice = stored_user_agent(config_json)
    if agent is None:
        return config
    chosen = agent != server_user_agent
    return replace(
        config,
        user_agent=agent,
        # robots.txt is matched against Axcess's own name whatever is sent,
        # as for a new scan (``_build_crawl_config``).
        robots_user_agent=server_user_agent if chosen else None,
        user_agent_choice=choice if chosen else None,
    )
