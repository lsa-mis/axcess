"""Pins each transcribed rule in ``upstream_candidates`` to upstream's source.

The instrument could be extracted verbatim; these detectors could not, because
their ``evaluate`` bodies carry TypeScript annotations. A hand transcription is
exactly where a rule quietly goes missing, so each test below fixes one rule
that differs from our own detector — the seven inline attributes, the five
handler properties, D3's tabindex *exclusion*, D4's token boundary, D5's event
set and depth, D6's element-only targets. Asserting a whole detector at once
would pass while any single rule drifted.

Every case runs in a real browser against the transcribed ``UPSTREAM_INIT_JS``,
because the detectors read ``window.__a11y`` and no mock reproduces a pierced
shadow tree.
"""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from experiments.tabbing.runner import upstream_candidates as uc
from experiments.tabbing.runner.upstream_instrument import UPSTREAM_INIT_JS

VIEWPORT = {"width": 1280, "height": 900}


@pytest.fixture
async def armed():
    """A page with upstream's instrument installed at document-start."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(viewport=VIEWPORT)
    await context.add_init_script(UPSTREAM_INIT_JS)
    page = await context.new_page()

    async def load(body: str):
        await page.goto("about:blank")
        await page.set_content(f"<!doctype html><html><body>{body}</body></html>")
        await page.wait_for_timeout(50)
        return page

    try:
        yield load
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


class TestD2InlineAttributeScan:
    """Upstream tests seven inline attributes; ours tested `onclick` alone."""

    @pytest.mark.parametrize(
        "attribute",
        [
            "onclick",
            "onkeyup",
            "onkeydown",
            "onkeypress",
            "onmousedown",
            "onmouseup",
            "onmouseover",
        ],
    )
    async def test_every_inline_attribute_is_scanned(self, armed, attribute):
        page = await armed(f'<div data-probe="p1" {attribute}="void 0">x</div>')
        assert await uc.survey(page, "attrScan") == {"p1"}

    async def test_a_natively_focusable_element_is_excluded(self, armed):
        page = await armed('<button data-probe="p1" onclick="void 0">x</button>')
        assert await uc.survey(page, "attrScan") == set()

    async def test_an_anchor_without_href_is_not_natively_focusable(self, armed):
        """Their `nativelyFocusable` requires href on <a>; without it the scan fires."""
        page = await armed('<a data-probe="p1" onclick="void 0">x</a>')
        assert await uc.survey(page, "attrScan") == {"p1"}

    async def test_an_anchor_with_href_is_excluded(self, armed):
        page = await armed('<a data-probe="p1" href="#" onclick="void 0">x</a>')
        assert await uc.survey(page, "attrScan") == set()

    async def test_any_tabindex_excludes(self, armed):
        page = await armed('<div data-probe="p1" tabindex="0" onclick="void 0">x</div>')
        assert await uc.survey(page, "attrScan") == set()


class TestD2bHandlerPropertyScan:
    """Five properties, not one, and the property rather than the attribute."""

    @pytest.mark.parametrize(
        "prop", ["onclick", "onmousedown", "onmouseup", "onmouseover", "ondblclick"]
    )
    async def test_every_handler_property_is_scanned(self, armed, prop):
        page = await armed('<div data-probe="p1">x</div>')
        await page.evaluate(
            f"() => {{ document.querySelector('[data-probe=p1]').{prop} = () => {{}}; }}"
        )
        assert await uc.survey(page, "handlerProp") == {"p1"}

    async def test_an_assigned_property_is_seen_without_any_markup(self, armed):
        """The point of D2b: React assigns the property, leaving the markup bare."""
        page = await armed('<div data-probe="p1">x</div>')
        assert await uc.survey(page, "handlerProp") == set()
        await page.evaluate(
            "() => { document.querySelector('[data-probe=p1]').onclick = () => {}; }"
        )
        assert await uc.survey(page, "handlerProp") == {"p1"}


class TestD3TabindexCounter:
    """Upstream *excludes* anything carrying tabindex; ours proposed on it."""

    async def test_an_interactive_role_without_tabindex_is_proposed(self, armed):
        page = await armed('<div data-probe="p1" role="button">x</div>')
        assert await uc.survey(page, "tabindexCounter") == {"p1"}

    async def test_the_same_element_with_tabindex_is_excluded(self, armed):
        page = await armed('<div data-probe="p1" role="button" tabindex="0">x</div>')
        assert await uc.survey(page, "tabindexCounter") == set()

    @pytest.mark.parametrize("attribute", ["aria-expanded", "aria-haspopup"])
    async def test_aria_state_counts_as_looking_interactive(self, armed, attribute):
        page = await armed(f'<div data-probe="p1" {attribute}="true">x</div>')
        assert await uc.survey(page, "tabindexCounter") == {"p1"}

    async def test_an_inline_handler_counts_as_looking_interactive(self, armed):
        page = await armed('<div data-probe="p1" onmouseup="void 0">x</div>')
        assert await uc.survey(page, "tabindexCounter") == {"p1"}

    async def test_a_plain_div_is_not_proposed(self, armed):
        page = await armed('<div data-probe="p1">x</div>')
        assert await uc.survey(page, "tabindexCounter") == set()


class TestD4CssLexical:
    """Their lexicon matches on token boundaries; a substring match over-fires."""

    async def test_a_class_token_matches(self, armed):
        page = await armed('<div data-probe="p1" class="btn primary">x</div>')
        assert await uc.survey(page, "cssLexical") == {"p1"}

    async def test_a_bare_substring_does_not_match(self, armed):
        """`subtlety` contains `tab`, and a substring lexicon would fire on it."""
        page = await armed('<div data-probe="p1" class="subtlety">x</div>')
        assert await uc.survey(page, "cssLexical") == set()

    @pytest.mark.parametrize("cls", ["icon-close", "menu_open", "nav bar", "card"])
    async def test_separators_delimit_tokens(self, armed, cls):
        page = await armed(f'<div data-probe="p1" class="{cls}">x</div>')
        assert await uc.survey(page, "cssLexical") == {"p1"}

    async def test_cursor_pointer_alone_matches(self, armed):
        page = await armed('<div data-probe="p1" style="cursor:pointer">x</div>')
        assert await uc.survey(page, "cssLexical") == {"p1"}


class TestD7ReactProps:
    """Three fiber props, and only on the randomised __reactProps$ key."""

    async def test_a_fiber_onclick_is_found(self, armed):
        page = await armed('<div data-probe="p1">x</div>')
        await page.evaluate(
            "() => { const e = document.querySelector('[data-probe=p1]');"
            " e['__reactProps$abc'] = { onClick: () => {} }; }"
        )
        assert await uc.survey(page, "reactProps") == {"p1"}

    async def test_an_unrelated_prop_key_is_ignored(self, armed):
        page = await armed('<div data-probe="p1">x</div>')
        await page.evaluate(
            "() => { const e = document.querySelector('[data-probe=p1]');"
            " e['__somethingElse'] = { onClick: () => {} }; }"
        )
        assert await uc.survey(page, "reactProps") == set()


class TestVisibilityGate:
    """Every generator is filtered through upstream's isVisible."""

    async def test_a_hidden_probe_is_not_surveyed(self, armed):
        page = await armed(
            '<div data-probe="p1" style="display:none" onclick="void 0">x</div>'
            '<div data-probe="p2" onclick="void 0">y</div>'
        )
        assert await uc.survey(page, "attrScan") == {"p2"}
        assert "p1" not in await uc.visible_probes(page)


class TestD6ListenerShim:
    """Seven types, and delegation to document/window is excluded by nodeType."""

    async def test_an_element_listener_is_recorded(self, armed):
        page = await armed('<div data-probe="p1">x</div>')
        await page.evaluate(
            "() => document.querySelector('[data-probe=p1]')"
            ".addEventListener('pointerdown', () => {})"
        )
        hits, provenance = await uc.d6_listener_shim(page)
        assert hits == {"p1"} and provenance["p1"]

    async def test_delegation_on_document_is_excluded(self, armed):
        page = await armed('<div data-probe="p1">x</div>')
        await page.evaluate("() => document.addEventListener('click', () => {})")
        hits, _ = await uc.d6_listener_shim(page)
        assert hits == set()

    async def test_a_keyboard_listener_is_not_a_mouse_listener(self, armed):
        page = await armed('<div data-probe="p1">x</div>')
        await page.evaluate(
            "() => document.querySelector('[data-probe=p1]').addEventListener('keydown', () => {})"
        )
        hits, _ = await uc.d6_listener_shim(page)
        assert hits == set()


class TestD0CurrentCrawler:
    """Their crawler's own selector list, filters and probeOf mapping."""

    async def test_a_button_is_collected(self, armed):
        page = await armed('<button data-probe="p1">x</button>')
        assert await uc.d0_current_crawler(page) == {"p1"}

    async def test_an_element_inside_a_link_is_dropped(self, armed):
        page = await armed('<a href="#"><button data-probe="p1">x</button></a>')
        assert await uc.d0_current_crawler(page) == set()

    async def test_table_cells_are_dropped(self, armed):
        page = await armed('<table><tr><td data-probe="p1" onclick="void 0">x</td></tr></table>')
        assert await uc.d0_current_crawler(page) == set()

    async def test_probe_of_walks_up_to_an_ancestor(self, armed):
        """`probeOf` climbs to the nearest labelled ancestor rather than giving up."""
        page = await armed('<div data-probe="p1"><button id="inner">x</button></div>')
        assert await uc.d0_current_crawler(page) == {"p1"}


class TestD5CdpListeners:
    """Pierced resolution, depth 0, eight mouse types."""

    async def test_a_listener_inside_a_closed_shadow_root_is_found(self, armed):
        """The capability our Playwright-locator version does not have."""
        page = await armed("<div id='host'></div>")
        await page.evaluate(
            "() => { const r = document.getElementById('host').attachShadow({mode:'closed'});"
            " const b = document.createElement('div'); b.setAttribute('data-probe','p1');"
            " b.textContent = 'x'; b.addEventListener('click', () => {}); r.appendChild(b); }"
        )
        cdp = await page.context.new_cdp_session(page)
        nodes = await uc.resolve_probe_nodes(cdp)
        assert "p1" in nodes, "the pierced tree must reach a closed root"
        assert await uc.d5_cdp_listeners(cdp, nodes) == {"p1"}

    @pytest.mark.parametrize("event", sorted(uc.UPSTREAM_MOUSE_EVENTS))
    async def test_every_mouse_event_in_their_set_counts(self, armed, event):
        page = await armed('<div data-probe="p1">x</div>')
        await page.evaluate(
            f"() => document.querySelector('[data-probe=p1]')"
            f".addEventListener('{event}', () => {{}})"
        )
        cdp = await page.context.new_cdp_session(page)
        nodes = await uc.resolve_probe_nodes(cdp)
        assert await uc.d5_cdp_listeners(cdp, nodes) == {"p1"}

    async def test_a_descendants_listener_is_not_credited_at_depth_zero(self, armed):
        """`depth: 1` would report a child's listener as the probe's own."""
        page = await armed('<div data-probe="p1"><span id="kid">x</span></div>')
        await page.evaluate(
            "() => document.getElementById('kid').addEventListener('click', () => {})"
        )
        cdp = await page.context.new_cdp_session(page)
        nodes = await uc.resolve_probe_nodes(cdp)
        assert await uc.d5_cdp_listeners(cdp, nodes) == set()
