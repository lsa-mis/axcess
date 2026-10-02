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
import pytest_asyncio

from audit.analyzer.focus import FocusProbe
from audit.analyzer.focus.base import RULE_FOCUS_OBSCURED, RULE_POSITIVE_TABINDEX

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "focus"


def _file_url(name: str) -> str:
    return (FIXTURE_DIR / name).resolve().as_uri()


playwright = pytest.importorskip("playwright.async_api")

# One browser per module (tests/integration/conftest.py), so the tests run on
# the module's event loop. Each still gets its own context from ``page``.
pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


async def test_clean_page_has_no_findings(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("clean.html"))
    findings = await FocusProbe().run(page)
    assert findings == [], "Expected zero findings on the clean fixture, got: " + ", ".join(
        f.target_selector for f in findings
    )


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


async def test_flags_positive_tabindex_only(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("tabindex.html"))
    findings = await FocusProbe().run(page)
    ti = [f for f in findings if f.rule_id == RULE_POSITIVE_TABINDEX]
    selectors = {f.target_selector for f in ti}
    # Only tabindex="3" is flagged; tabindex 0 / -1 / no-tabindex are fine.
    assert selectors == {"input#jumps-first"}, f"got {selectors}"
    f0 = ti[0]
    assert f0.criterion_sc == "2.4.3"
    assert f0.wcag_level == "A"
    assert "focus-order" in f0.help_url
    assert f0.to_repo_kwargs()["pipeline"] == "focus"


async def test_flags_no_visible_focus_extra_stops_and_reordered_rows(page) -> None:  # type: ignore[no-untyped-def]
    from audit.analyzer.focus.base import (
        RULE_FOCUS_NOT_VISIBLE,
        RULE_NON_INTERACTIVE_STOP,
        RULE_VISUAL_ORDER,
    )

    await page.goto(_file_url("visibility_order.html"))
    findings = await FocusProbe().run(page)
    found: dict[str, list[str | None]] = {}
    for f in findings:
        found.setdefault(f.rule_id, []).append(
            await page.locator(f.target_selector).get_attribute("id")
        )
    # Exactly one of each: the link with no focus style (not the default ring,
    # the custom ring, the ring that fades in, the text field or the styled
    # checkbox), the paragraph with tabindex="0" (not the scroller, the custom
    # control or the described term) and the floated row (not the plain nav).
    assert found == {
        RULE_FOCUS_NOT_VISIBLE: ["none", "f78"],
        RULE_NON_INTERACTIVE_STOP: ["stop"],
        RULE_VISUAL_ORDER: ["broken"],
    }
    visible = next(f for f in findings if f.rule_id == RULE_FOCUS_NOT_VISIBLE)
    assert (visible.criterion_sc, visible.wcag_level) == ("2.4.7", "AA")
    assert visible.help_url.endswith("/focus-visible.html")
    # The page is left as it was: no frozen transitions, no marker attributes.
    assert await page.evaluate("document.querySelectorAll('[data-axcess-stop]').length") == 0
    fade = "getComputedStyle(document.getElementById('fade')).transitionDuration"
    assert await page.evaluate(fade) == "0.4s"


async def test_the_newer_checks_can_be_turned_off(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("visibility_order.html"))
    assert await FocusProbe(focus_order_checks=False).run(page) == []


async def test_focus_appearance_runs_only_when_asked_and_flags_thin_indicators(page) -> None:  # type: ignore[no-untyped-def]
    from audit.analyzer.focus.base import RULE_FOCUS_APPEARANCE

    await page.goto(_file_url("visibility_order.html"))
    assert RULE_FOCUS_APPEARANCE not in {f.rule_id for f in await FocusProbe().run(page)}
    findings = await FocusProbe(include_aaa=True).run(page)
    thin = [f for f in findings if f.rule_id == RULE_FOCUS_APPEARANCE]
    ids = {await page.locator(f.target_selector).get_attribute("id") for f in thin}
    # The 1px grey outline fails; the 3px blue outline, the default ring and
    # the 3px box-shadow ring pass.
    assert "thin" in ids and not ids & {"thick", "default", "ring"}
    assert (thin[0].criterion_sc, thin[0].wcag_level) == ("2.4.13", "AAA")


async def test_a_control_left_focused_is_measured_unfocused_first(page) -> None:  # type: ignore[no-untyped-def]
    # One control with a box-shadow ring. The obscured check focuses it and
    # leaves it focused; the visibility check must not read that as "before".
    await page.set_content(
        "<style>.b:focus{outline:none;box-shadow:0 0 0 3px #005fcc}</style>"
        "<main><button class='b'>Only control</button></main>"
    )
    assert await FocusProbe().run(page) == []
