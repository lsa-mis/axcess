"""Integration test for the live-page element screenshot helper.

Exercises ``JsFetcher._capture_element`` against a real Playwright page
built from inline HTML. Two cases:

  * A known element (``#x``) → non-empty PNG bytes (signature ``\\x89PNG``).
  * A missing element (``#missing``) → ``None``.

Skipped when Playwright + chromium aren't installed, mirroring how the
keyboard-trap integration tests gate. We don't need a fixture HTTP
server: ``page.set_content`` renders the markup in-process.
"""

from __future__ import annotations

import pytest

from audit.crawler.js_fetcher import JsFetcher

# Skip the whole module if Playwright isn't importable / chromium not installed.
playwright = pytest.importorskip("playwright.async_api")


@pytest.fixture
async def browser():  # type: ignore[no-untyped-def]
    """One headless chromium per test."""
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            await browser.close()
    finally:
        await pw.stop()


@pytest.fixture
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context()
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


def _fetcher() -> JsFetcher:
    """A JsFetcher with capture on; only ``_capture_element`` is exercised."""
    return JsFetcher(user_agent="test", capture_screenshots=True)


async def test_capture_element_returns_png_for_known_element(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content("<html><body><button id='x'>Hi</button></body></html>")
    png = await _fetcher()._capture_element(page, "#x")
    assert png is not None
    assert png[:4] == b"\x89PNG"


async def test_capture_element_returns_none_for_missing_element(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content("<html><body><button id='x'>Hi</button></body></html>")
    assert await _fetcher()._capture_element(page, "#missing") is None
