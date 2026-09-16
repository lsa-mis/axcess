"""Edits the inspector makes to a capture before rendering it, and their limit.

A stored capture is correct markup that renders wrongly the moment it leaves
the site it came from: its relative URLs resolve against the review UI, its
`crossorigin` stylesheets become cross-origin CORS requests the origin server
never agreed to, and its `<noscript>` fallback appears because the frame runs
with scripts disabled. Those edits exist to render the evidence, never to
change it, so the DOM-source view must keep showing exactly what was stored.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path

import pytest
from playwright import async_api as playwright_async

from audit.db.schema import connect

pytestmark = pytest.mark.ui

CAPTURE = (
    "<!doctype html><html><head><title>App</title>"
    # Same-origin on the real site, cross-origin here.
    '<link rel="stylesheet" crossorigin="" href="/assets/app.css">'
    '<link rel="stylesheet" crossorigin href="/assets/other.css">'
    "</head><body>"
    "<noscript>You need to enable JavaScript to run this app.</noscript>"
    '<div id="app">Hydrated content</div>'
    "</body></html>"
)


def _seed_capture(db_path: Path, scan_id: int) -> int:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(CAPTURE.encode()), page["id"]),
        )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_the_rendered_frame_drops_what_would_break_the_capture(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
) -> None:
    """Without these the page renders as unstyled serif text under a banner
    telling the reviewer to enable JavaScript, on a capture taken with
    JavaScript running."""
    db_path, _, scan_id = seeded_db
    page_id = _seed_capture(db_path, scan_id)
    base = live_server[0]

    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(
                f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect",
                wait_until="domcontentloaded",
            )
            await page.locator("iframe").wait_for(timeout=15000)
            await page.wait_for_timeout(1500)
            frame = page.frame_locator("iframe")
            state = await frame.locator("html").evaluate(
                """el => ({
                    crossorigin: el.querySelectorAll('link[crossorigin]').length,
                    links: el.querySelectorAll('link[rel="stylesheet"]').length,
                    noscript: el.querySelectorAll('noscript').length,
                    base: el.querySelectorAll('base[href]').length,
                    body: el.querySelector('#app')?.textContent || '',
                })"""
            )
        finally:
            await browser.close()

    assert state["crossorigin"] == 0, "a CORS-mode stylesheet request is refused here"
    # Dropped the attribute, not the stylesheet.
    assert state["links"] == 2
    assert state["noscript"] == 0, "the capture was taken with JavaScript running"
    assert state["base"] == 1, "relative URLs must resolve against the scanned site"
    assert state["body"] == "Hydrated content"


@pytest.mark.asyncio
async def test_the_dom_source_view_still_shows_the_capture_as_stored(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
) -> None:
    """That tab is the evidence. Rendering edits must not reach it."""
    db_path, _, scan_id = seeded_db
    page_id = _seed_capture(db_path, scan_id)
    base = live_server[0]

    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(
                f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?view=dom",
                wait_until="domcontentloaded",
            )
            source = await page.locator('pre[aria-label="Loaded DOM source"]').inner_text()
        finally:
            await browser.close()

    assert "crossorigin" in source
    assert "noscript" in source
    assert "<base href" not in source
