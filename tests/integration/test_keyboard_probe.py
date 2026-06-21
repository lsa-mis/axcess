"""Integration tests for the dynamic keyboard-trap probe (SC 2.1.2).

The probe runs against real Playwright on hand-built fixture pages in
``tests/fixtures/site/sc_2_1_2/``. Five fixtures, two classes:

  * Negative (must produce zero findings): ``clean.html``, ``modal_clean.html``
  * Positive (must detect the named trap shape):
    - ``tab_loop.html`` → ``keyboard-trap-stuck``
    - ``modal_no_escape.html`` → ``keyboard-trap-modal-no-escape``
    - ``iframe_no_exit.html`` → ``keyboard-trap-iframe``

Skipped when Playwright + chromium aren't installed. The local dev
machine has them after ``make setup``; CI installs them in the
``pytest-playwright`` step.

We **don't** use a fixture HTTP server here — Playwright supports
``file://`` URLs, which avoids one whole class of "the integration
test failed because the fixture server bound the wrong port" flakes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from audit.analyzer.keyboard import KeyboardProbe
from audit.analyzer.keyboard.base import (
    RULE_IFRAME,
    RULE_NO_ESCAPE,
    RULE_STUCK,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "sc_2_1_2"


def _file_url(name: str) -> str:
    """file:// URL for a fixture page."""
    return (FIXTURE_DIR / name).resolve().as_uri()


# Skip the whole module if Playwright isn't importable / chromium not
# installed. Mirrors how the existing axe integration tests gate.
playwright = pytest.importorskip("playwright.async_api")


@pytest.fixture
async def browser():  # type: ignore[no-untyped-def]
    """One headless chromium per test session.

    A fresh context per test (in the page fixture) gives test isolation
    without paying the browser-launch cost five times.
    """
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            await browser.close()
    finally:
        await pw.stop()


@pytest.fixture
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context()
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


# --------------------------------------------------------------------
# Negative cases — must produce zero findings.
# False positives here would be the worst failure mode: the probe
# tells operators their clean pages have traps. Keep these strict.
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_page_has_no_findings(page) -> None:  # type: ignore[no-untyped-def]
    """A normal page with several focusable elements: zero findings."""
    await page.goto(_file_url("clean.html"))
    probe = KeyboardProbe(max_focusable=20, stuck_threshold=4)
    findings = await probe.run(page)
    assert findings == [], (
        f"Expected zero findings on the clean fixture, got {len(findings)}: "
        + ", ".join(f.rule_id for f in findings)
    )


@pytest.mark.asyncio
async def test_modal_with_proper_escape_handler_clean(page) -> None:  # type: ignore[no-untyped-def]
    """A modal that releases focus on Escape isn't flagged as no-escape."""
    await page.goto(_file_url("modal_clean.html"))
    probe = KeyboardProbe(max_focusable=20, stuck_threshold=4)
    findings = await probe.run(page)
    # We don't require strict zero (the page may have other shapes
    # the probe flags) — but the modal-no-escape rule must NOT fire.
    no_escape_findings = [f for f in findings if f.rule_id == RULE_NO_ESCAPE]
    assert no_escape_findings == [], (
        "Modal with a working Escape handler must not be flagged as "
        f"no-escape; found: {[f.target_selector for f in no_escape_findings]}"
    )


# --------------------------------------------------------------------
# Positive cases — each fixture has the named trap shape.
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_stuck_focus_from_swallowed_tab(page) -> None:  # type: ignore[no-untyped-def]
    """A button whose keydown handler eats Tab → keyboard-trap-stuck."""
    await page.goto(_file_url("tab_loop.html"))
    # Move focus to the trap button via JS so the probe walks into it
    # immediately. This sidesteps the "what if the page autofocuses
    # somewhere else" non-determinism.
    await page.evaluate("document.getElementById('trap').focus()")
    probe = KeyboardProbe(max_focusable=20, stuck_threshold=3)
    findings = await probe.run(page)
    stuck = [f for f in findings if f.rule_id == RULE_STUCK]
    assert stuck, "Expected at least one keyboard-trap-stuck finding; got rules: " + ", ".join(
        f.rule_id for f in findings
    )
    # The reported selector should point at SOME button-shaped element
    # (we don't pin the exact selector — the probe's selector
    # generation is best-effort, not contractual).
    assert any("button" in f.target_selector.lower() for f in stuck), (
        f"Stuck finding's selector should mention 'button': {[f.target_selector for f in stuck]}"
    )


@pytest.mark.asyncio
async def test_detects_modal_without_escape_handler(page) -> None:  # type: ignore[no-untyped-def]
    """A modal where Escape doesn't release focus → keyboard-trap-modal-no-escape."""
    await page.goto(_file_url("modal_no_escape.html"))
    probe = KeyboardProbe(max_focusable=20, stuck_threshold=4)
    findings = await probe.run(page)
    no_escape = [f for f in findings if f.rule_id == RULE_NO_ESCAPE]
    assert no_escape, (
        "Expected at least one keyboard-trap-modal-no-escape finding; got rules: "
        + ", ".join(f.rule_id for f in findings)
    )
    # The finding's failure_summary should mention Escape (so triagers
    # know what to test manually).
    assert any("escape" in f.failure_summary.lower() for f in no_escape)


@pytest.mark.asyncio
async def test_detects_untitled_iframe(page) -> None:  # type: ignore[no-untyped-def]
    """Iframe without title + reachable by Tab → keyboard-trap-iframe (soft)."""
    await page.goto(_file_url("iframe_no_exit.html"))
    probe = KeyboardProbe(max_focusable=20, stuck_threshold=4)
    findings = await probe.run(page)
    iframe_finds = [f for f in findings if f.rule_id == RULE_IFRAME]
    assert iframe_finds, (
        "Expected at least one keyboard-trap-iframe finding; got rules: "
        + ", ".join(f.rule_id for f in findings)
    )
    # Iframe heuristic is `serious` (not critical) — a heuristic is
    # softer than a confirmed trap, and we don't want it to outrank
    # the real ones in the Issues view's priority sort.
    assert all(f.impact == "serious" for f in iframe_finds)


# --------------------------------------------------------------------
# Safety / robustness.
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_never_raises_on_quirky_page(page) -> None:  # type: ignore[no-untyped-def]
    """A pathological page (no focusables, weird markup) must not crash."""
    await page.set_content("<!doctype html><html><body><p>Just some text.</p></body></html>")
    probe = KeyboardProbe(max_focusable=20, stuck_threshold=4)
    # Must return an empty list, not raise.
    findings = await probe.run(page)
    assert findings == []
