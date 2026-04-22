"""End-to-end VLM pipeline against the fixture site with a stub provider.

We don't hit a real Ollama daemon here — :class:`_StubVlm` records the
context it receives and returns a canned classification so we can verify:
  * only OCR text-candidates are routed to the VLM,
  * OCR text and context are threaded into the provider,
  * the combined analyses row carries both OCR fields and VLM fields,
  * the --skip-vlm equivalent (``vlm_enabled=False``) disables routing.

A separate live test is gated on ``AUDIT_OLLAMA_LIVE=1`` so developers can
exercise a real VLM when one is installed.
"""

from __future__ import annotations

import asyncio
import http.server
import os
import shutil
import socketserver
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from audit.analyzer.vlm.base import Classification, ClassifyContext, VlmLabel
from audit.analyzer.vlm.ollama import OllamaProvider
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


class _StubVlm:
    """In-memory :class:`VlmProvider` that records every call."""

    model_version = "stub-vlm:1.0"
    prompt_version = "v1-stub"

    def __init__(self, label: VlmLabel = VlmLabel.ESSENTIAL) -> None:
        self._label = label
        self.calls: list[ClassifyContext] = []

    async def classify(
        self, image_bytes: bytes, mime: str, context: ClassifyContext
    ) -> Classification:
        self.calls.append(context)
        return Classification(
            label=self._label,
            rationale=f"stub: {self._label.value}",
            model_version=self.model_version,
            prompt_version=self.prompt_version,
        )


def _config(base: str, *, vlm_enabled: bool = True) -> CrawlConfig:
    return CrawlConfig(
        seed_url=f"{base}/gallery.html",
        max_pages=5,
        rps=100.0,
        workers=2,
        ocr_max_workers=0,
        vlm_enabled=vlm_enabled,
    )


def test_only_text_candidates_are_sent_to_vlm(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    stub = _StubVlm(label=VlmLabel.ESSENTIAL)
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=stub))

    assert summary.status == "completed"
    assert summary.ocr_text_candidates >= 1
    # Stub should have been called exactly for text candidates.
    assert summary.vlm_classified == summary.ocr_text_candidates
    assert len(stub.calls) == summary.vlm_classified

    # The text-banner call should carry both the alt text and the OCR output.
    banner_calls = [c for c in stub.calls if c.ocr_text and "buy" in c.ocr_text.lower()]
    assert banner_calls
    banner_ctx = banner_calls[0]
    assert banner_ctx.alt_text == "Banner"
    assert banner_ctx.ocr_text


def test_combined_analyses_row_has_both_ocr_and_vlm(
    tmp_db: sqlite3.Connection, blob_dir: Path
) -> None:
    with _serve() as base:
        asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))

    rows = tmp_db.execute(
        """
        SELECT a.ocr_text, a.ocr_confidence, a.vlm_classification, a.vlm_rationale,
               a.model_versions_json, i.src_url_canonical
          FROM analyses a
          JOIN images i ON i.id = a.image_id
         WHERE a.vlm_classification IS NOT NULL
        """
    ).fetchall()
    assert rows, "expected at least one row with VLM classification"
    row = rows[0]
    assert row["ocr_text"]
    assert row["ocr_confidence"] is not None
    assert row["vlm_classification"] == "essential"
    assert row["vlm_rationale"]
    # model_versions_json should contain both ocr and vlm keys.
    assert '"ocr"' in row["model_versions_json"]
    assert '"vlm"' in row["model_versions_json"]
    assert '"prompt"' in row["model_versions_json"]


def test_non_candidates_stay_ocr_only(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    with _serve() as base:
        asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))

    blank_rows = tmp_db.execute(
        """
        SELECT a.vlm_classification, a.model_versions_json
          FROM analyses a
          JOIN images i ON i.id = a.image_id
         WHERE i.src_url_canonical LIKE '%blank%'
        """
    ).fetchall()
    assert blank_rows
    for row in blank_rows:
        assert row["vlm_classification"] is None
        assert '"vlm"' not in row["model_versions_json"]


def test_skip_vlm_disables_routing(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    stub = _StubVlm()
    with _serve() as base:
        summary = asyncio.run(
            run_crawl(tmp_db, _config(base, vlm_enabled=False), vlm_provider=stub)
        )

    assert summary.vlm_classified == 0
    assert stub.calls == []
    row = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM analyses WHERE vlm_classification IS NOT NULL"
    ).fetchone()
    assert row["n"] == 0


@pytest.mark.skipif(
    os.environ.get("AUDIT_OLLAMA_LIVE") != "1",
    reason="set AUDIT_OLLAMA_LIVE=1 to exercise a real Ollama daemon",
)
def test_live_ollama_classifies_text_banner(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    """Hits the real Ollama daemon. Requires the model from AUDIT_VLM_MODEL (or qwen2-vl:2b)."""
    model = os.environ.get("AUDIT_VLM_MODEL", "qwen2-vl:2b")

    async def go() -> tuple[int, int]:
        async with httpx.AsyncClient() as client:
            provider = OllamaProvider(client, model=model)
            assert await provider.healthy(), f"Ollama model {model} not available"
            with _serve() as base:
                summary = await run_crawl(
                    tmp_db,
                    _config(base),
                    http_client=client,
                    vlm_provider=provider,
                )
            return summary.vlm_classified, summary.vlm_errors

    classified, errors = asyncio.run(go())
    assert classified >= 1
    assert errors == 0
