"""First-page pictures of linked PDFs (the Documents tab's thumbnails).

``first_page_jpeg`` draws page 1 with PDFium; the tracker keeps it in the
blob store with the check's result, shares it between copies, and draws
nothing when the scan chose not to store rendered pages.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import httpx
import pytest
from PIL import Image

from audit.blob_store import BlobStore
from audit.linked_files.thumbnail import (
    MAX_HEIGHT_PX,
    SMALL_BOX_PX,
    WIDTH_PX,
    first_page_jpegs,
)

FILES = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "documents" / "files"


def test_the_first_page_is_drawn_in_two_sizes() -> None:
    pictures = first_page_jpegs((FILES / "clean.pdf").read_bytes())
    assert pictures is not None
    large = Image.open(io.BytesIO(pictures.large))
    small = Image.open(io.BytesIO(pictures.small))
    assert large.format == small.format == "JPEG"
    assert large.width <= WIDTH_PX and large.height <= MAX_HEIGHT_PX
    assert large.width >= WIDTH_PX - 1 or large.height >= MAX_HEIGHT_PX - 1
    # The table's picture fits its box and is much lighter than the large one.
    assert small.width <= SMALL_BOX_PX[0] and small.height <= SMALL_BOX_PX[1]
    assert SMALL_BOX_PX[1] - 1 <= small.height or SMALL_BOX_PX[0] - 1 <= small.width
    assert len(pictures.small) < len(pictures.large)


@pytest.mark.parametrize(
    "body",
    [b"", b"not a pdf", b"%PDF-1.7\n" + b"\x00" * 200],
    ids=["empty", "text", "damaged"],
)
def test_a_file_pdfium_cannot_open_has_no_picture(body: bytes) -> None:
    assert first_page_jpegs(body) is None


def _scan_and_page(conn: sqlite3.Connection) -> tuple[int, int]:
    scan_id = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://site.test/', 'running', '{}')"
    ).lastrowid
    page_id = conn.execute(
        "INSERT INTO pages (scan_id, url_normalized, status_code, render_mode) "
        "VALUES (?, 'https://site.test/', 200, 'static')",
        (scan_id,),
    ).lastrowid
    conn.commit()
    assert scan_id is not None and page_id is not None
    return int(scan_id), int(page_id)


async def _check_two_copies(
    conn: sqlite3.Connection, blobs: BlobStore | None
) -> list[tuple[str, str | None]]:
    """Check one PDF linked at two addresses; return (url, thumbnail_hash)."""
    from audit.crawler.rate_limit import HostLimiter
    from audit.crawler.robots import RobotsChecker
    from audit.crawler.url_policy import build_scope
    from audit.linked_files.tracker import LinkedFileTracker

    scan_id, page_id = _scan_and_page(conn)
    pdf = (FILES / "clean.pdf").read_bytes()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=pdf)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tracker = LinkedFileTracker(
            conn,
            scan_id=scan_id,
            scope=build_scope("https://site.test/"),
            allow_subdomains=False,
        )
        tracker.attach_downloads(
            client=client,
            limiter=HostLimiter(rps=100.0),
            robots=RobotsChecker(client, user_agent="test"),
            ignore_robots=True,
            blocked_url_patterns=(),
            excluded_scopes=(),
            thumbnails=blobs,
        )
        tracker.record_page(
            page_id=page_id,
            base_url="https://site.test/",
            body=(
                b'<a href="https://other.test/a.pdf">A</a>'
                b'<a href="https://other.test/copy-of-a.pdf">Copy</a>'
            ),
        )
        tracker.queue_page(page_id, lambda _ok: None)
        await tracker.drain()
    return [
        (str(row[0]), row[1])
        for row in conn.execute(
            "SELECT url, thumbnail_hash || ' ' || thumbnail_small_hash FROM linked_files "
            "WHERE scan_id = ? ORDER BY url",
            (scan_id,),
        )
    ]


async def test_a_checked_pdf_keeps_a_picture_its_copy_shares(
    tmp_db: sqlite3.Connection, tmp_path: Path
) -> None:
    blobs = BlobStore(tmp_path / "blobs")
    rows = await _check_two_copies(tmp_db, blobs)
    pairs = {thumbnail for _url, thumbnail in rows}
    assert len(rows) == 2
    # Both copies point at the same two pictures, each stored once.
    assert len(pairs) == 1
    (pair,) = pairs
    assert pair is not None
    large, small = pair.split(" ")
    assert large != small
    assert blobs.path_of(large, "image/jpeg").is_file()
    assert blobs.path_of(small, "image/jpeg").is_file()


async def test_no_picture_when_the_scan_stores_no_rendered_pages(
    tmp_db: sqlite3.Connection,
) -> None:
    rows = await _check_two_copies(tmp_db, None)
    assert [thumbnail for _url, thumbnail in rows] == [None, None]


def test_the_migration_rolls_back_and_forward(tmp_db: sqlite3.Connection) -> None:
    migrations = Path(__file__).parents[2] / "src/audit/db/migrations"
    forward = (migrations / "0041_linked_file_thumbnails.sql").read_text()
    rollback = (migrations / "0041_linked_file_thumbnails.rollback.sql").read_text()

    added = {"thumbnail_hash", "thumbnail_small_hash"}

    def columns() -> set[str]:
        return {row[1] for row in tmp_db.execute("PRAGMA table_info(linked_files)")}

    assert added <= columns()
    tmp_db.executescript(rollback)
    assert not added & columns()
    tmp_db.executescript(forward)
    assert added <= columns()
