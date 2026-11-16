"""The document check's downloads in a sign-in scan (SignedInFileFetcher).

A PDF behind the sign-in is downloaded through the signed-in browser's
request client; every address and redirect goes through the sign-in scan's
egress policy, and a file on another site is refused, never downloaded.
Run against a stand-in for Playwright's APIRequestContext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from audit.crawler.orchestrator import CrawlConfig, _linked_files_on, run_crawl
from audit.linked_files.fetch import SignedInFileFetcher

SITE = "https://app.example.test"


@dataclass
class _Response:
    status: int
    headers: dict[str, str]
    content: bytes = b""

    async def body(self) -> bytes:
        return self.content


@dataclass
class _Request:
    """Answers by address; records what was asked, method first."""

    routes: dict[str, _Response]
    asked: list[tuple[str, str]] = field(default_factory=list)

    async def head(self, url: str, **_: Any) -> _Response:
        self.asked.append(("HEAD", url))
        answer = self.routes[url]
        return _Response(answer.status, answer.headers)

    async def get(self, url: str, **_: Any) -> _Response:
        self.asked.append(("GET", url))
        return self.routes[url]


def _only_the_site(url: str) -> str:
    if not url.startswith(SITE + "/"):
        raise ValueError("outside the sign-in scan's scope")
    return url


def _fetcher(routes: dict[str, _Response], **kwargs: Any) -> tuple[SignedInFileFetcher, _Request]:
    request = _Request(routes)
    return SignedInFileFetcher(request, validate_url=_only_the_site, **kwargs), request  # type: ignore[arg-type]


PDF = {"content-type": "application/pdf"}


async def test_a_pdf_on_the_signed_in_site_is_downloaded() -> None:
    fetch, _ = _fetcher({f"{SITE}/a.pdf": _Response(200, PDF, b"%PDF-1.7 body")})
    got = await fetch(f"{SITE}/a.pdf")
    assert (got.outcome, got.http_status, got.body) == ("ok", 200, b"%PDF-1.7 body")


async def test_a_file_on_another_site_is_never_requested() -> None:
    fetch, request = _fetcher({})
    got = await fetch("https://other.example.test/a.pdf")
    assert got.outcome == "blocked"
    assert request.asked == []


async def test_a_redirect_off_the_site_is_not_followed() -> None:
    fetch, request = _fetcher(
        {f"{SITE}/a.pdf": _Response(302, {"location": "https://cdn.example.test/a.pdf"})}
    )
    got = await fetch(f"{SITE}/a.pdf")
    assert got.outcome == "blocked"
    assert all(url.startswith(SITE) for _method, url in request.asked)


async def test_a_redirect_on_the_site_is_followed() -> None:
    fetch, _ = _fetcher(
        {
            f"{SITE}/a.pdf": _Response(302, {"location": "/files/a.pdf"}),
            f"{SITE}/files/a.pdf": _Response(200, PDF, b"%PDF-1.7"),
        }
    )
    got = await fetch(f"{SITE}/a.pdf")
    assert got.outcome == "ok"


async def test_a_file_declared_too_large_is_not_downloaded() -> None:
    fetch, request = _fetcher(
        {f"{SITE}/big.pdf": _Response(200, {**PDF, "content-length": "999999999"})}
    )
    got = await fetch(f"{SITE}/big.pdf")
    assert got.outcome == "too_large"
    assert ("GET", f"{SITE}/big.pdf") not in request.asked


async def test_a_file_too_large_without_a_declared_size_is_refused() -> None:
    fetch, _ = _fetcher({f"{SITE}/big.pdf": _Response(200, PDF, b"x" * 101)}, max_bytes=100)
    assert (await fetch(f"{SITE}/big.pdf")).outcome == "too_large"


async def test_an_error_status_is_reported() -> None:
    fetch, _ = _fetcher({f"{SITE}/gone.pdf": _Response(404, {})})
    got = await fetch(f"{SITE}/gone.pdf")
    assert (got.outcome, got.http_status) == ("http_error", 404)


def test_a_sign_in_scan_records_documents_only_when_marked_signed_in() -> None:
    signed_in = CrawlConfig(seed_url=SITE + "/", browser_only=True, documents_signed_in=True)
    agent = CrawlConfig(seed_url=SITE + "/", browser_only=True)
    off = CrawlConfig(
        seed_url=SITE + "/", browser_only=True, documents_signed_in=True, linked_files_enabled=False
    )
    assert _linked_files_on(signed_in) is True
    assert _linked_files_on(agent) is False
    assert _linked_files_on(off) is False


async def test_a_sign_in_scan_will_not_check_documents_without_the_signed_in_fetcher(
    tmp_db: Any,
) -> None:
    config = CrawlConfig(seed_url=SITE + "/", browser_only=True, documents_signed_in=True)
    with pytest.raises(ValueError, match="signed-in file fetcher"):
        await run_crawl(tmp_db, config)


async def test_the_tracker_downloads_through_the_signed_in_fetcher_only(tmp_db: Any) -> None:
    """With ``fetch`` given, the crawl's own client is never used: a file on
    the site comes through the signed-in browser, one on another site is
    "could not check", reason blocked."""
    import httpx

    from audit.crawler.rate_limit import HostLimiter
    from audit.crawler.robots import RobotsChecker
    from audit.crawler.url_policy import build_scope
    from audit.linked_files.tracker import LinkedFileTracker

    scan_id = tmp_db.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', '{}')",
        (SITE + "/",),
    ).lastrowid
    page_id = tmp_db.execute(
        "INSERT INTO pages (scan_id, url_normalized, render_mode) VALUES (?, ?, 'js')",
        (scan_id, SITE + "/"),
    ).lastrowid
    fetch, request = _fetcher({f"{SITE}/a.pdf": _Response(200, PDF, b"not really a pdf")})
    anonymous: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        anonymous.append(str(req.url))
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tracker = LinkedFileTracker(
            tmp_db, scan_id=scan_id, scope=build_scope(SITE + "/"), allow_subdomains=False
        )
        tracker.attach_downloads(
            client=client,
            limiter=HostLimiter(rps=100.0),
            robots=RobotsChecker(client, user_agent="test"),
            ignore_robots=True,
            blocked_url_patterns=(),
            excluded_scopes=(),
            fetch=fetch,
        )
        tracker.record_page(
            page_id=page_id,
            base_url=SITE + "/",
            body=b'<a href="/a.pdf">A</a><a href="https://other.example.test/b.pdf">B</a>',
        )
        tracker.queue_page(page_id, lambda _ok: None)
        await tracker.drain()
    rows = dict(
        tmp_db.execute(
            "SELECT url, status || ':' || COALESCE(reason, '') FROM linked_files WHERE scan_id = ?",
            (scan_id,),
        ).fetchall()
    )
    assert anonymous == []
    assert ("GET", f"{SITE}/a.pdf") in request.asked
    assert rows[f"{SITE}/a.pdf"] == "could_not_check:not_a_pdf"
    assert rows["https://other.example.test/b.pdf"] == "could_not_check:blocked"
