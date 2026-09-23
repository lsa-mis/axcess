"""The New scan form: two tabs, one live form, errors that are announced.

Playwright against the built SPA. Every test here is about the behaviour the
rework introduced: the URL hero's states, the focused error alert, the live
default card and summary rail, 44 px targets, and axe with the AAA rules on.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from .test_accessibility_axe import _AXE_TEXT, _render_violations

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")


# Interactive elements in the form that are shorter than 44 px. Native
# checkboxes are exempt: they are 22 px inside a 44 px label row, and the
# row is the target.
_SMALL_TARGETS = """() => {
    const selector = 'form a, form button, form input, form select';
    return [...document.querySelectorAll(selector)]
        .filter(el => el.getClientRects().length
                      && getComputedStyle(el).position !== 'absolute')
        .map(el => {
            const box = el.getBoundingClientRect();
            const name = el.innerText || el.getAttribute('aria-label') || el.type || '';
            return {tag: el.tagName, type: el.type, name: name.trim().slice(0, 40),
                    w: Math.round(box.width), h: Math.round(box.height)};
        })
        .filter(el => el.h > 0 && el.h < 44
                      && !(el.tag === 'INPUT' && el.type === 'checkbox'));
}"""


async def _run_axe_aaa(page) -> list[dict]:  # type: ignore[no-untyped-def]
    """axe with the AAA rules it ships disabled switched on."""
    await page.add_script_tag(content=_AXE_TEXT)
    return list(
        await page.evaluate(
            """async () => {
                const res = await window.axe.run(document, {
                    rules: {
                        'color-contrast-enhanced': {enabled: true},
                        'target-size': {enabled: true},
                        'identical-links-same-purpose': {enabled: true},
                    },
                });
                return res.violations;
            }"""
        )
    )


async def test_url_hero_names_the_field_and_describes_the_scope(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    url = page.get_by_role("textbox", name="Site URL", exact=True)
    await playwright_async.expect(url).to_be_focused()
    # The name is the label alone; help and scope are descriptions.
    described = await url.get_attribute("aria-describedby")
    assert described == "scan-url-help scan-url-scope"
    scope = page.locator("#scan-url-scope")
    await playwright_async.expect(scope).to_have_text("")

    await url.fill("https://example.com/section")
    await playwright_async.expect(scope).to_contain_text("Will scan")
    await playwright_async.expect(scope).to_contain_text("example.com/section/")
    await playwright_async.expect(scope).to_contain_text("A trailing slash was added")
    assert await scope.get_attribute("role") == "status"


async def test_empty_submit_is_announced_focused_and_linked(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    start = page.get_by_role("button", name="Start scan")
    # Never disabled: pressing it is how you find out what is wrong.
    await playwright_async.expect(start).to_be_enabled()
    await start.click()
    alert = page.get_by_role("alert")
    await playwright_async.expect(alert).to_be_visible()
    await playwright_async.expect(alert).to_be_focused()
    url = page.get_by_role("textbox", name="Site URL", exact=True)
    assert await url.get_attribute("aria-invalid") == "true"
    assert "scan-url-error" in (await url.get_attribute("aria-describedby") or "")
    await alert.get_by_role("link", name="Enter the page to start from.").click()
    await playwright_async.expect(url).to_be_focused()
    # Typing clears that line; the alert goes with it.
    await url.fill("https://example.com/")
    await playwright_async.expect(alert).to_have_count(0)


async def test_fast_crawl_with_axe_blocks_start_with_an_inline_alert(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await page.get_by_role("textbox", name="Site URL", exact=True).fill("https://example.com/")
    await page.get_by_role("button", name="Speed and debugging", exact=True).click()
    fast = page.get_by_role("switch", name=re.compile(r"^Fast crawl without a browser"))
    await fast.check()
    # Rendered-page checks switch themselves off and say why.
    keyboard = page.get_by_role("switch", name=re.compile(r"^Check for keyboard traps"))
    await playwright_async.expect(keyboard).to_be_disabled()
    await page.get_by_role("button", name="Start scan").click()
    inline = page.locator("#scan-static-only-error")
    await playwright_async.expect(inline).to_contain_text("cannot run with axe-core")
    assert await fast.get_attribute("aria-invalid") == "true"
    await playwright_async.expect(page.get_by_role("alert").first).to_be_focused()


async def test_default_card_and_summary_follow_the_switches(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    card = page.get_by_role("region", name=re.compile(r"^Default scan settings"))
    summary = page.get_by_role("complementary", name="What this scan will do")
    await playwright_async.expect(card.get_by_text("Selected", exact=True)).to_be_visible()
    await playwright_async.expect(summary).to_contain_text("5 of 8 checks on")

    pages = page.get_by_role("spinbutton", name="Max pages")
    await pages.fill("300")
    await playwright_async.expect(summary).to_contain_text("Up to 300 pages")
    await playwright_async.expect(card).to_contain_text("Up to 300 pages")
    await playwright_async.expect(card.get_by_text("Customized", exact=True)).to_be_visible()

    keyboard = page.get_by_role("switch", name=re.compile(r"^Check for keyboard traps"))
    await keyboard.uncheck()
    await playwright_async.expect(summary).to_contain_text("Keyboard traps off")
    await playwright_async.expect(summary).to_contain_text("4 of 8 checks on")
    # Struck through, and said out loud.
    await playwright_async.expect(card.locator("li", has_text="Keyboard traps")).to_contain_text(
        "turned off"
    )

    await card.get_by_role("button", name="Reset to default").click()
    await playwright_async.expect(card.get_by_text("Selected", exact=True)).to_be_visible()
    await playwright_async.expect(pages).to_have_value("2500")
    await playwright_async.expect(keyboard).to_be_checked()


@pytest.mark.parametrize("mode", ["public", "login"])
async def test_form_targets_are_44px_and_axe_aaa_clean(
    live_server: tuple[str, int], mode: str, new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new?mode={mode}", wait_until="networkidle")
    for name in ("Local AI", "Speed and debugging"):
        await page.get_by_role("button", name=name, exact=True).click()
    small = await page.evaluate(_SMALL_TARGETS)
    # Native checkboxes are 22px inside a 44px label row, which is the
    # target; everything else must stand on its own.
    assert not small, small
    violations = await _run_axe_aaa(page)
    assert not violations, _render_violations(violations)

    await page.set_viewport_size({"width": 375, "height": 812})
    assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
