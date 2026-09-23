"""Shared fixtures for UI tests.

Builds a fresh tmp DB and blob store, seeds them with a few findings, and
exposes a FastAPI ``TestClient`` so route-level tests don't need a browser.
Playwright-based tests in ``test_accessibility_axe.py`` use the same seed
data via a live uvicorn server, and open their pages with ``new_page``.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import uvicorn
from fastapi.testclient import TestClient

from audit.blob_store import BlobStore
from audit.db import repo
from audit.db.schema import connect
from audit.synthesizer.findings import synthesize_findings
from audit.web.server import create_app

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page


def _seed(conn: sqlite3.Connection, blob_dir: Path) -> int:
    """Create a scan with a mix of findings. Returns the scan id."""
    store = BlobStore(blob_dir)

    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES ('http://example.com/', 'completed', 2, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)

    page_a = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://example.com/",
        status_code=200,
        title="Home",
        render_mode="static",
        html_hash="0" * 64,
    )
    page_b = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://example.com/about",
        status_code=200,
        title="About",
        render_mode="static",
        html_hash="1" * 64,
    )

    # Essential banner with missing alt — will become high severity.
    png_bytes = _pixel_png()
    png_hash, png_rel = store.store(png_bytes, "image/png")
    banner_id = repo.upsert_image(
        conn,
        content_hash=png_hash,
        src_url="http://example.com/banner.png",
        mime="image/png",
        bytes_len=len(png_bytes),
        width=40,
        height=40,
        blob_path=png_rel,
        has_svg_text=False,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        conn,
        page_id=page_a,
        image_id=banner_id,
        alt_text=None,
        role=None,
        context_snippet="Buy our widgets",
        position=0,
        above_fold=True,
    )
    repo.upsert_page_image(
        conn,
        page_id=page_b,
        image_id=banner_id,
        alt_text=None,
        role=None,
        context_snippet="Buy our widgets",
        position=1,
        above_fold=False,
    )
    repo.upsert_analysis(
        conn,
        image_id=banner_id,
        ocr_text="BUY OUR WIDGETS TODAY",
        ocr_confidence=92.5,
        vlm_classification="essential",
        vlm_rationale="Clearly text-as-image promoting an offer.",
        has_text=True,
        model_versions={"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"},
    )

    # Logo with correct alt — will become info.
    logo_bytes = _pixel_png(color=(50, 50, 200))
    logo_hash, logo_rel = store.store(logo_bytes, "image/png")
    logo_id = repo.upsert_image(
        conn,
        content_hash=logo_hash,
        src_url="http://example.com/logo.png",
        mime="image/png",
        bytes_len=len(logo_bytes),
        width=40,
        height=40,
        blob_path=logo_rel,
        has_svg_text=False,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        conn,
        page_id=page_a,
        image_id=logo_id,
        alt_text="Acme Corp",
        role=None,
        context_snippet=None,
        position=2,
    )
    repo.upsert_analysis(
        conn,
        image_id=logo_id,
        ocr_text="Acme Corp",
        ocr_confidence=88.0,
        vlm_classification="logo",
        vlm_rationale="Brand mark.",
        has_text=True,
        model_versions={"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"},
    )

    synthesize_findings(conn, scan_id=scan_id)
    return scan_id


def _pixel_png(color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (40, 40), color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def seeded_db(
    tmp_path: Path, migrate_db: Callable[[sqlite3.Connection], None]
) -> tuple[Path, Path, int]:
    """Return ``(db_path, blob_dir, scan_id)`` with a seeded schema."""
    db_path = tmp_path / "audit.db"
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir()
    conn = connect(db_path)
    try:
        migrate_db(conn)
        scan_id = _seed(conn, blob_dir)
    finally:
        conn.close()
    return db_path, blob_dir, scan_id


@pytest.fixture
def client(seeded_db: tuple[Path, Path, int]) -> TestClient:
    """FastAPI TestClient pointed at the seeded DB + blob store."""
    db_path, blob_dir, _ = seeded_db
    return TestClient(create_app(db_path=db_path, blob_dir=blob_dir))


@pytest.fixture
def live_server(seeded_db: tuple[Path, Path, int]) -> Iterator[tuple[str, int]]:
    """Run the FastAPI app on an ephemeral port in a background thread.

    Yielded as ``(base_url, scan_id)``. Used by Playwright tests.
    """
    db_path, blob_dir, scan_id = seeded_db
    app = create_app(db_path=db_path, blob_dir=blob_dir)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for uvicorn to bind a port and start.
    for _ in range(100):
        if server.started and server.servers:
            break
        time.sleep(0.05)
    sock = server.servers[0].sockets[0]
    port = sock.getsockname()[1]
    try:
        yield (f"http://127.0.0.1:{port}", scan_id)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def browser() -> AsyncIterator[Browser]:
    """One Chromium for every test in a module.

    Launching it costs more than many of the tests that use it. Tests reach it
    through ``new_page``, never directly, so each one still starts from a
    context of its own. Playwright objects belong to the event loop that
    created them, so a module using this runs its tests on the module's loop:
    ``pytest.mark.asyncio(loop_scope="module")``. Off that loop they hang
    rather than fail. A bare ``@pytest.mark.asyncio`` on a test overrides the
    module's mark and does exactly that, so tests/conftest.py refuses to
    collect one.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            yield browser
        finally:
            await browser.close()


@pytest_asyncio.fixture(loop_scope="module")
async def new_page(browser: Browser) -> AsyncIterator[Callable[..., Awaitable[Page]]]:
    """``Browser.new_page`` for one test: a fresh context per page, closed after.

    Takes the same options, so cookies, storage, permissions, routes and the
    viewport never carry from one test, or one page, to the next.
    """
    contexts: list[BrowserContext] = []

    async def open_page(**options: Any) -> Page:
        context = await browser.new_context(**options)
        contexts.append(context)
        return await context.new_page()

    try:
        yield open_page
    finally:
        for context in contexts:
            await context.close()
