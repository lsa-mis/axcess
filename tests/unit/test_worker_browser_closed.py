"""A crawl whose browser goes away stops, and its waiting pages keep their tries.

Scan 71 (2026-11-17): the app restarted mid-scan and its browser closed. The
eight workers kept taking pages, each failed at once on the dead browser, and
within 40 seconds every waiting page had used its three tries and was marked
failed for good. Continuing the scan later could not bring them back.
"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, cast

import pytest

from audit.crawler import orchestrator
from audit.crawler.orchestrator import CrawlConfig, CrawlSummary, _LazyJs, _worker, _WorkerContext
from audit.db import queue

SCAN_ID = 7
SEED = "https://site.example.test/"


class _FakeFetcher:
    def __init__(self, *, browser_closed: bool) -> None:
        self.browser_closed = browser_closed


def _context(conn: sqlite3.Connection, *, browser_closed: bool) -> _WorkerContext:
    none = cast(Any, None)
    return _WorkerContext(
        conn=conn,
        config=CrawlConfig(seed_url=SEED),
        scope=none,
        scan_id=SCAN_ID,
        limiter=none,
        robots=none,
        static=none,
        js=_LazyJs(
            user_agent="test",
            injected=cast(Any, _FakeFetcher(browser_closed=browser_closed)),
        ),
        downloader=none,
        blob_store=none,
        ocr=None,
        vlm=None,
        alfa=None,
        in_flight=0,
        summary=CrawlSummary(scan_id=SCAN_ID, seed_url=SEED),
    )


def _enqueue(conn: sqlite3.Connection, count: int) -> None:
    for n in range(count):
        url = f"{SEED}page-{n}/"
        queue.enqueue(
            conn,
            orchestrator.JOB_KIND,
            {"scan_id": SCAN_ID, "url": url, "depth": 1},
            dedupe_key=f"{orchestrator.JOB_KIND}:{SCAN_ID}:{url}",
        )


async def test_a_closed_browser_stops_the_crawl_and_keeps_every_try(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def broken(ctx: _WorkerContext, job: queue.Job) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("Browser.new_context: the handler is closed")

    monkeypatch.setattr(orchestrator, "_process_job", broken)
    _enqueue(tmp_db, 29)
    ctx = _context(tmp_db, browser_closed=True)

    await asyncio.gather(*(_worker(ctx) for _ in range(8)))

    assert ctx.browser_closed
    assert calls <= 8, "each worker stops after its first failure at most"
    rows = tmp_db.execute("SELECT state, attempts FROM jobs").fetchall()
    assert len(rows) == 29
    assert {r["state"] for r in rows} == {"pending"}, "every page is still waiting"
    assert {r["attempts"] for r in rows} == {0}, "no page used a try"
    assert ctx.summary.errors == 0, "a closed browser is not a page error"


async def test_a_page_that_fails_with_the_browser_running_still_uses_its_tries(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(ctx: _WorkerContext, job: queue.Job) -> None:
        raise RuntimeError("the page broke")

    monkeypatch.setattr(orchestrator, "_process_job", broken)
    _enqueue(tmp_db, 1)
    ctx = _context(tmp_db, browser_closed=False)

    await _worker(ctx)

    assert not ctx.browser_closed
    row = tmp_db.execute("SELECT state, attempts FROM jobs").fetchone()
    assert row["state"] == "failed"
    assert row["attempts"] == 3
    assert ctx.summary.errors == 3
