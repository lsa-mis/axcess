"""A crawl finds every linked file on the fixture pages, and checks each PDF.

tests/fixtures/site/documents/ reaches files every way R2 of the Documents
brief lists: plain links, a link that exists only after a click, a frame, an
object and an embed, an address with no extension that the server answers
with a PDF, a PDF on another host, a Google Docs link and a broken link.
Each seeded PDF (tests/support/linked_file_pdfs.py) has a status fixed in
advance. The test runs a real crawl in a real browser and asserts the stored
rows exactly: no file missing, none extra, every referring page and link
text, every status.

The fixture server answers to two host names, 127.0.0.1 (the scanned site)
and localhost (the "other host"), and records every request, so the test
can also prove that the other host was asked for exactly one file and never
crawled, and that the Google file was never fetched.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import socketserver
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from audit.crawler.orchestrator import CrawlConfig, run_crawl

pytestmark = pytest.mark.integration

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "site"
FILES = FIXTURE_ROOT / "documents" / "files"


class _Handler(http.server.SimpleHTTPRequestHandler):
    requests: list[tuple[str, str]]
    port: int

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        host = (self.headers.get("Host") or "").split(":")[0]
        self.requests.append((host, self.path))
        if self.path == "/documents/download?id=7":
            body = (FILES / "clean.pdf").read_bytes()
            self._send(body, "application/pdf")
            return
        if self.path in {"/documents/", "/documents/index.html"}:
            html = (FIXTURE_ROOT / "documents" / "index.html").read_text(encoding="utf-8")
            html = html.replace("__OFF_SITE__", f"http://localhost:{self.port}")
            self._send(html.encode("utf-8"), "text/html; charset=utf-8")
            return
        super().do_GET()

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


@contextmanager
def _serve() -> Iterator[tuple[str, int, list[tuple[str, str]]]]:
    requests: list[tuple[str, str]] = []

    def handler(*args: object, **kwargs: object) -> _Handler:
        return _Handler(*args, directory=str(FIXTURE_ROOT), **kwargs)  # type: ignore[arg-type]

    with _Server(("127.0.0.1", 0), handler) as httpd:
        port = int(httpd.server_address[1])
        _Handler.requests = requests
        _Handler.port = port
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}", port, requests
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


class _LocalOnly(httpx.AsyncBaseTransport):
    """Refuse every request off this computer, and remember each one asked for."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()
        self.asked: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(str(request.url))
        if request.url.host not in {"127.0.0.1", "localhost"}:
            raise httpx.ConnectError("test: no network", request=request)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def _crawl(conn: sqlite3.Connection, base: str, transport: _LocalOnly, **overrides: object) -> int:
    settings: dict[str, object] = {
        "seed_url": f"{base}/documents/",
        "max_pages": 30,
        "rps": 100.0,
        "workers": 2,
        "js_eager": True,
        "vlm_enabled": False,
        "semantic_enabled": False,
        "ocr_enabled": False,
        "keyboard_probe_enabled": False,
        "responsive_checks_enabled": False,
        "focus_checks_enabled": False,
        "visual_checks_enabled": False,
        "markup_checks_enabled": False,
        "interaction_checks_enabled": True,
    }
    config = CrawlConfig(**{**settings, **overrides})  # type: ignore[arg-type]

    async def run() -> int:
        async with httpx.AsyncClient(transport=transport, timeout=15.0) as client:
            summary = await run_crawl(conn, config, http_client=client)
        assert summary.status == "completed"
        return summary.scan_id

    return asyncio.run(run())


def _files(conn: sqlite3.Connection, scan_id: int) -> dict[str, tuple[object, ...]]:
    return {
        row["url"]: (
            row["file_type"],
            row["found_by"],
            row["off_site"],
            row["status"],
            row["reason"],
            tuple(json.loads(row["failed_checks"])),
            row["http_status"],
        )
        for row in conn.execute(
            "SELECT url, file_type, found_by, off_site, status, reason, failed_checks, "
            "http_status FROM linked_files WHERE scan_id = ?",
            (scan_id,),
        )
    }


def _refs(conn: sqlite3.Connection, scan_id: int) -> set[tuple[str, str, str, str, str | None]]:
    return {
        (row["file_url"], row["page_url"], row["how"], row["link_text"], row["revealed_by"])
        for row in conn.execute(
            "SELECT f.url AS file_url, p.url_normalized AS page_url, r.how, r.link_text, "
            "r.revealed_by FROM linked_file_refs r "
            "JOIN linked_files f ON f.id = r.file_id JOIN pages p ON p.id = r.page_id "
            "WHERE r.scan_id = ?",
            (scan_id,),
        )
    }


def test_every_linked_file_is_found_located_and_checked(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    transport = _LocalOnly()
    with _serve() as (base, port, requests):
        scan_id = _crawl(tmp_db, base, transport)

    d = f"{base}/documents"
    off = f"http://localhost:{port}/documents/files/offsite.pdf"
    google = "https://docs.google.com/document/d/1AxcessFixture/edit"
    assert _files(tmp_db, scan_id) == {
        # The clean control: passes every machine check, so "Not sure".
        f"{d}/files/clean.pdf": ("pdf", "extension", 0, "not_sure", None, (), 200),
        f"{d}/files/untagged.pdf": (
            "pdf",
            "extension",
            0,
            "mostly_sure",
            None,
            ("not_tagged",),
            200,
        ),
        f"{d}/files/encrypted.pdf": (
            "pdf",
            "extension",
            0,
            "mostly_sure",
            None,
            ("blocks_assistive_tech",),
            200,
        ),
        f"{d}/files/password.pdf": ("pdf", "extension", 0, "could_not_check", "password", (), 200),
        f"{d}/files/missing.pdf": ("pdf", "extension", 0, "could_not_check", "http_error", (), 404),
        f"{d}/files/report.docx": (
            "docx",
            "extension",
            0,
            "could_not_check",
            "type_not_checked_yet",
            (),
            None,
        ),
        f"{d}/files/budget.xls": ("xls", "extension", 0, "could_not_check", "old_format", (), None),
        f"{d}/download?id=7": ("pdf", "content_type", 0, "not_sure", None, (), 200),
        off: ("pdf", "extension", 1, "mostly_sure", None, ("not_tagged",), 200),
        google: ("google_doc", "host", 1, "could_not_check", "google_file", (), None),
        f"{d}/files/scanned.pdf": ("pdf", "extension", 0, "mostly_sure", None, ("no_text",), 200),
        f"{d}/files/no-title.pdf": ("pdf", "extension", 0, "mostly_sure", None, ("no_title",), 200),
        f"{d}/files/no-language.pdf": (
            "pdf",
            "extension",
            0,
            "mostly_sure",
            None,
            ("no_language",),
            200,
        ),
        f"{d}/files/revealed.pdf": ("pdf", "extension", 0, "not_sure", None, (), 200),
    }

    index, more = f"{d}/", f"{d}/more.html"
    assert _refs(tmp_db, scan_id) == {
        (f"{d}/files/clean.pdf", index, "link", "Annual report 2026 (PDF)", None),
        (f"{d}/files/clean.pdf", more, "link", "Annual report", None),
        (f"{d}/files/untagged.pdf", index, "link", "Untagged leaflet (PDF)", None),
        (f"{d}/files/encrypted.pdf", index, "link", "Locked handbook (PDF)", None),
        (f"{d}/files/password.pdf", index, "link", "Board minutes (PDF)", None),
        (f"{d}/files/missing.pdf", index, "link", "Old newsletter (PDF)", None),
        (f"{d}/files/report.docx", index, "link", "Committee report (Word)", None),
        (f"{d}/files/budget.xls", index, "link", "Budget 2003 (Excel)", None),
        (f"{d}/download?id=7", index, "link", "Price list", None),
        (f"{d}/download?id=7", more, "link", "Prices", None),
        (off, index, "link", "Partner guide (PDF)", None),
        (google, index, "link", "Meeting notes (Google Docs)", None),
        (f"{d}/files/scanned.pdf", index, "iframe", "Course map", None),
        (f"{d}/files/no-title.pdf", index, "object", "Floor plan", None),
        (f"{d}/files/no-language.pdf", index, "embed", "Price sheet", None),
        (
            f"{d}/files/revealed.pdf",
            index,
            "revealed_link",
            "Extra forms (PDF)",
            "Show more files",
        ),
    }

    # The other host was asked for its robots.txt and the one file, once,
    # and nothing else: it was checked, not crawled.
    other_host = [path for host, path in requests if host == "localhost"]
    assert sorted(other_host) == ["/documents/files/offsite.pdf", "/robots.txt"]
    # Nothing left this computer: the Google file was never fetched.
    assert not [url for url in transport.asked if "google" in url]

    config = json.loads(
        tmp_db.execute("SELECT config_json FROM scans WHERE id = ?", (scan_id,)).fetchone()[0]
    )
    assert config["linked_files_enabled"] is True


def test_turning_it_off_records_nothing(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    transport = _LocalOnly()
    with _serve() as (base, _port, requests):
        scan_id = _crawl(
            tmp_db, base, transport, linked_files_enabled=False, interaction_checks_enabled=False
        )

    assert tmp_db.execute("SELECT COUNT(*) FROM linked_files").fetchone()[0] == 0
    assert tmp_db.execute("SELECT COUNT(*) FROM linked_file_refs").fetchone()[0] == 0
    # Without the feature the other host is never contacted at all.
    assert not [path for host, path in requests if host == "localhost"]
    config = json.loads(
        tmp_db.execute("SELECT config_json FROM scans WHERE id = ?", (scan_id,)).fetchone()[0]
    )
    assert config["linked_files_enabled"] is False
