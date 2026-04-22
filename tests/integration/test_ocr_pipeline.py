"""End-to-end OCR pipeline against the fixture site.

Requires a real tesseract binary. Generates a PNG with known text at test
time (instead of checking it in) so font-availability doesn't drift between
contributor machines.
"""

from __future__ import annotations

import asyncio
import http.server
import shutil
import socketserver
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from audit.crawler.orchestrator import CrawlConfig, run_crawl

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed"),
]

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
    d = tmp_path / "blobs"
    d.mkdir()
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(d))
    return d


def _config(base: str, **overrides: object) -> CrawlConfig:
    defaults: dict[str, object] = {
        "seed_url": f"{base}/gallery.html",
        "max_pages": 5,
        "rps": 100.0,
        "workers": 2,
        "ocr_max_workers": 0,  # in-process for test determinism
        "vlm_enabled": False,
    }
    defaults.update(overrides)
    return CrawlConfig(**defaults)  # type: ignore[arg-type]


def test_text_banner_is_flagged_as_text_candidate(
    tmp_db: sqlite3.Connection, blob_dir: Path
) -> None:
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base)))

    assert summary.status == "completed"
    assert summary.ocr_analyzed >= 3  # blank, 2x, photo, banner (and any picture sources)
    assert summary.ocr_text_candidates >= 1  # banner should land as a candidate

    # Join analyses to page_images → find the text-banner row and confirm has_text=1.
    rows = tmp_db.execute(
        """
        SELECT a.has_text, a.ocr_text, a.ocr_confidence, i.src_url_canonical
          FROM analyses a
          JOIN images i ON i.id = a.image_id
        """
    ).fetchall()
    banner_rows = [r for r in rows if "text-banner.png" in (r["src_url_canonical"] or "")]
    assert banner_rows, "expected an analysis row for text-banner.png"
    banner = banner_rows[0]
    assert banner["has_text"] == 1
    assert banner["ocr_confidence"] is not None and banner["ocr_confidence"] > 0
    lowered = (banner["ocr_text"] or "").lower()
    assert any(tok in lowered for tok in ("buy", "now", "today"))


def test_blank_image_does_not_pass_text_candidate_gate(
    tmp_db: sqlite3.Connection, blob_dir: Path
) -> None:
    with _serve() as base:
        asyncio.run(run_crawl(tmp_db, _config(base)))

    rows = tmp_db.execute(
        """
        SELECT a.has_text, i.src_url_canonical
          FROM analyses a
          JOIN images i ON i.id = a.image_id
         WHERE i.src_url_canonical LIKE '%blank%.png'
        """
    ).fetchall()
    assert rows, "expected analyses for the blank fixture"
    assert all(r["has_text"] == 0 for r in rows)


def test_skip_ocr_flag_disables_analysis(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base, ocr_enabled=False)))

    assert summary.ocr_analyzed == 0
    assert summary.images_persisted > 0  # images still downloaded
    rows = tmp_db.execute("SELECT COUNT(*) AS n FROM analyses").fetchone()
    assert rows["n"] == 0


def test_svg_image_is_not_sent_to_ocr(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    with _serve() as base:
        asyncio.run(run_crawl(tmp_db, _config(base)))

    rows = tmp_db.execute(
        """
        SELECT i.mime
          FROM analyses a
          JOIN images i ON i.id = a.image_id
        """
    ).fetchall()
    mimes = {r["mime"] for r in rows}
    assert "image/svg+xml" not in mimes
