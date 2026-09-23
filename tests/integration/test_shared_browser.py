"""The module's shared browser keeps tests apart (tests/integration/conftest.py).

One Chromium serves every test in a module, so what keeps a test from seeing
another's cookies, storage or permissions is the context it opens, which the
page fixtures here build per test and close. Two runs of the same test each
check that they start clean, then leave all of that behind for the next.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio(loop_scope="module")

ORIGIN = "https://isolation.test"
STORED = "() => [localStorage.length, sessionStorage.length]"
STORE = "() => { localStorage.setItem('left', '1'); sessionStorage.setItem('left', '1'); }"

_seen: dict[str, list[Any]] = {"browsers": [], "contexts": []}


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    # The same shape as the page fixtures in this directory.
    ctx = await browser.new_context()
    try:
        await ctx.route(
            f"{ORIGIN}/**",
            lambda route: route.fulfill(content_type="text/html", body="<title>isolation</title>"),
        )
        p = await ctx.new_page()
        await p.goto(f"{ORIGIN}/")
        yield p
    finally:
        await ctx.close()


async def _geolocation(page) -> str:  # type: ignore[no-untyped-def]
    state: str = await page.evaluate(
        "async () => (await navigator.permissions.query({name: 'geolocation'})).state"
    )
    return state


@pytest.mark.parametrize("run", ["first", "second"])
async def test_each_test_starts_from_a_clean_context(browser, page, run) -> None:  # type: ignore[no-untyped-def]
    # One browser for the module, but no earlier test's context is open or reused.
    assert all(earlier is browser for earlier in _seen["browsers"])
    assert browser.contexts == [page.context]
    assert all(earlier is not page.context for earlier in _seen["contexts"])
    # Nor is anything an earlier test left behind.
    assert await page.context.cookies() == []
    assert await page.evaluate(STORED) == [0, 0]
    assert await _geolocation(page) != "granted"

    _seen["browsers"].append(browser)
    _seen["contexts"].append(page.context)
    await page.context.add_cookies([{"name": "left", "value": run, "url": ORIGIN}])
    await page.evaluate(STORE)
    await page.context.grant_permissions(["geolocation"], origin=ORIGIN)
    # The state is really there, so the next run's checks mean something.
    assert len(await page.context.cookies()) == 1
    assert await page.evaluate(STORED) == [1, 1]
    assert await _geolocation(page) == "granted"
