"""A crawl saves each frame's document with the page, placed by parent and position.

The fixture page (tests/fixtures/site/saved-frames/) has a same-site frame
with a frame inside it that the frame's own code fills (as Google Sites fills
its embeds), a ``srcdoc`` frame, and an ``<iframe>`` inside ``<noscript>``,
which is text while scripts run and must not shift the count the inspector
uses to put each frame back.
"""

from __future__ import annotations

import asyncio
import gzip
import sqlite3
from pathlib import Path

import pytest

from audit.crawler.orchestrator import CrawlConfig, run_crawl

from .test_saved_copy_styles_crawl import _serve

pytestmark = pytest.mark.integration


def _frames(conn: sqlite3.Connection, scan_id: int) -> list[tuple[int, int, int, str, str]]:
    rows = conn.execute(
        "SELECT frame_id, parent_id, frame_index, url, html FROM page_frames "
        "WHERE scan_id = ? ORDER BY frame_id",
        (scan_id,),
    ).fetchall()
    return [
        (
            r["frame_id"],
            r["parent_id"],
            r["frame_index"],
            r["url"],
            gzip.decompress(r["html"]).decode(),
        )
        for r in rows
    ]


def _config(base: str, **overrides: object) -> CrawlConfig:
    return CrawlConfig(
        js_eager=True,
        seed_url=f"{base}/saved-frames/",
        max_pages=1,
        rps=100.0,
        workers=1,
        vlm_enabled=False,
        semantic_enabled=False,
        interaction_checks_enabled=False,
        **overrides,  # type: ignore[arg-type]
    )


def test_a_crawl_saves_frames_where_the_inspector_can_put_them_back(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base)))
    frames = _frames(tmp_db, summary.scan_id)

    by_place = {(parent, index): (fid, url, html) for fid, parent, index, url, html in frames}
    assert set(by_place) == {(0, 0), (0, 1), (by_place[(0, 0)][0], 0)}, frames
    same_site_id, same_site_url, same_site = by_place[(0, 0)]
    assert same_site_url.endswith("/saved-frames/frame.html")
    assert "Inside the frame" in same_site
    assert "From srcdoc" in by_place[(0, 1)][2]
    # The frame inside the frame was filled by code: only the scan saw it.
    assert "Built by script" in by_place[(same_site_id, 0)][2]


def test_no_frames_are_saved_when_the_scan_keeps_no_copies(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base, store_rendered_html=False)))
    assert _frames(tmp_db, summary.scan_id) == []
