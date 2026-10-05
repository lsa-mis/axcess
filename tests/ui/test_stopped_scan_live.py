"""Stopping a real scan shows its partial report at once, with no reload.

Reproduced in a real browser: Stop on a normal scan showed "No report was
produced" with 3 pages saved, then "Partial report" about 15 seconds later.
The cancel endpoint marked the scan interrupted at once, but the row's page
count was written only when the crawl task wound down, and the stopped-scan
page chooses its heading from that count.

This runs a real scan of the fixture site through the live server, presses
Stop once a few pages are saved, and watches the page from before the click:
the "No report was produced" heading must never appear, not even briefly.

How long a crawl takes to wind down depends on what its page was doing when
Stop arrived, and on this fixture site it is often quick enough to hide the
bug. So the crawl's final write (``_finalize_scan``, the only writer of the
count before the fix) is held back 15 seconds, as in the reproduction. The
scan, the server, the Stop button and the page are all real.
"""

from __future__ import annotations

import functools
import http.server
import socketserver
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

FIXTURE_SITE = Path(__file__).resolve().parents[1] / "fixtures" / "site"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: Any) -> None:
        return


@contextmanager
def _fixture_site() -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(FIXTURE_SITE))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as httpd:
        httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}/"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _saved_pages(db_path: Path, scan_id: int) -> int:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM pages WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        return int(row["n"])
    finally:
        conn.close()


@pytest.fixture
def slow_final_write(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Write the crawl's final row update 15 seconds late, on its own connection."""
    from audit.crawler import orchestrator

    db_path = seeded_db[0]
    real = orchestrator._finalize_scan
    timers: list[threading.Timer] = []

    def finalize_later(_conn: sqlite3.Connection, scan_id: int, summary: Any) -> None:
        def write() -> None:
            conn = connect(db_path)
            try:
                real(conn, scan_id, summary)
            finally:
                conn.close()

        timer = threading.Timer(15, write)
        timer.daemon = True
        timers.append(timer)
        timer.start()

    monkeypatch.setattr(orchestrator, "_finalize_scan", finalize_later)
    yield
    for timer in timers:
        timer.cancel()


async def test_stopping_a_real_scan_shows_the_partial_report_at_once(
    seeded_db: tuple[Path, Path, int],
    slow_final_write: None,
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, _, _ = seeded_db
    base, _ = live_server
    with _fixture_site() as site:
        page = await new_page(viewport={"width": 1280, "height": 900})
        # A normal browser scan, slowed to one page a second so it is still
        # running when Stop is pressed. Image text and AI checks are off:
        # they need tools this test does not depend on.
        created = await page.request.post(
            f"{base}/api/scans",
            data={
                "url": site,
                "max_pages": 40,
                "max_depth": 5,
                "rps": 1,
                "workers": 1,
                "skip_ocr": True,
                "skip_vlm": True,
                "skip_semantic": True,
            },
        )
        assert created.status == 201, await created.text()
        scan_id = int((await created.json())["scan_id"])
        try:
            await page.goto(f"{base}/app/scans/{scan_id}", wait_until="domcontentloaded")
            stop = page.get_by_role("button", name="Stop scan")
            await playwright_async.expect(stop).to_be_visible()

            deadline = time.monotonic() + 90
            while _saved_pages(db_path, scan_id) < 3:
                assert time.monotonic() < deadline, "the scan saved fewer than 3 pages in 90 s"
                await page.wait_for_timeout(250)

            # Watch from before the click, so a heading shown for a moment and
            # then replaced is still caught. The marker shows the page was not
            # reloaded: a reload would drop it.
            await page.evaluate(
                """() => {
                    window.__sameDocument = true;
                    window.__sawNoReport = false;
                    const check = () => {
                        for (const h of document.querySelectorAll('h1, h2')) {
                            if (h.textContent.trim() === 'No report was produced') {
                                window.__sawNoReport = true;
                            }
                        }
                    };
                    new MutationObserver(check).observe(document.body, {
                        childList: true, subtree: true, characterData: true,
                    });
                }"""
            )
            page.once("dialog", lambda dialog: dialog.accept())
            await stop.click()

            # "Immediately": well inside the 15 seconds the crawl took to
            # write its count, and with no reload.
            await playwright_async.expect(
                page.get_by_role("heading", name="Partial report", exact=True)
            ).to_be_visible(timeout=5_000)
            review = page.get_by_role("link", name="Review what the scan found")
            await playwright_async.expect(review).to_be_visible(timeout=1_000)
            await playwright_async.expect(review).to_have_attribute(
                "href", f"/app/scans/{scan_id}/issues"
            )
            assert await page.evaluate("window.__sawNoReport") is False, (
                "the page said 'No report was produced' for a scan that had saved pages"
            )
            assert await page.evaluate("window.__sameDocument === true"), "the page reloaded"
        finally:
            # Leave no crawl running into the next test.
            await page.request.post(f"{base}/api/scans/{scan_id}/cancel")
            await page.context.close()
