"""Each page code rule's question, asked of small pages in a real browser.

One test page per case, positive and negative. These are pages we wrote:
regression tests for the rules' code, not a measure of how well a rule works
on real sites (AGENTS.md, "Building a check: real pages first").
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from audit.analyzer.markup import MarkupProbe
from audit.analyzer.markup import probe as markup_probe
from audit.analyzer.markup.base import RULE_LABEL_FOR_MISSING, RULE_PLACEHOLDER_ONLY

playwright = pytest.importorskip("playwright.async_api")

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

# The "screen-reader-only" pattern sites use to hide text from sight.
SR_ONLY = (
    "position:absolute;width:1px;height:1px;padding:0;margin:-1px;"
    "overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0"
)


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        yield await ctx.new_page()
    finally:
        await ctx.close()


async def _flagged(page, rule_id: str, body: str) -> list[str]:  # type: ignore[no-untyped-def]
    """Element ids (or selectors) the rule flags on a page with ``body``."""
    await page.set_content(f"<!doctype html><html lang='en'><body>{body}</body></html>")
    findings = await MarkupProbe()._run_rule(page, rule_id, markup_probe._RULE_JS[rule_id])
    return [f.target_selector for f in findings]


# --- markup-placeholder-only (WCAG 3.3.2) --------------------------------


@pytest.mark.parametrize(
    "body",
    [
        '<input id="f" type="email" placeholder="Email address">',
        '<textarea id="f" placeholder="Your message"></textarea>',
        # A label with no text names nothing.
        '<label for="f"></label><input id="f" placeholder="Name">',
        # A label wrapped round a select: its options are not its label.
        '<label><select id="f" placeholder="Pick"><option>One</option></select></label>',
        # aria-labelledby that points at nothing, or at an empty element.
        '<input id="f" placeholder="City" aria-labelledby="missing">',
        '<span id="e"></span><input id="f" placeholder="City" aria-labelledby="e">',
        '<input id="f" placeholder="Search" aria-label="  ">',
    ],
)
async def test_a_field_named_only_by_its_placeholder_is_flagged(page, body: str) -> None:  # type: ignore[no-untyped-def]
    assert await _flagged(page, RULE_PLACEHOLDER_ONLY, body) == ["#f"]


@pytest.mark.parametrize(
    "body",
    [
        # Named some other way.
        '<label for="f">Email</label><input id="f" placeholder="name@example.com">',
        '<label>Email <input id="f" placeholder="name@example.com"></label>',
        '<input id="f" placeholder="Search" aria-label="Search the site">',
        '<h2 id="h">Search</h2><input id="f" placeholder="Words" aria-labelledby="h">',
        '<input id="f" placeholder="dd/mm/yyyy" title="Date of birth">',
        '<label for="f"><img src="x.png" alt="Email"></label><input id="f" placeholder="x">',
        # No placeholder, or one that is empty: the rule check (axe) covers it.
        '<input id="f">',
        '<input id="f" placeholder="   ">',
        # Not a field a placeholder names.
        '<input id="f" type="submit" placeholder="Send">',
        '<input id="f" type="hidden" placeholder="token">',
        # Hidden from everyone, or from sight.
        '<input id="f" placeholder="Email" style="display:none">',
        '<div style="display:none"><input id="f" placeholder="Email"></div>',
        '<input id="f" placeholder="Email" style="visibility:hidden">',
        f'<input id="f" placeholder="Email" style="{SR_ONLY}">',
        '<div aria-hidden="true"><input id="f" placeholder="Email"></div>',
    ],
)
async def test_a_field_with_a_name_or_out_of_sight_is_not_flagged(page, body: str) -> None:  # type: ignore[no-untyped-def]
    assert await _flagged(page, RULE_PLACEHOLDER_ONLY, body) == []


async def test_the_summary_quotes_the_placeholder(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content('<input id="f" placeholder="Email address">')
    [finding] = await MarkupProbe().run(page)
    assert '"Email address"' in finding.failure_summary
    assert finding.html_snippet.startswith("<input")


async def test_results_stop_at_the_rule_cap(page) -> None:  # type: ignore[no-untyped-def]
    fields = "".join(f'<input id="f{i}" placeholder="Field {i}">' for i in range(70))
    assert len(await _flagged(page, RULE_PLACEHOLDER_ONLY, fields)) == 50


# --- markup-label-for-missing (WCAG 1.3.1) --------------------------------


@pytest.mark.parametrize(
    "body",
    [
        '<label id="l" for="phone-number">Phone</label><input id="phone">',
        # Points at an element a label cannot name.
        '<label id="l" for="d">Notes</label><div id="d">x</div>',
        '<label id="l" for="h">Token</label><input type="hidden" id="h">',
        # An empty for value names nothing, even with a field inside.
        '<label id="l" for="">Name <input></label>',
        # Hidden from sight only: it is there for screen reader users.
        f'<label id="l" for="nope" style="{SR_ONLY}">Search</label><input id="q">',
    ],
)
async def test_a_label_tied_to_no_field_is_flagged(page, body: str) -> None:  # type: ignore[no-untyped-def]
    assert await _flagged(page, RULE_LABEL_FOR_MISSING, body) == ["#l"]


@pytest.mark.parametrize(
    "body",
    [
        '<label id="l" for="phone">Phone</label><input id="phone">',
        '<label id="l" for="s">Size</label><select id="s"><option>M</option></select>',
        '<label id="l" for="t">Notes</label><textarea id="t"></textarea>',
        '<label id="l" for="b">Go</label><button id="b">Go</button>',
        # No for value at all: a wrapped field, or a label for nothing (axe's job).
        '<label id="l">Name <input></label>',
        # Hidden from everyone: it names nothing anyway.
        '<label id="l" for="nope" style="display:none">Phone</label>',
    ],
)
async def test_a_label_tied_to_its_field_is_not_flagged(page, body: str) -> None:  # type: ignore[no-untyped-def]
    assert await _flagged(page, RULE_LABEL_FOR_MISSING, body) == []


async def test_the_summary_names_the_field_it_probably_meant(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content('<label for="phone-number">Phone</label><input id="phone">')
    [finding] = await MarkupProbe().run(page)
    assert finding.rule_id == RULE_LABEL_FOR_MISSING
    assert 'for="phone-number"' in finding.failure_summary
    assert 'id="phone"' in finding.failure_summary
