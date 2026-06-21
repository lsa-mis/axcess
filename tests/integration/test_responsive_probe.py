"""Integration tests for the responsive/zoom/text-spacing probe.

Real Playwright against hand-built fixtures in
``tests/fixtures/site/responsive/``. Four fixtures, two classes:

  * Negative (must produce zero findings): ``clean.html`` — the
    false-positive guard for all three checks.
  * Positive (each fires exactly its named check):
    - ``reflow_overflow.html``  → ``responsive-reflow-overflow``  (SC 1.4.10)
    - ``zoom_clipped.html``     → ``responsive-text-clipped``      (SC 1.4.4)
    - ``spacing_clipped.html``  → ``responsive-text-spacing-clipped`` (SC 1.4.12)

Isolation matters as much as detection: each positive fixture is built
so the OTHER two checks stay quiet on it (see the geometry notes in the
fixture files). A probe that fires three rules on one defect would
triple the triage load.

Same gating as the keyboard-probe tests: skipped when Playwright /
chromium aren't installed; ``file://`` URLs instead of a fixture server.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from audit.analyzer.responsive import ResponsiveProbe
from audit.analyzer.responsive.base import (
    RULE_REFLOW,
    RULE_SPACING_CLIPPED,
    RULE_TEXT_CLIPPED,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "responsive"


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
    # Match the crawler's standard viewport so the probe's restore step
    # and the fixtures' vw-based geometry behave exactly as production.
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


# --------------------------------------------------------------------
# Negative case — the false-positive guard.
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_page_has_no_findings(page) -> None:  # type: ignore[no-untyped-def]
    """A fluid page must produce zero findings from all three checks."""
    await page.goto(_file_url("clean.html"))
    findings = await ResponsiveProbe().run(page)
    assert findings == [], "Expected zero findings on the clean fixture, got: " + ", ".join(
        f"{f.rule_id} on {f.target_selector}" for f in findings
    )


@pytest.mark.asyncio
async def test_probe_restores_viewport(page) -> None:  # type: ignore[no-untyped-def]
    """The probe must leave the page at the crawl's standard viewport."""
    await page.goto(_file_url("clean.html"))
    await ResponsiveProbe().run(page)
    size = page.viewport_size
    assert size == {"width": 1440, "height": 900}, f"viewport left at {size}"


# --------------------------------------------------------------------
# Positive cases — one named rule each, others quiet.
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_reflow_overflow_at_320(page) -> None:  # type: ignore[no-untyped-def]
    """A fixed 900px container → responsive-reflow-overflow, only."""
    await page.goto(_file_url("reflow_overflow.html"))
    findings = await ResponsiveProbe().run(page)
    rules = {f.rule_id for f in findings}
    assert RULE_REFLOW in rules, f"reflow not detected; got {rules}"
    # The offender should be named (the fixed-width div, not just html).
    reflow = [f for f in findings if f.rule_id == RULE_REFLOW]
    assert any("fixed-width" in f.target_selector for f in reflow), (
        "Expected div#fixed-width to be named as the offender; got "
        + str([f.target_selector for f in reflow])
    )
    # Check isolation: this fixture must not fire the clipping rules.
    assert RULE_TEXT_CLIPPED not in rules
    assert RULE_SPACING_CLIPPED not in rules
    # Every reflow finding carries the right SC for the Issues view.
    assert all(f.criterion_sc == "1.4.10" for f in reflow)


@pytest.mark.asyncio
async def test_detects_text_clipping_at_zoom_proxy(page) -> None:  # type: ignore[no-untyped-def]
    """A vw-sized nowrap box that clips only at 640px → text-clipped, only."""
    await page.goto(_file_url("zoom_clipped.html"))
    findings = await ResponsiveProbe().run(page)
    rules = {f.rule_id for f in findings}
    assert RULE_TEXT_CLIPPED in rules, f"zoom clipping not detected; got {rules}"
    clipped = [f for f in findings if f.rule_id == RULE_TEXT_CLIPPED]
    assert any("vw-box" in f.target_selector for f in clipped), (
        "Expected p#vw-box to be named; got " + str([f.target_selector for f in clipped])
    )
    assert RULE_REFLOW not in rules
    assert RULE_SPACING_CLIPPED not in rules
    assert all(f.criterion_sc == "1.4.4" for f in clipped)


@pytest.mark.asyncio
async def test_detects_clipping_under_text_spacing_override(page) -> None:  # type: ignore[no-untyped-def]
    """A height-locked overflow-hidden box → spacing-clipped, only."""
    await page.goto(_file_url("spacing_clipped.html"))
    findings = await ResponsiveProbe().run(page)
    rules = {f.rule_id for f in findings}
    assert RULE_SPACING_CLIPPED in rules, f"spacing clip not detected; got {rules}"
    clipped = [f for f in findings if f.rule_id == RULE_SPACING_CLIPPED]
    assert any("tight-box" in f.target_selector for f in clipped), (
        "Expected p#tight-box to be named; got " + str([f.target_selector for f in clipped])
    )
    assert RULE_REFLOW not in rules
    assert RULE_TEXT_CLIPPED not in rules
    assert all(f.criterion_sc == "1.4.12" for f in clipped)


# --------------------------------------------------------------------
# Persistence shape — findings flow into page_a11y_findings rows.
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finding_repo_kwargs_shape(page) -> None:  # type: ignore[no-untyped-def]
    """to_repo_kwargs() carries the pipeline + SC the Issues view needs."""
    await page.goto(_file_url("reflow_overflow.html"))
    findings = await ResponsiveProbe().run(page)
    assert findings
    kwargs = findings[0].to_repo_kwargs()
    assert kwargs["pipeline"] == "responsive"
    assert kwargs["rule_id"].startswith("responsive-")
    assert kwargs["criterion_sc"] == kwargs["wcag_sc"] == "1.4.10"
    assert kwargs["wcag_level"] == "AA"
    assert kwargs["target_hash"]  # non-empty stable dedupe key
    assert "www.w3.org" in kwargs["help_url"]
