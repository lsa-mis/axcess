"""Shared fixtures for the integration suite.

Launching Chromium costs more than most of the browser tests that use it,
and a test needs a clean context, not a clean browser. So a module gets one
browser, and each test builds its own context from it and closes it: cookies,
storage, permissions, routes and the viewport all stay per test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest_asyncio

if TYPE_CHECKING:
    from playwright.async_api import Browser


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def browser() -> AsyncIterator[Browser]:
    """One headless Chromium for every test in a module.

    Playwright objects belong to the event loop that created them, so the
    tests and fixtures that touch this browser must run on the module's
    loop: mark the module ``pytest.mark.asyncio(loop_scope="module")`` and
    give its async fixtures ``loop_scope="module"`` as well.
    """
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
