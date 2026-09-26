"""Integration test for the live-page element screenshot helper.

Exercises ``JsFetcher._capture_element`` against a real Playwright page
built from inline HTML:

  * A known element (``#x``) → non-empty PNG bytes (signature ``\\x89PNG``).
  * A missing element (``#missing``) → ``None``.
  * Short text in a wide block → the outline hugs the text, not the row.
  * An element at the viewport's bottom edge → centering keeps context below.

Skipped when Playwright + chromium aren't installed, mirroring how the
keyboard-trap integration tests gate. We don't need a fixture HTTP
server: ``page.set_content`` renders the markup in-process.
"""

from __future__ import annotations

import io

import pytest
import pytest_asyncio
from PIL import Image

from audit.crawler.js_fetcher import JsFetcher

# Skip the whole module if Playwright isn't importable / chromium not installed.
playwright = pytest.importorskip("playwright.async_api")

# One browser per module (tests/integration/conftest.py), so the tests run on
# the module's event loop. Each still gets its own context from ``page``.
pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(loop_scope="module")
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
    assert len(_marker_xs(png)) > 20  # issue-location outline


async def test_capture_element_returns_none_for_missing_element(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content("<html><body><button id='x'>Hi</button></body></html>")
    assert await _fetcher()._capture_element(page, "#missing") is None


async def test_outline_hugs_short_text_in_a_wide_block(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content(
        "<html><body><p id='x' style='width:600px;margin:80px'>Hi</p></body></html>"
    )
    png = await _fetcher()._capture_element(page, "#x")
    assert png is not None
    image = Image.open(io.BytesIO(png))
    assert image.width > 600  # the capture still spans the whole block
    # The text starts at the 56px capture padding; a block-sized outline would
    # reach past x=656 instead of stopping just after the two letters.
    assert max(_marker_xs(png)) < 150


async def test_centered_capture_keeps_context_below_an_edge_element(page) -> None:  # type: ignore[no-untyped-def]
    # Default context viewport is 720px tall; the button ends just above it.
    await page.set_content(
        "<html><body style='margin:0'><div style='height:690px'></div>"
        "<button id='x' style='height:24px'>Hi</button>"
        "<div style='height:2000px'></div></body></html>"
    )
    fetcher = _fetcher()
    edge = await fetcher._capture_element(page, "#x")
    await page.evaluate("window.scrollTo(0, 0)")
    centered = await fetcher._capture_element(page, "#x", center=True)
    assert edge is not None
    assert centered is not None
    # Uncentered, the capture is cut off at the viewport's bottom edge.
    assert Image.open(io.BytesIO(edge)).height < 24 + 2 * 56
    assert Image.open(io.BytesIO(centered)).height >= 24 + 2 * 56


def _marker_xs(png: bytes) -> list[int]:
    """X positions of the marker's red stroke pixels."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    return [
        index % image.width
        for index, (red, green, blue) in enumerate(image.get_flattened_data())
        if red >= 170 and green <= 50 and blue <= 70
    ]
