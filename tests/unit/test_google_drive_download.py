"""Downloading files kept in Google Drive (audit.linked_files.google).

Google's answers are stood in for here; the real ones these follow were
recorded from real links (docs/internal/google-files-research.md): a
public file comes from drive.usercontent.google.com, a private one
redirects to accounts.google.com, a large one gets a virus-scan page with
a "download anyway" form. The browser fallback runs in real Chromium
against a page served on this computer.
"""

from __future__ import annotations

import http.server
import sqlite3
import threading
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from support.office_docs import word

from audit.linked_files.fetch import FetchedFile
from audit.linked_files.google import (
    DOWNLOAD_URL,
    download_with_button,
    drive_file_id,
    fetch_drive_file,
    view_url,
)

FILE_ID = "1-5fbJabcdefghijklmnop"
VIEW = f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing"
PDF = b"%PDF-1.7\n" + b"x" * 200
SIGN_IN_PAGE = b"<!doctype html><html><title>Sign in - Google Accounts</title></html>"
VIRUS_PAGE = (
    b"<!doctype html><html><title>Google Drive - Virus scan warning</title><body>"
    b'<form id="download-form" action="https://drive.usercontent.google.com/download" method="get">'
    b'<input type="submit" value="Download anyway">'
    b'<input type="hidden" name="id" value="' + FILE_ID.encode() + b'">'
    b'<input type="hidden" name="export" value="download">'
    b'<input type="hidden" name="confirm" value="t">'
    b'<input type="hidden" name="uuid" value="abc-123">'
    b"</form></body></html>"
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (VIEW, FILE_ID),
        (f"https://drive.google.com/file/d/{FILE_ID}", FILE_ID),
        (f"http://drive.google.com/open?id={FILE_ID}", FILE_ID),
        (f"https://drive.google.com/uc?id={FILE_ID}&export=download", FILE_ID),
        ("https://drive.google.com/drive/folders/1abcdefghijk", None),
        (f"https://docs.google.com/document/d/{FILE_ID}/edit", None),
        ("https://drive.google.com/file/d/short/view", None),
    ],
)
def test_the_file_id_comes_from_the_forms_pages_link_with(url: str, expected: str | None) -> None:
    assert drive_file_id(url) == expected


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_a_public_file_comes_from_googles_download_address() -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        headers = {"Content-Type": "application/octet-stream"}
        return httpx.Response(200, headers=headers, content=PDF)

    async with _client(handler) as client:
        got = await fetch_drive_file(client, VIEW)
    assert (got.outcome, got.body) == ("ok", PDF)
    assert asked == [f"{DOWNLOAD_URL}?id={FILE_ID}&export=download"]


async def test_a_private_file_is_a_sign_in_not_a_broken_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "drive.usercontent.google.com":
            return httpx.Response(
                302, headers={"Location": "https://accounts.google.com/v3/signin"}
            )
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=SIGN_IN_PAGE)

    async with _client(handler) as client:
        got = await fetch_drive_file(client, VIEW)
    assert (got.outcome, got.http_status) == ("http_error", 401)


async def test_a_deleted_file_reports_googles_status() -> None:
    async with _client(lambda request: httpx.Response(404)) as client:
        got = await fetch_drive_file(client, VIEW)
    assert (got.outcome, got.http_status) == ("http_error", 404)


async def test_the_virus_scan_page_is_passed_once_with_its_own_form() -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if "uuid" in request.url.params:
            return httpx.Response(200, content=PDF)
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=VIRUS_PAGE)

    async with _client(handler) as client:
        got = await fetch_drive_file(client, VIEW)
    assert (got.outcome, got.body) == ("ok", PDF)
    assert len(asked) == 2
    assert "confirm=t" in asked[1] and "uuid=abc-123" in asked[1]


async def test_a_page_in_place_of_the_file_falls_back_to_the_button() -> None:
    pressed: list[str] = []

    async def button(url: str) -> FetchedFile:
        pressed.append(url)
        return FetchedFile("ok", 200, None, PDF)

    page = b"<!doctype html><html><title>Something new</title></html>"
    async with _client(lambda request: httpx.Response(200, content=page)) as client:
        assert (await fetch_drive_file(client, VIEW, button=button)).body == PDF
        assert pressed == [view_url(FILE_ID)]
        # Without the fallback, the row says the link gave no file.
        assert (await fetch_drive_file(client, VIEW)).outcome == "broken_link"


async def test_a_file_over_the_limit_is_not_kept() -> None:
    async with _client(lambda request: httpx.Response(200, content=PDF)) as client:
        got = await fetch_drive_file(client, VIEW, max_bytes=50)
    assert got.outcome == "too_large"


@pytest.fixture
def drive_like_site() -> Iterator[str]:
    """A page with a "Download" button that downloads a PDF, on this computer."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/file/d/"):
                body = (
                    b"<!doctype html><html><body><h1>report.pdf</h1>"
                    b"<button type='button' aria-label='Download'"
                    b" onclick=\"location.href='/download'\">"
                    b"<svg aria-hidden='true' width='16' height='16'></svg></button>"
                    b"</body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
            else:
                body = PDF
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="report.pdf"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


async def test_the_button_fallback_presses_download_and_keeps_the_file(
    drive_like_site: str,
) -> None:
    """The button is an icon named only by its accessible name, as Drive's
    is: found by role and name, then pressed."""
    pytest.importorskip("playwright.async_api")
    got = await download_with_button(f"{drive_like_site}/file/d/{FILE_ID}/view", user_agent="test")
    assert (got.outcome, got.body) == ("ok", PDF)


async def _track_drive_links(
    conn: sqlite3.Connection, *, ignore_robots: bool
) -> dict[str, tuple[str, str | None]]:
    """A page links a Drive PDF, a Drive Word file and another site's PDF;
    every robots.txt says "Disallow: /", as Google's does for its download
    host. The rows each file gets."""
    from audit.crawler.rate_limit import HostLimiter
    from audit.crawler.robots import RobotsChecker
    from audit.crawler.url_policy import build_scope
    from audit.linked_files.tracker import LinkedFileTracker

    scan_id = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', '{}')",
        ("https://site.test/",),
    ).lastrowid
    page_id = conn.execute(
        "INSERT INTO pages (scan_id, url_normalized, render_mode) VALUES (?, ?, 'js')",
        (scan_id, "https://site.test/"),
    ).lastrowid
    docx = word(image="missing")
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        asked.append(str(request.url))
        if request.url.host == "drive.usercontent.google.com":
            return httpx.Response(200, content=docx if request.url.params["id"] == DOCX_ID else PDF)
        return httpx.Response(200, content=PDF)

    async with _client(handler) as client:
        tracker = LinkedFileTracker(
            conn, scan_id=scan_id, scope=build_scope("https://site.test/"), allow_subdomains=False
        )
        tracker.attach_downloads(
            client=client,
            limiter=HostLimiter(rps=100.0),
            robots=RobotsChecker(client, user_agent="test"),
            ignore_robots=ignore_robots,
            blocked_url_patterns=(),
            excluded_scopes=(),
        )
        tracker.record_page(
            page_id=page_id,
            base_url="https://site.test/",
            body=(
                f'<a href="{VIEW}">Guide</a>'
                f'<a href="https://drive.google.com/file/d/{DOCX_ID}/view">Form</a>'
                '<a href="https://other.test/a.pdf">Other</a>'
            ).encode(),
        )
        tracker.queue_page(page_id, lambda _ok: None)
        await tracker.drain()
    if not ignore_robots:
        assert asked == [], asked
    return {
        url: (status, reason)
        for url, status, reason in conn.execute(
            "SELECT url, status, reason FROM linked_files WHERE scan_id = ?", (scan_id,)
        )
    }


DOCX_ID = "1docxabcdefghijklmnop"


async def test_a_scan_that_follows_robots_txt_does_not_download_drive_files(
    tmp_db: sqlite3.Connection,
) -> None:
    """Google's robots.txt says "Disallow: /" for the host every Drive
    download comes from, and Axcess asks about that host, not the link
    (the developer's decision, 2026-11-16). Nothing is downloaded."""
    rows = await _track_drive_links(tmp_db, ignore_robots=False)
    assert set(rows.values()) == {("could_not_check", "robots")}


async def test_a_scan_set_to_ignore_robots_txt_downloads_drive_files(
    tmp_db: sqlite3.Connection,
) -> None:
    """With "Ignore the site's robots.txt rules", Drive files are downloaded
    and checked as what they are: a PDF as a PDF, a Word file kept in Drive
    as a Word file (since 2026-11-17; it waited for that check before)."""
    rows = await _track_drive_links(tmp_db, ignore_robots=True)
    assert rows[VIEW][0] in {"mostly_sure", "not_sure", "could_not_check"}
    assert rows[VIEW][1] not in {"robots", "not_a_pdf"}
    assert rows[f"https://drive.google.com/file/d/{DOCX_ID}/view"] == ("mostly_sure", None)
    assert rows["https://other.test/a.pdf"][1] != "robots"
