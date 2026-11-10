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
from audit.analyzer.markup import MarkupProbe
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


@pytest_asyncio.fixture(loop_scope="module")
async def needs_review(page):  # type: ignore[no-untyped-def]
    """axe's "needs review" results at load, as a scan stores them: rule id -> selectors."""
    found: dict[str, list[str]] = {}
    for v in await AxeAnalyzer.from_bundled().run(page, "AA", include_incomplete=True):
        if v.outcome == "cant_tell":
            found.setdefault(v.rule_id, []).append(v.target_selector)
    return found


@pytest_asyncio.fixture(loop_scope="module")
async def page_code(page):  # type: ignore[no-untyped-def]
    """The page code check's results at load, as a scan stores them: rule id -> element code."""
    found: dict[str, list[str]] = {}
    for f in await MarkupProbe().run(page):
        found.setdefault(f.rule_id, []).append(f.html_snippet)
    return found


async def test_finds_the_button_with_no_name(at_load) -> None:  # type: ignore[no-untyped-def]
    assert any("icon-only" in s for s in at_load.get("button-name", [])), at_load


async def test_finds_the_skipped_heading_level(at_load) -> None:  # type: ignore[no-untyped-def]
    assert "heading-order" in at_load, at_load


async def test_finds_the_low_contrast_text(at_load) -> None:  # type: ignore[no-untyped-def]
    # axe names it by its shortest unique selector. With a second paragraph
    # on the page (row 7), that is its class.
    assert at_load.get("color-contrast") == [".faint"], at_load


async def test_text_over_a_gradient_is_needs_review_not_a_failure(  # type: ignore[no-untyped-def]
    at_load, needs_review
) -> None:
    # Not among the failures (the faint text is the only one), but kept as
    # "needs review", which the report shows as Not sure.
    assert at_load.get("color-contrast") == [".faint"], at_load
    assert ".over-gradient" in needs_review.get("color-contrast", []), needs_review


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


async def test_finds_the_input_with_only_a_placeholder(at_load, page_code) -> None:  # type: ignore[no-untyped-def]
    # axe's label rule accepts a placeholder as the field's name, so axe is
    # quiet about it; the page code check reports it (backlog item 8).
    assert "#email" not in at_load.get("label", []), at_load
    fields = page_code.get("markup-placeholder-only", [])
    assert len(fields) == 1 and 'id="email"' in fields[0], page_code


async def test_finds_the_label_connected_to_no_field(page_code) -> None:  # type: ignore[no-untyped-def]
    # axe reports the field the label leaves unnamed (above); the page code
    # check reports the label itself (backlog item 9).
    labels = page_code.get("markup-label-for-missing", [])
    assert len(labels) == 1 and labels[0].startswith('<label for="phone-number">'), page_code


async def test_finds_the_title_that_repeats_its_link_text(page_code) -> None:  # type: ignore[no-untyped-def]
    # A best practice that axe has no rule for (row 8).
    links = page_code.get("markup-title-repeats-text", [])
    assert len(links) == 1 and 'title="Contact us"' in links[0], page_code
