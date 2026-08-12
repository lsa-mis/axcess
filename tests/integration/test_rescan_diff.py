"""End-to-end rescan + diff against a mutable copy of the fixture site.

Flow:
  1. Copy ``tests/fixtures/site`` into a tmp dir.
  2. Serve it on an ephemeral port; run a first crawl with a stub VLM.
  3. Mutate the site (add an alt on the banner, delete a page).
  4. Run a second crawl.
  5. Assert compute_diff buckets the changes correctly and that
     ``finding_history`` has first_seen + resolved rows.

Gated on tesseract being installed because the full crawl path runs OCR.
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

from audit.analyzer.vlm.base import Classification, ClassifyContext, VlmLabel
from audit.crawler.orchestrator import CrawlConfig, run_crawl
from audit.synthesizer.diff import compute_diff

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed"),
]

SRC_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "site"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _serve(root: Path) -> Iterator[str]:
    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(root), **kw)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


class _StubVlm:
    model_version = "stub-vlm:1.0"
    prompt_version = "v1-stub"

    async def classify(
        self, image_bytes: bytes, mime: str, context: ClassifyContext
    ) -> Classification:
        lowered = (context.ocr_text or "").lower()
        label = VlmLabel.ESSENTIAL if "buy" in lowered else VlmLabel.LOGO
        return Classification(
            label=label,
            rationale=f"stub:{label.value}",
            model_version=self.model_version,
            prompt_version=self.prompt_version,
        )


@pytest.fixture
def site_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Copy the fixture site to a writable tmp dir and point blobs there."""
    dest = tmp_path / "site"
    shutil.copytree(SRC_FIXTURE, dest)
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir()
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(blob_dir))
    return dest


def _config(base: str, **overrides: object) -> CrawlConfig:
    defaults: dict[str, object] = {
        "js_eager": False,  # pin the pre-flip fast path; rendering isn't under test
        "seed_url": f"{base}/gallery.html",
        "max_pages": 20,
        "rps": 100.0,
        "workers": 1,
        "ocr_max_workers": 0,
        "vlm_enabled": True,
        # This suite uses a stub VLM; semantic rules are tested separately and
        # must not turn fixture tests into live Ollama calls.
        "semantic_enabled": False,
    }
    defaults.update(overrides)
    return CrawlConfig(**defaults)  # type: ignore[arg-type]


def test_rescan_diff_buckets_new_resolved_and_still_open(
    tmp_db: sqlite3.Connection, site_copy: Path
) -> None:
    with _serve(site_copy) as base:
        first = asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))
        # Mutate site between crawls:
        #   - add a brand new page, with its own occurrence of the text banner
        #     (so compute_diff sees a fresh (content_hash, url) pair)
        #   - drop the banner from gallery.html (simulates a remediation)
        #   - link gallery.html → promo.html so the crawler discovers it
        new_page = site_copy / "promo.html"
        new_page.write_text(
            "<!doctype html><html><body>"
            '<a href="/gallery.html">Back</a>'
            "<h1>Promo</h1>"
            '<img src="/images/text-banner.png" alt="Buy now today">'
            "</body></html>",
            encoding="utf-8",
        )
        gallery = site_copy / "gallery.html"
        mutated = gallery.read_text(encoding="utf-8").replace(
            '<img src="/images/text-banner.png" alt="Banner">',
            '<a href="/promo.html">Promo</a>',
        )
        gallery.write_text(mutated, encoding="utf-8")

        second = asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))

    assert first.status == "completed"
    assert second.status == "completed"
    assert first.scan_id != second.scan_id

    # Orchestrator should have picked up the previous scan automatically.
    assert second.compare_to_scan_id == first.scan_id
    # At least one finding appeared or disappeared between the two scans.
    assert (second.first_seen + second.resolved) >= 1

    report = compute_diff(
        tmp_db,
        current_scan_id=second.scan_id,
        compare_to_scan_id=first.scan_id,
    )
    new_urls = {e.url_normalized for e in report.new}
    resolved_urls = {e.url_normalized for e in report.resolved}

    # The banner occurrence on gallery.html should be resolved.
    assert any("gallery.html" in u for u in resolved_urls)
    # Some new URL should have appeared (promo.html with the banner).
    assert any("promo.html" in u for u in new_urls)

    # finding_history got system-authored rows.
    rows = tmp_db.execute(
        "SELECT change_type, COUNT(*) AS n FROM finding_history "
        "WHERE scan_id = ? GROUP BY change_type",
        (second.scan_id,),
    ).fetchall()
    by_type = {r["change_type"]: int(r["n"]) for r in rows}
    assert by_type.get("first_seen", 0) >= 1
    assert by_type.get("resolved", 0) >= 1


def test_rescan_no_changes_gives_empty_first_seen_and_resolved(
    tmp_db: sqlite3.Connection, site_copy: Path
) -> None:
    with _serve(site_copy) as base:
        first = asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))
        second = asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.first_seen == 0
    assert second.resolved == 0
    report = compute_diff(
        tmp_db,
        current_scan_id=second.scan_id,
        compare_to_scan_id=first.scan_id,
    )
    assert report.new == []
    assert report.resolved == []
