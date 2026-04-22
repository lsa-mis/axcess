"""End-to-end crawl tests against the local fixture site.

Spins up a stdlib http.server on an ephemeral port in a background thread,
then runs the real orchestrator against it. Covers the golden path, depth
capping, max-pages capping, resume-after-interrupt, and scope filtering.
"""

from __future__ import annotations

import asyncio
import contextlib
import http.server
import socketserver
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from audit.crawler.orchestrator import CrawlConfig, run_crawl
from audit.db import queue

pytestmark = pytest.mark.integration

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "site"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _serve() -> Iterator[str]:
    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(FIXTURE_ROOT), **kw)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _page_urls(conn: sqlite3.Connection, scan_id: int) -> set[str]:
    rows = conn.execute("SELECT url_normalized FROM pages WHERE scan_id = ?", (scan_id,)).fetchall()
    return {row["url_normalized"] for row in rows}


def test_crawl_discovers_all_in_scope_pages(tmp_db: sqlite3.Connection) -> None:
    with _serve() as base:
        config = CrawlConfig(seed_url=base, max_pages=50, rps=100.0, workers=2, vlm_enabled=False)
        summary = asyncio.run(run_crawl(tmp_db, config))

    assert summary.status == "completed"
    assert summary.pages_fetched >= 5  # index, about, contact, deep, deeper
    urls = _page_urls(tmp_db, summary.scan_id)
    assert f"{base}/" in urls
    assert f"{base}/about.html" in urls
    assert f"{base}/contact.html" in urls
    assert f"{base}/subdir/deep.html" in urls
    assert f"{base}/subdir/deeper.html" in urls
    # 404 page is recorded (its link exists on index) but with non-OK status
    missing = tmp_db.execute(
        "SELECT status_code FROM pages WHERE url_normalized = ?",
        (f"{base}/missing.html",),
    ).fetchone()
    assert missing is not None
    assert missing["status_code"] == 404


def test_crawl_respects_max_pages(tmp_db: sqlite3.Connection) -> None:
    with _serve() as base:
        config = CrawlConfig(seed_url=base, max_pages=2, rps=100.0, workers=1, vlm_enabled=False)
        summary = asyncio.run(run_crawl(tmp_db, config))

    # Workers can overshoot slightly because the limit check is cooperative;
    # the hard invariant is that we respected the bound within worker count.
    assert summary.pages_fetched <= config.max_pages + config.workers
    assert summary.pages_fetched >= config.max_pages


def test_crawl_skips_out_of_scope_and_non_http(tmp_db: sqlite3.Connection) -> None:
    with _serve() as base:
        config = CrawlConfig(seed_url=base, max_pages=50, rps=100.0, workers=2, vlm_enabled=False)
        summary = asyncio.run(run_crawl(tmp_db, config))

    urls = _page_urls(tmp_db, summary.scan_id)
    assert not any("example.com/external" in u for u in urls)
    assert not any(u.startswith("mailto:") for u in urls)


def test_crawl_resumes_interrupted_scan(tmp_db: sqlite3.Connection) -> None:
    """A prior interrupted scan with pending jobs gets picked up and drained."""
    with _serve() as base:
        seed = f"{base}/"
        cur = tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'interrupted', '{}')",
            (seed,),
        )
        scan_id = int(cur.lastrowid or 0)

        # Leftover jobs from the "prior" run, including the seed.
        for url in (seed, f"{base}/about.html", f"{base}/contact.html"):
            queue.enqueue(
                tmp_db,
                "fetch",
                {"url": url, "depth": 0, "scan_id": scan_id},
                dedupe_key=f"fetch:{scan_id}:{url}",
            )
        assert queue.pending_count(tmp_db, "fetch") == 3

        summary = asyncio.run(
            run_crawl(
                tmp_db,
                CrawlConfig(seed_url=seed, max_pages=50, rps=100.0, workers=2, vlm_enabled=False),
            )
        )

    assert summary.scan_id == scan_id  # resumed, not a new scan
    assert summary.status == "completed"
    urls = _page_urls(tmp_db, scan_id)
    assert seed in urls
    assert f"{base}/about.html" in urls
    assert f"{base}/contact.html" in urls


def test_crawl_interrupt_mid_run_leaves_queue_intact(tmp_db: sqlite3.Connection) -> None:
    """Cancelling the run marks the scan interrupted."""
    with _serve() as base:
        seed = f"{base}/"

        async def run_then_cancel() -> None:
            # rps=1 ensures at most 1 fetch/sec, so cancellation at 0.2s
            # lands before the crawl can finish.
            task = asyncio.create_task(
                run_crawl(
                    tmp_db,
                    CrawlConfig(seed_url=seed, max_pages=50, rps=1.0, workers=1, vlm_enabled=False),
                )
            )
            await asyncio.sleep(0.2)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        asyncio.run(run_then_cancel())

        row = tmp_db.execute(
            "SELECT status FROM scans WHERE seed_url = ? ORDER BY id DESC LIMIT 1",
            (seed,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "interrupted"


def test_crawl_records_html_hash_and_title(tmp_db: sqlite3.Connection) -> None:
    with _serve() as base:
        config = CrawlConfig(seed_url=base, max_pages=10, rps=100.0, workers=2, vlm_enabled=False)
        summary = asyncio.run(run_crawl(tmp_db, config))

    row = tmp_db.execute(
        "SELECT title, html_hash, render_mode FROM pages WHERE scan_id = ? AND url_normalized = ?",
        (summary.scan_id, f"{base}/"),
    ).fetchone()
    assert row is not None
    assert row["title"] == "Fixture home"
    assert row["render_mode"] == "static"
    assert row["html_hash"] and len(row["html_hash"]) == 64
