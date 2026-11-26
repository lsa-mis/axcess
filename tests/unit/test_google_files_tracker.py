"""The document check with a public scan's Google sign-in (2026-11-26).

The tracker routes each file: a Google Doc or Slides export and a Drive file
through the Google session, everything else through the crawl's client.
robots.txt is asked as before; after the downloads, Google files with no
date get the days Google's File > Details shows. A fake session stands in
for Google.
"""

from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from dataclasses import dataclass, field
from typing import Any

import httpx
from structlog.testing import capture_logs
from support.office_docs import word

from audit.crawler.rate_limit import HostLimiter
from audit.crawler.robots import RobotsChecker
from audit.crawler.url_policy import build_scope
from audit.db import linked_files as store
from audit.linked_files.fetch import FetchedFile
from audit.linked_files.google_session import DatesRead, GoogleDates, google_file_key
from audit.linked_files.tracker import LinkedFileTracker

SITE = "https://site.test/"
DOC = "https://docs.google.com/document/d/1docAAAAAAAAAAAAAAAAAA/edit"
DOC_AGAIN = "https://docs.google.com/document/d/1docAAAAAAAAAAAAAAAAAA/view?usp=sharing"
SHEET = "https://docs.google.com/spreadsheets/d/1sheetBBBBBBBBBBBBBBBB/edit"
SLIDES = "https://docs.google.com/presentation/d/1slideCCCCCCCCCCCCCCCC/edit"
DRIVE = "https://drive.google.com/file/d/1driveDDDDDDDDDDDDDDDD/view"
PDF_URL = "https://other.test/report.pdf"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _google_export() -> bytes:
    """A Word file as Google exports one: no created or modified date."""
    source = zipfile.ZipFile(io.BytesIO(word(image="missing")))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "docProps/core.xml":
                data = re.sub(rb"<dcterms:(created|modified)[^>]*>[^<]*</dcterms:\1>", b"", data)
            target.writestr(item, data)
    return out.getvalue()


@dataclass
class FakeGoogle:
    """What the tracker asks of the Google session, and fixed answers."""

    active: bool = True
    dates: dict[str, GoogleDates] = field(default_factory=dict)
    lose_on_read: bool = False
    exports: list[str] = field(default_factory=list)
    drives: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)
    closed: int = 0

    def allow_file(self, url: str) -> bool:
        self.allowed.append(url)
        return True

    async def fetch_export(self, address: str) -> FetchedFile:
        self.exports.append(address)
        return FetchedFile("ok", 200, None, _google_export())

    async def fetch_drive(self, url: str) -> FetchedFile:
        self.drives.append(url)
        return FetchedFile("ok", 200, None, word(image="missing"))

    async def read_dates(self, url: str) -> DatesRead:
        assert url in self.allowed, "a page is opened only after it is registered"
        self.reads.append(url)
        if self.lose_on_read:
            self.active = False
            return DatesRead("lost")
        key = google_file_key(url)
        assert key is not None
        found = self.dates.get(key[1])
        return DatesRead("dates", found or GoogleDates())

    async def close(self) -> None:
        self.closed += 1


def _robots(disallow: str) -> str:
    return f"User-agent: *\nDisallow: {disallow}\n" if disallow else "User-agent: *\nAllow: /\n"


async def _run(
    conn: sqlite3.Connection,
    google: FakeGoogle,
    *,
    links: list[str],
    ignore_robots: bool = False,
    robots: dict[str, str] | None = None,
) -> tuple[int, list[str]]:
    """Record one page linking ``links``, check them all, read the dates."""
    scan_id = int(
        conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', '{}')", (SITE,)
        ).lastrowid
        or 0
    )
    page_id = int(
        conn.execute(
            "INSERT INTO pages (scan_id, url_normalized, render_mode) VALUES (?, ?, 'js')",
            (scan_id, SITE),
        ).lastrowid
        or 0
    )
    asked: list[str] = []
    rules = robots or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=_robots(rules.get(request.url.host, "")))
        asked.append(str(request.url))
        return httpx.Response(200, content=PDF)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tracker = LinkedFileTracker(
            conn, scan_id=scan_id, scope=build_scope(SITE), allow_subdomains=False
        )
        limiter = HostLimiter(rps=1000.0)
        checker = RobotsChecker(client, user_agent="test")
        tracker.attach_downloads(
            client=client,
            limiter=limiter,
            robots=checker,
            ignore_robots=ignore_robots,
            blocked_url_patterns=(),
            excluded_scopes=(),
            google=google,
        )
        body = "".join(f'<a href="{link}">x</a>' for link in links).encode()
        tracker.record_page(page_id=page_id, base_url=SITE, body=body)
        await tracker.check_pending(
            client=client,
            limiter=limiter,
            robots=checker,
            ignore_robots=ignore_robots,
            blocked_url_patterns=(),
            excluded_scopes=(),
        )
    return scan_id, asked


def _rows(conn: sqlite3.Connection, scan_id: int) -> dict[str, tuple[Any, ...]]:
    return {
        row[0]: tuple(row[1:])
        for row in conn.execute(
            "SELECT url, status, reason, file_created_at, file_modified_at FROM linked_files "
            "WHERE scan_id = ?",
            (scan_id,),
        )
    }


async def test_a_doc_is_exported_through_the_google_session(tmp_db: sqlite3.Connection) -> None:
    google = FakeGoogle()
    scan_id, asked = await _run(tmp_db, google, links=[DOC, PDF_URL])
    assert google.exports == [
        "https://docs.google.com/document/d/1docAAAAAAAAAAAAAAAAAA/export?format=docx"
    ]
    # The other site's PDF comes through the crawl's own client, as before.
    assert asked == [PDF_URL]
    rows = _rows(tmp_db, scan_id)
    assert rows[DOC][0] == "mostly_sure"


async def test_a_drive_file_follows_robots_txt_as_before(tmp_db: sqlite3.Connection) -> None:
    """Google's robots.txt says "Disallow: /" for Drive's download host:
    a scan that follows it never asks the session for the file."""
    google = FakeGoogle()
    rules = {"drive.usercontent.google.com": "/"}
    scan_id, _ = await _run(tmp_db, google, links=[DRIVE], robots=rules)
    assert google.drives == []
    assert _rows(tmp_db, scan_id)[DRIVE][:2] == ("could_not_check", "robots")


async def test_a_drive_file_downloads_through_the_session_when_robots_is_ignored(
    tmp_db: sqlite3.Connection,
) -> None:
    google = FakeGoogle()
    rules = {"drive.usercontent.google.com": "/"}
    scan_id, asked = await _run(tmp_db, google, links=[DRIVE], robots=rules, ignore_robots=True)
    assert google.drives == [DRIVE]
    assert asked == []
    assert _rows(tmp_db, scan_id)[DRIVE][0] == "mostly_sure"


async def test_a_lost_sign_in_falls_back_to_the_crawls_client(tmp_db: sqlite3.Connection) -> None:
    google = FakeGoogle(active=False)
    scan_id, asked = await _run(tmp_db, google, links=[DOC])
    assert google.exports == []
    assert asked == ["https://docs.google.com/document/d/1docAAAAAAAAAAAAAAAAAA/export?format=docx"]
    # Nor is any page opened for dates.
    assert google.reads == []
    assert _rows(tmp_db, scan_id)[DOC][2:] == (None, None)


async def test_dates_fill_only_google_docs_sheets_and_slides_with_no_date(
    tmp_db: sqlite3.Connection,
) -> None:
    google = FakeGoogle(
        dates={
            "1docAAAAAAAAAAAAAAAAAA": GoogleDates("2024-10-17", "2025-07-29"),
            "1sheetBBBBBBBBBBBBBBBB": GoogleDates("2020-01-02", None),
            "1slideCCCCCCCCCCCCCCCC": GoogleDates("2019-05-06", "2019-05-07"),
        }
    )
    scan_id, _ = await _run(
        tmp_db, google, links=[DOC, DOC_AGAIN, SHEET, SLIDES, DRIVE, PDF_URL], ignore_robots=True
    )
    rows = _rows(tmp_db, scan_id)
    assert rows[DOC][2:] == ("2024-10-17", "2025-07-29")
    # One Google file ID, two addresses: read once, both dated.
    assert rows[DOC_AGAIN][2:] == ("2024-10-17", "2025-07-29")
    assert rows[SHEET][2:] == ("2020-01-02", None)
    assert rows[SLIDES][2:] == ("2019-05-06", "2019-05-07")
    # A Drive file keeps the dates its own file gave (a Word file here),
    # and neither it nor another site's file is opened for dates.
    assert rows[DRIVE][2] is not None and rows[DRIVE][2] != "2024-10-17"
    assert sorted(google.reads) == sorted(
        [
            "https://docs.google.com/document/d/1docAAAAAAAAAAAAAAAAAA/edit",
            "https://docs.google.com/spreadsheets/d/1sheetBBBBBBBBBBBBBBBB/edit",
            "https://docs.google.com/presentation/d/1slideCCCCCCCCCCCCCCCC/edit",
        ]
    )


async def test_a_page_robots_txt_refuses_is_not_opened(tmp_db: sqlite3.Connection) -> None:
    google = FakeGoogle(dates={"1sheetBBBBBBBBBBBBBBBB": GoogleDates("2020-01-02", None)})
    rules = {"docs.google.com": "/spreadsheets"}
    scan_id, _ = await _run(tmp_db, google, links=[SHEET], robots=rules)
    assert google.reads == []
    assert _rows(tmp_db, scan_id)[SHEET][2:] == (None, None)


def test_a_date_the_file_gave_is_never_replaced(tmp_db: sqlite3.Connection) -> None:
    scan_id = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', '{}')", (SITE,)
        ).lastrowid
        or 0
    )
    file_id = store.upsert_file(
        tmp_db, scan_id=scan_id, url=DOC, file_type="google_doc", found_by="host", off_site=True
    )
    assert file_id is not None
    tmp_db.execute(
        "UPDATE linked_files SET file_created_at = '2001-01-01T00:00:00+00:00' WHERE id = ?",
        (file_id,),
    )
    # Not a candidate: it has a date.
    assert store.google_files_without_dates(tmp_db, scan_id) == []
    assert store.set_file_dates(
        tmp_db, scan_id=scan_id, file_id=file_id, created="2024-10-17", modified="2025-07-29"
    )
    created, modified = tmp_db.execute(
        "SELECT file_created_at, file_modified_at FROM linked_files WHERE id = ?", (file_id,)
    ).fetchone()
    assert (created, modified) == ("2001-01-01T00:00:00+00:00", "2025-07-29")
    # Another scan's file is never touched.
    assert not store.set_file_dates(
        tmp_db, scan_id=scan_id + 1, file_id=file_id, created="1999-01-01", modified=None
    )


async def test_a_lost_sign_in_stops_the_date_reads(tmp_db: sqlite3.Connection) -> None:
    google = FakeGoogle(lose_on_read=True)
    await _run(tmp_db, google, links=[SHEET, SLIDES], ignore_robots=True)
    assert len(google.reads) == 1


async def test_no_date_from_any_file_opened_is_a_warning(tmp_db: sqlite3.Connection) -> None:
    google = FakeGoogle()
    with capture_logs() as logs:
        await _run(tmp_db, google, links=[SHEET, SLIDES], ignore_robots=True)
    warnings = [entry for entry in logs if entry["event"] == "linked_files.google_dates_none_found"]
    assert len(warnings) == 1 and warnings[0]["opened"] == 2
    assert "Google's screen may have changed" in warnings[0]["message"]
    # Counts only, never an address.
    summary = next(entry for entry in logs if entry["event"] == "linked_files.google_dates")
    assert "docs.google.com" not in repr(summary)


async def test_some_dates_found_is_no_warning(tmp_db: sqlite3.Connection) -> None:
    google = FakeGoogle(dates={"1sheetBBBBBBBBBBBBBBBB": GoogleDates("2020-01-02", None)})
    with capture_logs() as logs:
        await _run(tmp_db, google, links=[SHEET, SLIDES], ignore_robots=True)
    assert not [e for e in logs if e["event"] == "linked_files.google_dates_none_found"]


def test_a_sign_in_scan_cannot_take_a_google_session(tmp_db: sqlite3.Connection) -> None:
    import pytest

    tracker = LinkedFileTracker(tmp_db, scan_id=1, scope=build_scope(SITE), allow_subdomains=False)

    async def fetch(_url: str) -> FetchedFile:
        return FetchedFile("broken_link")

    with pytest.raises(ValueError, match="public scans only"):
        tracker.attach_downloads(
            client=httpx.AsyncClient(),
            limiter=HostLimiter(),
            robots=RobotsChecker(httpx.AsyncClient(), user_agent="t"),
            ignore_robots=False,
            blocked_url_patterns=(),
            excluded_scopes=(),
            fetch=fetch,
            google=FakeGoogle(),
        )
