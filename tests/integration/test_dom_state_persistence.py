"""A revealed finding must be able to reach the markup it was found in.

The interaction fixtures are the only pages in the suite whose defects do not
exist until something is clicked, which makes them the only place this can be
tested end to end: crawl, capture, store, and join back.
"""

from __future__ import annotations

import asyncio
import gzip
import http.server
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
    # The interaction pages are not linked from the site index, so the
    # directory listing is the seed that reaches all of them.
    return CrawlConfig(
        js_eager=True,
        seed_url=f"{base}/interaction/",
        max_pages=10,
        rps=100.0,
        workers=2,
        vlm_enabled=False,
        semantic_enabled=False,
        **overrides,  # type: ignore[arg-type]
    )


def test_revealed_findings_can_reach_their_captured_state(
    tmp_db: sqlite3.Connection,
) -> None:
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base)))

    revealed = tmp_db.execute(
        "SELECT f.revealed_by, f.revealed_state_key FROM page_a11y_findings f "
        "JOIN pages p ON p.id = f.page_id "
        "WHERE p.scan_id = ? AND f.revealed_by IS NOT NULL",
        (summary.scan_id,),
    ).fetchall()
    assert revealed, "the interaction fixtures must produce revealed findings"

    states = {
        row["state_key"]: row
        for row in tmp_db.execute(
            "SELECT * FROM page_dom_states WHERE scan_id = ?", (summary.scan_id,)
        )
    }
    assert states, "revealed findings must come with their states"

    # The join that the inspector will make. Without it a reviewer is sent to
    # look for an element in a document that never contained it.
    for row in revealed:
        assert row["revealed_state_key"], f"{row['revealed_by']} has no state key"
        assert row["revealed_state_key"] in states, row["revealed_by"]

    for row in states.values():
        assert row["encoding"] == "gzip"
        assert gzip.decompress(row["dom"]).lstrip().lower().startswith(b"<!doctype")

    # A capture is only kept for a state that held something new, so there can
    # never be more of them than the pass counted.
    counted = tmp_db.execute(
        "SELECT COALESCE(SUM(states), 0) AS total FROM scan_interaction_runs WHERE scan_id = ?",
        (summary.scan_id,),
    ).fetchone()["total"]
    assert len(states) <= counted


def test_declining_to_store_pages_declines_to_store_states(
    tmp_db: sqlite3.Connection,
) -> None:
    """The opt-out covers both: they are the same documents from the same site.

    Refused at the probe rather than at the write, so the markup is never held
    in memory either — which matters most on the protected path, where these
    are captured after authentication.
    """
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base, store_rendered_html=False)))

    assert tmp_db.execute(
        "SELECT COUNT(*) AS c FROM page_dom_states WHERE scan_id = ?",
        (summary.scan_id,),
    ).fetchone()["c"] == 0
    # The findings themselves are unaffected; only their markup is withheld.
    assert tmp_db.execute(
        "SELECT COUNT(*) AS c FROM page_a11y_findings f JOIN pages p ON p.id = f.page_id "
        "WHERE p.scan_id = ? AND f.revealed_by IS NOT NULL",
        (summary.scan_id,),
    ).fetchone()["c"] > 0
