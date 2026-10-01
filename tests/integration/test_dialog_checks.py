"""Keyboard checks on the dialogs Click-Through opens (``interaction.dialogs``).

Real Playwright, real axe, on ``tests/fixtures/site/dialogs/dialogs.html``:
one well-built modal, five broken ones (after the GDS audit's lightbox
cases, plus one with no keyboard way out), a status message and a disclosure
menu drawer, which must not be treated as dialogs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe, dialogs

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "dialogs" / "dialogs.html"

playwright = pytest.importorskip("playwright.async_api")
pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


async def _run(page, **kwargs):  # type: ignore[no-untyped-def]
    await page.goto(FIXTURE.as_uri())
    probe = InteractionProbe(axe=AxeAnalyzer.from_bundled(), **kwargs)
    return await probe.run(page)


def _by_rule(result) -> dict[str, set[str]]:  # type: ignore[no-untyped-def]
    out: dict[str, set[str]] = {}
    for f in result.keyboard_findings:
        out.setdefault(f.rule_id, set()).add(f.target_selector)
    return out


async def test_each_broken_dialog_fails_its_own_check_and_only_that(page) -> None:  # type: ignore[no-untyped-def]
    result = await _run(page, dialog_checks=True, max_dialog_checks=10)
    assert _by_rule(result) == {
        dialogs.RULE_FOCUS_NOT_MOVED: {"#far"},
        dialogs.RULE_CLOSE_NOT_FOCUSABLE: {"#spanclose > span:nth-of-type(1)"},
        # An undeclared lightbox is treated as modal: it also lets focus out.
        dialogs.RULE_FOCUS_ESCAPES: {"#far", "#leaky"},
        dialogs.RULE_ESCAPE_DOES_NOT_CLOSE: {"#stuck"},
        dialogs.RULE_NO_KEYBOARD_EXIT: {"#trapped"},
    }
    trap = next(f for f in result.keyboard_findings if f.rule_id == dialogs.RULE_NO_KEYBOARD_EXIT)
    assert (trap.criterion_sc, trap.wcag_level, trap.impact) == ("2.1.2", "A", "critical")
    escape = next(
        f for f in result.keyboard_findings if f.rule_id == dialogs.RULE_ESCAPE_DOES_NOT_CLOSE
    )
    # It has a close button the keyboard can use: best practice, not a trap.
    assert (escape.criterion_sc, escape.wcag_level, escape.impact) == ("", "", "moderate")
    row = next(
        f for f in result.keyboard_findings if f.rule_id == dialogs.RULE_FOCUS_NOT_MOVED
    ).to_repo_kwargs()
    assert (row["pipeline"], row["wcag_sc"]) == ("keyboard", "2.4.3")
    assert 'by clicking "Open dialog that does not take focus"' in row["failure_summary"]


async def test_off_by_default_and_the_sweep_is_unchanged(page) -> None:  # type: ignore[no-untyped-def]
    off = await _run(page)
    on = await _run(page, dialog_checks=True)
    assert off.keyboard_findings == ()
    assert (off.controls_discovered, off.dialogs_opened) == (
        on.controls_discovered,
        on.dialogs_opened,
    )


async def test_the_page_is_cap_bounded(page) -> None:  # type: ignore[no-untyped-def]
    result = await _run(page, dialog_checks=True, max_dialog_checks=1)
    assert len({f.target_selector for f in result.keyboard_findings}) <= 1
    assert "dialog_checks" in result.limits
