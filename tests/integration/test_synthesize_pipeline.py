"""End-to-end synthesis against the fixture site with a stub VLM.

Covers the crawl → OCR → VLM (stub) → synthesize path producing findings
rows with expected severity mix. Separate assertions exercise the same
synthesize_findings function called twice (idempotence at the orchestrator
layer, not just at the repo layer).
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
from audit.synthesizer.findings import synthesize_findings

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
    """Returns ESSENTIAL for anything with banner-like OCR text, LOGO otherwise."""

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


def _config(base: str, **overrides: object) -> CrawlConfig:
    defaults: dict[str, object] = {
        "seed_url": f"{base}/gallery.html",
        "max_pages": 5,
        "rps": 100.0,
        "workers": 1,
        "ocr_max_workers": 0,
    }
    defaults.update(overrides)
    return CrawlConfig(**defaults)  # type: ignore[arg-type]


def test_crawl_writes_findings_rows(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))

    assert summary.status == "completed"
    assert summary.findings_written >= 1
    assert sum(summary.findings_by_severity.values()) == summary.findings_written

    # Banner image should produce the highest-severity finding (essential + banner alt match).
    rows = tmp_db.execute(
        """
        SELECT f.severity, f.priority_score, f.remediation_hint, i.src_url_canonical
          FROM findings f
          JOIN images i ON i.id = f.image_id
         WHERE f.scan_id = ?
        """,
        (summary.scan_id,),
    ).fetchall()
    by_url = {row["src_url_canonical"]: row for row in rows}
    banner = next(
        (v for k, v in by_url.items() if "text-banner.png" in k),
        None,
    )
    assert banner is not None
    # essential(4) + some adequacy + log1p(1) = at least minor, likely major
    assert banner["severity"] in ("major", "minor", "critical")
    assert banner["remediation_hint"] and "alt" in banner["remediation_hint"].lower()

    # Scan row should reflect the finding count.
    scan_row = tmp_db.execute(
        "SELECT finding_count FROM scans WHERE id = ?", (summary.scan_id,)
    ).fetchone()
    assert scan_row["finding_count"] == summary.findings_written


def test_inline_svg_text_produces_finding(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))

    svg_rows = tmp_db.execute(
        """
        SELECT f.severity, i.has_svg_text, i.mime
          FROM findings f
          JOIN images i ON i.id = f.image_id
         WHERE f.scan_id = ? AND i.has_svg_text = 1
        """,
        (summary.scan_id,),
    ).fetchall()
    assert svg_rows, "expected a finding for the inline SVG text"


def test_skip_synthesize_does_not_write_findings(
    tmp_db: sqlite3.Connection, blob_dir: Path
) -> None:
    with _serve() as base:
        summary = asyncio.run(
            run_crawl(
                tmp_db,
                _config(base, synthesize_enabled=False),
                vlm_provider=_StubVlm(),
            )
        )

    assert summary.findings_written == 0
    count = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM findings WHERE scan_id = ?", (summary.scan_id,)
    ).fetchone()["n"]
    assert count == 0

    # Running synthesize_findings after the fact should produce the same
    # output the automatic path would have.
    after = synthesize_findings(tmp_db, scan_id=summary.scan_id)
    assert after.findings_written >= 1


def test_idempotent_synthesis_after_crawl(tmp_db: sqlite3.Connection, blob_dir: Path) -> None:
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base), vlm_provider=_StubVlm()))

    original = summary.findings_written
    again = synthesize_findings(tmp_db, scan_id=summary.scan_id)
    assert again.findings_written == original
    # No duplicate rows.
    count = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM findings WHERE scan_id = ?", (summary.scan_id,)
    ).fetchone()["n"]
    assert count == original
