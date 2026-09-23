"""Keyboard and accessibility coverage for report review and comparison."""

from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import pytest

from .test_accessibility_axe import _render_violations, _run_axe

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")


@pytest.mark.parametrize("width", [1280, 320])
async def test_report_links_and_review_lanes(
    live_server: tuple[str, int], width: int, new_page: Any
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
    await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_text("Evidence for expert review, not a conformance verdict.", exact=True)
    ).to_have_count(0)
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
    issues = page.get_by_role("table", name="Accessibility issue groups")
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
    await page.get_by_label("Level", exact=True).select_option("A")
    await page.wait_for_url("**q=Decorative*")
    await playwright_async.expect(
        issues.get_by_role("rowheader").get_by_role(
            "link", name="Decorative image note", exact=False
        )
    ).to_be_visible()
    url_params = parse_qs(urlparse(page.url).query)
    assert url_params["q"] == ["Decorative"]
    assert url_params["conformance"] == ["A"]
    # "Type" filters on the review lane the Type column shows. It is
    # a URL parameter like the others, so it narrows the table to the
    # one lane, reads the way the cells do, and clears with the rest.
    await page.get_by_role("button", name="Clear filters").click()
    await page.wait_for_url(re.compile(r"/issues$"))
    await page.get_by_label("Type", exact=True).select_option("expert_review")
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


def _comparison(scan_id: int) -> dict[str, Any]:
    before = {
        "occurrences": 2,
        "pages": 1,
        "statuses": {"new": 2},
        "outcomes": {"cant_tell": 2},
        "issues": [
            {
                "label": "Earlier contrast issue",
                "url": "/app/scans/99/issues/alfa%3Ar69%3Acant_tell",
            }
        ],
        "evidence": [
            {"label": "Earlier contrast evidence", "url": "/app/scans/99/pages/1#finding-1"}
        ],
    }
    after = {
        **before,
        "outcomes": {"failed": 2},
        "issues": [
            {
                "label": "Current contrast issue",
                "url": f"/app/scans/{scan_id}/issues/alfa%3Ar69%3Afailed",
            }
        ],
        "evidence": [
            {
                "label": "Current contrast evidence",
                "url": f"/app/scans/{scan_id}/pages/1#finding-77",
            }
        ],
    }
    return {
        "current": {"id": scan_id, "seed_url": "http://example.com/", "started_at": "2026-09-02"},
        "baseline": {"id": 99, "seed_url": "http://example.com/", "started_at": "2026-09-01"},
        "counts": {
            "new": 0,
            "still_detected": 0,
            "changed": 51,
            "no_longer_detected": 0,
            "cannot_compare": 0,
        },
        "pipeline_counts": {"alfa": 51},
        "coverage": [],
        "limitations": ["Historical report coverage is incomplete."],
        "rows": [
            {
                "key": "alfa:r69",
                "pipeline": "alfa",
                "title": "Text contrast",
                "category": "changed",
                "before": before,
                "after": after,
                "limitations": ["Some engine evidence was truncated."],
            }
        ],
        "total": 51,
        "page": 1,
        "page_size": 50,
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
async def test_verify_changes_keyboard_filters_links_and_axe(
    live_server: tuple[str, int], width: int, new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page(viewport={"width": width, "height": 900})
    requests: list[dict[str, list[str]]] = []

    async def comparison(route: Any) -> None:
        query = parse_qs(urlparse(route.request.url).query)
        requests.append(query)
        payload = _comparison(scan_id)
        payload["page"] = int(query.get("page", ["1"])[0])
        await asyncio.sleep(0.05)
        await route.fulfill(json=payload)

    await page.route(f"**/api/scans/{scan_id}/comparison*", comparison)
    await page.route(
        f"**/api/scans/{scan_id}/pages/1",
        lambda route: route.fulfill(json=_page_evidence(scan_id)),
    )
    await page.goto(f"{base}/app/scans/{scan_id}/diff", wait_until="networkidle")
    await playwright_async.expect(
        page.get_by_role("heading", name="Verify changes", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("navigation", name="Report workspace").get_by_role(
            "link", name="Verify changes"
        )
    ).to_have_attribute("aria-current", "page")
    await playwright_async.expect(
        page.get_by_role("heading", name="How to read this comparison", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("Check results: Cannot tell (manual review): 2", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("region", name="Reports being compared")
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("The finding and page counts are unchanged", exact=False)
    ).to_be_visible()
    coverage = page.locator("summary").filter(has_text="Comparison coverage")
    await coverage.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(
        page.get_by_text("Historical report coverage is incomplete.", exact=True)
    ).to_be_visible()
    await page.keyboard.press("Space")
    category = page.get_by_label("Change category")
    await category.focus()
    await page.keyboard.press("c")
    await page.keyboard.press("Enter")
    await playwright_async.expect(category).to_have_value("changed")
    await page.wait_for_function(
        "!document.querySelector('[aria-label=\"Compared issue groups\"]')"
        ".matches('[aria-busy=true]')"
    )
    await playwright_async.expect(category).to_be_focused()
    method = page.get_by_label("Detection method")
    await method.focus()
    await page.keyboard.press("s")
    await page.keyboard.press("Enter")
    await playwright_async.expect(method).to_have_value("alfa")
    next_page = page.get_by_role("button", name="Next page")
    await playwright_async.expect(next_page).to_be_enabled()
    await next_page.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(
        page.get_by_text("51 issue groups · Page 2 of 2", exact=True)
    ).to_be_visible()
    assert requests[-1]["category"] == ["changed"]
    assert requests[-1]["pipeline"] == ["alfa"]
    assert requests[-1]["page"] == ["2"]
    assert requests[-1]["page_size"] == ["50"]
    assert await page.evaluate("document.body.scrollWidth <= innerWidth")
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
    evidence = page.get_by_role("link", name="Current contrast evidence", exact=True)
    evidence_section = (
        page.get_by_role("region", name="Compared issue groups")
        .locator("details")
        .filter(has_text="Current contrast evidence")
    )
    await evidence_section.locator("summary").focus()
    await page.keyboard.press("Enter")
    await evidence.focus()
    await page.keyboard.press("Enter")
    # The link carries ?origin=&back= so the topbar trail can offer the
    # way back to this comparison; the anchor still has to land.
    await page.wait_for_url(re.compile(rf"/app/scans/{scan_id}/pages/1\?[^#]*#finding-77$"))
    await playwright_async.expect(page.locator("#finding-77")).to_be_focused()
    await playwright_async.expect(
        page.get_by_text("Incomplete evidence.", exact=True)
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_text("Text in the first paragraph", exact=False)
    ).to_be_visible()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


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
    status = page.get_by_role("status").filter(has_text="issue groups shown")
    await playwright_async.expect(status).to_contain_text("issue groups shown")
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


async def test_issue_evidence_trail_names_the_issue(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """The trail's last chip is the issue itself, not the name of the view.

    "Issue evidence" told the reader what kind of page they were on, which
    they could already see; which issue they were reading was the part only
    the trail could carry once the title scrolled out of view.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    row = (await response.json())["rows"][0]
    await page.goto(
        f"{base}/app/scans/{scan_id}/issues/{quote(row['issue_key'], safe='')}",
        wait_until="networkidle",
    )
    # The topbar stops at the tab; the issue itself is named under it,
    # in the sub-trail, so the same thing is not said in two places.
    crumb = page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
    await playwright_async.expect(crumb.get_by_text("Issues", exact=True)).to_be_visible()
    await playwright_async.expect(crumb.get_by_text(row["title"], exact=True)).to_have_count(0)
    sub = page.get_by_role("navigation", name="Where you are in Issues")
    await playwright_async.expect(sub.get_by_text(row["title"], exact=True)).to_be_visible()
    # The list is the issue's parent, and the path alone proves it, so a deep
    # link lands with the whole trail rather than a gap. The sub-trail starts
    # at Issues, as a link, so the way back is the first step of the path
    # being read, not only the lit tab above it.
    steps = sub.get_by_role("listitem").filter(has_text=re.compile(r"\S"))
    await playwright_async.expect(steps.first).to_have_text("Issues")
    back = sub.get_by_role("link", name="Issues", exact=True)
    await playwright_async.expect(back).to_have_count(1)
    tab = page.get_by_role("navigation", name="Report workspace").get_by_role(
        "link", name="Issues", exact=True
    )
    await playwright_async.expect(tab).to_have_attribute("aria-current", "page")
    await back.click()
    await page.wait_for_url(f"**/app/scans/{scan_id}/issues")


async def test_sub_trail_issues_link_returns_to_the_filtered_list(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """The sub-trail's Issues link goes back to the list as the reviewer left it.

    The crumb is the link the list was opened from, so a search typed into
    the list survives the round trip through an issue.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    row = (await response.json())["rows"][0]
    query = row["title"].split()[0]
    await page.goto(f"{base}/app/scans/{scan_id}/issues?q={quote(query)}", wait_until="networkidle")
    table = page.get_by_role("table", name="Accessibility issue groups")
    await table.get_by_role("rowheader").get_by_role("link", name=row["title"]).first.click()
    await page.wait_for_url(re.compile(rf"/app/scans/{scan_id}/issues/[^?]+\?"))
    sub = page.get_by_role("navigation", name="Where you are in Issues")
    back = sub.get_by_role("link", name="Issues", exact=True)
    await playwright_async.expect(back).to_be_visible()
    await back.click()
    await page.wait_for_url(re.compile(rf"/app/scans/{scan_id}/issues\?q="))
    assert parse_qs(urlparse(page.url).query)["q"] == [query]


async def test_issue_evidence_page_link_offers_the_way_back(
    live_server: tuple[str, int],
    new_page: Any,
) -> None:
    """Page evidence opened from Issues names Issues in the trail, and returns.

    The desktop app has no browser chrome, so the topbar trail is the only way
    back out of a drill-down. Before this, stored evidence was a dead end: the
    trail read ``Reports > site > Page evidence`` and nothing on the page led
    back to the list the reviewer had been working through.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    row = (await response.json())["rows"][0]
    issue_path = f"/app/scans/{scan_id}/issues/{quote(row['issue_key'], safe='')}"
    await page.goto(f"{base}{issue_path}", wait_until="networkidle")
    evidence = page.get_by_role("link", name="stored evidence").first
    await playwright_async.expect(evidence).to_be_visible()
    await evidence.click()
    await page.wait_for_url(re.compile(rf"/app/scans/{scan_id}/pages/\d+\?"))
    sub = page.get_by_role("navigation", name="Where you are in Issues")
    back = sub.get_by_role("link", name=row["title"], exact=True)
    await playwright_async.expect(back).to_be_visible()
    await back.click()
    await page.wait_for_url(f"**{issue_path}")


@pytest.mark.parametrize("width", [1280, 320])
async def test_actual_comparison_links_reach_stored_finding(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    width: int,
    new_page: Any,
) -> None:
    """Follow the real service's URLs, including its finding identity and hash."""
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
    await page.goto(f"{base}/app/scans/{new}/diff?pipeline=alfa", wait_until="networkidle")
    coverage = page.locator("summary").filter(has_text="Comparison coverage")
    await coverage.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(
        page.get_by_role("table", name="Detection method coverage in the compared reports")
    ).to_be_visible()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
    # Each snapshot keeps its evidence behind an "Example evidence"
    # disclosure, so the link is in the DOM but not yet focusable.
    # Open the one holding this link, by keyboard, before following it.
    # The rendered link adds ?origin=&back= so the evidence page can
    # offer the way back to this comparison; match around that.
    path, _, anchor = target.partition("#")
    link = page.locator(f'a[href^="/app{path}?"][href$="#{anchor}"]')
    await link.locator("xpath=ancestor::details[1]").locator("summary").focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(link).to_be_visible()
    await link.focus()
    await page.keyboard.press("Enter")
    await page.wait_for_url(
        re.compile(rf"{re.escape(base)}/app{re.escape(path)}\?[^#]*#{re.escape(anchor)}$")
    )
    await playwright_async.expect(page.locator(f"#{anchor}")).to_be_focused()
    # …and the trail names it, the only way back with no browser chrome.
    await playwright_async.expect(
        page.get_by_role("navigation", name="Report workspace").get_by_role(
            "link", name="Verify changes", exact=True
        )
    ).to_have_attribute("aria-current", "page")
    await playwright_async.expect(
        page.get_by_role("navigation", name="Where you are in Verify changes")
    ).to_contain_text("Page evidence")


async def test_inspector_trail_names_the_page_it_shows(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """The inspector's step in the trail is the page's heading.

    It reads ``Page inspector: “<page title>”`` after the issue, and it is
    the page's only h1: a screen reader's heading list gets that step, then
    the steps above it as context in words, not the whole trail.
    """
    base, scan_id = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    response = await page.request.get(f"{base}/api/scans/{scan_id}/issues")
    row = (await response.json())["rows"][0]
    await page.goto(
        f"{base}/app/scans/{scan_id}/issues/{quote(row['issue_key'], safe='')}",
        wait_until="networkidle",
    )
    inspect = page.locator("a[href*='/inspect']").first
    await playwright_async.expect(inspect).to_be_visible()
    await inspect.click()
    await page.wait_for_url(re.compile(rf"/app/scans/{scan_id}/pages/\d+/inspect\?"))
    sub = page.get_by_role("navigation", name="Where you are in Issues")
    heading = sub.get_by_role("heading", level=1)
    await playwright_async.expect(page.get_by_role("heading", level=1)).to_have_count(1)
    await playwright_async.expect(heading).to_have_attribute("aria-current", "page")
    await playwright_async.expect(heading).to_contain_text(re.compile(r"^Page inspector: “.+”"))
    await playwright_async.expect(heading).to_contain_text(f", in Issues, {row['title']}")
    for step in ("Issues", row["title"]):
        link = sub.get_by_role("link", name=step, exact=True)
        await playwright_async.expect(link).to_be_visible()
