"""The network guard always lifts itself, even when a time limit cancels it.

On a real page (get.foundation) the form error check's 30-second limit fired
while the guard was being installed. Playwright had recorded the route but
the guard's cleanup never ran, so every later request in that browser
context was refused. A stand-in page pins both moments a cancellation can
land, while the route is installed and while it is removed, and that a
cleanup the browser never answers cannot hang the caller.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from audit.analyzer.interaction.safety import exploration_guard


class _Context:
    def __init__(self, *, slow_route: bool = False, slow_unroute: bool = False) -> None:
        self.service_workers: list[Any] = []
        self.routes: list[Any] = []
        self.slow_route = slow_route
        self.slow_unroute = slow_unroute

    async def route(self, pattern: str, handler: Any) -> None:
        # As Playwright does: record the handler first, then wait on the browser.
        self.routes.append(handler)
        if self.slow_route:
            await asyncio.sleep(10)

    async def unroute(self, pattern: str, handler: Any) -> None:
        if self.slow_unroute:
            await asyncio.sleep(0.05)
        self.routes.remove(handler)


class _Page:
    def __init__(self, context: _Context) -> None:
        self.url = "https://example.org/form"
        self.context = context
        self.listeners: list[str] = []

    def on(self, event: str, handler: Any) -> None:
        self.listeners.append(event)

    def remove_listener(self, event: str, handler: Any) -> None:
        self.listeners.remove(event)


async def test_cancelled_while_installing_still_lifts() -> None:
    context = _Context(slow_route=True)
    page = _Page(context)

    async def guarded() -> None:
        async with exploration_guard(page, set(), (), strict=True):  # type: ignore[arg-type]
            raise AssertionError("the body must not run")

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await guarded()
    assert context.routes == []
    assert page.listeners == []


async def test_cancelled_while_lifting_still_finishes() -> None:
    context = _Context(slow_unroute=True)
    page = _Page(context)

    async def guarded() -> None:
        async with exploration_guard(page, set(), (), strict=True):  # type: ignore[arg-type]
            await asyncio.sleep(0.04)

    # The limit lands after the body, during the slow unroute.
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.06):
            await guarded()
    assert context.routes == []
    assert page.listeners == []


async def test_cleanup_that_never_finishes_cannot_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    import audit.analyzer.interaction.safety as safety

    monkeypatch.setattr(safety, "_LIFT_TIMEOUT_S", 0.1)

    class _Stuck(_Context):
        async def unroute(self, pattern: str, handler: Any) -> None:
            await asyncio.Event().wait()  # a browser that stopped answering

    page = _Page(_Stuck())

    async def guarded() -> None:
        async with exploration_guard(page, set(), (), strict=True):  # type: ignore[arg-type]
            await asyncio.sleep(10)

    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await guarded()
    assert asyncio.get_running_loop().time() - started < 2
