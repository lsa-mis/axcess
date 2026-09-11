"""Tab-order walk against a real browser.

Set T is the foundation the whole differential rests on: if the walk stops
early, every probe past the stopping point looks unreachable and the detector
manufactures violations out of its own instrumentation bug. These tests drive a
real Chromium and press real keys, because that failure mode is invisible to a
unit test.
"""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from audit.analyzer.keyboard.kbdiff.taborder import compute_tab_order

pytestmark = pytest.mark.integration


@pytest.fixture
async def page():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1280, "height": 900})
    target = await context.new_page()
    try:
        yield target
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


@pytest.mark.asyncio
async def test_walk_is_not_truncated_by_repeated_unnamed_tags(page):
    """Two plain <a> in a row must not read as a completed cycle.

    Regression: markers for unlabelled elements were once just the tag name, so
    consecutive links both produced ``#el:a``. The cycle check saw the same
    marker twice, concluded focus had wrapped, and stopped after two presses —
    leaving every later probe scored "not in the tab order".
    """
    await page.set_content(
        """
        <a href="#">one</a>
        <a href="#">two</a>
        <button data-probe="p1">first probe</button>
        <a href="#" data-probe="p2">second probe</a>
        <button>tail</button>
        """
    )
    order = await compute_tab_order(page)

    assert order.contains("p1"), "walk stopped before reaching p1"
    assert order.contains("p2"), "walk stopped before reaching p2"
    assert order.position("p1") < order.position("p2")


@pytest.mark.asyncio
async def test_positive_tabindex_comes_before_document_order(page):
    """`tabindex > 0` reorders the sequence ahead of everything natural.

    This is the walk's first use of the page, which matters: the ordering is
    only observable from a page that has never been focused. See the note in
    ``compute_tab_order``.
    """
    await page.set_content(
        """
        <button data-probe="first-in-dom">first in dom</button>
        <button data-probe="jumps-queue" tabindex="5">jumps the queue</button>
        """
    )
    order = await compute_tab_order(page)

    assert order.position("jumps-queue") < order.position("first-in-dom")


@pytest.mark.asyncio
async def test_negative_tabindex_is_focusable_but_never_a_tab_stop(page):
    """Focusability is not tab-order membership.

    ``el.focus()`` would succeed on this element. Tab never lands on it, which
    is why reachability has to be established by pressing keys rather than by
    calling ``focus()``.
    """
    await page.set_content(
        """
        <div data-probe="script-focusable" tabindex="-1">reachable only by script</div>
        <button data-probe="real-stop">real stop</button>
        """
    )
    order = await compute_tab_order(page)

    assert not order.contains("script-focusable")
    assert order.contains("real-stop")


@pytest.mark.asyncio
async def test_hidden_and_disabled_controls_are_not_tab_stops(page):
    await page.set_content(
        """
        <button data-probe="hidden" style="display:none">hidden</button>
        <button data-probe="disabled" disabled>disabled</button>
        <button data-probe="visible">visible</button>
        """
    )
    order = await compute_tab_order(page)

    assert not order.contains("hidden")
    assert not order.contains("disabled")
    assert order.contains("visible")


@pytest.mark.asyncio
async def test_cap_is_reported_rather_than_silently_swallowed(page):
    """Hitting the cap must be visible, because it changes what a miss means.

    With the cap hit, "this probe is not in the tab order" is not a finding —
    it is an unfinished measurement, and ``reachability_is_certain`` says so.
    """
    buttons = "".join(f'<button data-probe="b{i}">{i}</button>' for i in range(30))
    await page.set_content(buttons)

    order = await compute_tab_order(page, max_tabs=5)

    assert order.capped is True
    assert order.presses == 5
    assert not order.reachability_is_certain("b29")
    assert order.reachability_is_certain("b0")


@pytest.mark.asyncio
async def test_shadow_dom_probes_are_found(page):
    """Open shadow roots splice their own stops into the sequence."""
    await page.set_content("<div id='host'></div>")
    await page.evaluate(
        """
        () => {
          const root = document.getElementById('host').attachShadow({ mode: 'open' });
          root.innerHTML = '<button data-probe="in-shadow">shadow button</button>';
        }
        """
    )
    order = await compute_tab_order(page)

    assert order.contains("in-shadow")


class TestUpstreamInstrumentActuallyRuns:
    """The transcribed upstream instrument must execute, not merely exist.

    Two source-level bugs got past unit tests because nothing asserted the JS
    ran in a browser: the snapshot was held in a non-raw Python string, so a
    ``\\n`` escape became a real newline inside a JS string literal and every
    ``evaluate`` raised SyntaxError; and the nav hook was an arrow function
    passed to ``add_init_script``, which injects source rather than calling it,
    so it was never installed. Both failed silently as "no channels changed".
    """

    async def test_the_init_script_installs_and_snapshots(self, page):
        from experiments.tabbing.runner.bakeoff import _frame_snapshot
        from experiments.tabbing.runner.upstream_instrument import UPSTREAM_INIT_JS

        await page.context.add_init_script(UPSTREAM_INIT_JS)
        await page.goto("about:blank")
        await page.set_content("<button id='b'>go</button>")

        snapshot, failures = await _frame_snapshot(page)
        assert not failures, f"upstream instrument did not run: {failures}"
        fields = set(next(iter(snapshot.values())))
        assert {
            "dom",
            "geometry",
            "mutations",
            "net",
            "storage",
            "console",
            "canvas",
            "nav",
            "href",
        } <= fields

    async def test_a_same_url_pushstate_counts_as_navigation(self, page):
        """The case a href-only comparison misses entirely."""
        from experiments.tabbing.runner.bakeoff import _frame_snapshot, upstream_delta
        from experiments.tabbing.runner.upstream_instrument import UPSTREAM_INIT_JS

        await page.context.add_init_script(UPSTREAM_INIT_JS)
        await page.goto("about:blank")
        await page.set_content("<p>x</p>")

        before, _ = await _frame_snapshot(page)
        await page.evaluate("() => history.pushState({}, '', location.href)")
        after, _ = await _frame_snapshot(page)

        delta = upstream_delta(next(iter(before.values())), next(iter(after.values())))
        assert "nav" in delta, "history hook was not installed"
