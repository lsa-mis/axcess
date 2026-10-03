"""Edits the inspector makes to a capture before rendering it, and their limit.

A stored capture is correct markup that renders wrongly the moment it leaves
the site it came from: its relative URLs resolve against the review UI (and a
relative `<base>` of its own against `about:srcdoc`), its `crossorigin`
stylesheets become cross-origin CORS requests the origin server never agreed
to (and `integrity` can then never pass), its Content-Security-Policy `<meta>`
treats the review UI as `'self'` and refuses the site's own stylesheets, and
its `<noscript>` fallback appears because the frame runs with scripts
disabled. Those edits exist to render the evidence, never to
change it, so the DOM-source view must keep showing exactly what was stored.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

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


# A page whose own policy names only CDNs besides 'self', with an SRI-pinned
# stylesheet and its own relative <base>, as Angular apps write it.
CAPTURE_WITH_POLICY = (
    "<!doctype html><html><head><title>App</title>"
    '<meta http-equiv="Content-Security-Policy" '
    "content=\"default-src 'self'; style-src 'self' https://cdn.example.net\">"
    '<base href="/static/">'
    '<link rel="stylesheet" href="assets/app.css" '
    'integrity="sha384-abc" crossorigin="anonymous">'
    '</head><body><div id="app">Hydrated content</div></body></html>'
)


def _seed_capture(
    db_path: Path, scan_id: int, capture: str = CAPTURE, path: str | None = None
) -> int:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if path is None:
            page = conn.execute(
                "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
            ).fetchone()
        else:
            page = conn.execute(
                "SELECT id FROM pages WHERE scan_id = ? AND url_normalized = ?",
                (scan_id, f"http://example.com{path}"),
            ).fetchone()
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(capture.encode()), page["id"]),
        )
        conn.commit()
        return int(page["id"])
    finally:
        conn.close()


async def test_the_rendered_frame_drops_what_would_break_the_capture(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Without these the page renders as unstyled serif text under a banner
    telling the reviewer to enable JavaScript, on a capture taken with
    JavaScript running."""
    db_path, _, scan_id = seeded_db
    page_id = _seed_capture(db_path, scan_id)
    base = live_server[0]

    page = await new_page(viewport={"width": 1280, "height": 900})
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

    assert state["crossorigin"] == 0, "a CORS-mode stylesheet request is refused here"
    # Dropped the attribute, not the stylesheet.
    assert state["links"] == 2
    assert state["noscript"] == 0, "the capture was taken with JavaScript running"
    assert state["base"] == 1, "relative URLs must resolve against the scanned site"
    assert state["body"] == "Hydrated content"


async def test_the_dom_source_view_still_shows_the_capture_as_stored(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """That tab is the evidence. Rendering edits must not reach it."""
    db_path, _, scan_id = seeded_db
    page_id = _seed_capture(db_path, scan_id)
    base = live_server[0]

    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?view=dom",
        wait_until="domcontentloaded",
    )
    # The source view prints one node per line from the capture; the
    # wording of the stored markup has to survive that unchanged.
    source = await page.locator('[aria-label="Scrollable page code (DOM)"]').inner_text()

    assert "crossorigin" in source
    assert "noscript" in source
    assert "<base href" not in source


async def test_the_site_policy_integrity_and_relative_base_do_not_unstyle_the_capture(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Each of these alone renders a styled page as plain HTML in the frame."""
    db_path, _, scan_id = seeded_db
    page_id = _seed_capture(db_path, scan_id, CAPTURE_WITH_POLICY, "/about")
    base = live_server[0]

    page = await new_page(viewport={"width": 1280, "height": 900})
    refusals: list[str] = []
    page.on(
        "console",
        lambda m: refusals.append(m.text) if "Content Security Policy" in m.text else None,
    )
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect",
        wait_until="domcontentloaded",
    )
    await page.locator("iframe").wait_for(timeout=15000)
    await page.wait_for_timeout(1500)
    state = (
        await page.frame_locator("iframe")
        .locator("html")
        .evaluate(
            """el => ({
            policy: el.querySelectorAll('meta[http-equiv]').length,
            integrity: el.querySelectorAll('link[integrity]').length,
            crossorigin: el.querySelectorAll('link[crossorigin]').length,
            firstBase: el.querySelector('base')?.getAttribute('href'),
            baseURI: el.ownerDocument.baseURI,
            sheet: el.querySelector('link[rel="stylesheet"]')?.href,
            body: el.querySelector('#app')?.textContent || '',
        })"""
        )
    )

    assert state["policy"] == 0, "'self' would mean the review UI and refuse the site's CSS"
    assert not [r for r in refusals if "app.css" in r]
    assert state["integrity"] == 0, "integrity can only pass on a CORS request"
    assert state["crossorigin"] == 0
    # The page's own base, resolved against its address, comes first and wins.
    assert state["firstBase"] == "http://example.com/static/"
    assert state["baseURI"] == "http://example.com/static/"
    assert state["sheet"] == "http://example.com/static/assets/app.css"
    assert state["body"] == "Hydrated content"

    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?view=dom",
        wait_until="domcontentloaded",
    )
    source = await page.locator('[aria-label="Scrollable page code (DOM)"]').inner_text()
    # The evidence keeps all three.
    assert "Content-Security-Policy" in source
    assert "integrity" in source
    assert '<base href="/static/">' in source
