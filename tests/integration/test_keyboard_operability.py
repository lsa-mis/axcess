"""Integration tests for the SC 2.1.1 mouse-only control probe.

Real Chromium on hand-built pages in ``tests/fixtures/site/sc_2_1_1/``.
``mouse_only.html`` holds seven controls the keyboard cannot fully operate
and six look-alikes that have a keyboard path; ``clean.html`` has none.
Elements carry ``data-t`` so leads can be named (the probe's harness hook).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from audit.analyzer.keyboard import KeyboardOperabilityProbe, KeyboardProbe
from audit.analyzer.keyboard.base import RULE_NO_KEY_HANDLER, RULE_STUCK, RULE_UNREACHABLE

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "site"

playwright = pytest.importorskip("playwright.async_api")

pytestmark = pytest.mark.asyncio(loop_scope="module")


def _url(name: str) -> str:
    return (FIXTURES / name).resolve().as_uri()


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


async def _leads(page, *, advanced: bool = False) -> dict[str, tuple[str, str]]:  # type: ignore[no-untyped-def]
    await page.goto(_url("sc_2_1_1/mouse_only.html"))
    # The Tab walk runs first in a scan; its visited set is part of the input.
    await KeyboardProbe().run(page)
    result = await KeyboardOperabilityProbe(advanced=advanced, annotate_attr="data-t").analyze(page)
    return {str(lead.probe): (lead.kind, lead.verdict) for lead in result.leads}


async def test_standard_reports_the_mouse_only_controls_and_nothing_else(page) -> None:  # type: ignore[no-untyped-def]
    leads = await _leads(page)
    assert leads == {
        "fake": ("unreachable", "lead"),
        "nokey": ("no_key_handler", "lead"),
        "label": ("label", "lead"),
        "blur": ("unreachable", "lead"),
        "linkbtn": ("no_key_handler", "lead"),
        # Standard cannot tell an empty handler from a working one.
        "noop": ("unreachable", "lead"),
    }


async def test_advanced_confirms_real_failures_and_clears_the_rest(page) -> None:  # type: ignore[no-untyped-def]
    leads = await _leads(page, advanced=True)
    confirmed = {name for name, (_kind, verdict) in leads.items() if verdict == "confirmed"}
    dismissed = {name for name, (_kind, verdict) in leads.items() if verdict == "dismissed"}
    # "Remember me" is not on the destructive-word list, so it is operated too.
    assert confirmed == {"fake", "nokey", "label", "blur", "linkbtn"}
    # A handler that changes nothing, and styling with no handler at all.
    assert dismissed == {"noop", "decor"}


async def test_a_clean_page_has_no_leads_in_either_mode(page) -> None:  # type: ignore[no-untyped-def]
    for advanced in (False, True):
        await page.goto(_url("sc_2_1_1/clean.html"))
        await KeyboardProbe().run(page)
        assert await KeyboardOperabilityProbe(advanced=advanced).run(page) == []


async def test_findings_are_sc_2_1_1_rows_in_the_keyboard_pipeline(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_url("sc_2_1_1/mouse_only.html"))
    findings = await KeyboardProbe(operability=KeyboardOperabilityProbe()).run(page)
    assert {f.rule_id for f in findings} == {RULE_UNREACHABLE, RULE_NO_KEY_HANDLER}
    for finding in findings:
        row = finding.to_repo_kwargs()
        assert (row["pipeline"], row["wcag_sc"], row["criterion_sc"]) == (
            "keyboard",
            "2.1.1",
            "2.1.1",
        )
        assert "Static evidence only" in row["failure_summary"]
        # The selector finds the element again (screenshots depend on it).
        assert await page.locator(finding.target_selector).count() == 1


async def test_traps_and_mouse_only_controls_are_reported_together(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_url("sc_2_1_2/tab_loop.html"))
    findings = await KeyboardProbe(operability=KeyboardOperabilityProbe()).run(page)
    assert RULE_STUCK in {f.rule_id for f in findings}


async def test_advanced_leaves_the_page_as_it_loaded(page) -> None:  # type: ignore[no-untyped-def]
    await _leads(page, advanced=True)
    assert await page.locator("#out").text_content() == ""


async def test_a_closed_page_returns_nothing_instead_of_raising(browser) -> None:  # type: ignore[no-untyped-def]
    ctx = await browser.new_context()
    p = await ctx.new_page()
    await p.goto(_url("sc_2_1_1/mouse_only.html"))
    await ctx.close()
    for advanced in (False, True):
        assert await KeyboardOperabilityProbe(advanced=advanced).run(p) == []


async def test_advanced_never_operates_a_destructive_looking_control(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content(
        "<div id='del' style='cursor:pointer'>Delete account</div>"
        "<script>window.clicked = 0;"
        "document.getElementById('del').addEventListener('click', () => { window.clicked += 1; });"
        "</script>"
    )
    result = await KeyboardOperabilityProbe(advanced=True).analyze(page)
    assert await page.evaluate("window.clicked") == 0
    assert [(lead.kind, lead.verdict) for lead in result.leads] == [("unreachable", "lead")]
    assert result.tested == 0


async def _named(page, **probe_args) -> dict[str, str]:  # type: ignore[no-untyped-def]
    await page.goto(_url("sc_2_1_1/delegation_hover.html"))
    await KeyboardProbe().run(page)
    probe = KeyboardOperabilityProbe(annotate_attr="data-t", **probe_args)
    result = await probe.analyze(page)
    return {str(lead.probe): lead.kind for lead in result.leads}


async def test_delegated_clicks_and_hover_only_menus_are_found(page) -> None:  # type: ignore[no-untyped-def]
    assert await _named(page) == {
        # document listener: closest('.row-action') and target.id === 'by-id'
        "closest": "unreachable",
        "byid": "unreachable",
        # jQuery's delegated-handler record
        "jq": "unreachable",
        # .menu:hover .panel with no focus rule: reported on what is pointed at
        "hover": "hover_only",
    }


async def test_the_first_release_rules_do_not_see_them(page) -> None:  # type: ignore[no-untyped-def]
    assert await _named(page, extended=False) == {}
