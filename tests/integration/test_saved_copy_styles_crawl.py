"""A crawl saves each copy's CSS, in cascade order, including script-added rules.

The fixture page (tests/fixtures/site/saved-styles/) has a linked stylesheet
that imports another, an inline ``<style>``, a rule a script inserted through
``insertRule`` (which ``page.content()`` serializes as an empty element), and a
CSP ``<meta>`` whose ``style-src 'self'`` would refuse the site's own CSS once
``'self'`` means the review UI. After a crawl the saved CSS must hold all of
them, in order, with URLs resolved against the site.
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

import pytest

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


def _config(base: str, **overrides: object) -> CrawlConfig:
    return CrawlConfig(
        js_eager=True,
        seed_url=f"{base}/saved-styles/",
        max_pages=1,
        rps=100.0,
        workers=1,
        vlm_enabled=False,
        semantic_enabled=False,
        interaction_checks_enabled=False,
        **overrides,  # type: ignore[arg-type]
    )


def _saved_css(conn: sqlite3.Connection, blob_dir: Path, scan_id: int) -> tuple[str, dict]:  # type: ignore[type-arg]
    row = conn.execute(
        "SELECT sheets_json, complete, fingerprint_json FROM saved_copy_styles "
        "WHERE scan_id = ? AND state_key = ''",
        (scan_id,),
    ).fetchone()
    assert row is not None, "the page's CSS was not saved"
    sheets = json.loads(row["sheets_json"])
    texts = [
        (blob_dir / s["sha256"][:2] / f"{s['sha256']}.css").read_text(encoding="utf-8")
        for s in sheets
    ]
    return "\n".join(texts), {
        "complete": row["complete"],
        "fingerprint": json.loads(row["fingerprint_json"]),
        "sheets": sheets,
    }


def test_the_crawl_saves_every_rule_in_cascade_order(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob_dir = tmp_path / "blobs"
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(blob_dir))
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base)))
        css, meta = _saved_css(tmp_db, blob_dir, summary.scan_id)

    order = [
        css.index(".imported-rule"),
        css.index(".linked-rule"),
        css.index(".inline-rule"),
        css.index(".script-rule"),
    ]
    assert order == sorted(order), css
    assert "@import" not in css
    assert "@charset" not in css
    # Relative to the sheet that wrote it, made absolute.
    assert f'url("{base}/saved-styles/img/dot.png")' in css
    assert meta["complete"] == 1
    assert meta["sheets"][0]["source_url"] == f"{base}/saved-styles/css/base.css"

    samples = meta["fingerprint"]["samples"]
    assert samples, "the fingerprint is recorded in the same evaluate"
    colors = {s["color"] for s in samples}
    assert {"rgb(128, 0, 0)", "rgb(0, 128, 0)", "rgb(0, 0, 255)"} <= colors
    assert meta["fingerprint"]["scheme"] == "light"


def test_a_scan_that_keeps_no_copies_keeps_no_css(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob_dir = tmp_path / "blobs"
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(blob_dir))
    with _serve() as base:
        asyncio.run(run_crawl(tmp_db, _config(base, store_rendered_html=False)))

    assert tmp_db.execute("SELECT COUNT(*) FROM saved_copy_styles").fetchone()[0] == 0
    assert not list(blob_dir.rglob("*.css"))


def test_each_captured_page_state_gets_its_own_css(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read while the state is open, through the probe's capture."""
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    with _serve() as base:
        summary = asyncio.run(
            run_crawl(
                tmp_db,
                CrawlConfig(
                    js_eager=True,
                    seed_url=f"{base}/interaction/",
                    max_pages=10,
                    rps=100.0,
                    workers=2,
                    vlm_enabled=False,
                    semantic_enabled=False,
                ),
            )
        )

    states = {
        row["state_key"]
        for row in tmp_db.execute(
            "SELECT state_key FROM page_dom_states WHERE scan_id = ?", (summary.scan_id,)
        )
    }
    styled = {
        row["state_key"]
        for row in tmp_db.execute(
            "SELECT state_key FROM saved_copy_styles WHERE scan_id = ? AND state_key != ''",
            (summary.scan_id,),
        )
    }
    assert states, "the interaction fixtures must capture page states"
    assert styled == states
