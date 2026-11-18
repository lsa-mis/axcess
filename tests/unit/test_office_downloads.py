"""Word and PowerPoint files in the document check (linked_files.tracker).

A page's Word and PowerPoint links are downloaded and checked like PDFs;
a Google Doc or Slides deck is downloaded as the file Google exports, and
robots.txt is asked about that export address; a Google Sheet and a copy
published to the web are never asked for. Google's answers are stood in
for; the real ones were recorded on 2026-11-17 from Docs linked from U-M
sites (docs/internal/google-files-research.md): a public Doc's export is a
.docx, a private one answers 401.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import httpx
from support.office_docs import slides, word

from audit.linked_files.google import export_address

SITE = "https://site.test/"
DOC = "https://docs.google.com/document/d/1DocAbcdefghijklmnopqrstu/edit?usp=sharing"
PRIVATE = "https://docs.google.com/document/d/1PrivAbcdefghijklmnopqrst/edit"
DECK = "https://docs.google.com/presentation/d/1DeckAbcdefghijklmnopqrst/edit"
SHEET = "https://docs.google.com/spreadsheets/d/1SheetAbcdefghijklmnopqr/edit"
PUBLISHED = "https://docs.google.com/document/d/e/2PACX-1vSabcdefghijklmnop/pub"
GOOGLE_ROBOTS = "User-agent: *\nAllow: /document\nAllow: /presentation\nDisallow: /\n"
CLEAN_WORD = word()
WORD_WITHOUT_ALT = word(image="missing")
CLEAN_DECK = slides()


def _scan(conn: sqlite3.Connection) -> tuple[int, int]:
    scan_id = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', '{}')", (SITE,)
    ).lastrowid
    page_id = conn.execute(
        "INSERT INTO pages (scan_id, url_normalized, render_mode) VALUES (?, ?, 'js')",
        (scan_id, SITE),
    ).lastrowid
    assert scan_id is not None and page_id is not None
    return scan_id, page_id


async def _track(
    conn: sqlite3.Connection,
    links: dict[str, str],
    answers: dict[str, httpx.Response],
    *,
    ignore_robots: bool = False,
    google_robots: str = GOOGLE_ROBOTS,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Record one page linking ``links`` (address -> text), answer each
    download from ``answers`` by address, and return each file's row and
    every address asked for."""
    from audit.crawler.rate_limit import HostLimiter
    from audit.crawler.robots import RobotsChecker
    from audit.crawler.url_policy import build_scope
    from audit.linked_files.tracker import LinkedFileTracker

    scan_id, page_id = _scan(conn)
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200, text=google_robots if request.url.host == "docs.google.com" else ""
            )
        asked.append(url)
        return answers.get(url, httpx.Response(404))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tracker = LinkedFileTracker(
            conn, scan_id=scan_id, scope=build_scope(SITE), allow_subdomains=False
        )
        tracker.attach_downloads(
            client=client,
            limiter=HostLimiter(rps=100.0),
            robots=RobotsChecker(client, user_agent="test"),
            ignore_robots=ignore_robots,
            blocked_url_patterns=(),
            excluded_scopes=(),
        )
        body = "".join(f'<a href="{url}">{text}</a>' for url, text in links.items())
        tracker.record_page(page_id=page_id, base_url=SITE, body=body.encode())
        tracker.queue_page(page_id, lambda _ok: None)
        await tracker.drain()
    rows = {
        row["url"]: {**dict(row), "failed_checks": json.loads(row["failed_checks"])}
        for row in conn.execute(
            "SELECT url, file_type, status, reason, failed_checks, http_status, checked_as, "
            "page_count, sha256 FROM linked_files WHERE scan_id = ?",
            (scan_id,),
        )
    }
    return rows, asked


def _ok(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body)


async def test_word_and_powerpoint_links_are_downloaded_and_checked(
    tmp_db: sqlite3.Connection,
) -> None:
    rows, _asked = await _track(
        tmp_db,
        {f"{SITE}a.docx": "Guide", f"{SITE}b.docx": "Form", f"{SITE}deck.pptx": "Slides"},
        {
            f"{SITE}a.docx": _ok(CLEAN_WORD),
            f"{SITE}b.docx": _ok(WORD_WITHOUT_ALT),
            f"{SITE}deck.pptx": _ok(CLEAN_DECK),
        },
    )
    assert rows[f"{SITE}a.docx"]["status"] == "not_sure"
    assert rows[f"{SITE}a.docx"]["checked_as"] == "docx"
    assert rows[f"{SITE}b.docx"]["status"] == "mostly_sure"
    assert rows[f"{SITE}b.docx"]["failed_checks"] == ["no_alt_text"]
    assert rows[f"{SITE}deck.pptx"]["checked_as"] == "pptx"
    assert rows[f"{SITE}deck.pptx"]["status"] == "not_sure"
    # A deck's page count is its slides.
    assert rows[f"{SITE}deck.pptx"]["page_count"] == 2


async def test_google_docs_and_slides_are_checked_as_the_file_google_exports(
    tmp_db: sqlite3.Connection,
) -> None:
    doc_export = export_address(DOC)
    deck_export = export_address(DECK)
    assert (
        doc_export
        == "https://docs.google.com/document/d/1DocAbcdefghijklmnopqrstu/export?format=docx"
    )
    assert (
        deck_export
        == "https://docs.google.com/presentation/d/1DeckAbcdefghijklmnopqrst/export/pptx"
    )
    rows, asked = await _track(
        tmp_db,
        {DOC: "Notes", PRIVATE: "Private", DECK: "Deck", SHEET: "Budget", PUBLISHED: "Published"},
        {
            doc_export: _ok(WORD_WITHOUT_ALT),
            deck_export: _ok(CLEAN_DECK),
            str(export_address(PRIVATE)): httpx.Response(401, text="<html>Sign in</html>"),
        },
    )
    assert (rows[DOC]["status"], rows[DOC]["checked_as"]) == ("mostly_sure", "docx")
    assert (rows[DECK]["status"], rows[DECK]["checked_as"]) == ("not_sure", "pptx")
    # Private: needs a sign-in, as a private Drive file does.
    assert (rows[PRIVATE]["reason"], rows[PRIVATE]["http_status"]) == ("http_error", 401)
    # Sheets are refused by Google's robots.txt; a published copy has no
    # export. Neither is asked for, and the editor addresses never are.
    assert (rows[SHEET]["status"], rows[SHEET]["reason"]) == ("could_not_check", "google_file")
    assert (rows[PUBLISHED]["status"], rows[PUBLISHED]["reason"]) == (
        "could_not_check",
        "google_file",
    )
    assert sorted(asked) == sorted([doc_export, deck_export, str(export_address(PRIVATE))])


async def test_robots_txt_is_asked_about_the_export_address(tmp_db: sqlite3.Connection) -> None:
    """A host whose robots.txt refuses /document: nothing is downloaded."""
    rows, asked = await _track(
        tmp_db, {DOC: "Notes"}, {}, google_robots="User-agent: *\nDisallow: /\n"
    )
    assert asked == []
    assert rows[DOC]["reason"] == "robots"


async def test_the_bytes_decide_the_check_not_the_address(tmp_db: sqlite3.Connection) -> None:
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
    compound = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100
    rows, _asked = await _track(
        tmp_db,
        {
            f"{SITE}page.docx": "A page",
            f"{SITE}old.docx": "Old",
            f"{SITE}locked.docx": "Locked",
            f"{SITE}really-a-pdf.pptx": "PDF",
        },
        {
            f"{SITE}page.docx": httpx.Response(200, text="<!doctype html><html></html>"),
            f"{SITE}old.docx": _ok(compound + "WordDocument".encode("utf-16-le")),
            f"{SITE}locked.docx": _ok(compound + "EncryptionInfo".encode("utf-16-le")),
            f"{SITE}really-a-pdf.pptx": _ok(pdf),
        },
    )
    assert rows[f"{SITE}page.docx"]["reason"] == "not_a_pdf"
    assert rows[f"{SITE}old.docx"]["reason"] == "old_format"
    assert rows[f"{SITE}locked.docx"]["reason"] == "password"
    assert rows[f"{SITE}really-a-pdf.pptx"]["checked_as"] in {"pdf", None}


async def test_a_copy_of_a_word_file_reuses_its_result(tmp_db: sqlite3.Connection) -> None:
    rows, _asked = await _track(
        tmp_db,
        {f"{SITE}a.docx": "One", f"{SITE}copy/a.docx": "Two"},
        {f"{SITE}a.docx": _ok(WORD_WITHOUT_ALT), f"{SITE}copy/a.docx": _ok(WORD_WITHOUT_ALT)},
    )
    first, copy = rows[f"{SITE}a.docx"], rows[f"{SITE}copy/a.docx"]
    assert first["sha256"] == copy["sha256"]
    for key in ("status", "failed_checks", "checked_as"):
        assert first[key] == copy[key]


async def test_a_word_file_kept_in_drive_is_checked(tmp_db: sqlite3.Connection) -> None:
    """Downloaded only in a scan set to ignore robots.txt (Google's asks
    scanners not to download Drive files); then checked as what it is."""
    drive = "https://drive.google.com/file/d/1WordInDriveAbcdefghij/view"
    download = (
        "https://drive.usercontent.google.com/download?id=1WordInDriveAbcdefghij&export=download"
    )
    rows, _asked = await _track(
        tmp_db, {drive: "Form"}, {download: _ok(WORD_WITHOUT_ALT)}, ignore_robots=True
    )
    assert (rows[drive]["status"], rows[drive]["checked_as"]) == ("mostly_sure", "docx")
