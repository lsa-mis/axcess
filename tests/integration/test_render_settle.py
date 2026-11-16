"""The page must be filled in before axe and the saved copy read it.

``networkidle`` means the network went quiet, not that the page finished
rendering. Alpine fills ``x-text`` and removes ``x-cloak`` when it starts;
a framework's next tick or a timer can still be changing the page after the
last request. ``settle_dom`` waits, bounded, for the page code to stop
changing and for every cloak attribute to go.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import pytest_asyncio

from audit.crawler.js_fetcher import settle_dom

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "settle" / "late_render.html"

playwright = pytest.importorskip("playwright.async_api")

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        yield await ctx.new_page()
    finally:
        await ctx.close()


async def test_waits_for_cloak_and_late_content(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(FIXTURE.as_uri(), wait_until="load")
    await page.wait_for_load_state("networkidle")
    assert await page.locator("#late-button").count() == 0, "fixture rendered too early"
    assert await settle_dom(page) == "settled"
    assert await page.locator("#late-button").count() == 1
    assert await page.text_content("#filled") == "Menu ready"
    assert await page.locator("[x-cloak]").count() == 0


async def test_gives_up_on_a_page_that_never_stops(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content(
        "<p id='t'>0</p><script>let n = 0;"
        "setInterval(() => { document.getElementById('t').textContent = ++n; }, 30);</script>"
    )
    started = time.monotonic()
    assert await settle_dom(page, max_ms=600) == "timeout"
    assert time.monotonic() - started < 2.0


async def test_attribute_changes_do_not_hold_it_open(page) -> None:  # type: ignore[no-untyped-def]
    # A carousel rewriting style forever must not cost the cap on every page.
    await page.set_content(
        "<div id='c'></div><script>let n = 0;"
        "setInterval(() => { document.getElementById('c').style.left = (++n) + 'px'; }, 30);"
        "</script>"
    )
    assert await settle_dom(page, max_ms=1500) == "settled"
