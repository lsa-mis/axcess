"""Keyboard and accessibility coverage for report review and comparison."""

from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import pytest

from ._seed_evidence import SCREENSHOT_ISSUE_KEY, add_screenshot_finding
from .test_accessibility_axe import _render_violations, _run_axe

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")


@pytest.mark.parametrize("width", [1280, 320])
async def test_report_links_and_review_lanes(
    live_server: tuple[str, int],
    width: int,
    new_page: Any,
    choose_filter: Any,
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": width, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    payload = await response.json()
    template = payload["rows"][0]
    rows = [
        {**template, "issue_key": lane, "title": title, "review_lane": lane}
        for lane, title in [
            ("likely_barrier", "Named control failure"),
            ("expert_review", "Contrast calculation needs review"),
            ("informational", "Decorative image note"),
        ]
    ]
    payload.update(rows=rows, total_unfiltered=3)

    async def issues(route: Any) -> None:
        query = parse_qs(urlparse(route.request.url).query)
        needle = query.get("q", [""])[0].lower()
        lane = query.get("review_lane", [""])[0]
        shown = [
            row
            for row in rows
            if needle in row["title"].lower() and (not lane or row["review_lane"] == lane)
        ]
        await asyncio.sleep(0.05)
        await route.fulfill(json={**payload, "rows": shown})

    await page.route(f"**/api/scans/{scan_id}/issues*", issues)
    # The report's own URL used to be its Overview tab. It opens on the
    # issue table now, so old links land there instead of breaking.
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")
    crumb = page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
    reports = crumb.get_by_role("link", name="Reports", exact=True)
    await reports.focus()
    assert await reports.evaluate("el => getComputedStyle(el).textDecorationLine") == "underline"
    assert await reports.evaluate("el => el.getBoundingClientRect().height") >= 44
    assert await reports.evaluate("el => getComputedStyle(el).boxShadow") != "none"
    await page.keyboard.press("Enter")
    await page.wait_for_url("**/app/scans")
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    # Every issue group is a row of one table, whatever lane it is in.
    issues = page.get_by_role("table", name="Accessibility issues")
    # Scoped to the row header: the count link in the same row also
    # names the issue, because a link's purpose has to be clear from
    # its own name (SC 2.4.9).
    for title in (
        "Named control failure",
        "Contrast calculation needs review",
        "Decorative image note",
    ):
        await playwright_async.expect(
            issues.get_by_role("rowheader").get_by_role("link", name=title, exact=False)
        ).to_be_visible()
    search = page.get_by_label("Search issues")
    await search.focus()
    await page.keyboard.type("Contrast")
    await playwright_async.expect(search).to_have_value("Contrast")
    await playwright_async.expect(
        issues.get_by_role("rowheader").get_by_role(
            "link", name="Contrast calculation needs review", exact=False
        )
    ).to_be_visible()
    await playwright_async.expect(search).to_be_focused()
    await page.wait_for_url("**q=Contrast*")
    # A pending search must preserve a filter changed during its debounce,
    # and the filter must not drop the term still sitting in the box.
    await search.fill("Decorative")
    await choose_filter(page, "Level", "A")
    await page.wait_for_url("**q=Decorative*")
    await playwright_async.expect(
        issues.get_by_role("rowheader").get_by_role(
            "link", name="Decorative image note", exact=False
        )
    ).to_be_visible()
    url_params = parse_qs(urlparse(page.url).query)
    assert url_params["q"] == ["Decorative"]
    assert url_params["conformance"] == ["A"]
    # Level is a checkbox group: a second level joins the first rather than
    # replacing it, and both are kept in the URL and written out.
    filter_button = page.get_by_role("button", name=re.compile(r"^Filter\b")).and_(
        page.locator("[aria-controls][aria-expanded]")
    )
    await filter_button.click()
    await (
        page.get_by_role("group", name="Level", exact=True)
        .get_by_role("checkbox", name=re.compile(r"^Level AA\b"))
        .click()
    )
    await page.wait_for_url(re.compile(r"[?&]conformance=A(%2C|,)AA(&|$)"))
    await page.keyboard.press("Escape")
    await playwright_async.expect(page.locator("p").filter(has_text="Filtered by")).to_contain_text(
        "Level: Level A, Level AA"
    )
    # "Type" filters on the review lane the Type column shows. It is
    # a URL parameter like the others, so it narrows the table to the
    # one lane, reads the way the cells do, and clears with the rest.
    await page.get_by_role("button", name="Clear filters").click()
    await page.wait_for_url(re.compile(r"/issues$"))
    await choose_filter(page, "Type", "expert_review")
    await page.wait_for_url("**type=expert_review*")
    await playwright_async.expect(
        issues.get_by_role("rowheader").get_by_role(
            "link", name="Contrast calculation needs review", exact=False
        )
    ).to_be_visible()
    for hidden in ("Named control failure", "Decorative image note"):
        await playwright_async.expect(
            issues.get_by_role("rowheader").get_by_role("link", name=hidden, exact=False)
        ).to_have_count(0)
    type_cells = issues.locator("tbody tr > td:nth-child(2)")
    assert set(await type_cells.all_inner_texts()) == {"Needs review"}
    assert "conformance" not in parse_qs(urlparse(page.url).query)
    assert await page.evaluate("document.body.scrollWidth <= innerWidth")
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


def _snapshot(scan_id: int, key: str, occurrences: int) -> dict[str, Any]:
    return {
        "occurrences": occurrences,
        "issue_occurrences": occurrences,
        "pages": 1,
        "statuses": {"new": occurrences},
        "outcomes": {},
        "issues": [{"label": key, "url": f"/app/scans/{scan_id}/issues/{quote(key, safe='')}"}],
        "evidence": [],
    }


def _comparison(scan_id: int) -> dict[str, Any]:
    """Twelve compared groups: one new, one resolved, ten remaining (two pages)."""
    rows = [
        {
            "key": "alfa:r69",
            "pipeline": "alfa",
            "title": "Text contrast",
            "category": "changed",
            "change": "new",
            "wcag_sc": "1.4.3",
            "wcag_name": "Contrast (Minimum)",
            "conformance": "AA",
            "before": None,
            "after": _snapshot(scan_id, "alfa:r69:failed", 7),
            "limitations": [],
        },
        {
            "key": "axe:image-alt",
            "pipeline": "axe",
            "title": "Images must have alternative text",
            "category": "no_longer_detected",
            "change": "resolved",
            "wcag_sc": "1.1.1",
            "wcag_name": "Non-text Content",
            "conformance": "A",
            "before": _snapshot(99, "axe:image-alt", 3),
            "after": None,
            "limitations": [],
        },
    ]
    for i in range(10):
        rows.append(
            {
                "key": f"axe:rule-{i}",
                "pipeline": "axe",
                "title": f"Remaining rule {i}",
                "category": "still_detected",
                "change": "remaining",
                "wcag_sc": None,
                "wcag_name": None,
                "conformance": "BP",
                "before": _snapshot(99, f"axe:rule-{i}", i + 1),
                "after": _snapshot(scan_id, f"axe:rule-{i}", i + 1),
                "limitations": [],
            }
        )
    return {
        "current": {"id": scan_id, "seed_url": "http://example.com/", "started_at": "2026-09-02"},
        "baseline": {"id": 99, "seed_url": "http://example.com/", "started_at": "2026-09-01"},
        "counts": {
            "new": 1,
            "still_detected": 10,
            "changed": 0,
            "no_longer_detected": 1,
            "cannot_compare": 0,
        },
        "changes": {"new": 1, "resolved": 1, "remaining": 10},
        "before_totals": {"groups": 11, "occurrences": 58},
        "after_totals": {"groups": 11, "occurrences": 62},
        "pipeline_counts": {"alfa": 1, "axe": 11},
        "coverage": [
            {
                "pipeline": "axe",
                "before": {"state": "complete", "checked": 5, "total": 5},
                "after": {"state": "complete", "checked": 5, "total": 5},
            },
            {
                "pipeline": "keyboard",
                "before": {"state": "unknown", "checked": 3, "total": 5},
                "after": {"state": "unknown", "checked": 5, "total": 5},
            },
        ],
        "settings_changed": [],
        "limitations": ["Historical report coverage is incomplete."],
        "notes": [
            {
                "text": "Errors were recorded while crawling or checking pages.",
                "scans": [scan_id],
                "differs": True,
            },
            {
                "text": "Historical report coverage is incomplete.",
                "scans": [99, scan_id],
                "differs": False,
            },
        ],
        "rows": rows,
        "total": 12,
        "page": 1,
        "page_size": 500,
    }


def _history(scan_id: int) -> dict[str, Any]:
    return {
        "site_url": "http://example.com/",
        "total": 3,
        "scans": [
            {
                "id": 98,
                "started_at": "2026-08-20 12:00:00",
                "finished_at": None,
                "groups": 14,
                "occurrences": 90,
            },
            {
                "id": 99,
                "started_at": "2026-09-01 12:00:00",
                "finished_at": None,
                "groups": 11,
                "occurrences": 58,
            },
            {
                "id": scan_id,
                "started_at": "2026-09-02 12:00:00",
                "finished_at": None,
                "groups": 11,
                "occurrences": 62,
            },
        ],
    }


def _page_evidence(scan_id: int) -> dict[str, Any]:
    return {
        "page": {
            "id": 1,
            "scan_id": scan_id,
            "url_normalized": "http://example.com/",
            "title": "Home",
            "status_code": 200,
            "render_mode": "playwright",
            "fetched_at": None,
        },
        "image_occurrences": [],
        "a11y_findings": [
            {
                "id": 77,
                "pipeline": "alfa",
                "rule_id": "r69",
                "wcag_sc": "1.4.3",
                "help": "Text contrast",
                "status": "new",
                "engine_outcome": "cant_tell",
                "screenshot_hash": None,
                "target_selector": "/html/body/p[1]/text()[1]",
                "target_display": "Text in the first paragraph: “Read more”",
                "failure_summary": (
                    "Alfa could not calculate contrast because background sizing is unsupported."
                ),
                "manual_review_hint": (
                    "Measure the text against the background at the text location."
                ),
                "engine_evidence_status": "recovered",
                "revealed_by": None,
            }
        ],
    }


@pytest.mark.parametrize("width", [1280, 320])
async def test_compare_scans_keyboard_filters_trend_and_axe(
    live_server: tuple[str, int], width: int, new_page: Any, choose_filter: Any
) -> None:
    """Every control on Compare reports works from the keyboard alone."""
    base, scan_id = live_server
    page = await new_page(viewport={"width": width, "height": 900})
    requests: list[dict[str, list[str]]] = []

    async def comparison(route: Any) -> None:
        requests.append(parse_qs(urlparse(route.request.url).query))
        await asyncio.sleep(0.05)
        await route.fulfill(json=_comparison(scan_id))

    await page.route(f"**/api/scans/{scan_id}/comparison*", comparison)
    await page.route(
        f"**/api/scans/{scan_id}/history", lambda route: route.fulfill(json=_history(scan_id))
    )
    await page.goto(f"{base}/app/scans/{scan_id}/compare", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_role("heading", name="Compare reports", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("navigation", name="Report views").get_by_role(
            "link", name="Compare reports"
        )
    ).to_have_attribute("aria-current", "page")
    # One request for every group: the page sorts, filters and pages them.
    assert requests[-1]["page_size"] == ["500"]
    status = page.get_by_role("status").filter(has_text="issues shown")
    await playwright_async.expect(status).to_contain_text("12 of 12 issues shown")

    # A number is a filter, and says so by its pressed state. It is the
    # table's Change filter too, written out under the table's bar.
    cards = page.get_by_role("group", name="Filter the table by change")
    new_card = cards.get_by_role("button", name=re.compile(r"^New"))
    await new_card.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(new_card).to_have_attribute("aria-pressed", "true")
    await playwright_async.expect(status).to_contain_text("1 of 12 issues shown")
    await playwright_async.expect(page.get_by_text("Filtered by Change: New")).to_be_visible()
    await page.keyboard.press("Enter")
    await playwright_async.expect(new_card).to_have_attribute("aria-pressed", "false")
    await playwright_async.expect(status).to_contain_text("12 of 12 issues shown")

    # The table's Filter menu from the keyboard: Enter opens it, Tab reaches
    # the Change checkboxes, Space checks the focused one at once (the card
    # follows), and Escape closes it back on its button.
    filter_button = page.get_by_role("button", name=re.compile(r"^Filter\b"))
    await filter_button.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(filter_button).to_have_attribute("aria-expanded", "true")
    change_boxes = page.get_by_role("group", name="Change", exact=True)
    new_box = change_boxes.get_by_role("checkbox", name=re.compile(r"^New\b"))
    await page.keyboard.press("Tab")
    await playwright_async.expect(new_box).to_be_focused()
    await page.keyboard.press("Space")
    await playwright_async.expect(new_box).to_be_checked()
    await playwright_async.expect(status).to_contain_text("1 of 12 issues shown")
    await playwright_async.expect(new_card).to_have_attribute("aria-pressed", "true")
    await page.keyboard.press("Escape")
    await playwright_async.expect(filter_button).to_be_focused()
    await playwright_async.expect(filter_button).to_have_attribute("aria-expanded", "false")
    await choose_filter(page, "Change", "")
    await playwright_async.expect(new_card).to_have_attribute("aria-pressed", "false")
    await playwright_async.expect(status).to_contain_text("12 of 12 issues shown")

    search = page.get_by_role("searchbox", name="Search issues")
    await search.focus()
    await page.keyboard.type("contrast")
    await playwright_async.expect(status).to_contain_text("1 of 12 issues shown")
    await page.wait_for_url(re.compile(r"[?&]q=contrast"))
    await page.keyboard.press("ControlOrMeta+a")
    await page.keyboard.press("Backspace")
    await playwright_async.expect(status).to_contain_text("12 of 12 issues shown")

    issue_header = page.get_by_role("columnheader", name=re.compile(r"^Issue"))
    await issue_header.get_by_role("button").focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(issue_header).to_have_attribute("aria-sort", "ascending")
    await playwright_async.expect(status).to_contain_text("Sorted by issue, A to Z")

    terms = page.get_by_role("button", name="What do these terms mean?")
    await terms.focus()
    await page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="What these terms mean")
    await playwright_async.expect(dialog).to_be_visible()
    await playwright_async.expect(dialog).to_contain_text("not proof of a fix")
    await page.keyboard.press("Escape")
    await playwright_async.expect(dialog).to_be_hidden()
    await playwright_async.expect(terms).to_be_focused()

    # A trend point opens its scan's panel; closing it returns to the point.
    point = page.get_by_role("button", name=re.compile(r"^Report #98,"))
    await point.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(point).to_have_attribute("aria-pressed", "true")
    await playwright_async.expect(
        page.get_by_role("link", name="Open report #98 issues")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("link", name="Compare with this report")
    ).to_have_attribute("href", f"/app/scans/{scan_id}/compare?compare_to=98")
    await page.get_by_role("button", name="Close report #98 details").focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(point).to_be_focused()
    await page.keyboard.press("ArrowRight")
    await playwright_async.expect(
        page.get_by_role("button", name=re.compile(r"^Report #99,"))
    ).to_be_focused()

    toggle = page.get_by_role("button", name="Show as data table")
    await toggle.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(
        page.get_by_role("table", name="Completed scans of this site, oldest first")
    ).to_be_visible()

    # Closed, the notes still say how many differences there are.
    coverage = page.get_by_role("button", name=re.compile(r"^What was checked in each report"))
    await playwright_async.expect(coverage).to_have_attribute("aria-expanded", "false")
    await playwright_async.expect(coverage).to_contain_text("2 differences between the scans")
    await coverage.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(coverage).to_have_attribute("aria-expanded", "true")
    notes = page.get_by_role("region", name="What was checked in each report")
    for heading in ["What differs between the scans", "What each check covered"]:
        await playwright_async.expect(notes.get_by_role("heading", name=heading)).to_be_visible()
    await playwright_async.expect(
        notes.get_by_role("listitem").filter(has_text=f"Report #{scan_id} only:")
    ).to_contain_text("Errors were recorded")
    # A check whose coverage differs says so in words, not only by its tint.
    await playwright_async.expect(
        notes.get_by_role("rowheader", name=re.compile(r"^Keyboard check\s*,\s*Differs$"))
    ).to_be_visible()
    await playwright_async.expect(
        notes.get_by_role("rowheader", name="Rule check (axe)")
    ).to_be_visible()
    await playwright_async.expect(
        notes.get_by_text("Historical report coverage is incomplete.", exact=True)
    ).to_be_visible()

    assert await page.evaluate("document.body.scrollWidth <= innerWidth")
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # The issue opens in the report it was found in, with the way back.
    # Sorted A to Z it is on the second page, so find it first.
    await search.focus()
    await page.keyboard.type("contrast")
    await playwright_async.expect(status).to_contain_text("1 of 12 issues shown")
    # Chrome puts a space before the visually hidden words: "contrast , evidence".
    link = page.get_by_role(
        "link", name=re.compile(r"^Text contrast\s*, evidence in the later scan$")
    )
    await link.focus()
    await page.keyboard.press("Enter")
    await page.wait_for_url(
        re.compile(rf"/app/scans/{scan_id}/issues/alfa%3Ar69%3Afailed\?.*origin=Compare")
    )


async def test_finding_anchor_waits_for_scan_metadata(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page()
    scan = await (await page.request.get(f"{base}/api/scans/{scan_id}")).json()

    async def metadata(route: Any) -> None:
        await asyncio.sleep(0.2)
        await route.fulfill(json=scan)

    await page.route(f"**/api/scans/{scan_id}", metadata)
    await page.route(
        f"**/api/scans/{scan_id}/pages/1",
        lambda route: route.fulfill(json=_page_evidence(scan_id)),
    )
    await page.goto(f"{base}/app/scans/{scan_id}/pages/1#finding-77", wait_until="networkidle")
    await playwright_async.expect(page.locator("#finding-77")).to_be_focused()
    # The finding's evidence says what is missing and where the element is.
    # (These checks rode on the old Verify changes link to this page; Compare
    # scans links to the issue instead, so they live here now.)
    await playwright_async.expect(
        page.get_by_text("Some details are missing.", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("Text in the first paragraph", exact=False)
    ).to_be_visible()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


async def test_issue_filters_announce_results_and_keep_large_targets(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Filtering says what it did, and the row's links stay 44px (SC 4.1.3, 2.5.5).

    The table used to change under a screen-reader user in silence: the count
    line in the header updated, and nothing announced it. The row links were
    38px and 18px high, inside cells that looked bigger than the targets were.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    # The sort line is a status region of its own; this one reports
    # how many groups the filters left.
    status = page.get_by_role("status").filter(has_text="issues shown")
    await playwright_async.expect(status).to_contain_text("issues shown")
    search = page.get_by_label("Search issues")
    await search.fill("logo")
    await page.wait_for_url("**q=logo*")
    await playwright_async.expect(status).to_contain_text("filtered")

    sizes = await page.evaluate(
        """() => [...document.querySelectorAll('table tbody a')]
            .map(a => Math.round(a.getBoundingClientRect().height))
            .filter(h => h > 0)"""
    )
    assert sizes and all(height >= 44 for height in sizes), sizes


async def test_issue_table_recommended_order_is_lane_first_and_headers_sort_flat(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """The default order is lane first, in one flat body; every header sorts the same way.

    Priority used to be the one header that grouped by type while the others
    sorted flat. The lane-first order is now its own order, the default. It
    has no row-group header rows between the types: the Type cell names each
    row's type, and the live status line reads the count of each.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    issues = page.get_by_role("table", name="Accessibility issues")
    group_headers = issues.locator("tbody th[scope='rowgroup']")
    back = page.get_by_role("button", name="Back to recommended order")
    lane_order = ["Barrier", "Needs review", "Informational"]

    async def assert_recommended() -> None:
        await playwright_async.expect(
            page.get_by_role("status").filter(has_text="Recommended order")
        ).to_be_visible()
        await playwright_async.expect(back).to_have_count(0)
        await playwright_async.expect(group_headers).to_have_count(0)
        assert await issues.locator("tbody").count() == 1
        # Row header, then Type.
        lanes = [
            cell.strip()
            for cell in await issues.locator("tbody tr > td:nth-child(2)").all_inner_texts()
        ]
        assert lanes and lanes == sorted(lanes, key=lane_order.index), lanes
        await playwright_async.expect(
            page.get_by_role("status").filter(has_text="issues shown")
        ).to_have_text(
            re.compile(r"issues shown: Barrier \d+, Needs review \d+, Informational \d+$")
        )
        sorted_headers = issues.locator("thead th[aria-sort]:not([aria-sort='none'])")
        await playwright_async.expect(sorted_headers).to_have_count(0)

    await assert_recommended()
    # A link saved before the change named the lane-first order this way.
    await page.goto(
        f"{base}/app/scans/{scan_id}/issues?sort=priority_desc", wait_until="networkidle"
    )
    await assert_recommended()
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")

    priority = issues.get_by_role("columnheader", name="Priority")
    await priority.get_by_role("button").click()
    await page.wait_for_url("**sort=score_desc*")
    await playwright_async.expect(priority).to_have_attribute("aria-sort", "descending")
    await playwright_async.expect(group_headers).to_have_count(0)
    await playwright_async.expect(
        page.get_by_role("status").filter(has_text="Sorted by Priority, highest first")
    ).to_be_visible()
    # Flat, and "Does not apply" is not a low priority: it trails in both
    # directions.
    for direction in ("desc", "asc"):
        # Row header, Type, Found by, WCAG, then Priority.
        cells = await issues.locator("tbody tr > td:nth-child(5)").all_inner_texts()
        flags = [cell.strip() == "Does not apply" for cell in cells]
        assert flags == sorted(flags), (direction, cells)
        if direction == "desc":
            await priority.get_by_role("button").click()
            await page.wait_for_url("**sort=score_asc*")

    await back.click()
    await page.wait_for_url(re.compile(r"/issues$"))
    await assert_recommended()
    # The pressed button is gone; focus lands on the table it reordered.
    await playwright_async.expect(page.get_by_role("region", name="Issues table")).to_be_focused()


async def test_issue_table_finding_types_help_text_and_middle_alignment(
    live_server: tuple[str, int],
    new_page: Any,
    choose_filter: Any,
) -> None:
    """WCAG, Click-Through and Alt Text rows share one table, and say which is which.

    The DOM-engine and image-evidence views used to be buttons at the bottom
    of the report. Their rows were already in this table; the Finding type
    column and filter tell them apart, and each detailed view is linked from
    the filter it belongs to. The review-lane words carry their meaning where
    they are read, and every cell in a row is vertically centred.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    payload = await (await page.request.get(f"{base}/api/scans/{scan_id}/issues")).json()
    template = payload["rows"][0]
    rows = [
        {
            **template,
            "issue_key": key,
            "title": title,
            "review_lane": lane,
            "pipeline": pipeline,
            "finding_types": types,
            "occurrence_count": 9,
            "click_through_occurrence_count": clicks,
        }
        for key, title, lane, pipeline, types, clicks in [
            ("axe:a", "Load-state rule failure", "likely_barrier", "axe", ["wcag"], 0),
            (
                "axe:b",
                "Contrast inside an opened menu and on load",
                "likely_barrier",
                "axe",
                ["wcag", "click_through"],
                4,
            ),
            ("axe:c", "Only behind a dialog", "likely_barrier", "axe", ["click_through"], 9),
            ("image:d", "Image of text needs review", "expert_review", "image", ["alt_text"], 0),
            ("image:e", "Adequate alternative", "informational", "image", ["alt_text"], 0),
        ]
    ]
    counts = {"wcag": 2, "click_through": 2, "alt_text": 2}
    lanes = {"likely_barrier": 3, "expert_review": 1, "informational": 1}

    async def issues(route: Any) -> None:
        wanted = parse_qs(urlparse(route.request.url).query).get("finding_type", [""])[0]
        shown = [row for row in rows if not wanted or wanted in row["finding_types"]]
        await route.fulfill(
            json={
                **payload,
                "rows": shown,
                "total_unfiltered": len(rows),
                "finding_type_counts": counts,
                "review_lane_counts": lanes,
            }
        )

    await page.route(f"**/api/scans/{scan_id}/issues*", issues)
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    table = page.get_by_role("table", name="Accessibility issues")
    headers = await table.locator("thead th").all_inner_texts()
    names = [re.sub(r"\s+", " ", text).strip() for text in headers]
    # The Finding type column reads "Found by" ("finding" is not an interface word).
    assert names[:4] == ["Issue", "Type", "Found by", "WCAG"], names

    def row(title: str) -> Any:
        return table.locator("tbody tr").filter(
            has=page.get_by_role("rowheader").filter(has_text=title)
        )

    finding_type = "td:nth-child(3)"
    assert (
        await row("Load-state rule failure").locator(finding_type).inner_text()
    ).strip() == "WCAG"
    # Both tags, and nothing else: no count beside the Click-Through tag.
    mixed = row("Contrast inside an opened menu")
    assert re.sub(r"\s+", " ", await mixed.locator(finding_type).inner_text()).strip() == (
        "WCAG Click-Through"
    )
    assert (await row("Only behind a dialog").locator(finding_type).inner_text()).strip() == (
        "Click-Through"
    )
    assert (await row("Adequate alternative").locator(finding_type).inner_text()).strip() == (
        "Alt Text"
    )

    # No row-group header rows split the types; the live status counts each.
    await playwright_async.expect(table.locator("th[scope='rowgroup']")).to_have_count(0)
    await playwright_async.expect(
        page.get_by_role("status").filter(has_text="issues shown")
    ).to_contain_text("Barrier")

    # The glossary defines both sets of words, closed until asked for, under
    # real headings, each term drawn as the chip the table uses.
    glossary = page.get_by_role(
        "button", name="What Barrier, Needs review and the other labels mean", exact=True
    )
    # The glossary's terms, not the summary line's, which are terms too.
    definitions = page.get_by_role("term").filter(
        has_text=re.compile(r"^(Barrier|Needs review|Informational|WCAG|Click-Through|Alt Text)$")
    )
    await playwright_async.expect(definitions.first).to_be_hidden()
    await glossary.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(definitions).to_have_text(
        ["Barrier", "Needs review", "Informational", "WCAG", "Click-Through", "Alt Text"]
    )
    for heading in ("Type: how sure the evidence is", "Found by: which group of checks found it"):
        await playwright_async.expect(
            page.get_by_role("heading", name=heading, level=3)
        ).to_be_visible()
    meanings = page.get_by_role("definition")
    for meaning in (
        "A check failed a fixed rule",
        "A person must confirm it",
        "not a problem to fix",
    ):
        await playwright_async.expect(meanings.filter(has_text=meaning)).to_be_visible()

    # Every cell of a data row is vertically centred.
    alignments = await table.evaluate(
        """t => [...t.querySelectorAll('tbody tr')]
            .flatMap(tr => [...tr.children].map(c => getComputedStyle(c).verticalAlign))"""
    )
    assert alignments and set(alignments) == {"middle"}, set(alignments)
    widths = await page.get_by_role("region", name="Issues table").evaluate(
        "el => ({scroll: el.scrollWidth, client: el.clientWidth})"
    )
    assert widths["scroll"] <= widths["client"], widths
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # The filter narrows to the type, counts a mixed row under both, and
    # offers the detailed view the old bottom-of-report button led to.
    await choose_filter(page, "Found by", "click_through")
    await page.wait_for_url("**finding_type=click_through*")
    # The URL changes before the filtered response lands, so wait for the rows.
    issue_rows = table.locator("tbody th[scope='row']")
    await playwright_async.expect(issue_rows).to_have_count(2)
    shown = await issue_rows.all_inner_texts()
    assert [text.split(",")[0].strip() for text in shown] == [
        "Contrast inside an opened menu and on load",
        "Only behind a dialog",
    ], shown
    wcag_view = page.get_by_role("link", name="Rule check issues by WCAG criterion")
    await playwright_async.expect(wcag_view).to_have_attribute("href", f"/app/scans/{scan_id}/a11y")
    await choose_filter(page, "Found by", "alt_text")
    await page.wait_for_url("**finding_type=alt_text*")
    await playwright_async.expect(
        page.get_by_role("link", name=re.compile(r"^Images \(\d+\)$"))
    ).to_have_attribute("href", f"/app/scans/{scan_id}/findings")
    # The bottom of the report no longer carries an Expert tools section.
    await playwright_async.expect(
        page.locator("summary").filter(has_text="Expert tools and scan details")
    ).to_have_count(0)
    await playwright_async.expect(page.get_by_role("link", name="DOM engines")).to_have_count(0)
    await playwright_async.expect(
        page.get_by_role("link", name=re.compile(r"^Image evidence"))
    ).to_have_count(0)
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


async def test_pager_arrows_are_named_and_look_unavailable_at_either_end(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Previous and Next are arrows with names, grayed out where they do nothing.

    The Previous button used to look as pressable on page 1 as anywhere else:
    it was ``aria-disabled`` but styled like an active button. It stays
    ``aria-disabled`` (a native ``disabled`` drops keyboard focus), and now
    also looks unavailable.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    payload = await (await page.request.get(f"{base}/api/scans/{scan_id}/issues")).json()
    template = payload["rows"][0]
    rows = [{**template, "issue_key": f"k{n}", "title": f"Issue {n:02d}"} for n in range(12)]

    async def issues(route: Any) -> None:
        await route.fulfill(json={**payload, "rows": rows, "total_unfiltered": len(rows)})

    await page.route(f"**/api/scans/{scan_id}/issues*", issues)
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    pager = page.get_by_role("navigation", name="Issues: page controls")
    previous = pager.get_by_role("button", name="Previous page of issues", exact=True)
    next_page = pager.get_by_role("button", name="Next page of issues", exact=True)

    async def look(button: Any) -> dict[str, Any]:
        return await button.evaluate(
            """b => ({text: b.innerText.trim(), opacity: getComputedStyle(b).opacity,
                      cursor: getComputedStyle(b).cursor,
                      w: b.getBoundingClientRect().width, h: b.getBoundingClientRect().height})"""
        )

    await playwright_async.expect(previous).to_have_attribute("aria-disabled", "true")
    await playwright_async.expect(next_page).to_have_attribute("aria-disabled", "false")
    first, onward = await look(previous), await look(next_page)
    # Arrows only: the name is the accessible name, not visible text.
    assert first["text"] == "" and onward["text"] == "", (first, onward)
    assert first["w"] >= 44 and first["h"] >= 44, first
    assert float(first["opacity"]) < 1 and first["cursor"] == "not-allowed", first
    assert float(onward["opacity"]) == 1 and onward["cursor"] != "not-allowed", onward

    await next_page.focus()
    await page.keyboard.press("Enter")
    await page.wait_for_url("**page=2*")
    await playwright_async.expect(next_page).to_have_attribute("aria-disabled", "true")
    # Focus stays on the arrow at the end instead of falling to the page.
    await playwright_async.expect(next_page).to_be_focused()
    await page.keyboard.press("Enter")
    assert "page=2" in page.url
    assert float((await look(next_page))["opacity"]) < 1
    assert float((await look(previous))["opacity"]) == 1
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


async def _breadcrumb(page: Any) -> list[dict[str, Any]]:
    """The one visible breadcrumb trail, item by item, as the DOM has it.

    Asserts the WAI-ARIA breadcrumb structure on the way: exactly one visible
    ``nav`` named "Breadcrumb" wrapping an ordered list, and no second trail
    anywhere on the page.
    """
    crumb = page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
    await playwright_async.expect(crumb).to_have_count(1)
    # The second trail that hung under the tabs, named "Where you are in …".
    await playwright_async.expect(
        page.get_by_role("navigation", name=re.compile("^Where you are"))
    ).to_have_count(0)
    return await crumb.evaluate(
        r"""nav => {
            const list = nav.firstElementChild;
            if (list?.tagName !== "OL") throw new Error("breadcrumb is not an ordered list");
            return [...list.children].map(li => {
                const link = li.querySelector("a");
                const current = li.querySelector("[aria-current]");
                return {
                    tag: li.tagName,
                    text: li.innerText.replace(/\s+/g, " ").trim(),
                    link: link ? link.getAttribute("href") : null,
                    current: current ? current.getAttribute("aria-current") : null,
                    currentTag: current ? current.tagName : null,
                    background: current ? getComputedStyle(current).backgroundColor : null,
                };
            });
        }"""
    )


def _assert_current_is_plain_text(items: list[dict[str, Any]]) -> None:
    """Only the last crumb is current, and it is text, not a link or a chip."""
    *earlier, last = items
    assert all(item["tag"] == "LI" for item in items), items
    assert all(item["link"] and item["current"] is None for item in earlier), items
    assert last["link"] is None, last
    assert last["current"] == "page" and last["currentTag"] == "SPAN", last
    assert last["background"] in {"rgba(0, 0, 0, 0)", "transparent"}, last


async def test_report_breadcrumb_ends_at_the_report_on_its_views(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """``Reports > example.com [scan N]``, and nothing after it, on Issues and Compare reports.

    The lit tab says which view; "Issues" as a crumb as well was the third
    time the word appeared on one screen.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    for suffix in ("/issues", "/compare"):
        await page.goto(f"{base}/app/scans/{scan_id}{suffix}", wait_until="networkidle")
        items = await _breadcrumb(page)
        assert [item["text"] for item in items] == ["Reports", f"example.com Report #{scan_id}"], (
            items
        )
        assert items[0]["link"] == "/app/scans", items
        _assert_current_is_plain_text(items)
    # The tabs are the report's two views; Overview is gone.
    tabs = page.get_by_role("navigation", name="Report views").get_by_role("link")
    await playwright_async.expect(tabs).to_have_text(["Issues", "Compare reports"])


async def test_issue_evidence_trail_names_the_issue(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """The trail's last crumb is the issue itself, under the report.

    "Issue evidence" told the reader what kind of page they were on, which
    they could already see; which issue they were reading was the part only
    the trail could carry once the title scrolled out of view. The issue
    sits inside the report, so there are no report tabs here, and the
    report crumb is the way back to the list.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    row = (await response.json())["rows"][0]
    await page.goto(
        f"{base}/app/scans/{scan_id}/issues/{quote(row['issue_key'], safe='')}",
        wait_until="networkidle",
    )
    await playwright_async.expect(
        page.get_by_role("heading", name=row["title"], level=1)
    ).to_be_visible()
    items = await _breadcrumb(page)
    # A deep link lands with the whole trail: the path alone proves the
    # issue sits in this report, and "Issues" is never a crumb of its own.
    assert [item["text"] for item in items] == [
        "Reports",
        f"example.com Report #{scan_id}",
        row["title"],
    ], items
    _assert_current_is_plain_text(items)
    await playwright_async.expect(
        page.get_by_role("navigation", name="Report views")
    ).to_have_count(0)
    crumb = page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
    await crumb.get_by_role("link", name=f"example.com Report #{scan_id}").click()
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")


async def test_inspector_has_one_full_trail_and_no_report_tabs(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """Issues → an issue's pages → the inspector: one trail naming every step.

    There used to be two: the topbar stopped at "Issues" and a second trail
    under the tabs carried the rest. The topbar now shows the whole path, and
    the report tabs are gone from a page that is inside the report rather
    than one of its views.

    Each crumb names the specific thing, not the kind of view: the page list
    by its size and the inspector by the page's own title. "Pages" and "Page
    inspector" read the same for every issue and every page.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    row = (await response.json())["rows"][0]
    await page.goto(f"{base}/app/scans/{scan_id}/issues?type={row['review_lane']}")
    table = page.get_by_role("table", name="Accessibility issues")
    await table.get_by_role("link", name=f"with {row['title']}", exact=False).click()
    await page.wait_for_url("**/pages?**")
    await playwright_async.expect(
        page.get_by_role("navigation", name="Report views")
    ).to_have_count(0)
    inspector = page.get_by_role(
        "link", name="opens the saved copy with this issue marked", exact=False
    )
    await inspector.first.click()
    await page.wait_for_url("**/inspect?**")
    page_id = int(re.search(r"/pages/(\d+)/inspect", page.url)[1])
    inspected = (
        await (await page.request.get(f"{base}/api/scans/{scan_id}/pages/{page_id}")).json()
    )["page"]
    page_name = inspected["title"] or inspected["url_normalized"].removeprefix("http://")
    affected = f"{row['page_count']} affected page{'' if row['page_count'] == 1 else 's'}"
    await playwright_async.expect(
        page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
    ).to_contain_text(page_name)
    items = await _breadcrumb(page)
    assert [item["text"] for item in items] == [
        "Reports",
        f"example.com Report #{scan_id}",
        row["title"],
        affected,
        page_name,
    ], items
    _assert_current_is_plain_text(items)
    # The report crumb goes back to the table the reader left, filter kept.
    assert items[1]["link"] == f"/app/scans/{scan_id}/issues?type={row['review_lane']}", items
    await playwright_async.expect(page.get_by_role("heading", level=1)).to_have_count(1)
    await playwright_async.expect(
        page.get_by_role("navigation", name="Report views")
    ).to_have_count(0)


async def test_report_crumb_returns_to_the_searched_list(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """The report crumb goes back to the list as the reviewer left it.

    It points at the link the issue was opened from, so a search typed into
    the list survives the round trip through an issue.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    row = (await response.json())["rows"][0]
    query = row["title"].split()[0]
    await page.goto(f"{base}/app/scans/{scan_id}/issues?q={quote(query)}", wait_until="networkidle")
    table = page.get_by_role("table", name="Accessibility issues")
    await table.get_by_role("rowheader").get_by_role("link", name=row["title"]).first.click()
    await page.wait_for_url(re.compile(rf"/app/scans/{scan_id}/issues/[^?]+\?"))
    crumb = page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
    back = crumb.get_by_role("link", name=f"example.com Report #{scan_id}")
    await playwright_async.expect(back).to_be_visible()
    await back.click()
    await page.wait_for_url(re.compile(rf"/app/scans/{scan_id}/issues\?q="))
    assert parse_qs(urlparse(page.url).query)["q"] == [query]


async def test_first_report_has_no_compare_tab(live_server: tuple[str, int], new_page: Any) -> None:
    """A site's first report has nothing to compare with, so no tab offers it.

    A saved link to its Compare reports page still opens, with its tabs.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_role("heading", name="Issues", exact=True, level=1)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("navigation", name="Report views")
    ).to_have_count(0)
    await page.goto(f"{base}/app/scans/{scan_id}/compare", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_role("heading", name="Nothing earlier to compare with")
    ).to_be_visible()
    tabs = page.get_by_role("navigation", name="Report views").get_by_role("link")
    await playwright_async.expect(tabs).to_have_text(["Issues", "Compare reports"])


async def test_report_opens_keyboard_only_in_reading_order(
    seeded_db: tuple[Path, Path, int], live_server: tuple[str, int], new_page: Any
) -> None:
    """Tab from the page top: breadcrumb, tabs, search, filters, then the table.

    Every stop shows a focus indicator, and each group is reached in the
    order it reads on screen.
    """
    # Compare reports is a tab only once the site has an earlier report.
    with sqlite3.connect(seeded_db[0]) as conn:
        conn.execute(
            "INSERT INTO scans(seed_url,status,started_at,config_json) "
            "VALUES('http://example.com/','completed','2000-01-01 00:00:00','{}')"
        )
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")
    # The route focuses <main> on arrival; start from the top of the
    # document instead, the skip link, so the whole order is walked.
    await page.get_by_role("link", name="Skip to main content").focus()
    stops: list[dict[str, Any]] = []
    for _ in range(40):
        await page.keyboard.press("Tab")
        stop = await page.evaluate(
            r"""() => {
                const el = document.activeElement;
                const style = getComputedStyle(el);
                const label = el.labels?.[0]?.innerText
                    ?? el.getAttribute("aria-label")
                    ?? el.innerText;
                const landmark = el.closest("nav[aria-label]")?.getAttribute("aria-label")
                    ?? (el.closest("table") ? "table" : null)
                    ?? (el.getAttribute("role") === "region" ? "table-region" : null);
                return {
                    name: (label || "").replace(/\s+/g, " ").trim(),
                    tag: el.tagName,
                    role: el.getAttribute("role"),
                    group: landmark,
                    visible: style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0
                        || style.boxShadow !== "none",
                };
            }"""
        )
        stops.append(stop)
        if stop["group"] == "table":
            break
    names = [stop["name"] for stop in stops]

    def first(predicate: Any) -> int:
        found = next((i for i, stop in enumerate(stops) if predicate(stop)), None)
        assert found is not None, stops
        return found

    order = [
        first(lambda s: s["group"] == "Breadcrumb" and s["name"] == "Reports"),
        first(lambda s: s["group"] == "Report views" and s["name"] == "Issues"),
        first(lambda s: s["group"] == "Report views" and s["name"] == "Compare reports"),
        first(lambda s: s["name"] == "Search issues"),
        # One Filter menu holds Level, Type and Found by.
        first(lambda s: s["tag"] == "BUTTON" and s["name"] == "Filter"),
        first(lambda s: s["group"] == "table-region"),
        first(lambda s: s["group"] == "table"),
    ]
    assert order == sorted(order), names
    # The current crumb is text, so it is not a tab stop.
    assert f"example.com Report #{scan_id}" not in names, names
    missing = [stop for stop in stops if not stop["visible"]]
    assert not missing, missing


async def test_issue_evidence_page_link_offers_the_way_back(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Page evidence reached from an issue names the issue in the trail, and returns.

    The desktop app has no browser chrome, so the topbar trail is the only way
    back out of a drill-down. Before this, the page's evidence was a dead end:
    the trail read ``Reports > site > Page evidence`` and nothing on the page
    led back to the list the reviewer had been working through. The issue's
    pages table no longer links Page details itself; the way there is the
    page's screenshots, which do.
    """
    db_path, blob_dir, _ = seeded_db
    base, scan_id = live_server
    add_screenshot_finding(db_path, blob_dir, scan_id)
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    row = next(r for r in (await response.json())["rows"] if r["issue_key"] == SCREENSHOT_ISSUE_KEY)
    issue_path = f"/app/scans/{scan_id}/issues/{quote(row['issue_key'], safe='')}"
    await page.goto(f"{base}{issue_path}", wait_until="networkidle")
    await page.get_by_role("link", name=re.compile(r"^1 screenshot of this issue on ")).click()
    await page.wait_for_url(re.compile(r"/pages/\d+/screenshots"))
    await page.get_by_role("link", name="Page details", exact=True).click()
    await page.wait_for_url(re.compile(rf"/app/scans/{scan_id}/pages/\d+\?"))
    crumb = page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
    back = crumb.get_by_role("link", name=row["title"], exact=True)
    await playwright_async.expect(back).to_be_visible()
    await back.click()
    await page.wait_for_url(f"**{issue_path}")


@pytest.mark.parametrize("width", [1280, 320])
async def test_actual_comparison_links_reach_the_issue(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    width: int,
    new_page: Any,
) -> None:
    """Follow the real service's issue URL from Compare reports, and the way back."""
    db_path, _, old = seeded_db
    base, _ = live_server
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE scans SET started_at='2026-09-01 12:00:00' WHERE id=?", (old,))
        new = int(
            conn.execute(
                "INSERT INTO scans(seed_url,status,started_at,config_json,"
                "page_count,alfa_pages_scanned) "
                "VALUES('http://example.com/','completed','2026-09-02 12:00:00','{}',1,1)"
            ).lastrowid
            or 0
        )
        new_page_id = int(
            conn.execute(
                "INSERT INTO pages(scan_id,url_normalized,status_code,render_mode,title) "
                "VALUES(?,'http://example.com/',200,'js','Home')",
                (new,),
            ).lastrowid
            or 0
        )
        old_page_id = conn.execute(
            "SELECT id FROM pages WHERE scan_id=? ORDER BY id", (old,)
        ).fetchone()[0]
        for report, page_id, outcome in [
            (old, old_page_id, "cant_tell"),
            (new, new_page_id, "failed"),
        ]:
            conn.execute(
                "INSERT INTO page_a11y_findings(scan_id,page_id,pipeline,rule_id,help,"
                "target_selector,target_hash,engine_outcome,engine_evidence_json,status) "
                "VALUES(?,?,'alfa','sia-r69','Text contrast','#text',?,?, '{}','new')",
                (report, page_id, f"target-{report}", outcome),
            )
        conn.commit()
    page = await new_page(viewport={"width": width, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{new}/comparison?pipeline=alfa")
    assert response.ok
    payload = await response.json()
    assert payload["baseline"]["id"] == old
    row = payload["rows"][0]
    assert row["category"] == "changed"
    target = row["after"]["evidence"][0]["url"]
    assert "#finding-" in target
    await page.goto(f"{base}/app/scans/{new}/compare", wait_until="networkidle")
    coverage = page.get_by_role("button", name=re.compile(r"^What was checked in each report"))
    await coverage.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(
        page.get_by_role("table", name="What each check covered")
    ).to_be_visible()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
    # The issue's title opens it in the later report, carrying the way back
    # to this comparison for the topbar trail.
    issue_url = row["after"]["issues"][0]["url"]
    link = page.locator(f'a[href^="/app{issue_url}?"]')
    await link.focus()
    await page.keyboard.press("Enter")
    await page.wait_for_url(re.compile(rf"{re.escape(base)}/app{re.escape(issue_url)}\?"))
    # Issue evidence sits inside the report, so it has no report tabs; the
    # one trail carries the way back to the comparison instead.
    await playwright_async.expect(
        page.get_by_role("navigation", name="Report views")
    ).to_have_count(0)
    await playwright_async.expect(
        page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
    ).to_contain_text("Compare reports")
    items = await _breadcrumb(page)
    assert [item["text"] for item in items][:3] == [
        "Reports",
        f"example.com Report #{new}",
        "Compare reports",
    ], items
    assert items[2]["link"] and items[2]["link"].startswith(f"/app/scans/{new}/compare"), items
    _assert_current_is_plain_text(items)


async def test_crumbs_stay_on_one_line_and_cut_the_longest_first(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Each page view names its page, on one line, whole whenever it fits.

    The trail never wraps or scrolls. With room to spare nothing is cut. When
    the line is full, only the longest crumbs are cut, all to the same width,
    and every shorter crumb (the report name, "Reports") keeps every
    character: cutting a short crumb removes most of what it says. A cut
    crumb keeps its whole name in the DOM for a screen reader and in
    ``title`` for a hover.
    """
    db_path, _, _ = seeded_db
    base, scan_id = live_server
    long_title = "Editing submission by … for LSA CodeGrade Test in LSA LTI Test Course - CodeGrade"
    conn = sqlite3.connect(db_path)
    try:
        page_id = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()[0]
        conn.execute("UPDATE pages SET title = ? WHERE id = ?", (long_title, page_id))
        conn.commit()
    finally:
        conn.close()
    response = await (await new_page()).request.get(f"{base}/api/scans/{scan_id}/issues")
    row = (await response.json())["rows"][0]
    issue_path = f"/scans/{scan_id}/issues/{quote(row['issue_key'], safe='')}"
    measure = """nav => {
        const list = nav.firstElementChild;
        const crumbs = [...list.children].map(li => li.querySelector("a, [aria-current]"));
        return {
            overflows: list.scrollWidth > list.clientWidth + 1,
            rows: new Set(
                [...list.children].map(li => Math.round(li.getBoundingClientRect().top))
            ).size,
            texts: crumbs.map(el => {
                const text = el.querySelector("[data-crumb-text]");
                return text
                    ? {
                          natural: text.scrollWidth,
                          shown: text.getBoundingClientRect().width,
                          cut: text.scrollWidth > text.clientWidth + 1,
                      }
                    : { natural: el.scrollWidth, shown: el.clientWidth, cut: false };
            }),
            titles: crumbs.map(el => el.getAttribute("title")),
            text: crumbs.map(el => el.textContent),
        };
    }"""
    for path, expected in (
        (f"/scans/{scan_id}/pages/{page_id}/inspect", long_title),
        (f"/scans/{scan_id}/pages/{page_id}", f"Page details for {long_title}"),
    ):
        # The issue as context puts a second long crumb in the trail.
        url = f"{base}/app{path}?context=Issue&contextTo={quote(issue_path, safe='')}"
        for width, fits in ((1920, True), (1024, False)):
            page = await new_page(viewport={"width": width, "height": 900})
            try:
                await page.goto(url, wait_until="networkidle")
                crumb = page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
                await playwright_async.expect(crumb).to_contain_text(expected)
                await playwright_async.expect(crumb).to_contain_text(row["title"][:10])
                state = await crumb.evaluate(measure)
                assert state["rows"] == 1, (width, state)
                assert not state["overflows"], (width, state)
                assert state["text"][-1] == expected, state
                assert state["titles"][-1] == expected, state
                texts = state["texts"]
                cut = [t for t in texts if t["cut"]]
                if fits:
                    assert not cut, state
                    continue
                assert texts[-1]["cut"], state
                assert not texts[0]["cut"] and not texts[1]["cut"], state  # Reports, report
                widths = [t["shown"] for t in cut]
                assert max(widths) - min(widths) <= 2, state  # cut to one shared width
                assert all(t["natural"] <= min(widths) + 2 for t in texts if not t["cut"]), state
            finally:
                await page.context.close()
