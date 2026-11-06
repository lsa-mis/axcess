"""A small page of known issues: what Axcess finds on it, and what it misses.

``tests/fixtures/site/known_issues/index.html`` holds one short, real
pattern per issue. This test is the regression check for the detectors that
run on it: if a change stops Axcess finding one of them, it fails here.

The issues Axcess does not find yet are ``xfail(strict=True)``: when a new
check starts finding one, the test reports XPASS and fails, so the list of
known gaps is updated in the same change.

The same file can be opened in WAVE or another tool to compare counts by
hand; see docs/internal/known-issues-page.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe
from audit.crawler.js_fetcher import settle_dom

PAGE = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "known_issues" / "index.html"

playwright = pytest.importorskip("playwright.async_api")

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = await ctx.new_page()
        await p.goto(PAGE.as_uri(), wait_until="load")
        await settle_dom(p)
        yield p
    finally:
        await ctx.close()


@pytest_asyncio.fixture(loop_scope="module")
async def at_load(page):  # type: ignore[no-untyped-def]
    """axe's results on the page as it loads: rule id -> selectors."""
    found: dict[str, list[str]] = {}
    for v in await AxeAnalyzer.from_bundled().run(page, "AA"):
        found.setdefault(v.rule_id, []).append(v.target_selector)
    return found


async def test_finds_the_button_with_no_name(at_load) -> None:  # type: ignore[no-untyped-def]
    assert any("icon-only" in s for s in at_load.get("button-name", [])), at_load


async def test_finds_the_skipped_heading_level(at_load) -> None:  # type: ignore[no-untyped-def]
    assert "heading-order" in at_load, at_load


async def test_finds_the_low_contrast_text(at_load) -> None:  # type: ignore[no-untyped-def]
    # axe names it by its shortest unique selector, here just "p".
    assert at_load.get("color-contrast") == ["p"], at_load


async def test_finds_the_field_an_unconnected_label_leaves_unnamed(at_load) -> None:  # type: ignore[no-untyped-def]
    # The label points at no field, so the phone field has no name: axe
    # flags the field. The label itself is the gap below.
    assert "#phone" in at_load.get("label", []), at_load


async def test_the_hidden_menu_is_quiet_at_load(at_load) -> None:  # type: ignore[no-untyped-def]
    assert "link-name" not in at_load, at_load


async def test_click_through_finds_the_link_in_the_hidden_menu(page) -> None:  # type: ignore[no-untyped-def]
    probe = InteractionProbe(axe=AxeAnalyzer.from_bundled())
    baseline = await probe.axe.run(page, "AA")
    result = await probe.run(page, baseline=baseline)
    revealed = {(f.violation.rule_id, f.revealed_by) for f in result.findings}
    assert ("link-name", "Menu") in revealed, revealed


@pytest.mark.xfail(strict=True, reason="Known gap: no placeholder-only label check yet (item 8)")
async def test_finds_the_input_with_only_a_placeholder(at_load) -> None:  # type: ignore[no-untyped-def]
    # axe's label rule accepts a placeholder as the field's name.
    assert any("email" in s for rule in ("label",) for s in at_load.get(rule, [])), at_load


@pytest.mark.xfail(strict=True, reason="Known gap: no check for a label tied to no field (item 9)")
async def test_finds_the_label_connected_to_no_field(at_load) -> None:  # type: ignore[no-untyped-def]
    selectors = [s for found in at_load.values() for s in found]
    assert any("phone-number" in s or s.startswith("label") for s in selectors), at_load
