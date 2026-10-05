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
from .test_accessibility_axe import _SCAN_GROUPS as _GROUPS
from .test_accessibility_axe import _open_scan_groups as _open_groups

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")


async def _rail_items(summary: Any, term: str) -> list[str]:
    """The items listed, one per line, under one part of the summary rail."""
    texts = (
        await summary.locator("dt", has_text=re.compile(rf"^{term}$"))
        .locator("xpath=following-sibling::dd[1]")
        .locator("li")
        .all_text_contents()
    )
    return [text.strip() for text in texts]


async def _switch_label(switch: Any) -> str:
    """A switch's name: its label's title line, not its hint."""
    return str(
        await switch.evaluate(
            "el => el.closest('label').querySelector('span.font-semibold').textContent"
        )
    )


# Each check switch and the short name the rail lists it by.
_RAIL_NAME = {
    "Open menus, tabs, and pop-up windows (Click-Through)": (
        "Opens menus and pop-up windows (Click-Through)"
    ),
    "Check for keyboard traps": "Keyboard check",
    "Check that keyboard focus is never hidden": "Focus check",
    "Check narrow screens and zoom": "Zoom and layout check",
    "Read text inside images (OCR)": "Image text check",
    "Compare image text with alt text (vision model)": "Vision model review",
    "AI review of wording": "AI review",
    "Check motion and animation": "Motion and reading-order check",
}


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
    url = page.get_by_role("textbox", name="Website address", exact=True)
    await playwright_async.expect(url).to_be_focused()
    # The name is the label alone; help and scope are descriptions.
    described = await url.get_attribute("aria-describedby")
    assert described == "scan-url-help scan-url-scope"
    scope = page.locator("#scan-url-scope")
    # Before anything is typed it says where the answer will appear.
    await playwright_async.expect(scope).to_have_text(
        "Enter a website address to see what will be scanned."
    )

    await url.fill("https://example.com/section")
    await playwright_async.expect(scope).to_contain_text("Will scan")
    await playwright_async.expect(scope).to_contain_text("example.com/section/")
    await playwright_async.expect(scope).to_contain_text("Axcess added a slash (/) at the end")
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
    url = page.get_by_role("textbox", name="Website address", exact=True)
    assert await url.get_attribute("aria-invalid") == "true"
    assert "scan-url-error" in (await url.get_attribute("aria-describedby") or "")
    await alert.get_by_role("link", name="Enter a website address to start from.").click()
    await playwright_async.expect(url).to_be_focused()
    # Typing clears that line; the alert goes with it.
    await url.fill("https://example.com/")
    await playwright_async.expect(alert).to_have_count(0)


async def test_enter_in_the_address_field_starts_the_scan(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Start is at the foot of the summary rail, and still the form's default button.

    It names the form it submits, so Enter in a field submits as before: an
    empty address shows the alert rather than doing nothing.
    """
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    url = page.get_by_role("textbox", name="Website address", exact=True)
    await url.focus()
    await page.keyboard.press("Enter")
    alert = page.get_by_role("alert")
    await playwright_async.expect(alert).to_be_focused()
    await playwright_async.expect(alert).to_contain_text("Enter a website address to start from.")


async def test_fast_crawl_with_axe_blocks_start_with_an_inline_alert(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await page.get_by_role("textbox", name="Website address", exact=True).fill(
        "https://example.com/"
    )
    await _open_groups(page)
    fast = page.get_by_role("switch", name=re.compile(r"^Fast scan without a browser"))
    await fast.check()
    # Rendered-page checks switch themselves off and say why.
    keyboard = page.get_by_role("switch", name=re.compile(r"^Check for keyboard traps"))
    await playwright_async.expect(keyboard).to_be_disabled()
    # Folded again: a failed submit must reopen it so the alert's link
    # lands on a visible switch.
    speed = page.get_by_role("button", name="Speed and browser window", exact=True)
    start = page.get_by_role("button", name="Start scan")
    await speed.click()
    await playwright_async.expect(speed).to_have_attribute("aria-expanded", "false")
    await start.click()
    await playwright_async.expect(speed).to_have_attribute("aria-expanded", "true")
    inline = page.locator("#scan-static-only-error")
    await playwright_async.expect(inline).to_contain_text("cannot run Rule check (axe)")
    assert await fast.get_attribute("aria-invalid") == "true"
    await playwright_async.expect(page.get_by_role("alert").first).to_be_focused()
    # And again on a second try with the same error.
    await speed.click()
    await playwright_async.expect(speed).to_have_attribute("aria-expanded", "false")
    await start.click()
    await playwright_async.expect(speed).to_have_attribute("aria-expanded", "true")
    await playwright_async.expect(inline).to_be_visible()


async def test_summary_rail_follows_the_switches_and_resets(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    summary = page.get_by_role("complementary", name="What this scan will do")
    await playwright_async.expect(
        summary.get_by_text("Default settings", exact=True)
    ).to_be_visible()
    assert "Keyboard check" in await _rail_items(summary, "Checks that run")
    # The spoken digest is outside the summary and silent until something
    # changes, so reading the rail never hears it twice.
    digest = page.get_by_role("status").filter(has_text="Summary updated")
    await playwright_async.expect(digest).to_have_count(0)
    assert await summary.get_by_role("status").count() == 0

    await _open_groups(page)
    pages = page.get_by_role("spinbutton", name="Maximum pages")
    await pages.fill("300")
    await playwright_async.expect(summary).to_contain_text("Up to 300 pages")
    await playwright_async.expect(summary.get_by_text("Customized", exact=True)).to_be_visible()
    await playwright_async.expect(digest).to_contain_text("Up to 300 pages, 10 clicks deep")

    keyboard = page.get_by_role("switch", name=re.compile(r"^Check for keyboard traps"))
    await keyboard.uncheck()
    # Off moves it from Checks that run to Not included.
    await playwright_async.expect(summary).to_contain_text("Customized")
    assert "Keyboard check" not in await _rail_items(summary, "Checks that run")
    assert "Keyboard check" in await _rail_items(summary, "Not included")

    # Reset sits at the top right of the summary, beside "Customized", and
    # only while something has changed. Pressed, it goes away, and focus
    # moves to the summary's heading instead of being lost.
    reset = summary.get_by_role("button", name="Reset to default settings")
    await reset.click()
    await playwright_async.expect(
        summary.get_by_text("Default settings", exact=True)
    ).to_be_visible()
    await playwright_async.expect(reset).to_have_count(0)
    await playwright_async.expect(
        summary.get_by_role("heading", name="What this scan will do")
    ).to_be_focused()
    await playwright_async.expect(pages).to_have_value("2500")
    await playwright_async.expect(keyboard).to_be_checked()


@pytest.mark.parametrize("mode", ["public", "login"])
async def test_form_targets_are_44px_and_axe_aaa_clean(
    live_server: tuple[str, int], mode: str, new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new?mode={mode}", wait_until="networkidle")
    # A collapsed panel is hidden, so axe and the target check would skip
    # every control in it: open every group first.
    await _open_groups(page)
    small = await page.evaluate(_SMALL_TARGETS)
    # Native checkboxes are 22px inside a 44px label row, which is the
    # target; everything else must stand on its own.
    assert not small, small
    violations = await _run_axe_aaa(page)
    assert not violations, _render_violations(violations)

    await page.set_viewport_size({"width": 375, "height": 812})
    # The settled layout must fit. The Scan type tabs' sliding indicator
    # glides to its new place after a resize, so measure once it has landed.
    await page.wait_for_function(
        "document.documentElement.scrollWidth <= window.innerWidth", timeout=2000
    )


async def test_wcag_version_defaults_to_21_and_rides_in_the_payload(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """2.1 is the default; picking 2.2 customizes the scan and is what posts."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    posted: list[dict[str, Any]] = []

    async def capture(route: Any) -> None:
        posted.append(route.request.post_data_json)
        # Refuse politely so the form stays put and no crawl starts.
        await route.fulfill(status=409, json={"error": "A crawl is already running."})

    await page.route("**/api/scans", capture)
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    summary = page.get_by_role("complementary", name="What this scan will do")
    await _open_groups(page)
    versions = page.get_by_role("group", name="WCAG version")
    v21 = versions.get_by_role("radio", name="2.1", exact=True)
    v22 = versions.get_by_role("radio", name="2.2", exact=True)

    await playwright_async.expect(v21).to_be_checked()
    await playwright_async.expect(
        summary.get_by_text("Default settings", exact=True)
    ).to_be_visible()
    await playwright_async.expect(summary).to_contain_text(
        "WCAG 2.1 Level AA, checked with Rule check (axe)"
    )
    checks_before = await _rail_items(summary, "Checks that run")

    await v22.check()
    await playwright_async.expect(summary.get_by_text("Customized", exact=True)).to_be_visible()
    await playwright_async.expect(summary).to_contain_text(
        "WCAG 2.2 Level AA, checked with Rule check (axe)"
    )
    # The version is a standard, not a check: nothing else in the list moves.
    assert await _rail_items(summary, "Checks that run") == checks_before

    await page.get_by_role("textbox", name="Website address", exact=True).fill(
        "https://example.com/"
    )
    await page.get_by_role("button", name="Start scan").click()
    await playwright_async.expect(page.get_by_role("alert").first).to_be_visible()
    assert posted and posted[-1]["wcag_version"] == "2.2"

    await page.locator("form").get_by_role("button", name="Reset to default settings").click()
    await playwright_async.expect(v21).to_be_checked()
    await playwright_async.expect(
        summary.get_by_text("Default settings", exact=True)
    ).to_be_visible()


@pytest.mark.parametrize(
    ("typed", "completed"),
    [
        ("example.edu/section/", "https://example.edu/section/"),
        ("localhost:8000", "http://localhost:8000"),
        ("192.168.1.10/app", "http://192.168.1.10/app"),
        ("http://example.edu/", "http://example.edu/"),
    ],
)
async def test_an_address_without_a_scheme_is_completed(
    live_server: tuple[str, int], new_page: Any, typed: str, completed: str
) -> None:
    """No "Add https://" error: New scan adds the scheme (lib/webAddress.ts),
    shows it in the box on leaving it, and sends it, even on Enter."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})

    async def refuse(route: Any) -> None:
        # Refuse politely so the form stays put and no crawl starts.
        await route.fulfill(status=409, json={"error": "A crawl is already running."})

    await page.route("**/api/scans", refuse)
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    field = page.get_by_role("textbox", name="Website address", exact=True)

    # Leaving the box shows the address as it will be scanned.
    await field.fill(typed)
    await page.keyboard.press("Tab")
    await playwright_async.expect(field).to_have_value(completed)
    await playwright_async.expect(field).not_to_have_attribute("aria-invalid", "true")

    # Enter submits without leaving the box; what is sent is still complete.
    await field.fill(typed)
    async with page.expect_request("**/api/scans") as sent:
        await field.press("Enter")
    assert (await sent.value).post_data_json["url"] == completed


@pytest.mark.parametrize("mode", ["public", "login"])
async def test_settings_are_closed_accordions_and_start_is_top_right(
    live_server: tuple[str, int], new_page: Any, mode: str
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new?mode={mode}", wait_until="networkidle")
    # Every group is an accordion row, closed on arrival: the first screen
    # is the address, the group names and the rail saying what will run.
    for name in _GROUPS:
        button = page.get_by_role("button", name=name, exact=True)
        await playwright_async.expect(button).to_have_attribute("aria-expanded", "false")
        panel = page.locator(f"#{await button.get_attribute('aria-controls')}")
        await playwright_async.expect(panel).to_be_hidden()
    await playwright_async.expect(
        page.get_by_role("spinbutton", name="Maximum pages")
    ).to_be_hidden()
    # No second summary to keep in step with the rail.
    await playwright_async.expect(
        page.get_by_role("heading", name="Advanced settings", exact=True)
    ).to_have_count(0)

    # One click opens a group; its fieldset keeps the group's name.
    limits = page.get_by_role("button", name="Limits and rule check tool", exact=True)
    await limits.click()
    await playwright_async.expect(limits).to_have_attribute("aria-expanded", "true")
    await playwright_async.expect(
        page.get_by_role("group", name="Limits and rule check tool", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("group", name="Rule check tool", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("spinbutton", name="Maximum pages")
    ).to_be_visible()

    # Start is at the foot of the summary rail, beside the form, not in the
    # page header; it comes after the fields in keyboard order, and it stays
    # in view as the page scrolls. Start still names the form.
    heading = await page.get_by_role("heading", name="New scan", level=1).bounding_box()
    start_button = page.get_by_role("button", name=re.compile(r"^(Start scan|Open browser)"))
    start = await start_button.bounding_box()
    url = await page.locator("#scan-url").bounding_box()
    assert heading and start and url
    assert start["x"] > url["x"] + url["width"], "Start sits in the rail, right of the form"
    assert start["y"] > heading["y"] + 40, "Start is not on the title's row"
    after_url = await page.evaluate(
        """() => {
          const url = document.getElementById('scan-url');
          const start = [...document.querySelectorAll('button')].find(
            (b) => /^(Start scan|Open browser)/.test(b.textContent.trim()));
          return !!(url.compareDocumentPosition(start) & Node.DOCUMENT_POSITION_FOLLOWING);
        }"""
    )
    assert after_url, "Start comes after the fields in keyboard order"
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await playwright_async.expect(start_button).to_be_in_viewport()
    await page.evaluate("window.scrollTo(0, 0)")
    await playwright_async.expect(start_button).to_be_in_viewport()
    await playwright_async.expect(start_button).to_have_attribute("form", "scan-form")
    # Start is the only button there: leaving is the sidebar's Reports link
    # or Back, not a Cancel beside Start (SubmitBar.tsx).
    await playwright_async.expect(
        page.get_by_role("button", name=re.compile(r"^Cancel"))
    ).to_have_count(0)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("Maximum pages", "", "Maximum pages is empty. Enter a whole number from 1 to 10,000."),
        ("Maximum pages", "0", "Maximum pages must be at least 1."),
        (
            "Maximum pages",
            "10001",
            "Maximum pages can be at most 10,000 for a public website scan.",
        ),
        ("Maximum pages", "2.5", "Maximum pages must be a whole number."),
        (
            "Maximum link depth",
            "",
            "Maximum link depth is empty. Enter a whole number from 1 to 20.",
        ),
        ("Maximum link depth", "0", "Maximum link depth must be at least 1."),
        (
            "Maximum link depth",
            "21",
            "Maximum link depth can be at most 20 for a public website scan.",
        ),
    ],
)
async def test_limits_are_validated_by_name_with_their_range(
    live_server: tuple[str, int], new_page: Any, field: str, value: str, message: str
) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    posted: list[Any] = []

    async def refuse(route: Any) -> None:
        if route.request.method != "POST":
            await route.continue_()
            return
        posted.append(route.request.post_data_json)
        await route.abort()

    await page.route("**/api/scans", refuse)
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await page.get_by_role("textbox", name="Website address", exact=True).fill(
        "https://example.com/"
    )
    await _open_groups(page)
    box = page.get_by_role("spinbutton", name=field, exact=True)
    # The range is in the field's description before anything goes wrong.
    hint_id = (await box.get_attribute("aria-describedby") or "").split()[0]
    await playwright_async.expect(page.locator(f"#{hint_id}")).to_contain_text(
        "Enter a whole number from 1 to"
    )
    await box.fill(value)
    # An emptied box stays empty; it does not snap back to 0.
    await playwright_async.expect(box).to_have_value(value)
    # Folded before Start: the failed submit opens the group again, so the
    # alert's link lands on a visible field.
    limits = page.get_by_role("button", name="Limits and rule check tool", exact=True)
    await limits.click()
    await playwright_async.expect(box).to_be_hidden()

    await page.get_by_role("button", name="Start scan").click()
    await playwright_async.expect(limits).to_have_attribute("aria-expanded", "true")
    alert = page.get_by_role("alert").first
    await playwright_async.expect(alert).to_be_focused()
    assert await box.get_attribute("aria-invalid") == "true"
    await alert.get_by_role("link", name=message).click()
    await playwright_async.expect(box).to_be_focused()
    assert not posted, "an invalid limit must never be posted"

    # Fixing the value clears its line.
    await box.fill("5")
    await playwright_async.expect(alert.get_by_role("link", name=message)).to_have_count(0)


async def test_scan_every_page_it_finds(live_server: tuple[str, int], new_page: Any) -> None:
    """No page limit: Maximum pages goes off, the rail says so, and it is what posts.

    A sign-in scan keeps its cap, so its form does not offer the switch.
    """
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    posted: list[dict[str, Any]] = []

    async def capture(route: Any) -> None:
        posted.append(route.request.post_data_json)
        await route.fulfill(status=409, json={"error": "A crawl is already running."})

    await page.route("**/api/scans", capture)
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await _open_groups(page)
    summary = page.get_by_role("complementary", name="What this scan will do")
    every = page.get_by_role("switch", name=re.compile(r"^Scan every page it finds"))
    pages = page.get_by_role("spinbutton", name="Maximum pages")
    await playwright_async.expect(every).not_to_be_checked()
    await playwright_async.expect(pages).to_be_enabled()

    await every.check()
    await playwright_async.expect(pages).to_be_disabled()
    hint_id = (await pages.get_attribute("aria-describedby") or "").split()[0]
    await playwright_async.expect(page.locator(f"#{hint_id}")).to_have_text(
        "Off while the scan visits every page it finds."
    )
    await playwright_async.expect(summary).to_contain_text("Every page it finds, 10 clicks deep")
    await playwright_async.expect(summary.get_by_text("Customized", exact=True)).to_be_visible()

    await page.get_by_role("textbox", name="Website address", exact=True).fill(
        "https://example.com/"
    )
    await page.get_by_role("button", name="Start scan").click()
    # The refused request shows its alert once it has been sent.
    await playwright_async.expect(page.get_by_role("alert").first).to_be_visible()
    assert posted and posted[-1]["all_pages"] is True

    await page.goto(f"{base}/app/scans/new?mode=login", wait_until="networkidle")
    await _open_groups(page)
    await playwright_async.expect(
        page.get_by_role("spinbutton", name="Maximum pages")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("switch", name=re.compile(r"^Scan every page it finds"))
    ).to_have_count(0)


async def test_depth_dots_are_gone(live_server: tuple[str, int], new_page: Any) -> None:
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await _open_groups(page)
    limits = page.get_by_role("group", name="Limits and rule check tool", exact=True)
    await playwright_async.expect(
        limits.get_by_role("spinbutton", name="Maximum link depth")
    ).to_be_visible()
    await playwright_async.expect(
        limits.locator("span.rounded-full[class*='h-3.5']")
    ).to_have_count(0)


@pytest.mark.parametrize(
    ("mode", "included", "left_out"),
    [
        (
            "public",
            [
                "Opens menus and pop-up windows (Click-Through)",
                "Keyboard check",
                "Focus check",
                "Zoom and layout check",
                "Image text check",
            ],
            [
                "Pages behind a sign-in",
                "Whole website",
                "Subdomains",
                "Vision model review",
                "AI review",
                "Motion and reading-order check",
            ],
        ),
        (
            "login",
            [
                "Opens menus and pop-up windows (Click-Through)",
                "Keyboard check",
                "Zoom and layout check",
            ],
            [
                "Pages on any other website",
                "Whole signed-in website",
                "Image text check",
                "Vision model review",
            ],
        ),
    ],
)
async def test_rail_names_every_switch_on_the_side_its_state_says(
    live_server: tuple[str, int],
    new_page: Any,
    mode: str,
    included: list[str],
    left_out: list[str],
) -> None:
    """What is on is listed under Checks that run, what is off under Not
    included, each by its short rail name, and a check that cannot run is
    off."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/new?mode={mode}", wait_until="networkidle")
    summary = page.get_by_role("complementary", name="What this scan will do")

    await playwright_async.expect(summary).to_contain_text(
        "WCAG 2.1 Level AA, checked with Rule check (axe)"
    )
    assert await _rail_items(summary, "Checks that run") == included
    assert await _rail_items(summary, "Not included") == left_out
    await _open_groups(page)

    async def agrees() -> None:
        """Every check switch sits on the rail's side its state says."""
        on = set(await _rail_items(summary, "Checks that run"))
        off = set(await _rail_items(summary, "Not included"))
        for group in ("Checks", "AI checks on this computer"):
            switches = page.get_by_role("group", name=group, exact=True).get_by_role("switch")
            for index in range(await switches.count()):
                switch = switches.nth(index)
                label = _RAIL_NAME[await _switch_label(switch)]
                runs = await switch.is_checked() and await switch.is_enabled()
                assert (label in on, label in off) == (runs, not runs), (label, runs)

    await agrees()
    if mode == "public":
        # Fast scan makes the browser checks impossible: they move to Not
        # included even though their switches still read on.
        await _open_groups(page)
        await page.get_by_role("switch", name=re.compile(r"^Fast scan without a browser")).check()
        await playwright_async.expect(summary).to_contain_text("Page code (HTML) only, no browser")
        assert "Keyboard check" in await _rail_items(summary, "Not included")
        await agrees()


def _insert_scan(db_path: Any, *, seed_url: str, config: Any, status: str = "failed") -> int:
    from audit.crawler.orchestrator import config_json_for_scan
    from audit.db.schema import connect

    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, ?, ?)",
            (seed_url, status, config_json_for_scan(config)),
        )
        return int(cursor.lastrowid or 0)


async def test_a_stopped_scan_is_restarted_with_its_settings_and_no_credentials(
    live_server: tuple[str, int],
    seeded_db: tuple[Any, Any, int],
    new_page: Any,
) -> None:
    from audit.crawler.orchestrator import CrawlConfig

    base, _ = live_server
    scan_id = _insert_scan(
        seeded_db[0],
        seed_url="https://reviewer:hunter2@recover.example.test/docs/",
        config=CrawlConfig(
            seed_url="https://recover.example.test/docs/",
            max_pages=321,
            max_depth=4,
            whole_host=True,
            keyboard_probe_enabled=False,
            axe_level="AAA",
            wcag_version="2.2",
        ),
        status="interrupted",
    )
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    edit = page.get_by_role("link", name="Change settings first")
    await playwright_async.expect(edit).to_have_attribute("href", re.compile(rf"from={scan_id}$"))
    await edit.click()

    await playwright_async.expect(
        page.get_by_role("status").filter(
            has_text=re.compile(rf"Axcess copied the settings from scan #?{scan_id}\b")
        )
    ).to_be_visible()
    url = page.get_by_role("textbox", name="Website address", exact=True)
    await playwright_async.expect(url).to_have_value("https://recover.example.test/docs/")
    summary = page.get_by_role("complementary", name="What this scan will do")
    await playwright_async.expect(summary.get_by_text("Customized", exact=True)).to_be_visible()
    await playwright_async.expect(summary).to_contain_text("Up to 321 pages, 4 clicks deep")
    assert "Keyboard check" in await _rail_items(summary, "Not included")
    await _open_groups(page)
    await playwright_async.expect(
        page.get_by_role("spinbutton", name="Maximum pages")
    ).to_have_value("321")
    await playwright_async.expect(
        page.get_by_role("switch", name=re.compile(r"^Scan the whole website"))
    ).to_be_checked()
    await playwright_async.expect(
        page.get_by_role("group", name="WCAG version").get_by_role("radio", name="2.2", exact=True)
    ).to_be_checked()

    # Nothing about the scan, least of all a credential, was put in the
    # browser's storage or the page.
    stored = await page.evaluate(
        "JSON.stringify(Object.assign({}, localStorage))"
        " + JSON.stringify(Object.assign({}, sessionStorage))"
    )
    assert "hunter2" not in stored and "recover.example.test" not in stored
    assert "hunter2" not in await page.content()


async def test_a_login_scan_restarts_on_its_tab_with_confirmations_unticked(
    live_server: tuple[str, int],
    seeded_db: tuple[Any, Any, int],
    new_page: Any,
) -> None:
    from audit.crawler.orchestrator import CrawlConfig

    base, _ = live_server
    scan_id = _insert_scan(
        seeded_db[0],
        seed_url="https://portal.example.test/courses/",
        config=CrawlConfig(
            seed_url="https://portal.example.test/courses/",
            start_url="https://portal.example.test/courses/?ticket=sso-ticket-value",
            browser_only=True,
            resumable=False,
            ignore_robots=True,
            workers=3,
            max_pages=40,
        ),
    )
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    # A login scan cannot be retried without someone signing in.
    await playwright_async.expect(
        page.get_by_role("button", name="Scan again with faster settings")
    ).to_have_count(0)
    edit = page.get_by_role("link", name="Change settings first")
    await playwright_async.expect(edit).to_have_attribute("href", re.compile(r"mode=login"))

    # Even a link that names the wrong tab lands on the scan's own.
    await page.goto(f"{base}/app/scans/new?from={scan_id}", wait_until="networkidle")
    await page.wait_for_url("**mode=login**")
    await playwright_async.expect(
        page.get_by_role("status").filter(has_text="Axcess never saves your sign-in")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("textbox", name="Website address to scan after you sign in")
    ).to_have_value("https://portal.example.test/courses/")
    await playwright_async.expect(
        page.get_by_role("checkbox", name=re.compile(r"^The site owner allows this scan"))
    ).not_to_be_checked()
    await _open_groups(page)
    await playwright_async.expect(
        page.get_by_role("spinbutton", name="Maximum pages")
    ).to_have_value("40")
    await playwright_async.expect(
        page.get_by_role("spinbutton", name="Signed-in tabs")
    ).to_have_value("3")
    assert "sso-ticket-value" not in await page.content()


async def test_failed_scan_explains_both_retries(
    live_server: tuple[str, int],
    seeded_db: tuple[Any, Any, int],
    new_page: Any,
) -> None:
    from audit.crawler.orchestrator import CrawlConfig

    base, _ = live_server
    scan_id = _insert_scan(
        seeded_db[0],
        seed_url="https://retry.example.test/",
        config=CrawlConfig(seed_url="https://retry.example.test/"),
    )
    page = await new_page(viewport={"width": 1280, "height": 900})
    posted: list[dict[str, Any]] = []

    async def capture(route: Any) -> None:
        if route.request.method != "POST":
            await route.continue_()
            return
        posted.append(route.request.post_data_json)
        await route.fulfill(status=409, json={"error": "A crawl is already running."})

    await page.route("**/api/scans", capture)
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    assert "balanced" not in (await page.content()).lower()
    quick = page.get_by_role("button", name="Scan again with faster settings")
    hint = page.locator(f"#{await quick.get_attribute('aria-describedby')}")
    await playwright_async.expect(hint).to_contain_text(
        "It keeps only this scan\u2019s address and its Web Content Accessibility"
        " Guidelines (WCAG) version."
    )
    edit = page.get_by_role("link", name="Change settings first")
    edit_hint = page.locator(f"#{await edit.get_attribute('aria-describedby')}")
    await playwright_async.expect(edit_hint).to_contain_text("this scan\u2019s settings filled in")

    await quick.click()
    await playwright_async.expect(
        page.get_by_role("alert").filter(has_text="Axcess could not start this scan again")
    ).to_be_visible()
    # "Scan again with faster settings" is the defaults with Click-Through
    # off, on the same address.
    assert posted[-1]["url"] == "https://retry.example.test/"
    assert posted[-1]["skip_interaction"] is True
    assert posted[-1]["max_pages"] == 2500
