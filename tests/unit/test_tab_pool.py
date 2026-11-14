"""The signed-in tab pool: lending tabs, and falling back to the first."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from audit.crawler.tab_pool import TabPool


@dataclass(eq=False)
class _Tab:
    name: str
    closed: bool = False

    async def close(self, *, run_before_unload: bool) -> None:
        assert not run_before_unload
        self.closed = True


def _pool(n: int = 3, *, copied: bool = True) -> tuple[TabPool, list[_Tab]]:
    tabs = [_Tab(f"t{i}") for i in range(n)]
    return TabPool(tuple(tabs), copied_session=copied), tabs  # type: ignore[arg-type]


def test_only_copies_are_checked() -> None:
    assert _pool(3, copied=True)[0].checks_copies
    assert not _pool(3, copied=False)[0].checks_copies
    # One tab holds no copy, whatever the caller says.
    assert not _pool(1, copied=True)[0].checks_copies


@pytest.mark.asyncio
async def test_lends_every_tab_and_waits_when_none_is_free() -> None:
    pool, tabs = _pool(2)
    first = await pool.acquire()
    second = await pool.acquire()
    assert {first, second} == set(tabs)

    waiting = asyncio.create_task(pool.acquire())
    await asyncio.sleep(0)
    assert not waiting.done()
    await pool.release(first)
    assert await asyncio.wait_for(waiting, 1) is first


@pytest.mark.asyncio
async def test_primary_waits_for_the_first_tab_only() -> None:
    pool, tabs = _pool(3)
    held = await pool.acquire(primary=True)
    assert held is tabs[0]

    waiting = asyncio.create_task(pool.acquire(primary=True))
    await asyncio.sleep(0)
    assert not waiting.done(), "another tab is free, but only the first will do"
    await pool.release(held)
    assert await asyncio.wait_for(waiting, 1) is tabs[0]


@pytest.mark.asyncio
async def test_fall_back_closes_copies_now_or_when_returned() -> None:
    pool, tabs = _pool(3)
    busy = await pool.acquire()  # a worker holds a copy mid-page
    assert busy is tabs[0]
    busy = await pool.acquire()
    assert busy is tabs[1]

    assert await pool.fall_back() is True
    assert await pool.fall_back() is False, "reported once"
    assert pool.fell_back and not pool.checks_copies
    assert tabs[2].closed, "an idle copy closes at once"
    assert not tabs[1].closed, "a copy in use finishes its page first"

    await pool.release(tabs[1])
    assert tabs[1].closed
    await pool.release(tabs[0])
    assert not tabs[0].closed
    # From now on every page gets the first tab.
    assert await pool.acquire() is tabs[0]
    waiting = asyncio.create_task(pool.acquire())
    await asyncio.sleep(0)
    assert not waiting.done()
    await pool.release(tabs[0])
    assert await asyncio.wait_for(waiting, 1) is tabs[0]


def test_needs_a_tab() -> None:
    with pytest.raises(ValueError):
        TabPool(())
