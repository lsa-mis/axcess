"""End-to-end image extraction against the local fixture site."""

from __future__ import annotations

import asyncio
import http.server
import socketserver
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from audit.blob_store import BlobStore
from audit.crawler.orchestrator import CrawlConfig, run_crawl

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


@pytest.fixture
def blob_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the orchestrator's blob store at a tmp dir via AUDIT_BLOB_DIR."""
    d = tmp_path / "blobs"
    d.mkdir()
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(d))
    return d


def test_gallery_page_persists_images_and_svg_text(
    tmp_db: sqlite3.Connection, blob_dir: Path
) -> None:
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/gallery.html",
            max_pages=5,
            rps=100.0,
            workers=2,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    assert summary.status == "completed"
    assert summary.images_persisted >= 2  # at least blank.png and photo.jpg
    assert summary.svg_text_hits == 1  # ACME logo is the only SVG with text
    # /images/missing.png 404 should register as an image error.
    assert summary.image_errors >= 1

    # Blob store has at least one PNG and one JPEG file.
    ext_set = {p.suffix for p in blob_dir.rglob("*.*") if not p.name.endswith(".tmp")}
    assert ".png" in ext_set
    assert ".jpg" in ext_set

    # DB: images table has has_svg_text=1 row with blob_path NULL
    rows = tmp_db.execute(
        "SELECT content_hash, blob_path, has_svg_text, mime FROM images"
    ).fetchall()
    svg_rows = [r for r in rows if r["has_svg_text"] == 1]
    assert len(svg_rows) == 1
    assert svg_rows[0]["blob_path"] is None
    assert svg_rows[0]["mime"] == "image/svg+xml"

    # page_images: figcaption is captured; decorative image (alt="") is preserved.
    gallery_page_id = tmp_db.execute(
        "SELECT id FROM pages WHERE url_normalized LIKE ?", (f"{base}/gallery.html",)
    ).fetchone()["id"]
    page_imgs = tmp_db.execute(
        "SELECT alt_text, role, context_snippet FROM page_images "
        "WHERE page_id = ? ORDER BY position",
        (gallery_page_id,),
    ).fetchall()
    # At least one row must have alt='' (decorative image)
    alt_values = [r["alt_text"] for r in page_imgs]
    assert "" in alt_values
    # At least one row must reference the figcaption text
    assert any(
        r["context_snippet"] and "Plain gray square" in r["context_snippet"] for r in page_imgs
    )


def test_same_image_on_two_pages_dedupes_to_one_images_row(
    tmp_db: sqlite3.Connection, blob_dir: Path
) -> None:
    """srcset 1x and picture source both reference blank@2x.png; only one images row."""
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/gallery.html",
            max_pages=5,
            rps=100.0,
            workers=1,
            vlm_enabled=False,
            semantic_enabled=False,
            capture_screenshots=False,
        )
        asyncio.run(run_crawl(tmp_db, config))

    # blank.png, blank@2x.png, text-banner.png → 3 distinct-bytes PNGs, deduped.
    row = tmp_db.execute("SELECT COUNT(*) AS n FROM images WHERE blob_path LIKE '%.png'").fetchone()
    assert row["n"] == 3

    # Confirm the blob store has exactly 3 PNG files too.
    pngs = [p for p in blob_dir.rglob("*.png") if not p.name.endswith(".tmp")]
    assert len(pngs) == 3


def test_blob_store_contents_match_db(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    with _serve() as base:
        config = CrawlConfig(
            js_eager=False,
            seed_url=f"{base}/gallery.html",
            max_pages=5,
            rps=100.0,
            workers=1,
            vlm_enabled=False,
            semantic_enabled=False,
        )
        asyncio.run(run_crawl(tmp_db, config))

    store = BlobStore(blob_dir)
    rows = tmp_db.execute(
        "SELECT content_hash, blob_path FROM images WHERE blob_path IS NOT NULL"
    ).fetchall()
    for row in rows:
        assert store.path_for(row["blob_path"]).exists()
