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

import json
import re
from pathlib import Path
from typing import Any

import pytest

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


async def _run_axe(page: Any) -> list[dict[str, Any]]:
    """Return the list of axe violations for the current page."""
    await page.add_script_tag(content=_AXE_TEXT)
    result = await page.evaluate(
        """async (tags) => {
            const res = await window.axe.run(document, {
                runOnly: { type: 'tag', values: tags }
            });
            return res.violations;
        }""",
        _AXE_TAGS,
    )
    return list(result)


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


async def test_dashboard_has_no_axe_violations(live_server: tuple[str, int], new_page: Any) -> None:
    base, _ = live_server
    await _axe_clean(new_page, base, "/app/")


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


async def test_simple_scan_path_hides_advanced_controls_until_requested(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The default flow is URL -> standard profile -> start, without losing controls."""
    base, _ = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_role("textbox", name="Site URL", exact=True)
    ).to_be_visible()
    # The default card is open and readable without a click; Coverage
    # and Checks are open too, so the first screen already says what
    # will run. Local AI and Speed start collapsed.
    await playwright_async.expect(
        page.get_by_role("region", name=re.compile(r"^Default scan settings"))
    ).to_be_visible()
    await playwright_async.expect(page.get_by_role("button", name="Start scan")).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("button", name="Local AI", exact=True)
    ).to_have_attribute("aria-expanded", "false")
    await playwright_async.expect(page.get_by_label("Max pages")).to_be_visible()
    await playwright_async.expect(page.get_by_role("group", name="Rule engine")).to_be_visible()
    dom_discovery = page.get_by_role("switch", name=re.compile(r"^Click through menus"))
    await playwright_async.expect(dom_discovery).to_be_checked()
    await dom_discovery.uncheck()
    await playwright_async.expect(dom_discovery).not_to_be_checked()
    # ...and the default card says so, in words as well as a strike.
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
    await page.get_by_label("Type", exact=True).select_option("expert_review")
    await page.wait_for_url("**type=expert_review*")
    issues = page.get_by_role("table", name="Accessibility issue groups")
    # Contains, not equals: the sorted header also carries its direction chip.
    await playwright_async.expect(issues.get_by_role("columnheader")).to_contain_text(
        [
            "Issue",
            "Type",
            "WCAG",
            "Priority",
            "Pages",
            "Occurrences",
            "Difficulty",
            "Responsibility",
        ]
    )
    assert await issues.get_by_role("button", name="About", exact=False).count() == 0

    first = issues.get_by_role("rowheader").first.get_by_role("link")
    title = (await first.inner_text()).splitlines()[0].strip()
    await first.click()
    await page.wait_for_url("**/issues/**")
    await playwright_async.expect(page.get_by_role("heading", name=title, level=1)).to_be_visible()
    # What it is, why it matters (or the expert-decision caution for a
    # lead), and where it was found.
    await playwright_async.expect(
        page.get_by_role("heading", name="What it is", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text(re.compile("Why it matters|expert decision")).first
    ).to_be_visible()


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
    issues = page.get_by_role("table", name="Accessibility issue groups")
    scroller = page.get_by_role("region", name="Issue table")
    for column in (None, "Issue", "Occurrences", "Responsibility"):
        if column:
            await issues.get_by_role("button", name=column, exact=False).first.click()
        widths = await scroller.evaluate("el => ({scroll: el.scrollWidth, client: el.clientWidth})")
        assert widths["scroll"] <= widths["client"], (column, widths)


async def test_issue_list_reaches_exact_locations_without_sideways_scrolling(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """At 320px the page itself never scrolls sideways.

    The issues table is wider than a phone, so it overflows inside its own
    keyboard-focusable region (SC 2.1.1) instead of pushing the page wider
    (SC 1.4.10), and there is no custom scrollbar widget to operate.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 320, "height": 800})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await page.get_by_label("Type", exact=True).select_option("expert_review")
    await page.wait_for_url("**type=expert_review*")
    issues = page.get_by_role("table", name="Accessibility issue groups")
    await playwright_async.expect(issues).to_be_visible()

    widths = await page.evaluate(
        """() => ({
            client: document.documentElement.clientWidth,
            body: document.body.scrollWidth
        })"""
    )
    assert widths["body"] <= widths["client"], widths
    assert await page.get_by_role("scrollbar").count() == 0
    scroller = page.get_by_role("region", name="Issue table")
    await playwright_async.expect(scroller).to_have_attribute("tabindex", "0")
    assert await scroller.evaluate("el => el.scrollWidth > el.clientWidth")

    # Each row's title carries the reader to that issue's own
    # evidence route.
    first_row = issues.get_by_role("rowheader").first.get_by_role("link")
    href = await first_row.get_attribute("href")
    assert href is not None and "/issues/" in href
    await first_row.click()
    await page.wait_for_url("**/issues/**")
    await playwright_async.expect(
        page.get_by_role("link", name="opens the in-app page inspector", exact=False).first
    ).to_be_attached()
    # The protected-identity context refreshes every 15 seconds even
    # on public report routes. That security check must not unmount a
    # known-public table and reset the reader to the top.
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
    issues = page.get_by_role("table", name="Accessibility issue groups")
    row_link = issues.get_by_role("rowheader").get_by_role(
        "link", name="Logo image, adequate alt", exact=False
    )
    informational_row = row_link.locator("xpath=ancestor::tr[1]")
    await playwright_async.expect(
        informational_row.get_by_text("Informational", exact=True)
    ).to_be_visible()
    # Informational evidence never inherits triage or remediation
    # controls: the row has no buttons at all, only its links.
    assert await informational_row.get_by_role("button").count() == 0

    await page.goto(
        f"{base}/app/scans/{scan_id}/issues/image:logo_adequate",
        wait_until="networkidle",
    )
    await playwright_async.expect(
        page.get_by_role("heading", name="Informational evidence")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("No barrier was detected by this check.", exact=False)
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
    await page.goto(f"{base}/app/scans/{scan_id}/diff", wait_until="networkidle")
    workspace = page.get_by_role("navigation", name="Report workspace")
    await workspace.get_by_role("link", name="Issues").click()
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")
    await page.wait_for_function("document.activeElement?.id === 'main'")
    assert await page.title() == "Accessibility issues · Axcess"


async def test_completed_scan_opens_as_report_output_not_pipeline_dashboard(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """A settled scan lands on its issue table, with the overview folded in.

    There is no Overview tab any more: the report's URL redirects to Issues,
    and the stat cards and scan coverage the overview carried sit above the
    table, the coverage as one line that opens the full ledger.
    """
    base, scan_id = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")
    await playwright_async.expect(
        page.get_by_role("heading", name="Issues", exact=True, level=1)
    ).to_be_visible()
    workspace = page.get_by_role("navigation", name="Report workspace")
    await playwright_async.expect(workspace.get_by_role("link")).to_have_text(
        ["Issues", "Verify changes"]
    )
    await playwright_async.expect(
        workspace.get_by_role("link", name="Issues", exact=True)
    ).to_have_attribute("aria-current", "page")
    await playwright_async.expect(page.get_by_role("link", name="Overview")).to_have_count(0)
    await playwright_async.expect(page.get_by_text("Issue Groups", exact=True)).to_be_visible()
    await playwright_async.expect(page.get_by_text("Pages Tested", exact=True)).to_be_visible()

    # The coverage line counts the methods the scan recorded as run.
    response = await page.request.get(f"{base}/api/scans/{scan_id}")
    methods = (await response.json())["methods_used"]
    ran = sum(method["state"] in {"checked", "partial"} for method in methods)
    coverage = page.locator("summary").filter(has_text=f"{ran} of {len(methods)} checks ran")
    await playwright_async.expect(coverage).to_contain_text("Details")
    ledger = page.get_by_role("heading", name="What this scan actually checked")
    await playwright_async.expect(ledger).to_be_hidden()
    await coverage.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(ledger).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("Click Through DOM States", exact=True)
    ).to_be_visible()

    # The subtitle names the report without repeating a stat card's count.
    subtitle = page.locator("main h1 + p")
    text = await subtitle.inner_text()
    assert "issue groups" not in text and "occurrences" not in text, text
    issues = await (await page.request.get(f"{base}/api/scans/{scan_id}/issues")).json()
    for count in (issues["total_unfiltered"], issues["occurrence_counts"]["all_evidence"]):
        assert not re.search(rf"\b{count}\b", text), (count, text)


async def test_running_scan_shows_factual_pipeline_progress(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Live progress names the URL and completed engines without a fake percent."""
    base, scan_id = live_server
    page = await new_page()
    response = await page.request.get(f"{base}/api/scans/{scan_id}")
    assert response.ok
    payload = await response.json()
    payload.update(
        {
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
            },
        }
    )
    for method in payload["methods_used"]:
        if method["key"] == "alfa":
            method["enabled"] = True
            method["state"] = "running"
            method["result"] = "5 pages checked so far"
        elif method["key"] == "axe":
            method["state"] = "running"
            method["result"] = "6 pages checked so far"

    async def serve_running_scan(route: Any) -> None:
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    await page.route(f"**/api/scans/{scan_id}", serve_running_scan)
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_role("heading", name="Scan in progress")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("https://example.test/admissions/apply/", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("6 pages checked so far", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("5 pages checked so far", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("without reloading the page or moving your scroll", exact=False)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("40 sec\N{EN DASH}2 min for currently discovered pages", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("Recently completed pages", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("Loaded successfully (HTTP 200)", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("Rendered in a real browser", exact=True)
    ).to_be_visible()

    # A background data refresh must not reload, move the viewport, or
    # steal focus from the operator's current control.
    pause = page.get_by_role("button", name="Pause live updates")
    await pause.focus()
    await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    scroll_before = await page.evaluate("window.scrollY")
    navigations_before = await page.evaluate("performance.getEntriesByType('navigation').length")
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


async def test_every_spa_route_has_an_accurate_document_title(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Every route declared in App.tsx has a non-generic title announcement."""
    base, scan_id = live_server
    cases = [
        ("/app/", "Dashboard"),
        ("/app/scans", "Reports"),
        ("/app/scans/new", "New scan"),
        ("/app/scans/protected/new", "New scan"),
        (f"/app/scans/{scan_id}/protected", "Protected companion"),
        (f"/app/scans/{scan_id}/protected/manual-checks", "Protected manual checks"),
        (f"/app/scans/{scan_id}/protected/issues", "Protected issue index"),
        # A completed report's URL redirects to its issue table.
        (f"/app/scans/{scan_id}", "Accessibility issues"),
        (f"/app/scans/{scan_id}/review", "Accessibility issues"),
        (f"/app/scans/{scan_id}/manual-checks", "Accessibility issues"),
        (f"/app/scans/{scan_id}/handoff", "Accessibility issues"),
        (f"/app/scans/{scan_id}/pages/1", "Page evidence"),
        (f"/app/scans/{scan_id}/issues", "Accessibility issues"),
        (f"/app/scans/{scan_id}/issues/image:logo_adequate", "Issue evidence"),
        (f"/app/scans/{scan_id}/findings", "Image evidence"),
        (f"/app/scans/{scan_id}/findings/grouped", "Grouped image evidence"),
        (f"/app/scans/{scan_id}/a11y", "DOM-engine evidence"),
        (f"/app/scans/{scan_id}/a11y/by-rule", "DOM-engine rules"),
        (f"/app/scans/{scan_id}/diff", "Verify changes"),
        ("/app/findings/1", "Finding evidence"),
        ("/app/tracking", "Coverage tracking"),
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


async def test_header_uses_one_mode_neutral_new_scan_action(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The global CTA defers the public/login choice to the new-scan page."""
    base, _scan_id = live_server
    page = await new_page()
    await page.goto(f"{base}/app/", wait_until="networkidle")

    action = page.get_by_role("banner").get_by_role("link", name="Create New Scan", exact=True)
    await playwright_async.expect(action).to_have_count(1)
    href = await action.get_attribute("href")
    assert href is not None
    assert href.endswith("/app/scans/new")
    assert "mode=" not in href

    await action.click()
    assert page.url.endswith("/app/scans/new")
    await playwright_async.expect(page.get_by_role("tablist", name="Scan type")).to_be_visible()


async def test_header_offers_one_external_feedback_link(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Feedback is reachable from every screen and clearly leaves the app."""
    base, _scan_id = live_server
    page = await new_page()
    await page.goto(f"{base}/app/", wait_until="networkidle")

    feedback = page.get_by_role("banner").get_by_role(
        "link", name="Give feedback (opens in a new tab)", exact=True
    )
    await playwright_async.expect(feedback).to_have_count(1)
    assert await feedback.get_attribute("href") == (
        "https://form.asana.com/?k=nRyyF2UKBYMXEj3v8CKCCA&d=939514425027676"
    )
    # A new tab is a change of context, and the opened page must not
    # be able to reach back into this one.
    assert await feedback.get_attribute("target") == "_blank"
    rel = await feedback.get_attribute("rel") or ""
    assert "noopener" in rel and "noreferrer" in rel


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
    login = page.get_by_role("tab", name="Site with a login or 2FA", exact=True)
    await playwright_async.expect(public).to_have_attribute("aria-selected", "true")

    await login.click()
    await playwright_async.expect(login).to_have_attribute("aria-selected", "true")
    assert "mode=login" in page.url
    assert "url=https%3A%2F%2Fexample.com%2F" in page.url
    # The address survives the switch inside the form as well.
    await playwright_async.expect(
        page.get_by_role("textbox", name="Page to scan after you sign in")
    ).to_have_value("https://example.com/")

    await public.click()
    await playwright_async.expect(public).to_have_attribute("aria-selected", "true")
    assert "mode=" not in page.url
    assert "url=https%3A%2F%2Fexample.com%2F" in page.url


async def test_tracking_coverage_table_filters_and_sorts(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The coverage matrix can be narrowed and reordered, and says so.

    The tracker is one table with a group filter: "Current Coverage" (what
    Axcess checks, with a second row of method chips), "Future Coverage"
    (the manual-only long tail), and "AI Coverage" (the roadmap). "Manual
    only" is therefore a group, not one of the method chips — filtering the
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
    matrix = page.get_by_role("table", name="WCAG 2.2 A/AA coverage and AI roadmap")
    sections = page.get_by_role("group", name="Tracker sections")
    await sections.get_by_role("button", name=re.compile(r"^Current Coverage")).click()
    methods = page.get_by_role("group", name="Filter coverage by method")

    # Narrowing to one method leaves only that method's rows.
    automated = methods.get_by_role("button", name=re.compile(r"^Automated"))
    await automated.click()
    await playwright_async.expect(automated).to_have_attribute("aria-pressed", "true")
    assert "method=automated" in page.url
    status_cells = matrix.locator("tbody tr td:nth-child(5)")
    shown_labels = set(await status_cells.all_inner_texts())
    assert shown_labels == {labels["automated"]}, shown_labels

    reset = methods.get_by_role("button", name=re.compile(r"^All"))
    await reset.click()
    await playwright_async.expect(matrix.locator("tbody tr th[scope='row']")).to_have_count(
        len(covered)
    )

    # Success criteria sort as numbers: 1.4.4 before 1.4.10.
    sc_header = matrix.get_by_role("columnheader", name="SC")
    await playwright_async.expect(sc_header).to_have_attribute("aria-sort", "ascending")
    ascending = await matrix.locator("tbody tr th[scope='row']").all_inner_texts()
    assert ascending == sorted(ascending, key=lambda sc: tuple(int(part) for part in sc.split(".")))

    await sc_header.get_by_role("button").click()
    await playwright_async.expect(sc_header).to_have_attribute("aria-sort", "descending")
    descending = await matrix.locator("tbody tr th[scope='row']").all_inner_texts()
    assert descending == list(reversed(ascending))

    # The manual-only long tail is its own group, and it is the rest of
    # the criteria — the two groups together account for all of them.
    await sections.get_by_role("button", name=re.compile(r"^Future Coverage")).click()
    await playwright_async.expect(matrix.locator("tbody tr th[scope='row']")).to_have_count(
        len(manual)
    )


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
    login_tab = page.get_by_role("tab", name="Site with a login or 2FA", exact=True)
    await playwright_async.expect(login_tab).to_be_visible()
    await login_tab.click()
    await playwright_async.expect(login_tab).to_have_attribute("aria-selected", "true")
    assert "mode=login" in page.url
    await playwright_async.expect(
        page.get_by_role("heading", name="New scan", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("textbox", name="Page to scan after you sign in")
    ).to_be_visible()
    # Authorization sits with the URL, before any setting.
    await playwright_async.expect(
        page.get_by_role("checkbox", name=re.compile(r"^I have authorization"))
    ).to_be_visible()
    # No disabled-for-parity controls: what a login scan pins is said
    # once, in the Coverage group, and the switches are simply absent.
    await playwright_async.expect(
        page.get_by_role("note").filter(has_text="Fixed for login scans")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("switch", name=re.compile(r"^Follow links to subdomains"))
    ).to_have_count(0)
    await playwright_async.expect(
        page.get_by_role("switch", name=re.compile(r"^Fast crawl"))
    ).to_have_count(0)
    assert await page.get_by_role("switch", disabled=True).count() == 0
    dom_discovery = page.get_by_role("switch", name=re.compile(r"^Click through menus"))
    await playwright_async.expect(dom_discovery).to_be_checked()

    await page.get_by_role("button", name="Speed and debugging", exact=True).click()
    workers = page.get_by_role("spinbutton", name="Signed-in tabs")
    await playwright_async.expect(workers).to_be_enabled()
    await playwright_async.expect(workers).to_have_value("2")
    await workers.fill("4")
    await playwright_async.expect(workers).to_have_value("4")

    both_engines = page.get_by_role("radio", name="Both", exact=True)
    axe_only = page.get_by_role("radio", name="axe-core", exact=True)
    alfa_only = page.get_by_role("radio", name="Siteimprove Alfa", exact=True)
    await playwright_async.expect(both_engines).to_be_enabled()
    await playwright_async.expect(axe_only).to_be_checked()
    await both_engines.check()
    await playwright_async.expect(both_engines).to_be_checked()
    await alfa_only.check()
    await playwright_async.expect(alfa_only).to_be_checked()
    await playwright_async.expect(dom_discovery).not_to_be_checked()
    await playwright_async.expect(dom_discovery).to_be_disabled()

    await page.get_by_role("button", name="Local AI", exact=True).click()
    use_ocr = page.get_by_role("switch", name=re.compile(r"^Read text inside images"))
    use_vlm = page.get_by_role("switch", name=re.compile(r"^Review image text"))
    await playwright_async.expect(use_ocr).to_be_enabled()
    await playwright_async.expect(use_ocr).not_to_be_checked()
    await playwright_async.expect(use_vlm).to_be_disabled()
    await use_ocr.check()
    await playwright_async.expect(use_vlm).to_be_enabled()
    await use_vlm.check()
    # The no-downloads promise moved into the summary rail.
    await playwright_async.expect(
        page.get_by_text(re.compile(r"Uses only models already installed"))
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("checkbox", name=re.compile(r"^Store protected image-analysis evidence"))
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("button", name="Open browser to sign in")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("textbox", name="Site URL", exact=True)
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
    live_server: tuple[str, int], login: bool, new_page: Any
) -> None:
    base, _ = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/new", wait_until="networkidle")
    if login:
        await page.get_by_role("tab", name="Site with a login or 2FA", exact=True).focus()
        await page.keyboard.press("Enter")
        await page.wait_for_url("**mode=login**")
    # Search discovery lives in the Checks group, which starts open.
    toggle = page.get_by_role("checkbox", name=re.compile("^Search to discover result pages"))
    await toggle.focus()
    await page.keyboard.press("Space")
    await page.get_by_label("Field 1 label", exact=True).fill("Search reports")
    value = page.get_by_label("Field 1 value", exact=True)
    await value.focus()
    await page.keyboard.type("sample")
    await playwright_async.expect(value).to_have_value("sample")
    for label in ("Press a search button", "Follow result pagination"):
        await page.get_by_role("checkbox", name=re.compile("^" + label)).focus()
        await page.keyboard.press("Space")
    await page.get_by_role("button", name="Add search field", exact=True).click()
    await page.get_by_label("Field 2 label", exact=True).fill("Category")
    await page.get_by_role("combobox", name="Field 2 type", exact=True).select_option("select")
    await page.get_by_label("Field 2 value", exact=True).fill("All reports")
    await page.get_by_role("checkbox", name=re.compile("^I authorize these search")).check()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
