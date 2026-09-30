"""``new_page`` keeps tests apart on the module's shared browser (tests/ui/conftest.py).

One Chromium serves every test in a module, so what keeps a test from seeing
another's cookies, storage or permissions is that ``new_page`` opens every
page in a context of its own and closes them all when the test ends. Two
runs of the same test each check that they start clean, then leave all of
that behind for the next. Only this test reaches ``browser`` directly, to
inspect it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="module")

ORIGIN = "https://isolation.test"
STORED = "() => [localStorage.length, sessionStorage.length]"
STORE = "() => { localStorage.setItem('left', '1'); sessionStorage.setItem('left', '1'); }"
GEOLOCATION = "async () => (await navigator.permissions.query({name: 'geolocation'})).state"

_seen: dict[str, list[Any]] = {"browsers": [], "contexts": []}


async def _open(new_page: Callable[..., Awaitable[Any]], **options: Any) -> Any:
    page = await new_page(**options)
    await page.route(
        f"{ORIGIN}/**",
        lambda route: route.fulfill(content_type="text/html", body="<title>isolation</title>"),
    )
    await page.goto(f"{ORIGIN}/")
    return page


async def _assert_clean(page: Any) -> None:
    assert await page.context.cookies() == []
    assert await page.evaluate(STORED) == [0, 0]
    assert await page.evaluate(GEOLOCATION) != "granted"


@pytest.mark.parametrize("run", ["first", "second"])
async def test_every_page_starts_from_a_clean_context(browser, new_page, run) -> None:  # type: ignore[no-untyped-def]
    page = await _open(new_page)
    # One browser for the module, but no earlier test's context is open or reused.
    assert all(earlier is browser for earlier in _seen["browsers"])
    assert browser.contexts == [page.context]
    assert all(earlier is not page.context for earlier in _seen["contexts"])
    # Nor is anything an earlier test left behind.
    await _assert_clean(page)

    _seen["browsers"].append(browser)
    _seen["contexts"].append(page.context)
    await page.context.add_cookies([{"name": "left", "value": run, "url": ORIGIN}])
    await page.evaluate(STORE)
    await page.context.grant_permissions(["geolocation"], origin=ORIGIN)
    # The state is really there, so the next page's checks mean something.
    assert len(await page.context.cookies()) == 1
    assert await page.evaluate(STORED) == [1, 1]
    assert await page.evaluate(GEOLOCATION) == "granted"

    # A second page in the same test gets its own context, and the options.
    other = await _open(new_page, viewport={"width": 320, "height": 640})
    assert other.context is not page.context
    assert other.viewport_size == {"width": 320, "height": 640}
    assert {id(context) for context in browser.contexts} == {id(page.context), id(other.context)}
    await _assert_clean(other)
    _seen["contexts"].append(other.context)
