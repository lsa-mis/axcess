"""What the shipped probes actually report for modal dialogs.

Asana 1218150268010182 asked whether the keyboard probe covers modal
dialogs. This module records the answer against the fixtures in
``tests/fixtures/site/sc_2_1_2/modal_verify/``; the write-up is
``docs/keyboard-probe-modal-verification.md``.

These tests pin current behaviour, including gaps. A test that asserts
"nothing is reported" for a broken modal documents a known limit, not a
desired outcome: if the probe learns to catch that case, update the test
and the verification doc together.

Each fixture switches off one piece of correct modal behaviour:

  good, no-trap, no-escape, no-return, no-exit, hard-trap
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe
from audit.analyzer.keyboard import KeyboardProbe
from audit.analyzer.keyboard.base import RULE_NO_ESCAPE, RULE_STUCK

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures/site/sc_2_1_2/modal_verify"
VARIANTS = ("good", "no-trap", "no-escape", "no-return", "no-exit", "hard-trap")
SOFT_FAILURES = ("no-trap", "no-escape", "no-return", "no-exit")

playwright = pytest.importorskip("playwright.async_api")
pytestmark = pytest.mark.asyncio(loop_scope="module")

_ACTIVE = "() => { const a = document.activeElement; return a ? (a.id || a.tagName) : null; }"


def _url(variant: str, *, open_at_load: bool = False) -> str:
    uri = (FIXTURE_DIR / f"{variant}.html").resolve().as_uri()
    return uri + "?open=1" if open_at_load else uri


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        yield await ctx.new_page()
    finally:
        await ctx.close()


@pytest.fixture
def axe() -> AxeAnalyzer:
    return AxeAnalyzer.from_bundled()


# --------------------------------------------------------------------
# The fixtures themselves: prove each one has the defect it claims, so
# a "nothing reported" result below cannot be blamed on a broken page.
# --------------------------------------------------------------------


async def _open_and_tab(page, variant: str) -> list[str]:  # type: ignore[no-untyped-def]
    await page.goto(_url(variant))
    await page.focus("#trigger")
    await page.keyboard.press("Enter")
    seen = []
    for _ in range(4):
        await page.keyboard.press("Tab")
        seen.append(await page.evaluate(_ACTIVE))
    return seen


async def test_fixture_good_keeps_tab_inside_and_returns_focus(page) -> None:  # type: ignore[no-untyped-def]
    assert await _open_and_tab(page, "good") == ["close", "name", "close", "name"]
    await page.keyboard.press("Escape")
    assert await page.evaluate("() => document.getElementById('dialog').hidden")
    assert await page.evaluate(_ACTIVE) == "trigger"


async def test_fixture_no_trap_lets_tab_leave(page) -> None:  # type: ignore[no-untyped-def]
    seen = await _open_and_tab(page, "no-trap")
    assert "trigger" in seen or "A" in seen, seen


async def test_fixture_no_escape_ignores_escape(page) -> None:  # type: ignore[no-untyped-def]
    await _open_and_tab(page, "no-escape")
    await page.keyboard.press("Escape")
    assert not await page.evaluate("() => document.getElementById('dialog').hidden")


async def test_fixture_no_return_drops_focus_on_close(page) -> None:  # type: ignore[no-untyped-def]
    await _open_and_tab(page, "no-return")
    await page.keyboard.press("Escape")
    assert await page.evaluate(_ACTIVE) == "BODY"


async def test_fixture_hard_trap_holds_focus(page) -> None:  # type: ignore[no-untyped-def]
    assert await _open_and_tab(page, "hard-trap") == ["name"] * 4
    await page.keyboard.press("Shift+Tab")
    await page.keyboard.press("Escape")
    assert await page.evaluate(_ACTIVE) == "name"


# --------------------------------------------------------------------
# Keyboard probe (pipeline "keyboard", SC 2.1.2): the only probe that
# writes modal-related occurrences to page_a11y_findings.
# --------------------------------------------------------------------


@pytest.mark.parametrize("variant", VARIANTS)
async def test_keyboard_probe_never_opens_a_closed_dialog(page, variant: str) -> None:  # type: ignore[no-untyped-def]
    """It runs on the page as loaded; a dialog behind a button is never walked.

    Known limit: includes hard-trap, a real SC 2.1.2 failure.
    """
    await page.goto(_url(variant))
    assert await KeyboardProbe(max_focusable=20, stuck_threshold=4).run(page) == []


@pytest.mark.parametrize("variant", ("good", *SOFT_FAILURES))
async def test_keyboard_probe_reports_nothing_for_open_soft_failures(page, variant: str) -> None:  # type: ignore[no-untyped-def]
    """Missing Tab containment, Escape or focus return is not a 2.1.2 lead."""
    await page.goto(_url(variant, open_at_load=True))
    assert await KeyboardProbe(max_focusable=20, stuck_threshold=4).run(page) == []


async def test_keyboard_probe_catches_hard_trap_open_at_load(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_url("hard-trap", open_at_load=True))
    findings = await KeyboardProbe(max_focusable=20, stuck_threshold=4).run(page)
    assert [(f.rule_id, f.target_selector) for f in findings] == [(RULE_STUCK, "input#name")]
    assert "4 Tab attempts and 4 Shift+Tab attempts" in findings[0].failure_summary


@pytest.mark.parametrize("variant", ("no-escape", "no-exit", "hard-trap"))
async def test_disabled_escape_check_would_flag_ignored_escape(page, variant: str) -> None:  # type: ignore[no-untyped-def]
    """``_probe_modal_escape`` still works but ``run()`` deliberately skips it."""
    await page.goto(_url(variant, open_at_load=True))
    legacy = await KeyboardProbe()._probe_modal_escape(page)
    assert [f.rule_id for f in legacy] == [RULE_NO_ESCAPE]


# --------------------------------------------------------------------
# Interaction probe ("Click-Through"): opens dialogs by clicking, but
# only checks whether they close again. Results are coverage counts,
# not occurrences.
# --------------------------------------------------------------------


@pytest.mark.parametrize("variant", ("good", *SOFT_FAILURES))
async def test_interaction_probe_opens_and_closes_soft_failures(page, axe, variant: str) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_url(variant))
    result = await InteractionProbe(axe=axe).run(page, baseline=await axe.run(page, "AA"))
    assert result.dialogs_opened == 1
    assert result.dialogs_stuck == 0
    assert result.findings == ()


async def test_interaction_probe_counts_hard_trap_as_stuck_dialog(page, axe) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_url("hard-trap"))
    result = await InteractionProbe(axe=axe).run(page, baseline=await axe.run(page, "AA"))
    assert result.dialogs_opened == 1
    assert result.dialogs_stuck == 1
    assert "dialog_not_dismissed" in result.limits
    assert "did not close (tried Escape)" in result.detail
    assert result.findings == ()
