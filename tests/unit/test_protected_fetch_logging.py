"""What a failed fetch inside a protected crawl is allowed to say.

The protected branch cannot log what its public sibling logs: a protected
target's URL and a driver's error string can both carry session detail. It had
been made silent instead, which meant a login scan that could not reach its
first page produced one line naming no cause, and the operator was told to
check a log that did not know either.

The exception's class name is the compromise these tests pin: enough to tell a
DNS failure from a timeout, a closed context, or the rendered-size cap, while
carrying nothing from the session.
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import structlog

from audit.crawler.fetcher import FetchError
from audit.crawler.js_fetcher import RenderedPageTooLargeError
from audit.crawler.orchestrator import CrawlConfig, _process_job, _WorkerContext
from audit.crawler.url_policy import build_scope
from audit.db import queue

SECRET_URL = "https://app.example.test/course/dashboard?session=abc123"


def _scan(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://app.example.test/', 'running', '{}')"
    )
    return int(cur.lastrowid or 0)


class _Robots:
    async def allowed(self, _url: str) -> bool:
        return True


class _Limiter:
    @asynccontextmanager
    async def throttle(self, _url: str) -> Any:
        yield


class _Js:
    """Stands in for the authenticated browser fetcher."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def get(self) -> Any:
        return self

    async def fetch(self, _url: str) -> Any:
        raise self._error


def _context(conn: sqlite3.Connection, scan_id: int, error: Exception) -> _WorkerContext:
    return _WorkerContext(
        conn=conn,
        config=CrawlConfig(seed_url="https://app.example.test/", browser_only=True),
        scope=build_scope("https://app.example.test/", whole_host=True),
        scan_id=scan_id,
        limiter=_Limiter(),  # type: ignore[arg-type]
        robots=_Robots(),  # type: ignore[arg-type]
        static=SimpleNamespace(),  # type: ignore[arg-type]
        js=_Js(error),  # type: ignore[arg-type]
        downloader=SimpleNamespace(),  # type: ignore[arg-type]
        blob_store=SimpleNamespace(),  # type: ignore[arg-type]
        ocr=None,
        vlm=None,
        alfa=None,
        in_flight=0,
        summary=SimpleNamespace(errors=0, pages_skipped_scope=0, pages_skipped_robots=0),  # type: ignore[arg-type]
    )


def _run(conn: sqlite3.Connection, error: Exception) -> list[dict[str, Any]]:
    scan_id = _scan(conn)
    ctx = _context(conn, scan_id, error)
    job = queue.Job(id=1, kind="fetch", payload={"url": SECRET_URL, "depth": 0}, attempts=0)
    with structlog.testing.capture_logs() as logs:
        asyncio.run(_process_job(ctx, job))
    return [entry for entry in logs if entry["event"] == "crawl.js_fetch_failed"]


def test_a_protected_fetch_failure_names_its_cause(tmp_db: sqlite3.Connection) -> None:
    """Without this the operator cannot tell one failure from another."""
    entries = _run(tmp_db, RenderedPageTooLargeError("page is 4000000 characters"))

    assert len(entries) == 1
    assert entries[0]["protected_context"] is True
    assert entries[0]["error_type"] == "RenderedPageTooLargeError"


def test_a_protected_fetch_failure_leaks_neither_url_nor_message(
    tmp_db: sqlite3.Connection,
) -> None:
    """The reason the branch is quieter than its public sibling."""
    entries = _run(tmp_db, FetchError(f"net::ERR_NAME_NOT_RESOLVED at {SECRET_URL}"))

    assert entries[0]["error_type"] == "FetchError"
    rendered = repr(entries[0])
    assert SECRET_URL not in rendered
    assert "session=abc123" not in rendered
    assert "ERR_NAME_NOT_RESOLVED" not in rendered
