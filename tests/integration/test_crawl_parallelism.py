"""Workers fetch pages at the same time, as many as "Pages at once" says.

A threaded fixture server delays each response and counts the plain HTTP
fetches in flight (a browser load, which the per-host limit has never
covered, carries Sec-Fetch-Mode and is not counted). With the per-host limit
at its old default of 2, every worker past two waited for a fetch slot: 32
workers scanned a delayed site barely faster than 8. The limit now follows
the worker count, which this pins.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from audit.crawler.orchestrator import CrawlConfig, run_crawl

pytestmark = pytest.mark.integration

PAGES = 24
DELAY_S = 0.15


@contextmanager
def _delayed_site() -> Iterator[tuple[str, dict[str, int]]]:
    lock = threading.Lock()
    counts = {"now": 0, "peak": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            if self.path == "/robots.txt":
                self.send_response(404)
                self.end_headers()
                return
            plain = self.headers.get("Sec-Fetch-Mode") is None
            with lock:
                if plain:
                    counts["now"] += 1
                    counts["peak"] = max(counts["peak"], counts["now"])
            try:
                time.sleep(DELAY_S)
                if self.path == "/":
                    links = "".join(f'<a href="/p{i}.html">Page {i}</a>' for i in range(PAGES))
                    body = f"<!doctype html><title>Index</title><main>{links}</main>"
                else:
                    body = f"<!doctype html><title>{self.path}</title><main>Page</main>"
                data = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                with lock:
                    if plain:
                        counts["now"] -= 1

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/", counts
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _crawl(tmp_db: sqlite3.Connection, base: str, workers: int, per_host: int) -> float:
    config = CrawlConfig(
        seed_url=base,
        js_eager=False,
        max_pages=PAGES + 1,
        rps=1000.0,
        workers=workers,
        concurrency_per_host=per_host,
        image_extraction_enabled=False,
        vlm_enabled=False,
        semantic_enabled=False,
    )
    start = time.perf_counter()
    summary = asyncio.run(run_crawl(tmp_db, config))
    assert summary.status == "completed"
    assert summary.pages_fetched == PAGES + 1
    return time.perf_counter() - start


def test_workers_fetch_pages_at_the_same_time(tmp_db: sqlite3.Connection) -> None:
    with _delayed_site() as (base, counts):
        _crawl(tmp_db, base, workers=8, per_host=8)
    # More than the old limit of two ran at once; the index page is fetched
    # alone first, so the peak is at most the worker count.
    assert 2 < counts["peak"] <= 8


def test_the_old_per_host_default_held_workers_to_two_at_a_time(
    tmp_db: sqlite3.Connection,
) -> None:
    with _delayed_site() as (base, counts):
        _crawl(tmp_db, base, workers=8, per_host=2)
    assert counts["peak"] <= 2
