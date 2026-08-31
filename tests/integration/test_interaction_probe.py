"""Integration tests for the live-page interaction probe.

Real Playwright + real axe against ``tests/fixtures/site/interaction/``.

The fixture is built so each guarantee fails loudly rather than silently:

  * an ``image-alt`` violation is present at load — it must be reported by
    the load-state pass and never again, however many revealed states it
    survives into;
  * an unlabelled input does not exist until "Add another guest" is pressed
    — a load-time-only scan cannot see it at all;
  * a "Sign out" button records its own activation, so the blocked-label
    guard is verified by observation rather than assumed;
  * ten same-shaped calendar buttons increment a counter, so the repeat cap
    is measured rather than assumed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "interaction"


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


@pytest.fixture
def axe() -> AxeAnalyzer:
    return AxeAnalyzer.from_bundled()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reveals_violation_that_only_exists_after_a_click(page, axe) -> None:  # type: ignore[no-untyped-def]
    """The unlabelled input appears only after "Add another guest"."""
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    # The whole premise: a load-time pass cannot see this.
    assert not any(v.rule_id == "label" for v in baseline)

    probe = InteractionProbe(axe=axe)
    revealed = await probe.run(page, baseline=baseline)

    label_findings = [r for r in revealed if r.violation.rule_id == "label"]
    assert label_findings, "probe did not find the input revealed by clicking"
    assert "Add another guest" in label_findings[0].revealed_by


@pytest.mark.integration
@pytest.mark.asyncio
async def test_load_state_violation_is_never_reported_again(page, axe) -> None:  # type: ignore[no-untyped-def]
    """The core dedupe guarantee.

    ``image-alt`` is on the page at load and survives into every state a
    click reveals. It must appear in the baseline and be entirely absent
    from the probe's output — otherwise it would be reported once per
    clicked state.
    """
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")
    assert any(v.rule_id == "image-alt" for v in baseline), "fixture regressed"

    revealed = await InteractionProbe(axe=axe).run(page, baseline=baseline)

    assert not any(r.violation.rule_id == "image-alt" for r in revealed)
    # Nothing is emitted twice, whatever the rule.
    hashes = [r.violation.target_hash for r in revealed]
    assert len(hashes) == len(set(hashes))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_never_operates_a_destructive_control(page, axe) -> None:  # type: ignore[no-untyped-def]
    """ "Sign out" must not be clicked, and the page proves it."""
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    await InteractionProbe(axe=axe).run(page, baseline=baseline)

    signed_out = await page.evaluate("() => document.body.dataset.signedOut || 'no'")
    assert signed_out == "no", "probe clicked a control whose label is blocked"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repeated_controls_are_sampled_not_exhausted(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Ten same-shaped buttons must not produce ten clicks."""
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    await InteractionProbe(axe=axe, max_repeated=3).run(page, baseline=baseline)

    clicks = int(await page.evaluate("() => document.getElementById('clicks').textContent"))
    assert clicks <= 3, f"repeat cap ignored: {clicks} calendar buttons clicked"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_click_budget_is_respected(page, axe) -> None:  # type: ignore[no-untyped-def]
    """A tight budget bounds the work even on a page full of controls."""
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    revealed = await InteractionProbe(axe=axe, max_clicks=2).run(page, baseline=baseline)

    # The budget counts CLICKS, not findings: one revealed state can carry
    # several violations at once (an unlabelled input fails `label` and
    # `target-size` together). So bound the number of distinct controls
    # credited with a reveal, which is what the budget actually governs.
    controls_used = {r.revealed_by for r in revealed}
    assert len(controls_used) <= 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_control_is_operated_only_once(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Regression: the nested sweep must not re-click its own parent.

    ``_operate`` recurses into whatever the click revealed. That nested
    sweep re-reads the DOM, so if the control were only recorded as seen
    *after* ``_operate`` returned, the nested sweep would find it untouched
    and press it again — once per depth level. An end-to-end run caught this
    as one "Add another guest" press appending three inputs and reporting
    one defect three times over.

    The form holds one input per press, so it counts the presses directly.
    """
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    revealed = await InteractionProbe(axe=axe, max_depth=2).run(page, baseline=baseline)

    presses = await page.evaluate(
        "() => document.getElementById('guests').querySelectorAll('input').length"
    )
    assert presses == 1, f"control operated {presses} times, expected once"

    # ...and therefore the one unlabelled input is one finding, not three.
    assert len([r for r in revealed if r.violation.rule_id == "label"]) == 1
