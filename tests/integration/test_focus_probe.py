"""Integration tests for the live-page focus probe (SC 2.4.11).

Real Playwright against hand-built fixtures in
``tests/fixtures/site/focus/``:

  * ``clean.html``    — no sticky/fixed overlay → zero findings (FP guard).
  * ``obscured.html`` — a link under a position:fixed header → exactly one
    ``focus-not-obscured`` finding on that link, and NOT on the visible one.

Skipped when Playwright / chromium aren't installed; uses ``file://`` URLs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from audit.analyzer.focus import FocusProbe
from audit.analyzer.focus.base import RULE_FOCUS_OBSCURED

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "focus"


def _file_url(name: str) -> str:
    return (FIXTURE_DIR / name).resolve().as_uri()


playwright = pytest.importorskip("playwright.async_api")


@pytest.fixture
async def browser():  # type: ignore[no-untyped-def]
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
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


@pytest.mark.asyncio
async def test_clean_page_has_no_findings(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("clean.html"))
    findings = await FocusProbe().run(page)
    assert findings == [], "Expected zero findings on the clean fixture, got: " + ", ".join(
        f.target_selector for f in findings
    )


@pytest.mark.asyncio
async def test_detects_element_under_fixed_header(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("obscured.html"))
    findings = await FocusProbe().run(page)
    # Exactly the hidden link is flagged; the visible one is not.
    selectors = {f.target_selector for f in findings}
    assert "a#hidden-link" in selectors, f"hidden link not flagged; got {selectors}"
    assert "a#visible-link" not in selectors, "visible link wrongly flagged"
    flagged = next(f for f in findings if f.target_selector == "a#hidden-link")
    assert flagged.rule_id == RULE_FOCUS_OBSCURED
    assert flagged.criterion_sc == "2.4.11"
    assert flagged.to_repo_kwargs()["pipeline"] == "focus"
