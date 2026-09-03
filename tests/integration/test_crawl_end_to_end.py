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
from typing import Any, cast

import httpx
import pytest

from audit.crawler.fetcher import FetchResult
from audit.crawler.orchestrator import CrawlConfig, CrawlSummary, run_crawl
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
        config = CrawlConfig(
            js_eager=False,
            seed_url=base,
            max_pages=50,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
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


def test_crawl_discovers_hash_router_pages(tmp_db: sqlite3.Connection) -> None:
    """SPA hash routes are distinct rendered pages; ordinary anchors are not."""
    with _serve() as base:
        seed = f"{base}/hash-spa/index.html"
        config = CrawlConfig(
            js_eager=True,
            seed_url=seed,
            max_pages=10,
            rps=100.0,
            workers=1,
            image_extraction_enabled=False,
            axe_enabled=False,
            vlm_enabled=False,
            semantic_enabled=False,
            keyboard_probe_enabled=False,
            responsive_checks_enabled=False,
            focus_checks_enabled=False,
            visual_checks_enabled=False,
            interaction_checks_enabled=False,
            capture_screenshots=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    assert summary.status == "completed"
    rows = tmp_db.execute(
        "SELECT url_normalized, final_url, title FROM pages WHERE scan_id = ?",
        (summary.scan_id,),
    ).fetchall()
    by_url = {row["url_normalized"]: row for row in rows}
    assert set(by_url) == {
        seed,
        f"{seed}#/about",
        f"{seed}#/projects",
    }
    assert by_url[f"{seed}#/about"]["title"] == "About | Hash SPA"
    assert by_url[f"{seed}#/projects"]["title"] == "Projects | Hash SPA"
    assert all(row["final_url"] is None for row in rows)


def test_crawl_respects_max_pages(tmp_db: sqlite3.Connection) -> None:
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=base,
            max_pages=2,
            rps=100.0,
            workers=1,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    # Workers can overshoot slightly because the limit check is cooperative;
    # the hard invariant is that we respected the bound within worker count.
    assert summary.pages_fetched <= config.max_pages + config.workers
    assert summary.pages_fetched >= config.max_pages


def test_crawl_skips_out_of_scope_and_non_http(tmp_db: sqlite3.Connection) -> None:
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=base,
            max_pages=50,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
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
                CrawlConfig(
                    js_eager=False,
                    seed_url=seed,
                    max_pages=50,
                    rps=100.0,
                    workers=2,
                    vlm_enabled=False,
                    semantic_enabled=False,
                ),
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
                    CrawlConfig(
                        js_eager=False,
                        seed_url=seed,
                        max_pages=50,
                        rps=1.0,
                        workers=1,
                        vlm_enabled=False,
                        semantic_enabled=False,
                    ),
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
    # js_enabled=False keeps this test focused on the static-fetcher path.
    # The tiny fixture pages otherwise trip the is_js_only heuristic and
    # get auto-escalated to Playwright — which is correct behavior, just
    # not what this particular test is checking.
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=base,
            max_pages=10,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
            js_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    row = tmp_db.execute(
        "SELECT title, html_hash, render_mode FROM pages WHERE scan_id = ? AND url_normalized = ?",
        (summary.scan_id, f"{base}/"),
    ).fetchone()
    assert row is not None
    assert row["title"] == "Fixture home"
    assert row["render_mode"] == "static"
    assert row["html_hash"] and len(row["html_hash"]) == 64


def test_browser_only_crawl_never_uses_anonymous_http(tmp_db: sqlite3.Connection) -> None:
    """Authenticated mode obtains documents only from its injected browser."""

    seed = "https://app.example.test/secure/"

    class _AuthenticatedBrowser:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def fetch(self, url: str) -> FetchResult:
            self.calls.append(url)
            return FetchResult(
                url=url,
                status_code=200,
                content_type="text/html",
                body=b"<!doctype html><html lang='en'><title>Private</title><main>OK</main>",
                retry_after=None,
            )

    browser = _AuthenticatedBrowser()

    def reject_anonymous_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"anonymous HTTP request attempted: {request.method}")

    async def run() -> CrawlSummary:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(reject_anonymous_request),
            trust_env=False,
        ) as client:
            return await run_crawl(
                tmp_db,
                CrawlConfig(
                    seed_url=seed,
                    max_pages=1,
                    workers=1,
                    ignore_robots=True,
                    browser_only=True,
                    image_extraction_enabled=False,
                    ocr_enabled=False,
                    vlm_enabled=False,
                    semantic_enabled=False,
                    alfa_enabled=False,
                ),
                http_client=client,
                js_fetcher=cast(Any, browser),
            )

    summary = asyncio.run(run())

    assert summary.pages_fetched == 1
    assert browser.calls == [seed]
    # Protected/login scans disable image extraction by default. Browser
    # analyzer coverage must not disappear with that unrelated option.
    assert summary.axe_pages_scanned == 1
    assert summary.keyboard_pages_probed == 1
    assert summary.responsive_pages_probed == 1
    row = tmp_db.execute(
        "SELECT axe_pages_scanned, keyboard_pages_probed, responsive_pages_probed "
        "FROM scans WHERE id = ?",
        (summary.scan_id,),
    ).fetchone()
    assert row is not None
    assert tuple(row) == (1, 1, 1)


def test_rendered_analyzers_persist_when_image_extraction_is_disabled(
    tmp_db: sqlite3.Connection,
) -> None:
    """The login-mode image default must not suppress DOM-rule evidence."""

    with _serve() as base:
        summary = asyncio.run(
            run_crawl(
                tmp_db,
                CrawlConfig(
                    seed_url=f"{base}/",
                    max_pages=1,
                    workers=1,
                    rps=100.0,
                    js_eager=True,
                    image_extraction_enabled=False,
                    ocr_enabled=False,
                    vlm_enabled=False,
                    semantic_enabled=False,
                    alfa_enabled=False,
                    capture_screenshots=False,
                ),
            )
        )

    assert summary.status == "completed"
    assert summary.pages_fetched == 1
    assert summary.axe_pages_scanned == 1
    assert summary.keyboard_pages_probed == 1
    assert summary.responsive_pages_probed == 1
    row = tmp_db.execute(
        "SELECT axe_pages_scanned, axe_violations_total, "
        "keyboard_pages_probed, responsive_pages_probed "
        "FROM scans WHERE id = ?",
        (summary.scan_id,),
    ).fetchone()
    assert row is not None
    assert row["axe_pages_scanned"] == 1
    assert row["axe_violations_total"] == summary.axe_violations_total
    assert row["keyboard_pages_probed"] == 1
    assert row["responsive_pages_probed"] == 1


def test_start_url_is_where_the_crawl_actually_begins(tmp_db: sqlite3.Connection) -> None:
    """The crawl starts at the signed-in landing page, not the configured seed.

    ``interaction/hidden_state.html`` is linked from nowhere in the fixture
    site, so it is reachable only by being seeded directly. If ``start_url``
    were ignored — the behaviour that made a login handoff re-fetch the
    sign-in page — the crawl would begin at the seed and this page could
    never appear, while ``about.html`` (one link from the seed) would.
    """
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=base,
            start_url=f"{base}/interaction/hidden_state.html",
            max_pages=50,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    urls = _page_urls(tmp_db, summary.scan_id)
    assert f"{base}/interaction/hidden_state.html" in urls, (
        "the crawl did not begin where sign-in landed"
    )
    assert f"{base}/about.html" not in urls, (
        "the crawl began at the seed and followed its links, ignoring start_url"
    )


def test_start_url_does_not_narrow_the_configured_scope(tmp_db: sqlite3.Connection) -> None:
    """Scope stays anchored to the seed even though the entry point moved.

    ``subdir/deep.html`` links back to ``/``. Adopting the landing URL as the
    seed would derive scope from its path — ``/subdir/`` — and that link
    would fall out of scope, silently confining an authenticated scan to
    whichever directory the identity provider happened to land on.
    """
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=base,
            start_url=f"{base}/subdir/deep.html",
            max_pages=50,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    urls = _page_urls(tmp_db, summary.scan_id)
    assert f"{base}/subdir/deep.html" in urls
    # Only reachable via "/" — in scope solely because scope came from the seed.
    assert f"{base}/about.html" in urls, "start_url narrowed the scope to its own directory"
    assert summary.seed_url.rstrip("/") == base.rstrip("/")


def test_out_of_scope_start_url_falls_back_to_the_seed(tmp_db: sqlite3.Connection) -> None:
    """An unusable entry point must not produce a zero-page scan.

    Every job is scope-checked again when it is leased, so seeding a URL
    outside the configured scope would leave the crawl rejecting its only
    queued job and reporting nothing. Falling back to the seed keeps the scan
    alive; the orchestrator logs why.
    """
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/subdir/",
            start_url="http://127.0.0.1:9/elsewhere.html",
            max_pages=20,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    urls = _page_urls(tmp_db, summary.scan_id)
    assert urls, "an out-of-scope start URL emptied the crawl instead of falling back"
    assert f"{base}/subdir/deep.html" in urls
    assert not any("127.0.0.1:9" in u for u in urls)


def test_default_start_url_is_unchanged_behaviour(tmp_db: sqlite3.Connection) -> None:
    """Every unauthenticated crawl leaves start_url unset and is unaffected."""
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/subdir/",
            max_pages=20,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        assert config.start_url is None
        summary = asyncio.run(run_crawl(tmp_db, config))

    urls = _page_urls(tmp_db, summary.scan_id)
    assert f"{base}/subdir/deep.html" in urls


def test_a_sign_out_link_is_never_followed(tmp_db: sqlite3.Connection) -> None:
    """An authenticated crawl must not end its own session.

    This is the shape of a real failure: a scan of an app signed in as the
    auditor followed the "Sign out" link in the header, and every page after
    that rendered the login screen. The scan still reported as completed,
    so the report looked like evidence about the application when it was
    evidence about a login form.
    """
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/authed/",
            start_url=f"{base}/authed/dashboard.html",
            max_pages=50,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    urls = _page_urls(tmp_db, summary.scan_id)
    assert f"{base}/authed/logout.html" not in urls, "the crawl signed itself out"
    # The rest of the app is still crawled — blocking is targeted, not a halt.
    assert f"{base}/authed/dashboard.html" in urls
    assert f"{base}/authed/reports.html" in urls
    assert f"{base}/authed/settings.html" in urls
    assert summary.pages_skipped_blocked >= 1


def test_excluded_scopes_are_not_visited(tmp_db: sqlite3.Connection) -> None:
    """The operator's explicit "never visit" list is honoured as a prefix."""
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/authed/",
            start_url=f"{base}/authed/dashboard.html",
            excluded_scopes=(f"{base}/authed/reports.html",),
            max_pages=50,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    urls = _page_urls(tmp_db, summary.scan_id)
    assert f"{base}/authed/reports.html" not in urls
    assert f"{base}/authed/settings.html" in urls


def test_blocklist_can_be_emptied_for_an_unauthenticated_scan(tmp_db: sqlite3.Connection) -> None:
    """Blocking is a default, not a rule: a public scan may want that page.

    Nothing is at risk without a session to lose, and a sign-out page has
    accessibility problems like any other.
    """
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/authed/",
            start_url=f"{base}/authed/dashboard.html",
            blocked_url_patterns=(),
            max_pages=50,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    urls = _page_urls(tmp_db, summary.scan_id)
    assert f"{base}/authed/logout.html" in urls


class _RedirectingHandler(_QuietHandler):
    """Serves the fixture site, but bounces one path to a login page.

    Reproduces a lapsed session: the application URL is requested, the server
    answers 302 to sign-in, and the crawler follows it without ever being
    told the page it received is not the page it asked for.
    """

    def do_GET(self) -> None:
        if self.path.startswith("/redirects/dashboard"):
            self.send_response(302)
            self.send_header("Location", "/redirects/login.html")
            self.end_headers()
            return
        super().do_GET()


@contextmanager
def _serve_with_redirect() -> Iterator[str]:
    handler = lambda *a, **kw: _RedirectingHandler(*a, directory=str(FIXTURE_ROOT), **kw)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def test_a_redirect_to_sign_in_is_recorded_and_counted(tmp_db: sqlite3.Connection) -> None:
    """The landing page is recorded, and the sign-in wall is counted.

    Previously the row was filed under the requested URL with the login
    page's content, so two scans of two different application URLs produced
    byte-identical HTML and nothing indicated why.
    """
    with _serve_with_redirect() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/redirects/",
            start_url=f"{base}/redirects/dashboard",
            max_pages=20,
            rps=100.0,
            workers=1,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    row = tmp_db.execute(
        "SELECT url_normalized, final_url, title FROM pages "
        "WHERE scan_id = ? AND url_normalized LIKE '%dashboard%'",
        (summary.scan_id,),
    ).fetchone()
    assert row is not None, "the requested URL is still the row's identity"
    assert row["final_url"] is not None, "the redirect was not recorded"
    assert row["final_url"].endswith("/redirects/login.html")
    assert summary.pages_redirected >= 1
    # Both the login page and the reset page behind it are sign-in walls.
    assert summary.pages_auth_wall >= 1


def test_a_page_that_was_not_redirected_records_no_landing_url(
    tmp_db: sqlite3.Connection,
) -> None:
    """final_url is a signal, so it must stay NULL in the ordinary case."""
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/subdir/",
            max_pages=10,
            rps=100.0,
            workers=1,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    finals = [
        r["final_url"]
        for r in tmp_db.execute("SELECT final_url FROM pages WHERE scan_id = ?", (summary.scan_id,))
    ]
    assert finals and all(f is None for f in finals)
    assert summary.pages_redirected == 0
