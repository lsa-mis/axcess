"""The settle after a click must outlast the page's own rendering.

A click commonly mutates the DOM twice: synchronously, flipping
``aria-expanded`` and a class, and again when the panel it revealed is
actually rendered. Only the second mutation carries the defect.

Getting this wrong is a silent under-report. Axe runs against the
intermediate document, finds nothing, and the scan looks clean. These tests
exist because two attempts to shorten the settle both failed here: skipping
it once the DOM changed, and waiting for mutations to go quiet. A pending
``setTimeout`` is indistinguishable from a finished page, so neither signal
can stand in for the wait.

The fixture renders its panel 250ms after the click, inside the 400ms
budget the probe already allows.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "interaction"

playwright = pytest.importorskip("playwright.async_api")

# One browser per module (tests/integration/conftest.py), so the tests run on
# the module's event loop. Each still gets its own context from ``page``.
pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        yield await ctx.new_page()
    finally:
        await ctx.close()


async def _revealed_rules(page, probe: InteractionProbe) -> set[str]:
    """Run the probe over the late-render fixture and return the rules found."""
    url = (FIXTURE_DIR / "late_render.html").resolve().as_uri()
    await page.goto(url, wait_until="load")
    baseline = await probe.axe.run(page, "AA")
    result = await probe.run(page, baseline=baseline)
    return {found.violation.rule_id for found in result.findings}


async def test_default_settle_sees_the_late_panel(page) -> None:
    """The shipped settle must catch a defect rendered 250ms after the click."""
    probe = InteractionProbe(axe=AxeAnalyzer.from_bundled())
    assert probe.settle_ms >= 250, "the settle must outlast the fixture's render"

    assert "image-alt" in await _revealed_rules(page, probe)


async def test_a_settle_shorter_than_the_render_misses_it(page) -> None:
    """Pin the failure mode, so a future shortening fails here rather than silently.

    This is what both attempts at a faster settle amounted to in practice:
    axe ran while the panel was still pending, and reported nothing.
    """
    impatient = InteractionProbe(axe=AxeAnalyzer.from_bundled(), settle_ms=20)

    assert "image-alt" not in await _revealed_rules(page, impatient)
