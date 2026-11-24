"""Click-Through with Alfa: each page state adds an Alfa check of the top page."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from audit.analyzer.alfa import AlfaError, AlfaResult
from audit.analyzer.alfa_states import AlfaPageChecks
from audit.analyzer.interaction.probe import InteractionProbe, _Budget


class _Page:
    url = "https://example.test/"


class _Frame:
    """A frame inside the page; Alfa must snapshot the page, not the frame."""

    def __init__(self, page: _Page) -> None:
        self.page = page


class _Worker:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.targets: list[Any] = []

    async def submit(self, target: Any, *, level: str, version: str) -> asyncio.Task[AlfaResult]:
        self.targets.append(target)
        if self.fail:
            raise AlfaError("The page is too large for Alfa")

        async def done() -> AlfaResult:
            return AlfaResult(target.url, 200, (), 0, 0, False)

        return asyncio.get_running_loop().create_task(done())


@pytest.mark.asyncio
async def test_alfa_only_probe_adds_a_state_check_for_the_top_page() -> None:
    worker = _Worker()
    probe = InteractionProbe(axe=None, alfa=worker)  # type: ignore[arg-type]
    checks = AlfaPageChecks()
    budget = _Budget(remaining=5, alfa_checks=checks)
    page = _Page()

    await probe._collect(_Frame(page), budget, [], "Menu", "main|nav button|Menu")  # type: ignore[arg-type]

    assert worker.targets == [page]
    assert [(c.revealed_by, c.state_key) for c in checks.states] == [
        ("Menu", "main|nav button|Menu")
    ]
    await asyncio.gather(*checks.tasks())


@pytest.mark.asyncio
async def test_a_snapshot_that_fails_keeps_its_reason() -> None:
    probe = InteractionProbe(axe=None, alfa=_Worker(fail=True))  # type: ignore[arg-type]
    checks = AlfaPageChecks()
    budget = _Budget(remaining=5, alfa_checks=checks)

    await probe._collect(_Frame(_Page()), budget, [], "Menu")  # type: ignore[arg-type]

    assert checks.states == []
    assert checks.state_errors == ["The page is too large for Alfa"]


def _capture(key: str, html: bytes = b"x") -> Any:
    from audit.analyzer.interaction import StateCapture

    return StateCapture(state_key=key, revealed_by=key, path_labels=(key,), html=html)


def test_only_tentative_states_alfa_points_to_are_kept() -> None:
    from audit.crawler.orchestrator import _states_to_keep

    axe_state = _capture("menu")
    kept = _states_to_keep(
        (axe_state,),
        (_capture("menu", b"tentative"), _capture("dialog"), _capture("tabs")),
        {"menu", "dialog"},
    )

    # Axe's own capture wins for "menu"; "dialog" is kept for Alfa; "tabs",
    # which nothing points to, is dropped.
    assert [(c.state_key, c.html) for c in kept] == [("menu", b"x"), ("dialog", b"x")]
