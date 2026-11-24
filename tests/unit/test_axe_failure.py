"""An axe failure is an error with a reason, never an empty "nothing found"."""

from __future__ import annotations

from typing import Any

import pytest

from audit.analyzer.axe import AxeAnalyzer, AxeError
from audit.analyzer.interaction.probe import InteractionProbe, _Budget


class _Page:
    url = "https://example.edu/page"

    def __init__(self, *, fail_on: int) -> None:
        self.calls = 0
        self.fail_on = fail_on

    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("Execution context was destroyed")
        return True if self.calls == 1 else {"violations": [], "incomplete": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(("fail_on", "step"), [(1, "Adding axe-core"), (2, "Axe's check")])
async def test_a_failed_axe_run_raises_with_the_reason(fail_on: int, step: str) -> None:
    axe = AxeAnalyzer(axe_source="/* stub */")

    with pytest.raises(AxeError, match=f"{step}.*Execution context was destroyed"):
        await axe.run(_Page(fail_on=fail_on))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_sign_in_scan_reason_has_only_the_error_type() -> None:
    axe = AxeAnalyzer(axe_source="/* stub */", suppress_diagnostics=True)

    with pytest.raises(AxeError) as raised:
        await axe.run(_Page(fail_on=2))  # type: ignore[arg-type]

    assert str(raised.value) == "Axe's check of the page failed (RuntimeError)."


@pytest.mark.asyncio
async def test_no_axe_in_page_states_when_axe_failed_on_the_loaded_page() -> None:
    """Without the load baseline every state's results would look new."""

    class _Axe:
        calls = 0

        async def run(self, *args: Any, **kwargs: Any) -> list[Any]:
            _Axe.calls += 1
            return []

    probe = InteractionProbe(axe=_Axe())  # type: ignore[arg-type]
    budget = _Budget(remaining=5, use_axe=False)

    await probe._collect(object(), budget, [], "Menu")  # type: ignore[arg-type]

    assert _Axe.calls == 0
