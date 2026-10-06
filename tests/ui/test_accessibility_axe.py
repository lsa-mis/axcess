"""Playwright + axe-core a11y tests against the React SPA.

Launches a live uvicorn server against a seeded DB, drives the React
bundle under ``/app/`` in a real chromium instance, injects the vendored
axe-core build, runs a scan, and fails on any violations.

Gated on three things, each skipped cleanly when missing: Playwright, the
vendored axe build, and a built SPA bundle (``npm run build``). The legacy
Jinja pages these tests used to cover are gone — the SPA is the only UI.

The rule pack is WCAG 2.2 **AAA** (the product target), so AAA contrast
and target-size regressions fail here, not just AA.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from audit.exports.audit_report import load_report_rules

from ._paging import all_pages_text
from ._seed_evidence import SCREENSHOT_ISSUE_KEY, add_screenshot_finding

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")

_WEB = Path(__file__).resolve().parents[2] / "src" / "audit" / "web"
_AXE_SCRIPT_PATH = _WEB / "static" / "axe.min.js"
_DIST_INDEX = _WEB / "frontend" / "dist" / "index.html"

if not _AXE_SCRIPT_PATH.exists():  # pragma: no cover - gated
    pytest.skip("axe-core bundle not vendored", allow_module_level=True)
if not _DIST_INDEX.exists():  # pragma: no cover - gated
    pytest.skip("SPA bundle not built (run `npm run build`)", allow_module_level=True)

_AXE_TEXT = _AXE_SCRIPT_PATH.read_text(encoding="utf-8")

# Tags scanned. Mirrors the broader set used by the baseline scanner so the
# in-tree gate and the baseline stay in sync.
_AXE_TAGS = [
    "wcag2a",
    "wcag2aa",
    "wcag2aaa",
    "wcag21a",
    "wcag21aa",
    "wcag22aa",
    "best-practice",
]


# WCAG 2.2 Level A and AA only: the gate for the sweeps that cover every
# screen (test_accessibility_sweep.py, test_accessibility_static_pages.py).
_AXE_TAGS_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]


async def _run_axe(page: Any, tags: list[str] | None = None) -> list[dict[str, Any]]:
    """Return the list of axe violations for the current page.

    ``tags`` defaults to ``_AXE_TAGS``, the AAA pack.

    It waits for running CSS transitions first. axe measures the colours on
    screen, and a tab or button still fading between two states (Tailwind's
    ``transition-colors``, 150 ms) is neither: a test that clicks and then
    checks quickly read a half-faded tab as a contrast failure. Endless
    animations, such as a spinner, are not transitions and are not waited on.
    """
    await page.wait_for_function(
        "() => document.getAnimations().every("
        "(a) => !(a instanceof CSSTransition) || a.playState !== 'running')"
    )
    await page.add_script_tag(content=_AXE_TEXT)
    result = await page.evaluate(
        """async (tags) => {
            const res = await window.axe.run(document, {
                runOnly: { type: 'tag', values: tags }
            });
            return res.violations;
        }""",
        tags or _AXE_TAGS,
    )
    return list(result)


# The New scan form's settings groups: accordion rows, closed on arrival.
_SCAN_GROUPS = (
    "Pages to scan",
    "Checks",
    "AI checks on this computer",
    "Limits and rule check tool",
    "Speed and browser window",
)


async def _open_scan_groups(page: Any) -> None:
    """Expand every New scan settings group, so the controls in them can be used."""
    for name in _SCAN_GROUPS:
        button = page.get_by_role("button", name=name, exact=True)
        if await button.get_attribute("aria-expanded") != "true":
            await button.click()


def _render_violations(violations: list[dict[str, Any]]) -> str:
    lines = []
    for v in violations:
        lines.append(f"{v.get('id')} ({v.get('impact')}): {v.get('help')}")
        for node in v.get("nodes", [])[:3]:
            target = node.get("target", ["?"])
            lines.append(f"  target: {target}")
    return "\n".join(lines) or "(no details)"


async def _axe_clean(new_page: Any, base: str, path: str) -> None:
    """Open a SPA route, wait for React to settle, assert no axe violations."""
    page = await new_page()
    try:
        await page.goto(f"{base}{path}", wait_until="networkidle")
        # The SPA renders into #main; wait for it to have content so axe
        # doesn't scan an empty shell.
        await page.wait_for_selector("main#main *", timeout=5000)
        violations = await _run_axe(page)
        assert not violations, f"{path}:\n{_render_violations(violations)}"
    finally:
        # One page at a time: close it now rather than at teardown.
        await page.context.close()


async def test_root_opens_reports_with_the_last_scanned_site(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """The Dashboard is hidden: ``/app/`` lands on Reports, led by the last scanned site."""
    base, scan_id = live_server
    page = await new_page()
    try:
        await page.goto(f"{base}/app/", wait_until="networkidle")
        await page.wait_for_url("**/app/scans")
        card = page.get_by_role("region", name="Last scanned site")
        await playwright_async.expect(card.get_by_role("heading", level=2)).to_have_text(
            "example.com"
        )
        await playwright_async.expect(
            card.get_by_role("link", name="Open latest scan of example.com", exact=True)
        ).to_have_attribute("href", f"/app/scans/{scan_id}/issues")
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_scans_list_has_no_axe_violations(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    await _axe_clean(new_page, base, "/app/scans")


async def test_tracking_page_has_no_axe_violations(
    live_server: tuple[str, int], new_page: Any
) -> None:
    # The tool's own coverage page must clear axe — status badges carry
    # text labels (not colour alone) and the tables are properly headed.
    base, _ = live_server
    await _axe_clean(new_page, base, "/app/tracking")


async def test_about_page_has_no_axe_violations(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    await _axe_clean(new_page, base, "/app/about")


async def test_about_is_reachable_from_the_sidebar_foot(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """About sits below the nav, beside feedback, and marks itself current."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/", wait_until="networkidle")
    sidebar = page.get_by_role("complementary", name="Primary")
    await sidebar.get_by_role("link", name="About", exact=True).click()
    await page.wait_for_url(f"{base}/app/about")
    await playwright_async.expect(
        page.get_by_role("heading", level=1, name="About Axcess")
    ).to_be_visible()
    await playwright_async.expect(
        sidebar.get_by_role("link", name="About", exact=True)
    ).to_have_attribute("aria-current", "page")
    # Every resource leaves the app, and says so in its name.
    links = page.get_by_role("main").get_by_role("link")
    assert await links.count() == 8
    for index in range(8):
        link = links.nth(index)
        assert (await link.get_attribute("target")) == "_blank"
        assert (await link.inner_text()).endswith("(opens in a new tab)")


@pytest.mark.parametrize("theme", ["light", "dark"])
async def test_settings_page_has_no_axe_violations(
    live_server: tuple[str, int], new_page: Any, theme: str
) -> None:
    """Both themes hold the AAA rule pack, contrast included."""
    base, _ = live_server
    page = await new_page()
    try:
        await page.add_init_script(
            f"localStorage.setItem('axcess.preferences', JSON.stringify({{theme: '{theme}'}}))"
        )
        await page.goto(f"{base}/app/settings", wait_until="networkidle")
        await page.wait_for_selector("main#main [role=radiogroup]", timeout=5000)
        assert await page.evaluate("document.documentElement.dataset.theme") == theme
        violations = await _run_axe(page)
        assert not violations, f"/app/settings ({theme}):\n{_render_violations(violations)}"
    finally:
        await page.context.close()


async def test_settings_work_by_keyboard_alone(live_server: tuple[str, int], new_page: Any) -> None:
    """Tab reaches a setting, arrows change it, it applies and survives a reload."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/settings", wait_until="networkidle")
    text_size = page.get_by_role("radiogroup", name="Text size")
    for _ in range(40):
        await page.keyboard.press("Tab")
        if await text_size.evaluate("(group) => group.contains(document.activeElement)"):
            break
    else:
        pytest.fail("Tab never reached the Text size setting")
    await page.keyboard.press("ArrowRight")
    await playwright_async.expect(
        text_size.get_by_role("radio", name="Large", exact=True)
    ).to_be_checked()
    root_size = "document.documentElement.style.fontSize"
    assert await page.evaluate(root_size) == "112.5%"

    await page.reload(wait_until="networkidle")
    assert await page.evaluate(root_size) == "112.5%"

    await page.get_by_role("button", name="Reset to defaults").focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(
        page.get_by_role("status").filter(has_text="Settings reset to defaults.")
    ).to_be_visible()
    assert await page.evaluate(root_size) == ""


async def test_quick_presets_turn_off_again(live_server: tuple[str, int], new_page: Any) -> None:
    """A preset is a toggle: selecting it again undoes it, sparing another's keys."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/settings", wait_until="networkidle")
    presets = page.get_by_role("list", name="Quick presets")
    low_vision = presets.get_by_role("button", name="Low vision")
    motor = presets.get_by_role("button", name="Motor / tremor")
    prefs = "JSON.parse(localStorage.getItem('axcess.preferences'))"

    await playwright_async.expect(low_vision).to_have_attribute("aria-pressed", "false")
    await low_vision.click()
    await motor.click()
    await playwright_async.expect(low_vision).to_have_attribute("aria-pressed", "true")
    await playwright_async.expect(motor).to_have_attribute("aria-pressed", "true")

    await low_vision.click()
    await playwright_async.expect(low_vision).to_have_attribute("aria-pressed", "false")
    await playwright_async.expect(
        page.get_by_role("status").filter(has_text="Low vision preset turned off.")
    ).to_be_visible()
    stored = await page.evaluate(prefs)
    assert stored["textSize"] == "100" and stored["contrast"] == "standard", stored
    # Motor is still on, so the keys it shares keep its values.
    assert stored["focusIndicator"] == "strong" and stored["tableDensity"] == "spacious", stored
    await playwright_async.expect(motor).to_have_attribute("aria-pressed", "true")

    # Changing one of its settings by hand turns a preset off.
    await (
        page.get_by_role("radiogroup", name="Button size")
        .get_by_role("radio", name="Default")
        .check()
    )
    await playwright_async.expect(motor).to_have_attribute("aria-pressed", "false")


async def test_findings_list_has_no_axe_violations(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    await _axe_clean(new_page, base, f"/app/scans/{scan_id}/findings")


async def test_new_scan_form_has_no_axe_violations(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _ = live_server
    await _axe_clean(new_page, base, "/app/scans/new")


async def test_simple_scan_path_shows_settings_and_folds_only_speed(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The default flow is URL -> standard profile -> start, without losing controls."""
    base, _ = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_role("textbox", name="Website address", exact=True)
    ).to_be_visible()
    # The summary rail says what will run, and every settings group is a
    # closed accordion row that one click opens, controls intact.
    await playwright_async.expect(
        page.get_by_role("complementary", name="What this scan will do")
    ).to_be_visible()
    await playwright_async.expect(page.get_by_role("button", name="Start scan")).to_be_visible()
    for name in _SCAN_GROUPS:
        await playwright_async.expect(
            page.get_by_role("button", name=name, exact=True)
        ).to_have_attribute("aria-expanded", "false")
    await _open_scan_groups(page)
    for name in _SCAN_GROUPS:
        await playwright_async.expect(
            page.get_by_role("group", name=name, exact=True)
        ).to_be_visible()
    await playwright_async.expect(page.get_by_label("Maximum pages")).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("group", name="Rule check tool", exact=True)
    ).to_be_visible()
    dom_discovery = page.get_by_role("switch", name=re.compile(r"^Open menus, tabs"))
    await playwright_async.expect(dom_discovery).to_be_checked()
    await dom_discovery.uncheck()
    await playwright_async.expect(dom_discovery).not_to_be_checked()
    # ...and the summary rail says so, and lists it under Not included.
    await playwright_async.expect(page.get_by_text("Customized", exact=True)).to_be_visible()


async def test_protected_scan_form_has_no_axe_violations(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The manual-authentication form must be usable before any sign-in happens."""
    base, _ = live_server
    await _axe_clean(new_page, base, "/app/scans/protected/new")


async def test_protected_companion_route_has_no_axe_violations(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The protected companion route remains accessible when access is denied."""
    base, scan_id = live_server
    await _axe_clean(new_page, base, f"/app/scans/{scan_id}/protected")


@pytest.mark.parametrize(
    "suffix",
    ["", "/review", "/manual-checks", "/handoff"],
    ids=["report", "review", "manual", "handoff"],
)
async def test_expert_workspace_routes_have_no_axe_violations(
    live_server: tuple[str, int], suffix: str, new_page: Any
) -> None:
    """The four core expert stages are part of the release accessibility gate."""
    base, scan_id = live_server
    await _axe_clean(new_page, base, f"/app/scans/{scan_id}{suffix}")


async def test_expert_workspace_reflows_without_document_overflow(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Core workbench routes fit a 320 CSS-pixel viewport.

    Wide evidence tables may scroll inside their own named container; the
    document itself must never force two-dimensional page scrolling.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 320, "height": 800})
    for suffix in ("", "/issues", "/review", "/manual-checks", "/handoff"):
        path = f"/app/scans/{scan_id}{suffix}"
        await page.goto(f"{base}{path}", wait_until="networkidle")
        await page.wait_for_selector("main#main h1", timeout=5000)
        widths = await page.evaluate(
            """() => ({
                client: document.documentElement.clientWidth,
                scroll: document.documentElement.scrollWidth,
                body: document.body.scrollWidth,
                overflowX: getComputedStyle(document.documentElement).overflowX
            })"""
        )
        assert widths["body"] <= widths["client"], f"{path}: {widths}"
        # All of these land on the issue table ("" redirects there, as the
        # legacy stage routes do), whose wide table scrolls inside its own
        # region, never the document.
        assert widths["overflowX"] == "hidden", f"{path}: {widths}"


async def test_issue_card_answers_what_why_fix_and_where(
    live_server: tuple[str, int],
    new_page: Any,
    choose_filter: Any,
) -> None:
    """The report still answers what, why, fix, and location, one issue at a time.

    The four answers used to be four columns, then the four sections of a
    side pane, then an "About" column whose button opened them under the
    row. That column repeated what the issue name opens and is gone; the
    issue name is the one way to them.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await choose_filter(page, "How sure", "expert_review")
    await page.wait_for_url("**type=expert_review*")
    issues = page.get_by_role("table", name="Accessibility issues")
    # Contains, not equals: the sorted header also carries its direction chip.
    await playwright_async.expect(issues.get_by_role("columnheader")).to_contain_text(
        [
            "Issue",
            "How sure",
            "WCAG",
            "Priority",
            "Pages",
            "Occurrences",
        ]
    )
    # Hidden for now (HIDDEN_ISSUE_FIELDS in the SPA); the data still exports.
    # Responsibility's column is headed "Who fixes it" when it is shown.
    for hidden in ("Difficulty", "Who fixes it", "Responsibility"):
        assert await issues.get_by_role("columnheader", name=hidden, exact=False).count() == 0
    assert await issues.get_by_role("button", name="About", exact=False).count() == 0

    first = issues.get_by_role("rowheader").get_by_role("link").first
    title = (await first.inner_text()).splitlines()[0].strip()
    await first.click()
    await page.wait_for_url("**/issues/**")
    await playwright_async.expect(page.get_by_role("heading", name=title, level=1)).to_be_visible()
    # The header names the type in the Issues table's word, the same one the
    # guidance dialog uses.
    await playwright_async.expect(page.locator("main h1 + p")).to_contain_text("Not sure")
    # The guidance opens from the top right, every section expanded at once;
    # the Not sure caution (a person checks it first) sits under What it is.
    guidance = page.get_by_role("button", name="Issue guidance", exact=True)
    await guidance.click()
    dialog = page.get_by_role("dialog", name="Issue guidance")
    await playwright_async.expect(dialog).to_be_visible()
    await playwright_async.expect(
        dialog.get_by_role("heading", name="What it is", exact=True, level=3)
    ).to_be_visible()
    await playwright_async.expect(
        dialog.get_by_role("heading", name=re.compile("^Why it matters"), level=3)
    ).to_be_visible()
    caution = dialog.get_by_text("a person checks it", exact=False)
    await playwright_async.expect(caution).to_be_visible()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
    # Escape closes it and focus goes back to the button that opened it.
    await page.keyboard.press("Escape")
    await playwright_async.expect(dialog).to_be_hidden()
    await playwright_async.expect(guidance).to_be_focused()


async def test_issue_table_fits_the_default_desktop_width(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """At 1280 px beside the expanded sidebar, no column is cut off.

    Whichever column is sorted (the sorted header carries a wider chip), the
    table is no wider than the region that holds it, so it never scrolls
    sideways at desktop width.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    issues = page.get_by_role("table", name="Accessibility issues")
    scroller = page.get_by_role("region", name="Issues table")
    # Who fixes it is hidden for now (HIDDEN_ISSUE_FIELDS), so Pages stands in.
    for column in (None, "Issue", "Occurrences", "Pages"):
        if column:
            await issues.get_by_role("button", name=column, exact=False).first.click()
        widths = await scroller.evaluate("el => ({scroll: el.scrollWidth, client: el.clientWidth})")
        assert widths["scroll"] <= widths["client"], (column, widths)


async def test_issue_list_reaches_exact_locations_without_sideways_scrolling(
    live_server: tuple[str, int],
    new_page: Any,
    choose_filter: Any,
) -> None:
    """At 320px the page itself never scrolls sideways.

    The issues table is wider than a phone, so it overflows inside its own
    keyboard-focusable region (SC 2.1.1) instead of pushing the page wider
    (SC 1.4.10), and there is no custom scrollbar widget to operate.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 320, "height": 800})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await choose_filter(page, "How sure", "expert_review")
    await page.wait_for_url("**type=expert_review*")
    issues = page.get_by_role("table", name="Accessibility issues")
    await playwright_async.expect(issues).to_be_visible()

    widths = await page.evaluate(
        """() => ({
            client: document.documentElement.clientWidth,
            body: document.body.scrollWidth
        })"""
    )
    assert widths["body"] <= widths["client"], widths
    assert await page.get_by_role("scrollbar").count() == 0
    scroller = page.get_by_role("region", name="Issues table")
    await playwright_async.expect(scroller).to_have_attribute("tabindex", "0")
    assert await scroller.evaluate("el => el.scrollWidth > el.clientWidth")

    # Each row's title carries the reader to that issue's own
    # evidence route.
    first_row = issues.get_by_role("rowheader").get_by_role("link").first
    href = await first_row.get_attribute("href")
    assert href is not None and "/issues/" in href
    await first_row.click()
    await page.wait_for_url("**/issues/**")
    await playwright_async.expect(
        page.get_by_role(
            "link", name="opens the saved copy with this issue marked", exact=False
        ).first
    ).to_be_attached()
    # The protected-identity context refreshes every 15 seconds even
    # on public report routes. That security check must not unmount a
    # known-public table and reset the reader to the top. A short viewport
    # keeps the page scrollable now that the guidance is in a dialog.
    await page.set_viewport_size({"width": 320, "height": 240})
    await page.evaluate("window.scrollTo(0, 500)")
    scroll_position = await page.evaluate("window.scrollY")
    assert scroll_position > 0
    await page.wait_for_timeout(16_000)
    assert await page.evaluate("window.scrollY") == scroll_position


async def test_informational_evidence_is_read_only_and_not_barrier_language(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Adequate-alt evidence never inherits triage or remediation controls."""
    base, scan_id = live_server
    page = await new_page()
    page_errors: list[str] = []
    failed_responses: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "response",
        lambda response: (
            failed_responses.append(f"{response.status}: {response.url}")
            if response.status >= 400
            else None
        ),
    )
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    issues = page.get_by_role("table", name="Accessibility issues")
    logo_title = load_report_rules()["image_findings"]["logo_adequate"]["title"]
    row_link = issues.get_by_role("rowheader").get_by_role("link", name=logo_title, exact=False)
    informational_row = row_link.locator("xpath=ancestor::tr[1]")
    await playwright_async.expect(
        informational_row.get_by_text("For information", exact=True)
    ).to_be_visible()
    # Informational evidence never inherits triage or remediation
    # controls: the row has no buttons at all, only its links.
    assert await informational_row.get_by_role("button").count() == 0

    await page.goto(
        f"{base}/app/scans/{scan_id}/issues/image:logo_adequate",
        wait_until="networkidle",
    )
    # The verdict leads the guidance dialog, under What Axcess found.
    await page.get_by_role("button", name="Issue guidance", exact=True).click()
    await playwright_async.expect(
        page.get_by_role("dialog", name="Issue guidance").get_by_role(
            "heading", name="What Axcess found", exact=True
        )
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("heading", name="For information", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("This check found no problem.", exact=False)
    ).to_be_visible()
    assert await page.get_by_role("link", name="Audit report").count() == 0
    assert await page.get_by_role("heading", name="Fix (do this)").count() == 0

    response = await page.goto(
        f"{base}/app/scans/{scan_id}/issues",
        wait_until="networkidle",
    )
    assert response is not None and response.ok
    try:
        await playwright_async.expect(
            page.get_by_role("heading", name="Issues", exact=True, level=1)
        ).to_be_visible()
    except AssertionError as error:
        body = await page.locator("body").inner_text()
        pytest.fail(
            f"{error}\nURL: {page.url}\nBrowser errors: {page_errors}\n"
            f"Failed responses: {failed_responses}\nRendered page: {body}"
        )
    assert not page_errors, page_errors
    assert await page.get_by_role("link", name="Audit report").count() == 0


async def test_spa_navigation_sets_title_and_focuses_main(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Client-side route changes announce context instead of dropping focus."""
    base, scan_id = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/{scan_id}/compare", wait_until="networkidle")
    workspace = page.get_by_role("navigation", name="Report views")
    await workspace.get_by_role("link", name="Issues").click()
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")
    await page.wait_for_function("document.activeElement?.id === 'main'")
    assert await page.title() == "Accessibility issues · Axcess"


async def test_completed_scan_opens_as_report_output_not_pipeline_dashboard(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """A settled scan lands on its issue table, with the overview folded in.

    There is no Overview tab any more: the report's URL redirects to Issues,
    and the stat cards and scan coverage the overview carried sit above the
    table, the coverage as one line that opens the full ledger.
    """
    # Compare reports is a tab only once the site has an earlier report.
    with sqlite3.connect(seeded_db[0]) as conn:
        conn.execute(
            "INSERT INTO scans(seed_url,status,started_at,config_json) "
            "VALUES('http://example.com/','completed','2000-01-01 00:00:00','{}')"
        )
    base, scan_id = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")
    await playwright_async.expect(
        page.get_by_role("heading", name="Issues", exact=True, level=1)
    ).to_be_visible()
    workspace = page.get_by_role("navigation", name="Report views")
    await playwright_async.expect(workspace.get_by_role("link")).to_have_text(
        ["Issues", "Compare reports"]
    )
    await playwright_async.expect(
        workspace.get_by_role("link", name="Issues", exact=True)
    ).to_have_attribute("aria-current", "page")
    await playwright_async.expect(page.get_by_role("link", name="Overview")).to_have_count(0)
    # The summary is one line of term and value pairs. Each term also carries
    # a short explanation in parentheses, so it is matched as contained text.
    terms = page.get_by_role("term")
    await playwright_async.expect(terms.filter(has_text="Issues found")).to_be_visible()
    await playwright_async.expect(terms.filter(has_text="Pages checked")).to_be_visible()
    # Under the title, only when the evidence was captured: no site name, no
    # disclaimer line, and no ACT rule note among the notes.
    await playwright_async.expect(
        page.get_by_text(re.compile(r"^Based on the (report generated|scan started) "))
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("Evidence for expert review, not a conformance verdict.", exact=True)
    ).to_have_count(0)
    await playwright_async.expect(
        page.get_by_role("button", name=re.compile(r"What is an ACT rule"))
    ).to_have_count(0)

    # The coverage row counts the methods the scan recorded as run, and the
    # count stays on screen while the row is closed.
    response = await page.request.get(f"{base}/api/scans/{scan_id}")
    methods = (await response.json())["methods_used"]
    ran = sum(method["state"] in {"checked", "partial"} for method in methods)
    coverage = page.get_by_role("button", name="What was checked", exact=True)
    await playwright_async.expect(coverage).to_have_attribute("aria-expanded", "false")
    await playwright_async.expect(
        page.get_by_text(f"{ran} of {len(methods)} checks ran", exact=True)
    ).to_be_visible()
    ledger = page.get_by_role("region", name="What was checked")
    await playwright_async.expect(ledger).to_be_hidden()
    await coverage.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(ledger).to_be_visible()
    # Scoped to the ledger panel: "Click-Through" may appear elsewhere on the
    # report, and exact text must match one element.
    await playwright_async.expect(ledger.get_by_text("Click-Through", exact=True)).to_be_visible()

    # The subtitle names the report without repeating a stat card's count.
    subtitle = page.locator("main h1 + p")
    text = await subtitle.inner_text()
    assert "issue groups" not in text and "issues" not in text, text
    assert "occurrences" not in text, text
    issues = await (await page.request.get(f"{base}/api/scans/{scan_id}/issues")).json()
    # The date after "started"/"generated" has its own numbers ("Oct 3, 2026"),
    # which matched a count of 3 on the 3rd of any month. Only the rest of the
    # subtitle must not repeat a count.
    words = re.sub(r"\b(started|generated)\b.*$", "", text)
    for count in (issues["total_unfiltered"], issues["occurrence_counts"]["all_evidence"]):
        assert not re.search(rf"\b{count}\b", words), (count, text)


async def test_running_scan_shows_factual_pipeline_progress(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """A running scan shows one bar, three steps, and a table of pages by checks.

    The details (each check's totals, live updates) sit behind Show details,
    and a background refresh must not move the reader's place or focus.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}")
    assert response.ok
    payload = await response.json()
    payload.update(
        {
            # The pages below are on this site, so the table names them by path.
            "seed_url": "https://example.test/",
            "status": "running",
            "page_count": 7,
            "axe_pages_scanned": 6,
            "alfa_pages_scanned": 5,
            "progress": {
                "stage": "scanning",
                "discovered": 12,
                "completed": 7,
                "pending": 4,
                "leased": 1,
                "failed": 0,
                "images_seen": 9,
                "rendered_pages": 7,
                "static_pages": 0,
                "eta": {
                    "state": "range",
                    "min_seconds": 40,
                    "max_seconds": 95,
                    "based_on_pages": 7,
                },
                "in_flight_pages": [
                    {
                        "url": "https://example.test/admissions/apply/",
                        "depth": 2,
                        "attempts": 1,
                        "lease_until": None,
                    }
                ],
                "recent_pages": [
                    {
                        "url_normalized": "https://example.test/admissions/",
                        "status_code": 200,
                        "render_mode": "js",
                        "fetched_at": "2026-08-11T12:00:00Z",
                    }
                ],
                "page_checks": [
                    {
                        "url": "https://example.test/admissions/apply/",
                        "state": "checking",
                        "checks": {"axe": "done", "alfa": "waiting", "keyboard": "running"},
                    },
                    {
                        "url": "https://example.test/admissions/",
                        "state": "checked",
                        "checks": {"axe": "done", "alfa": "done", "keyboard": "not_run"},
                    },
                    {
                        "url": "https://example.test/admissions/visit/",
                        "state": "waiting",
                        "checks": {},
                    },
                ],
            },
        }
    )
    results = {
        "axe": "6 pages checked so far",
        "alfa": "5 pages checked so far",
        "keyboard": "4 pages checked so far",
    }
    for method in payload["methods_used"]:
        method["enabled"] = method["key"] in results
        if method["key"] in results:
            method["state"] = "running"
            method["result"] = results[method["key"]]

    async def serve_running_scan(route: Any) -> None:
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    await page.route(f"**/api/scans/{scan_id}", serve_running_scan)
    try:
        await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
        await playwright_async.expect(
            page.get_by_role("heading", name="Scan in progress", level=1)
        ).to_be_visible()
        # The percent leads (7 of 12 is 58%, rounded down), with the counts
        # it comes from beside it.
        await playwright_async.expect(page.get_by_text("58%", exact=True)).to_be_visible()
        await playwright_async.expect(
            page.get_by_text("checked · 7 of 12 pages found so far", exact=True)
        ).to_be_visible()
        await playwright_async.expect(page.get_by_text(re.compile(r"^Time left: \d"))).to_have_text(
            "Time left: 40 seconds to 2 minutes for the pages found so far"
        )
        steps = page.get_by_role("list", name="Scan steps").get_by_role("listitem")
        await playwright_async.expect(steps).to_have_count(3)
        # One current step, and it says so in words as well.
        current = page.locator('[aria-current="step"]')
        await playwright_async.expect(current).to_have_count(1)
        await playwright_async.expect(current).to_contain_text("Check pages: In progress")
        await playwright_async.expect(steps.nth(2)).to_contain_text("Prepare report: Waiting")
        await playwright_async.expect(
            page.get_by_role("button", name="Stop scan", exact=True)
        ).to_be_visible()

        table = page.get_by_role("table", name="Each page and where each check stands on it")
        await playwright_async.expect(table.get_by_role("columnheader")).to_have_text(
            ["Page", "Status", "Rule check (axe)", "Rule check (Alfa)", "Keyboard check"]
        )

        def row(path: str) -> Any:
            return table.get_by_role("row").filter(
                has=page.get_by_role("rowheader", name=path, exact=True)
            )

        await playwright_async.expect(row("/admissions/apply/").get_by_role("cell")).to_have_text(
            ["Being checked", "Done", "Waiting", "Checking"]
        )
        await playwright_async.expect(row("/admissions/").get_by_role("cell")).to_have_text(
            ["Checked", "Done", "Done", "Not run"]
        )
        # A waiting page has started no check.
        await playwright_async.expect(row("/admissions/visit/").get_by_role("cell")).to_have_text(
            ["Waiting", "Waiting", "Waiting", "Waiting"]
        )

        # Each check's totals are details: closed at first, then one click away.
        show = page.get_by_role("button", name="Show details", exact=True)
        await playwright_async.expect(show).to_have_attribute("aria-expanded", "false")
        await playwright_async.expect(page.get_by_text("6 pages checked so far")).to_have_count(0)
        await show.click()
        hide = page.get_by_role("button", name="Hide details", exact=True)
        await playwright_async.expect(hide).to_have_attribute("aria-expanded", "true")
        for text in results.values():
            await playwright_async.expect(page.get_by_text(text, exact=True)).to_be_visible()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)

        # A background data refresh must not reload, move the viewport, or
        # steal focus from the operator's current control.
        pause = page.get_by_role("button", name="Pause live updates")
        await pause.focus()
        await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        scroll_before = await page.evaluate("window.scrollY")
        navigations_before = await page.evaluate(
            "performance.getEntriesByType('navigation').length"
        )
        await page.wait_for_timeout(2200)
        assert await page.evaluate("window.scrollY") == scroll_before
        assert await page.evaluate("document.activeElement?.textContent") == ("Pause live updates")
        assert (
            await page.evaluate("performance.getEntriesByType('navigation').length")
            == navigations_before
        )
        await pause.click()
        await playwright_async.expect(
            page.get_by_text(
                "Live updates paused. The scan continues in the background.",
                exact=True,
            )
        ).to_be_visible()
    finally:
        await page.context.close()


async def test_a_scan_without_per_check_records_shows_page_status_only(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """No check columns when no page has a record of its checks.

    A scan run in another process, or one that was running when Axcess
    restarted, has none; the columns then said "No record" on every row.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    payload = await (await page.request.get(f"{base}/api/scans/{scan_id}")).json()
    payload.update(
        {
            "seed_url": "https://example.test/",
            "status": "running",
            "progress": {
                "stage": "scanning",
                "discovered": 3,
                "completed": 1,
                "pending": 1,
                "leased": 1,
                "failed": 0,
                "images_seen": 0,
                "rendered_pages": 1,
                "static_pages": 0,
                "eta": {
                    "state": "estimating",
                    "min_seconds": None,
                    "max_seconds": None,
                    "based_on_pages": 1,
                },
                "in_flight_pages": [],
                "recent_pages": [],
                "page_checks": [
                    {"url": "https://example.test/#/about", "state": "checking", "checks": {}},
                    {"url": "https://example.test/#/", "state": "checked", "checks": {}},
                ],
            },
        }
    )
    for method in payload["methods_used"]:
        method["enabled"] = method["key"] == "axe"

    async def serve(route: Any) -> None:
        await route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    await page.route(f"**/api/scans/{scan_id}", serve)
    try:
        await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
        await playwright_async.expect(
            page.get_by_role("heading", name="Pages", exact=True)
        ).to_be_visible()
        await playwright_async.expect(
            page.get_by_text(
                re.compile(r"not available for this scan, so each page shows its status only")
            )
        ).to_be_visible()
        table = page.get_by_role("table", name="Each page and its status")
        await playwright_async.expect(table.get_by_role("columnheader")).to_have_text(
            ["Page", "Status"]
        )
        # A single-page app's pages keep their route.
        await playwright_async.expect(table.get_by_role("rowheader")).to_have_text(
            ["/#/about", "/#/"]
        )
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()


async def test_every_spa_route_has_an_accurate_document_title(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Every route declared in App.tsx has a non-generic title announcement."""
    base, scan_id = live_server
    cases = [
        ("/app/", "Reports"),
        ("/app/scans", "Reports"),
        ("/app/scans/new", "New scan"),
        ("/app/scans/protected/new", "New scan"),
        (f"/app/scans/{scan_id}/protected", "Sign-in scan"),
        (f"/app/scans/{scan_id}/protected/manual-checks", "Manual checks for the sign-in scan"),
        (f"/app/scans/{scan_id}/protected/issues", "Sign-in scan issues"),
        # A completed report's URL redirects to its issue table.
        (f"/app/scans/{scan_id}", "Accessibility issues"),
        (f"/app/scans/{scan_id}/review", "Accessibility issues"),
        (f"/app/scans/{scan_id}/manual-checks", "Accessibility issues"),
        (f"/app/scans/{scan_id}/handoff", "Accessibility issues"),
        (f"/app/scans/{scan_id}/pages/1", "Page details"),
        (f"/app/scans/{scan_id}/issues", "Accessibility issues"),
        (f"/app/scans/{scan_id}/issues/image:logo_adequate", "Issue evidence"),
        (f"/app/scans/{scan_id}/findings", "Images"),
        (f"/app/scans/{scan_id}/findings/grouped", "Images, grouped by issue"),
        (f"/app/scans/{scan_id}/a11y", "Rule check issues by WCAG criterion"),
        (f"/app/scans/{scan_id}/a11y/by-rule", "Rule check issues by rule"),
        (f"/app/scans/{scan_id}/compare", "Compare reports"),
        ("/app/findings/1", "Image details"),
        ("/app/tracking", "Product roadmap"),
        ("/app/about", "About"),
        ("/app/not-a-real-route", "Page not found"),
    ]
    page = await new_page()
    for path, expected in cases:
        await page.goto(f"{base}{path}", wait_until="domcontentloaded")
        await page.wait_for_function(
            "expected => document.title === `${expected} · Axcess`",
            arg=expected,
        )
        assert await page.title() == f"{expected} · Axcess", path


async def test_sidebar_leads_with_one_mode_neutral_new_scan_action(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The global CTA defers the public/login choice to the new-scan page.

    On a desktop it is the first action in the sidebar and the top bar has
    none; on a phone, where the sidebar is hidden, the top bar keeps it.
    """
    base, _scan_id = live_server
    phone = await new_page(viewport={"width": 390, "height": 800})
    await phone.goto(f"{base}/app/", wait_until="networkidle")
    await playwright_async.expect(
        phone.get_by_role("banner").get_by_role("link", name="Start a new scan", exact=True)
    ).to_be_visible()

    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_role("link", name="Start a new scan", exact=True).filter(visible=True)
    ).to_have_count(1)
    await playwright_async.expect(
        page.get_by_role("banner").get_by_role("link", name="Start a new scan").filter(visible=True)
    ).to_have_count(0)
    sidebar = page.get_by_role("complementary", name="Primary")
    first_action = sidebar.locator("a, button").filter(visible=True).nth(1)
    await playwright_async.expect(first_action).to_have_accessible_name("Start a new scan")

    action = sidebar.get_by_role("link", name="Start a new scan", exact=True)
    await playwright_async.expect(action).to_have_count(1)
    href = await action.get_attribute("href")
    assert href is not None
    assert href.endswith("/app/scans/new")
    assert "mode=" not in href

    await action.click()
    assert page.url.endswith("/app/scans/new")
    await playwright_async.expect(page.get_by_role("tablist", name="Scan type")).to_be_visible()


async def test_sidebar_offers_search_and_one_external_feedback_link(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Search and feedback live in the sidebar, reachable from every screen.

    They used to sit in the top bar, which now carries only the breadcrumb.
    """
    base, _scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/", wait_until="networkidle")

    banner = page.get_by_role("banner")
    await playwright_async.expect(
        banner.get_by_role("button", name="Search everything")
    ).to_have_count(0)
    await playwright_async.expect(banner.get_by_role("link", name="Give feedback")).to_have_count(0)

    sidebar = page.get_by_role("complementary", name="Primary")
    search = sidebar.get_by_role("button", name="Search everything (Cmd+K)", exact=True)
    await playwright_async.expect(search).to_be_visible()
    await search.click()
    await playwright_async.expect(page.get_by_role("dialog")).to_be_visible()
    await page.keyboard.press("Escape")

    feedback = sidebar.get_by_role("link", name="Give feedback (opens in a new tab)", exact=True)
    await playwright_async.expect(feedback).to_have_count(1)
    assert await feedback.get_attribute("href") == (
        "https://form.asana.com/?k=nRyyF2UKBYMXEj3v8CKCCA&d=939514425027676"
    )
    # A new tab is a change of context, and the opened page must not
    # be able to reach back into this one.
    assert await feedback.get_attribute("target") == "_blank"
    rel = await feedback.get_attribute("rel") or ""
    assert "noopener" in rel and "noreferrer" in rel


async def test_search_finds_every_sidebar_place(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Every place in the sidebar can be found and opened from Cmd+K.

    About and Settings were added to the sidebar but not to the palette,
    so searching for them found nothing.
    """
    base, _scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    sidebar = page.get_by_role("complementary", name="Primary")
    search = sidebar.get_by_role("button", name="Search everything (Cmd+K)", exact=True)
    dialog = page.get_by_role("dialog", name="Search everything")
    box = dialog.get_by_role("textbox", name="Search")

    for query, name, path in [
        ("about", "About Axcess", "/app/about"),
        ("settings", "Settings", "/app/settings"),
        # A setting's own name finds the page that holds it, and says why.
        ("dark", "Settings", "/app/settings"),
        ("new scan", "New scan", "/app/scans/new"),
        ("reports", "Reports", "/app/scans"),
    ]:
        await search.click()
        await box.fill(query)
        option = dialog.get_by_role("option").first
        await playwright_async.expect(option).to_have_attribute("aria-selected", "true")
        await playwright_async.expect(option.locator("span").first).to_have_text(name)
        if query == "dark":
            await playwright_async.expect(option).to_contain_text("Dark mode")
        await page.keyboard.press("Enter")
        await playwright_async.expect(dialog).to_have_count(0)
        await playwright_async.expect(page).to_have_url(re.compile(re.escape(path) + r"$"))


@pytest.mark.parametrize(
    ("chunk", "query", "heading"),
    [
        # The shell moves focus to <main> when the page changes.
        ("About", "about", "About Axcess"),
        # New scan also puts focus in its web address box; Enter there
        # submitted the scan form instead of choosing the Search result.
        ("NewScan", "new scan", "New scan"),
    ],
)
async def test_a_late_page_change_leaves_focus_in_search(
    live_server: tuple[str, int],
    new_page: Any,
    chunk: str,
    query: str,
    heading: str,
) -> None:
    """A page that finishes loading while Search is open does not take its focus.

    Each page's code loads on first visit, so on a slow machine the page
    change finishes after Search has closed and been opened again. The page
    then took focus out of the open Search, and Enter did nothing (the CI
    failure of the test above). Holding back the page's code makes that order
    certain.
    """
    base, _scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    release = asyncio.Event()

    async def hold(route: Any) -> None:
        await release.wait()
        await route.continue_()

    await page.route(re.compile(rf"/assets/{chunk}-[^/]*\.js$"), hold)
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    search = page.get_by_role("complementary", name="Primary").get_by_role(
        "button", name="Search everything (Cmd+K)", exact=True
    )
    dialog = page.get_by_role("dialog", name="Search everything")
    box = dialog.get_by_role("textbox", name="Search")

    await search.click()
    await box.fill(query)
    await page.keyboard.press("Enter")
    await playwright_async.expect(dialog).to_have_count(0)

    await search.click()
    await box.fill("settings")
    release.set()
    # Behind the open Search the page is inert, out of the accessibility tree,
    # so find its heading by tag, not by role.
    await playwright_async.expect(page.locator("main h1")).to_have_text(heading)
    # The shell moves focus a frame after the page changes: let two pass.
    await page.evaluate("new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    await playwright_async.expect(box).to_be_focused()
    await page.keyboard.press("Enter")
    await playwright_async.expect(dialog).to_have_count(0)
    await playwright_async.expect(page).to_have_url(re.compile(r"/app/settings$"))


async def test_search_changes_a_setting_from_its_results(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """A setting's choices are results of their own, applied without leaving Search.

    Searching "dark" used to lead only to the Settings page. Its Theme
    choices now follow it in the list: Enter applies one, Search stays open
    on the same list, and a status message says what changed.
    """
    base, _scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    try:
        await page.goto(f"{base}/app/scans", wait_until="networkidle")
        await (
            page.get_by_role("complementary", name="Primary")
            .get_by_role("button", name="Search everything (Cmd+K)", exact=True)
            .click()
        )
        dialog = page.get_by_role("dialog", name="Search everything")
        await dialog.get_by_role("textbox", name="Search").fill("dark")

        dark = dialog.get_by_role("option", name=re.compile(r"^Theme: Dark"))
        light = dialog.get_by_role("option", name=re.compile(r"^Theme: Light"))
        await playwright_async.expect(light).to_contain_text("Current setting")
        await playwright_async.expect(dark).not_to_contain_text("Current setting")

        # Arrow down from the first result (the Settings page) to Dark.
        options = dialog.get_by_role("option")
        names = await options.all_inner_texts()
        target = next(i for i, text in enumerate(names) if text.startswith("Theme: Dark"))
        for _ in range(target):
            await page.keyboard.press("ArrowDown")
        await playwright_async.expect(dark).to_have_attribute("aria-selected", "true")
        # Groups of options, each named by its heading, in light mode as the
        # other axe checks run.
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        await playwright_async.expect(
            dialog.get_by_role("group", name="Change a setting")
        ).to_contain_text("Theme: Dark")
        await page.keyboard.press("Enter")

        await playwright_async.expect(dialog).to_be_visible()
        await playwright_async.expect(dialog.get_by_role("status")).to_have_text(
            "Theme is now Dark."
        )
        await playwright_async.expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        await playwright_async.expect(dark).to_contain_text("Current setting")
        await playwright_async.expect(light).not_to_contain_text("Current setting")
    finally:
        await page.context.close()


async def test_scan_mode_choice_is_a_radio_group_that_keeps_other_params(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Switching scan type must not lose a pre-filled rescan URL."""
    base, _scan_id = live_server
    page = await new_page()
    await page.goto(
        f"{base}/app/scans/new?url=https%3A%2F%2Fexample.com%2F",
        wait_until="networkidle",
    )
    public = page.get_by_role("tab", name="Public website", exact=True)
    login = page.get_by_role(
        "tab", name="Site with a sign-in or two-step sign-in (2FA)", exact=True
    )
    await playwright_async.expect(public).to_have_attribute("aria-selected", "true")

    await login.click()
    await playwright_async.expect(login).to_have_attribute("aria-selected", "true")
    assert "mode=login" in page.url
    assert "url=https%3A%2F%2Fexample.com%2F" in page.url
    # The address survives the switch inside the form as well.
    await playwright_async.expect(
        page.get_by_role("textbox", name="Website address to scan after you sign in")
    ).to_have_value("https://example.com/")

    await public.click()
    await playwright_async.expect(public).to_have_attribute("aria-selected", "true")
    assert "mode=" not in page.url
    assert "url=https%3A%2F%2Fexample.com%2F" in page.url


async def test_tracking_coverage_table_filters_and_sorts(
    live_server: tuple[str, int],
    new_page: Any,
    choose_filter: Any,
) -> None:
    """The coverage matrix can be narrowed and reordered, and says so.

    The tracker is one table with a Section filter: "Checked now" (what
    Axcess checks, with a second "Kind of check" group), "Not checked yet"
    (the manual-only long tail), and "AI reviews" (the roadmap). "Manual
    only" is therefore a section, not one of the kinds of check — filtering the
    covered rows by it would always be empty. Expectations are derived from
    /api/tracking so this cannot drift again when a criterion changes method.
    """
    base, _scan_id = live_server
    page = await new_page()
    tracking = await (await page.request.get(f"{base}/api/tracking")).json()
    criteria = tracking["coverage"]["criteria"]
    covered = [c for c in criteria if c["method"] != "manual"]
    manual = [c for c in criteria if c["method"] == "manual"]
    assert covered and manual, "fixture needs both covered and manual criteria"
    labels = tracking["coverage"]["method_labels"]

    await page.goto(f"{base}/app/tracking", wait_until="networkidle")
    matrix = page.get_by_role(
        "table",
        name=(
            "What Axcess checks for each WCAG 2.2 Level A and AA criterion, and planned AI reviews"
        ),
    )
    await choose_filter(page, "Section", "current")

    # Narrowing to one method leaves only that method's rows.
    await choose_filter(page, "Kind of check", "automated")
    await playwright_async.expect(page).to_have_url(re.compile(r"method=automated"))
    status_cells = matrix.locator("tbody tr td:nth-child(5)")
    shown_labels = set(await all_pages_text(page, status_cells, "Criteria"))
    assert shown_labels == {labels["automated"]}, shown_labels

    await choose_filter(page, "Kind of check", "")
    sc_cells = matrix.locator("tbody tr th[scope='row']")
    # Ten rows a page; the pages together hold every covered criterion.
    await playwright_async.expect(sc_cells).to_have_count(min(len(covered), 10))
    assert len(await all_pages_text(page, sc_cells, "Criteria")) == len(covered)

    # Success criteria sort as numbers: 1.4.4 before 1.4.10.
    sc_header = matrix.get_by_role("columnheader", name="Number")
    await playwright_async.expect(sc_header).to_have_attribute("aria-sort", "ascending")
    ascending = await all_pages_text(page, sc_cells, "Criteria")
    assert ascending == sorted(ascending, key=lambda sc: tuple(int(part) for part in sc.split(".")))

    await sc_header.get_by_role("button").click()
    await playwright_async.expect(sc_header).to_have_attribute("aria-sort", "descending")
    descending = await all_pages_text(page, sc_cells, "Criteria")
    assert descending == list(reversed(ascending))

    # The manual-only long tail is its own group, and it is the rest of
    # the criteria — the two groups together account for all of them.
    await choose_filter(page, "Section", "future")
    assert len(await all_pages_text(page, sc_cells, "Criteria")) == len(manual)


async def test_tracking_page_stays_clean_while_filtered(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The new filter and sort controls must hold the AAA bar too."""
    base, _scan_id = live_server
    await _axe_clean(
        new_page, base, "/app/tracking?view=current&method=ai-assisted&sort=method&dir=desc"
    )


async def test_login_scan_is_visible_and_explains_login_before_crawl(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Loopback Axcess exposes the direct headed-browser login workflow."""
    base, _scan_id = live_server
    page = await new_page(viewport={"width": 320, "height": 800})
    await page.route(
        "**/api/capabilities/alfa",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"available":true,"reason":null}',
        ),
    )
    await page.route(
        "**/api/capabilities/local-analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=(
                '{"ocr":{"available":true,"engine":"Tesseract 5",'
                '"language":"eng","max_workers":2,"bundled_in_desktop":true},'
                '"ollama":{"reachable":true},'
                '"vision":{"available":true,"model":"qwen3-vl:2b-instruct",'
                '"installed_size_bytes":1900000000,"reason":null},'
                '"semantic":{"available":false,"models":[],"ready_models":[],'
                '"missing_models":[],"checks_per_page":0,"reason":"Not configured"}}'
            ),
        ),
    )
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    login_tab = page.get_by_role(
        "tab", name="Site with a sign-in or two-step sign-in (2FA)", exact=True
    )
    await playwright_async.expect(login_tab).to_be_visible()
    await login_tab.click()
    await playwright_async.expect(login_tab).to_have_attribute("aria-selected", "true")
    assert "mode=login" in page.url
    await playwright_async.expect(
        page.get_by_role("heading", name="New scan", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("textbox", name="Website address to scan after you sign in")
    ).to_be_visible()
    # Authorization sits with the URL, before any setting.
    await playwright_async.expect(
        page.get_by_role("checkbox", name=re.compile(r"^The site owner allows this scan"))
    ).to_be_visible()
    # No disabled-for-parity controls: what a login scan pins is said
    # once, in the Pages to scan group, and the switches are simply absent.
    await _open_scan_groups(page)
    await playwright_async.expect(
        page.get_by_role("note").filter(has_text="Sign-in scans always work this way")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("switch", name=re.compile(r"^Follow links to subdomains"))
    ).to_have_count(0)
    await playwright_async.expect(
        page.get_by_role("switch", name=re.compile(r"^Fast scan"))
    ).to_have_count(0)
    # The one disabled switch is a dependency, not parity: the vision
    # model waits for image text reading, which a login scan starts with off.
    disabled = page.get_by_role("switch", disabled=True)
    await playwright_async.expect(disabled).to_have_count(1)
    await playwright_async.expect(disabled).to_have_accessible_name(
        re.compile(r"^Compare image text with alt text")
    )
    dom_discovery = page.get_by_role("switch", name=re.compile(r"^Open menus, tabs"))
    await playwright_async.expect(dom_discovery).to_be_checked()

    workers = page.get_by_role("spinbutton", name="Signed-in tabs")
    await playwright_async.expect(workers).to_be_enabled()
    await playwright_async.expect(workers).to_have_value("2")
    await workers.fill("4")
    await playwright_async.expect(workers).to_have_value("4")

    both_engines = page.get_by_role("radio", name="Both", exact=True)
    axe_only = page.get_by_role("radio", name="axe", exact=True)
    alfa_only = page.get_by_role("radio", name="Alfa", exact=True)
    await playwright_async.expect(both_engines).to_be_enabled()
    await playwright_async.expect(axe_only).to_be_checked()
    await both_engines.check()
    await playwright_async.expect(both_engines).to_be_checked()
    await alfa_only.check()
    await playwright_async.expect(alfa_only).to_be_checked()
    await playwright_async.expect(dom_discovery).not_to_be_checked()
    await playwright_async.expect(dom_discovery).to_be_disabled()

    use_ocr = page.get_by_role("switch", name=re.compile(r"^Read text inside images"))
    use_vlm = page.get_by_role("switch", name=re.compile(r"^Compare image text with alt text"))
    await playwright_async.expect(use_ocr).to_be_enabled()
    await playwright_async.expect(use_ocr).not_to_be_checked()
    await playwright_async.expect(use_vlm).to_be_disabled()
    await use_ocr.check()
    await playwright_async.expect(use_vlm).to_be_enabled()
    await use_vlm.check()
    # The no-downloads promise moved into the summary rail.
    await playwright_async.expect(
        page.get_by_text(re.compile(r"Uses only AI models already installed"))
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("checkbox", name=re.compile(r"^Save images from signed-in pages"))
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("button", name="Open browser to sign in")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("textbox", name="Website address", exact=True)
    ).to_have_count(0)
    assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


async def test_skip_link_reachable_by_tab(live_server: tuple[str, int], new_page: Any) -> None:
    """The SPA's skip-link must be the first Tab stop and point at #main."""
    base, _ = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    await page.keyboard.press("Tab")
    href = await page.evaluate(
        "() => document.activeElement && document.activeElement.getAttribute('href')"
    )
    assert href == "#main"


@pytest.mark.parametrize("login", [False, True])
async def test_search_settings_keyboard_and_axe(
    live_server: tuple[str, int],
    login: bool,
    new_page: Any,
    choose_option: Any,
) -> None:
    base, _ = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    if login:
        login_tab = page.get_by_role(
            "tab", name="Site with a sign-in or two-step sign-in (2FA)", exact=True
        )
        await login_tab.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_url("**mode=login**")
        # The URL changes before the router's transition re-keys the form
        # for the new mode; wait for that render, or the controls below can
        # be filled in the public form just before it is replaced.
        await playwright_async.expect(login_tab).to_have_attribute("aria-selected", "true")
    # Search discovery lives in the Pages to scan group.
    await page.get_by_role("button", name="Pages to scan", exact=True).click()
    toggle = page.get_by_role("checkbox", name=re.compile("^Use a search box to find more pages"))
    await toggle.focus()
    await playwright_async.expect(toggle).to_be_focused()
    await page.keyboard.press("Space")
    await playwright_async.expect(toggle).to_be_checked()
    await page.get_by_label("Field 1 label", exact=True).fill("Search reports")
    value = page.get_by_label("Field 1 value", exact=True)
    await value.focus()
    await page.keyboard.type("sample")
    await playwright_async.expect(value).to_have_value("sample")
    for label in ("Press a search button", "Open more pages of results"):
        await page.get_by_role("checkbox", name=re.compile("^" + label)).focus()
        await page.keyboard.press("Space")
    await page.get_by_role("button", name="Add search field", exact=True).click()
    await page.get_by_label("Field 2 label", exact=True).fill("Category")
    await choose_option(page, "Field 2 type", "select")
    await page.get_by_label("Field 2 value", exact=True).fill("All reports")
    await page.get_by_role(
        "checkbox", name=re.compile("^I allow Axcess to type these searches")
    ).check()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


async def test_instance_screenshots_describe_the_outline_and_pass_axe(
    live_server: tuple[str, int],
    seeded_db: tuple[Path, Path, int],
    new_page: Any,
) -> None:
    """An issue's screenshots page says what the marker is, in text and alt text.

    The marker is drawn into the stored PNG, so the caption and alt text are
    the only way a reader who cannot see the image learns what it marks.
    """
    base, scan_id = live_server
    db_path, blob_dir, _ = seeded_db
    page_id = add_screenshot_finding(db_path, blob_dir, scan_id)
    page = await new_page()
    try:
        await page.goto(
            f"{base}/app/scans/{scan_id}/issues/{SCREENSHOT_ISSUE_KEY}/pages/{page_id}/screenshots",
            wait_until="networkidle",
        )
        await playwright_async.expect(
            page.get_by_text(re.compile(r"^Occurrence 1 of \d+\."))
        ).to_have_text(re.compile(r"The outline marks where it was found\.$"))
        await playwright_async.expect(
            page.get_by_role(
                "img",
                name=re.compile(r"^Occurrence 1 on .+\. An outline marks where it was found\.$"),
            )
        ).to_be_visible()
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()
