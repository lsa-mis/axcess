"""Edge cases the fixture corpus does not reach.

The frozen corpus is made of short, purpose-built pages, which is right for
scoring but leaves whole categories of real-page behaviour untested. Everything
here is a shape that occurs constantly on real sites and that quietly corrupts
results when the instrument mishandles it: content below the fold, targets a few
pixels across, inline elements that wrap, overlays, deep nesting, long tab
sequences, and handlers that take their time.

These test the *instrument*, not the detector's accuracy. A wrong answer here
does not lower a score — it invalidates one, which is worse, because nothing in
the numbers would look unusual.
"""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from audit.analyzer.keyboard.kbdiff import channels, coverage
from audit.analyzer.keyboard.kbdiff.differential import _LOCATE_JS
from audit.analyzer.keyboard.kbdiff.taborder import compute_tab_order

pytestmark = pytest.mark.integration

VIEWPORT = {"width": 1280, "height": 900}


@pytest.fixture
async def page():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(viewport=VIEWPORT)
    target = await context.new_page()
    try:
        yield target
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


@pytest.fixture
async def fresh_page():
    """Hands out a brand-new page per call.

    ``compute_tab_order`` requires a page that has never been focused, and only
    a new page provides that — ``set_content`` on a used page does not reset
    Chromium's sequential focus starting point. The runner does the same thing
    by opening a fresh context per trial.
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(viewport=VIEWPORT)

    async def make(html: str):
        target = await context.new_page()
        await target.set_content(html)
        return target

    try:
        yield make
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


async def locate(page, probe_id: str = "t1") -> dict:
    return await page.evaluate(_LOCATE_JS, probe_id)


class TestGeometry:
    """Where the mouse has to aim, and whether it can get there."""

    @pytest.mark.asyncio
    async def test_element_below_the_fold_is_measurable(self, page):
        """Regression: the single most damaging bug found in this instrument.

        Geometry is viewport-relative. Before the locator scrolled, an element
        3000px down reported a centre outside the viewport and was rejected as
        "not rendered" — so on any realistic long page the detector would have
        declared the majority of the content unmeasurable, and the corpus would
        never have shown it because its pages are one screen tall.
        """
        await page.set_content(
            """
            <div style="height:3000px">tall spacer</div>
            <button data-probe="t1">below the fold</button>
            """
        )
        found = await locate(page)

        assert found["found"]
        assert found["in_viewport"], "element below the fold was not scrolled into view"
        assert found["hit_testable"]
        assert 0 <= found["y"] <= VIEWPORT["height"]

    @pytest.mark.asyncio
    async def test_off_canvas_element_is_still_rejected(self, page):
        """Scrolling must not rescue the visually-hidden pattern.

        `left: -9999px` is how content is hidden from sight but kept for screen
        readers. No scroll brings it into view and no mouse can click it, so it
        must stay excluded — otherwise we would start reporting defects against
        elements that are deliberately unreachable.
        """
        await page.set_content(
            """
            <button data-probe="t1" style="position:absolute;left:-9999px">skip link</button>
            """
        )
        found = await locate(page)

        assert found["found"]
        assert not found["in_viewport"]

    @pytest.mark.asyncio
    async def test_one_pixel_target_is_hit_accurately(self, page):
        """Tiny targets are a real accessibility smell and must still measure."""
        await page.set_content(
            """
            <div data-probe="t1" style="width:1px;height:1px;cursor:pointer"></div>
            """
        )
        found = await locate(page)

        assert found["hit_testable"], "1x1 target could not be aimed at"
        assert found["width"] == 1 and found["height"] == 1

    @pytest.mark.asyncio
    async def test_wrapped_inline_element_is_aimed_at_a_point_it_owns(self, page):
        """An inline link spanning two lines has a box covering the gap between.

        Aiming at the bounding-box centre can land in that gap, hitting the
        paragraph instead. The click then does nothing, and a broken control
        scores as a working one — a false negative produced entirely by
        arithmetic.
        """
        await page.set_content(
            """
            <p style="width:90px;font-size:16px;line-height:2.4">
              aaa bbb ccc
              <a href="#" data-probe="t1">a link whose text wraps onto another line</a>
              ddd eee
            </p>
            """
        )
        found = await locate(page)

        assert found["hit_testable"], "no aim point on the link itself was found"

    @pytest.mark.asyncio
    async def test_occlusion_is_reported_with_the_blocking_element(self, page):
        """An overlay makes an element unclickable; say so, and say what did it.

        Upstream inferred occlusion from "the click produced no effect", which is
        indistinguishable from "the handler does nothing". Naming the blocker
        turns an absence of evidence into evidence.
        """
        await page.set_content(
            """
            <button data-probe="t1"
                    style="position:absolute;top:10px;left:10px;width:100px;height:40px">
              under
            </button>
            <div id="veil" style="position:absolute;top:0;left:0;width:400px;height:400px"></div>
            """
        )
        found = await locate(page)

        assert not found["hit_testable"]
        assert found["occluded_by"] == "div"

    @pytest.mark.asyncio
    async def test_scrolling_to_centre_clears_a_sticky_header(self, page):
        """Centring is what rescues content from a top-anchored sticky bar.

        A user meeting this scrolls until the control is clear of the header and
        clicks it, so it is genuinely operable and must not be reported. Had the
        locator scrolled to the *top* of the viewport instead, the element would
        land under the bar and we would report a defect that no user experiences.
        That is the whole reason for ``block: 'center'``.
        """
        await page.set_content(
            """
            <div style="position:fixed;top:0;left:0;right:0;height:120px;background:#eee"></div>
            <div style="height:2000px"></div>
            <button data-probe="t1">below a sticky header</button>
            """
        )
        found = await locate(page)

        assert found["hit_testable"], "centring failed to clear the sticky header"
        assert found["y"] > 120, "aim point is still inside the header band"

    @pytest.mark.asyncio
    async def test_pointer_events_none_and_inert_are_still_caught(self, page):
        """The two gates upstream's isVisible() lacked, on one page."""
        await page.set_content(
            """
            <button data-probe="t1" style="pointer-events:none">no pointer events</button>
            """
        )
        assert "pointer-events:none" in (await locate(page))["reasons"]

        await page.set_content("""<div inert><button data-probe="t1">inert</button></div>""")
        assert "inert" in (await locate(page))["reasons"]


class TestComplexPages:
    """Scale, nesting, and repetition."""

    @pytest.mark.asyncio
    async def test_deeply_nested_target_is_found(self, page):
        """200 levels of wrapper divs, which build tools produce routinely."""
        depth = 200
        html = "<div>" * depth + '<button data-probe="t1">deep</button>' + "</div>" * depth
        await page.set_content(html)

        found = await locate(page)
        assert found["found"]
        assert found["hit_testable"]

    @pytest.mark.asyncio
    async def test_many_identical_controls_get_distinct_tab_positions(self, page):
        """300 identical buttons must not collapse into one another.

        Identical markup is the norm in tables and lists. The walk identifies
        stops by probe id, and unlabelled stops by document position, so
        repetition must not confuse the sequence or trigger the cycle check.
        """
        buttons = "".join(f'<button data-probe="b{i}">go</button>' for i in range(300))
        await page.set_content(buttons)

        order = await compute_tab_order(page, max_tabs=400)

        assert len(order.index) == 300
        positions = sorted(order.index.values())
        assert positions == list(range(1, 301)), "tab positions are not distinct and ordered"

    @pytest.mark.asyncio
    async def test_long_page_hits_the_cap_and_says_so(self, page):
        """Past the budget, "not found" must not read as "not reachable"."""
        buttons = "".join(f'<button data-probe="b{i}">go</button>' for i in range(500))
        await page.set_content(buttons)

        order = await compute_tab_order(page, max_tabs=50)

        assert order.capped is True
        assert not order.reachability_is_certain("b499")

    @pytest.mark.asyncio
    async def test_nested_shadow_roots_are_traversed(self, page):
        """A component inside a component: open roots nested two deep."""
        await page.set_content("<div id='outer'></div>")
        await page.evaluate(
            """
            () => {
              const outer = document.getElementById('outer').attachShadow({ mode: 'open' });
              const mid = document.createElement('div');
              outer.appendChild(mid);
              const inner = mid.attachShadow({ mode: 'open' });
              inner.innerHTML = '<button data-probe="t1">two roots deep</button>';
            }
            """
        )
        order = await compute_tab_order(page)

        assert order.contains("t1")

    @pytest.mark.asyncio
    async def test_closed_shadow_root_is_unresolvable_and_admits_it(self, page):
        """The known capability gap, pinned so it cannot regress silently.

        `page.evaluate` cannot reach into a closed root; CDP with `pierce: true`
        can. Until the locator moves to CDP these probes are unmeasurable, and
        the honest report of that is `found: false` -> `unknown`, never a guess.
        """
        await page.set_content("<div id='host'></div>")
        await page.evaluate(
            """
            () => {
              const root = document.getElementById('host').attachShadow({ mode: 'closed' });
              root.innerHTML = '<button data-probe="t1">sealed</button>';
            }
            """
        )
        found = await locate(page)

        assert not found["found"], "closed root became readable; update the documented limitation"


class TestTiming:
    """Effects that are not instantaneous."""

    @pytest.mark.asyncio
    async def test_tab_order_is_reproducible_on_fresh_pages(self, fresh_page):
        """Determinism, measured the way the runner actually measures.

        Three separate loads of identical markup must agree. This is the property
        the experiment depends on; walking the *same* page twice deliberately
        does not have it, and ``compute_tab_order`` documents why.
        """
        html = """
            <button data-probe="a">a</button>
            <a href="#" data-probe="b">b</a>
            <input data-probe="c">
        """
        walks = [await compute_tab_order(await fresh_page(html)) for _ in range(3)]

        assert walks[0].index == walks[1].index == walks[2].index
        assert walks[0].index == {"a": 1, "b": 2, "c": 3}

    @pytest.mark.asyncio
    async def test_positive_tabindex_still_sorts_first_on_a_fresh_page(self, fresh_page):
        """Guards the regression that removing the focus reset fixed.

        A reset that focused ``body`` made this ordering come out backwards —
        stable, but wrong. Ordering is the one thing Set T exists to observe, so
        a stable wrong answer is worse than an unstable one.
        """
        target = await fresh_page(
            """
            <button data-probe="dom1">first in dom</button>
            <button data-probe="ti5" tabindex="5">jumps the queue</button>
            <button data-probe="dom2">second in dom</button>
            """
        )
        order = await compute_tab_order(target)

        assert order.position("ti5") == 1
        assert order.position("dom1") == 2

    @pytest.mark.asyncio
    async def test_dynamically_inserted_control_enters_the_tab_order(self, page):
        """Controls added after load must be picked up by a later walk."""
        await page.set_content("<button data-probe='static'>static</button>")
        await page.evaluate(
            """
            () => {
              const b = document.createElement('button');
              b.setAttribute('data-probe', 'added');
              b.textContent = 'added later';
              document.body.appendChild(b);
            }
            """
        )
        order = await compute_tab_order(page)

        assert order.contains("added")
        assert order.contains("static")


class TestEffectComparison:
    """Whether two effects compare equal must not depend on where we scrolled."""

    @pytest.mark.asyncio
    async def test_geometry_digest_is_scroll_independent(self, page):
        """Regression: scrolling alone must not look like a layout change.

        The mouse trial scrolls its target into view; the keyboard trial lands
        wherever Tab auto-scrolls. When the geometry digest used viewport
        coordinates the two never matched, so ``Effect.same_as`` was false for
        every probe and plain ``<button>`` elements were reported as keyboard
        defects. Document coordinates make the digest describe layout, which is
        what is actually being compared.
        """
        await page.set_content(
            """
            <div style="height:3000px">spacer</div>
            <button data-probe="t1">target</button>
            <div style="height:3000px">spacer</div>
            """
        )
        at_top = await page.evaluate(channels.SNAPSHOT_JS)
        await page.evaluate("() => window.scrollTo(0, 2000)")
        await page.wait_for_timeout(50)
        scrolled = await page.evaluate(channels.SNAPSHOT_JS)

        assert at_top["geometry"] == scrolled["geometry"], (
            "scrolling changed the geometry digest; effects across modalities "
            "can never compare equal"
        )
        assert channels.diff(at_top, scrolled).is_empty

    @pytest.mark.asyncio
    async def test_a_real_layout_change_is_still_detected(self, page):
        """The counterpart: scroll-independence must not blind us to reveals."""
        await page.set_content(
            """
            <style>#menu { display: none; }</style>
            <div id="menu">revealed</div>
            <button data-probe="t1">open</button>
            """
        )
        before = await page.evaluate(channels.SNAPSHOT_JS)
        await page.evaluate("() => { document.getElementById('menu').style.display = 'block'; }")
        await page.wait_for_timeout(50)
        after = await page.evaluate(channels.SNAPSHOT_JS)

        assert "geometry" in channels.diff(before, after).changed

    @pytest.mark.asyncio
    async def test_nondeterministic_content_is_a_disclosed_limitation(self, page):
        """A handler writing a fresh timestamp does NOT compare equal to itself.

        This is a deliberate trade-off, not an oversight, and it is pinned here
        so nobody "fixes" it back. Blanket digit/hex collapsing was tried: it
        absorbed timestamps, but it equally absorbed order numbers, account ids
        and amounts, so a keypress that saved the *wrong* record compared equal
        to one that saved the right one. That is a false negative with no trace
        in the evidence, which is strictly worse than a false positive we can
        see and explain.

        So: exact content by default. A genuinely nondeterministic handler
        produces a visible false positive, and the report discloses it as a
        known limitation of payload comparison.
        """
        await page.set_content("<div id='log'>idle</div>")

        before = await page.evaluate(channels.SNAPSHOT_JS)
        await page.evaluate(
            "() => { document.getElementById('log').textContent = 'saved 1737049322188'; }"
        )
        first = await page.evaluate(channels.SNAPSHOT_JS)
        await page.evaluate(
            "() => { document.getElementById('log').textContent = 'saved 1737049399999'; }"
        )
        second = await page.evaluate(channels.SNAPSHOT_JS)

        assert not channels.diff(before, first).is_empty
        assert not channels.diff(before, first).same_as(channels.diff(before, second))

    @pytest.mark.asyncio
    async def test_distinct_record_ids_are_never_conflated(self, page):
        """The reason exact content wins: these two outcomes are not the same.

        Saving order 847213 and saving order 847214 are different actions. Any
        normalisation aggressive enough to absorb a timestamp also absorbs this
        distinction, and then Stage-4 equivalence would dismiss a real defect
        because some other control "did the same thing".
        """
        await page.set_content("<div id='log'>idle</div>")

        before = await page.evaluate(channels.SNAPSHOT_JS)
        await page.evaluate(
            "() => { document.getElementById('log').textContent = 'order 847213'; }"
        )
        left = await page.evaluate(channels.SNAPSHOT_JS)
        await page.evaluate(
            "() => { document.getElementById('log').textContent = 'order 847214'; }"
        )
        right = await page.evaluate(channels.SNAPSHOT_JS)

        assert not channels.diff(before, left).same_as(channels.diff(before, right))

    @pytest.mark.asyncio
    async def test_genuinely_different_text_still_differs(self, page):
        """The counterpart: normalisation must not blind us to a real difference.

        This is the ``Enter does something else`` case. Both modalities change
        the DOM; they change it to different things, and that is the defect.
        """
        await page.set_content("<div id='log'>idle</div>")

        before = await page.evaluate(channels.SNAPSHOT_JS)
        await page.evaluate("() => { document.getElementById('log').textContent = 'CLICKED'; }")
        clicked = await page.evaluate(channels.SNAPSHOT_JS)
        await page.evaluate(
            "() => { document.getElementById('log').textContent = 'SOMETHING ELSE'; }"
        )
        other = await page.evaluate(channels.SNAPSHOT_JS)

        assert not channels.diff(before, clicked).same_as(channels.diff(before, other))


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["display:none", "width:0;height:0;overflow:hidden"])
async def test_zero_box_is_reported_without_locator_exception(page, style):
    await page.set_content(f'<div data-probe="t1" style="{style}">action</div>')
    found = await locate(page)
    assert found["found"]
    assert "zero-size" in found["reasons"]
    assert not found["hit_testable"]
    assert found["x"] is None and found["y"] is None


class TestCoverageAcrossReloads:
    """V8 must keep reporting a *named fixture handler* that runs again.

    With ``callCount`` false, precise coverage marks a function covered once and
    omits it from every later read, so a coverage differential sees an empty
    keyboard set for a handler that demonstrably ran.

    An earlier version of this test asserted only that *some* functions were
    recorded, and passed under both settings because the harness itself
    executes dozens of functions per read. The assertion has to name the
    fixture's own handler, over fixture-origin-filtered coverage, or it tests
    the instrument instead of the page.
    """

    async def test_the_named_handler_is_reported_on_a_second_run(self, page):
        origin = "https://example.test"
        await page.route(
            f"{origin}/**",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body=(
                    "<script>function openReport(){window.__ran=(window.__ran||0)+1;}</script>"
                    "<button id='t1' onclick='openReport()'>go</button>"
                ),
            ),
        )
        cdp = await page.context.new_cdp_session(page)
        await coverage.start(cdp)

        seen = []
        for _ in range(2):
            await page.goto(f"{origin}/p.html", wait_until="load")
            await coverage.take(cdp, origin)  # reset
            await page.click("#t1")
            await page.wait_for_timeout(150)
            executed = await coverage.take(cdp, origin)
            seen.append({c for c in executed if "openReport" in c})

        assert seen[0], "first click did not record the fixture handler at all"
        assert seen[1], (
            "the handler ran again after a reload but coverage reported nothing: "
            "precise coverage was armed with callCount false"
        )
        assert seen[0] == seen[1], "the same handler must have the same identity"
