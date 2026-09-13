"""Exercise cheap discovery features against browser behavior, without labels."""

import sys
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from audit.analyzer.keyboard.kbdiff.taborder import compute_tab_order
from experiments.tabbing.runner import candidate_analysis as ca
from experiments.tabbing.runner.upstream_instrument import UPSTREAM_INIT_JS


@pytest.fixture
async def page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        await context.add_init_script(UPSTREAM_INIT_JS)
        page = await context.new_page()
        await page.goto("about:blank")
        try:
            yield page
        finally:
            await context.close()
            await browser.close()


async def test_labels_use_association_and_real_tab_reachability(page):
    await page.set_content("""
        <input data-probe="hidden" id="hidden" type="checkbox" style="display:none">
        <label data-probe="bad-label" for="hidden">Hidden toggle</label>
        <input data-probe="clipped" id="clipped" type="checkbox"
          style="position:absolute;width:1px;height:1px;clip-path:inset(50%)">
        <label data-probe="good-label" for="clipped">Clipped toggle</label>
    """)
    order = await compute_tab_order(page)
    features = await ca.collect_features(page)
    assert "hidden" not in order.index and "clipped" in order.index
    assert features["bad-label"]["visible"]
    assert features["bad-label"]["control_visible"] is False
    assert features["good-label"]["control_probe"] == "clipped"
    result = ca.build_variants(
        {k: set() for k in ("D4", "D5", "D6", "D8")}, features, set(order.index)
    )
    assert result.reported[ca.LABEL] == {"bad-label"}


async def test_key_and_ancestor_features_do_not_pretend_to_prove_effects(page):
    await page.set_content("""
        <section id="parent">
          <div data-probe="mouse" tabindex="0">Mouse only</div>
          <div data-probe="keys" tabindex="0">Both handlers</div>
          <p data-probe="plain">Plain text</p>
          <button data-probe="native">Native button</button>
        </section>
        <script>
          const q = id => document.querySelector('[data-probe="' + id + '"]');
          q('mouse').addEventListener('click', () => {});
          q('keys').addEventListener('click', () => {});
          q('keys').addEventListener('keydown', () => {});
          document.getElementById('parent').addEventListener('click', () => {});
        </script>
    """)
    features = await ca.collect_features(page)
    assert features["keys"]["has_key_handler"]
    assert not features["mouse"]["has_key_handler"]
    assert features["plain"]["delegated_types"] == ["click"]
    assert features["native"]["native"]
    assert features["mouse"]["delegated_types"] == ["click"]


async def test_gates_observe_inert_ancestors_overlay_and_offscreen_uncertainty(page):
    await page.set_content("""
        <div inert><div data-probe="inert">Unavailable</div></div>
        <div data-probe="pointer" style="pointer-events:none">Not a pointer target</div>
        <div data-probe="covered" style="position:absolute;top:200px;left:100px;
            width:100px;height:50px">Behind</div>
        <div style="position:absolute;top:200px;left:100px;width:100px;height:50px;
            background:white;z-index:10">Cover</div>
        <div data-probe="offscreen" style="position:absolute;top:2000px">Below fold</div>
    """)
    features = await ca.collect_features(page)
    assert features["inert"]["inert"]
    assert features["pointer"]["pointer_events_none"]
    assert features["covered"]["center_hit"] is False
    assert features["offscreen"]["center_hit"] is None
    assert features["offscreen"]["visible"]


async def test_features_capture_closed_shadow_controls(page):
    await page.set_content('<div id="host"></div>')
    await page.evaluate("""() => {
        const root = document.getElementById('host').attachShadow({mode:'closed'});
        root.innerHTML = '<button data-probe="closed">Action</button>';
    }""")
    features = await ca.collect_features(page)
    assert features["closed"]["closed_shadow"]
    assert features["closed"]["visible"]


async def test_missing_instrument_is_failure_not_empty_evidence(page):
    await page.evaluate("delete window.__a11y")
    with pytest.raises(Exception, match="instrumentation is missing"):
        await ca.collect_features(page)
