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


# A copy the scan saved CSS for: its own stylesheets would come from the live
# site (and here the site's policy would refuse them), the saved file holds
# the rules a script added, which the markup has as an empty <style>.
CAPTURE_WITH_SAVED_STYLES = (
    "<!doctype html><html><head><title>App</title>"
    '<meta http-equiv="Content-Security-Policy" content="style-src \'self\'">'
    '<link rel="stylesheet" href="/assets/app.css" integrity="sha384-abc" crossorigin>'
    '<link rel="preload" href="/assets/font.woff2" as="font">'
    "<style>#app { color: rgb(255, 0, 0); }</style><style></style>"
    '</head><body><div id="app">Hydrated content</div>'
    "<style>.late { color: red; }</style></body></html>"
)


def _seed_saved_styles(
    db_path: Path, blob_dir: Path, page_id: int, scan_id: int, css: str, *, complete: bool = True
) -> None:
    from audit.blob_store import BlobStore
    from audit.crawler.style_snapshot import SheetRef, StoredStyles
    from audit.db import repo

    digest, _ = BlobStore(blob_dir).store(css.encode(), "text/css")
    conn = connect(db_path)
    try:
        repo.set_page_styles(
            conn,
            scan_id=scan_id,
            page_id=page_id,
            styles=StoredStyles(
                sheets=(SheetRef(sha256=digest, media="", source_url=None),),
                complete=complete,
                fingerprint={},
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def test_a_copy_with_saved_styles_uses_them_instead_of_the_sites(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The saved file comes from the review UI, so nothing can refuse it."""
    db_path, blob_dir, scan_id = seeded_db
    page_id = _seed_capture(db_path, scan_id, CAPTURE_WITH_SAVED_STYLES)
    _seed_saved_styles(db_path, blob_dir, page_id, scan_id, "#app { color: rgb(0, 0, 255); }")
    base = live_server[0]

    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect",
        wait_until="domcontentloaded",
    )
    await page.locator("iframe").wait_for(timeout=15000)
    frame = page.frame_locator("iframe")
    await frame.locator("link[data-axcess-saved-styles]").wait_for(state="attached", timeout=15000)
    await page.wait_for_timeout(500)
    state = await frame.locator("html").evaluate(
        """el => ({
            sheets: Array.from(el.querySelectorAll('link[rel~="stylesheet"]')).map(l => l.href),
            styles: el.querySelectorAll('style').length,
            preload: el.querySelectorAll('link[rel="preload"]').length,
            policy: el.querySelectorAll('meta[http-equiv]').length,
            base: el.querySelector('base')?.getAttribute('href'),
            lastInHead: el.querySelector('head').lastElementChild?.hasAttribute(
                'data-axcess-saved-styles'),
            color: getComputedStyle(el.querySelector('#app')).color,
        })"""
    )

    assert len(state["sheets"]) == 1
    assert state["sheets"][0].startswith(
        f"{base}/api/scans/{scan_id}/pages/{page_id}/saved-styles.css?v="
    ), "absolute on the review UI, not resolved against the site's <base>"
    assert state["styles"] == 0, "the copy's own rules are in the saved file"
    assert state["preload"] == 1, "only stylesheets are replaced"
    assert state["policy"] == 0
    assert state["base"] == "http://example.com/", "fonts and images still come from the site"
    assert state["lastInHead"]
    assert state["color"] == "rgb(0, 0, 255)"

    # The evidence tab still shows the copy exactly as stored.
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect?view=dom",
        wait_until="domcontentloaded",
    )
    source = await page.locator('[aria-label="Scrollable page code (DOM)"]').inner_text()
    assert "/assets/app.css" in source
    assert "saved-styles.css" not in source


# The page the style check is tested on: varied fonts and colours, with the
# elements the sample order skips (noscript, script, template, a <style> in
# the body) placed before the sampled ones, so a filter that disagreed with
# the capture's would look up the wrong elements.
STYLE_CHECK_PAGE = (
    "<!doctype html><html><head><title>Check</title><style>"
    "body { font-family: Georgia, serif; color: rgb(20, 20, 20); }"
    "h1 { font-family: 'Trebuchet MS', sans-serif; color: rgb(120, 0, 0); }"
    ".a { color: rgb(0, 90, 0); background-color: rgb(250, 240, 200); }"
    ".b { font-weight: 700; text-decoration: underline; }"
    "a { color: rgb(0, 0, 160); }"
    "</style></head><body>"
    "<noscript><p>off</p></noscript><script>var x = 1;</script>"
    "<template><p>inert</p></template><style>.late { color: rgb(1, 2, 3); }</style>"
    "<h1>Heading</h1>"
    + "".join(
        f'<p class="{"a" if i % 2 else "b"}">Paragraph {i} <a href="#">link {i}</a></p>'
        for i in range(30)
    )
    + "</body></html>"
)


async def _capture_for_seed(new_page: Any) -> tuple[str, Any]:
    """Render the page and take its copy and styles the way the crawl does."""
    from audit.crawler.style_snapshot import SheetCache, capture_styles

    live = await new_page()
    await live.set_content(STYLE_CHECK_PAGE)
    html = await live.content()
    snapshot = await capture_styles(live, SheetCache())
    assert snapshot is not None and snapshot.fingerprint["samples"]
    return html, snapshot


def _seed_snapshot(
    db_path: Path, blob_dir: Path, scan_id: int, page_id: int, snapshot: Any, *, css: str | None
) -> None:
    from audit.blob_store import BlobStore
    from audit.crawler.style_snapshot import SheetRef, StoredStyles
    from audit.db import repo

    store = BlobStore(blob_dir)
    texts = [sheet.css for sheet in snapshot.sheets] if css is None else [css]
    conn = connect(db_path)
    try:
        repo.set_page_styles(
            conn,
            scan_id=scan_id,
            page_id=page_id,
            styles=StoredStyles(
                sheets=tuple(
                    SheetRef(
                        sha256=store.store(t.encode(), "text/css")[0], media="", source_url=None
                    )
                    for t in texts
                ),
                complete=snapshot.complete,
                fingerprint=snapshot.fingerprint,
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def _style_note(page: Any, base: str, scan_id: int, page_id: int) -> str:
    await page.goto(
        f"{base}/app/scans/{scan_id}/pages/{page_id}/inspect", wait_until="domcontentloaded"
    )
    await page.locator("iframe").wait_for(timeout=15000)
    await (
        page.frame_locator("iframe")
        .locator("link[data-axcess-saved-styles]")
        .wait_for(state="attached", timeout=15000)
    )
    # The check runs after load, fonts and a settle tick.
    await page.wait_for_timeout(2000)
    notes = page.get_by_role("status").filter(has_text="This saved copy may look different")
    return " ".join(await notes.all_inner_texts())


async def test_a_copy_that_renders_like_the_scan_shows_no_style_note(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The frame's sample order and styles agree with the capture's."""
    db_path, blob_dir, scan_id = seeded_db
    html, snapshot = await _capture_for_seed(new_page)
    page_id = _seed_capture(db_path, scan_id, html)
    _seed_snapshot(db_path, blob_dir, scan_id, page_id, snapshot, css=None)

    page = await new_page(viewport={"width": 1280, "height": 900})
    assert await _style_note(page, live_server[0], scan_id, page_id) == ""


async def test_a_copy_whose_styles_did_not_load_says_so(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    html, snapshot = await _capture_for_seed(new_page)
    page_id = _seed_capture(db_path, scan_id, html)
    # The saved file holds none of the page's rules.
    _seed_snapshot(db_path, blob_dir, scan_id, page_id, snapshot, css="/* nothing */")

    page = await new_page(viewport={"width": 1280, "height": 900})
    note = await _style_note(page, live_server[0], scan_id, page_id)
    assert "This saved copy may look different from the page Axcess checked." in note
    assert "Some of its styles may not have loaded." in note
    assert "Use Open live page to compare." in note
    # The note meets the same bar as the rest of the inspector (WCAG 2.2 AAA
    # pack, including 7:1 contrast), in the light theme it was drawn in.
    from .test_accessibility_axe import _render_violations, _run_axe

    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


async def test_an_incomplete_save_is_said_instead(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    from dataclasses import replace

    db_path, blob_dir, scan_id = seeded_db
    html, snapshot = await _capture_for_seed(new_page)
    page_id = _seed_capture(db_path, scan_id, html)
    _seed_snapshot(db_path, blob_dir, scan_id, page_id, replace(snapshot, complete=False), css=None)

    page = await new_page(viewport={"width": 1280, "height": 900})
    note = await _style_note(page, live_server[0], scan_id, page_id)
    assert "Axcess could not save all of this page's styles." in note
    assert "may not have loaded" not in note
