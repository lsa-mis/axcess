"""Keyboard and accessibility coverage for report review and comparison."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = pytest.mark.ui
playwright_async = pytest.importorskip("playwright.async_api")


@pytest.mark.asyncio
@pytest.mark.parametrize("width", [1280, 320])
async def test_report_links_and_review_lanes(live_server: tuple[str, int], width: int) -> None:
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": width, "height": 900})
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
                shown = [
                    row for row in rows if query.get("q", [""])[0].lower() in row["title"].lower()
                ]
                await asyncio.sleep(0.05)
                await route.fulfill(json={**payload, "rows": shown})

            await page.route(f"**/api/scans/{scan_id}/issues*", issues)
            await page.goto(f"{base}/app/scans/{scan_id}", wait_until="networkidle")
            await playwright_async.expect(
                page.get_by_text(
                    "Evidence for expert review, not a conformance verdict.", exact=True
                )
            ).to_have_count(0)
            crumb = page.get_by_role("navigation", name="Breadcrumb").filter(visible=True)
            reports = crumb.get_by_role("link", name="Reports", exact=True)
            await reports.focus()
            assert (
                await reports.evaluate("el => getComputedStyle(el).textDecorationLine")
                == "underline"
            )
            assert await reports.evaluate("el => el.getBoundingClientRect().height") >= 44
            assert await reports.evaluate("el => getComputedStyle(el).boxShadow") != "none"
            await page.keyboard.press("Enter")
            await page.wait_for_url("**/app/scans")
            await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
            await playwright_async.expect(
                page.get_by_role("link", name="Named control failure", exact=False)
            ).to_be_visible()
            review = page.locator("summary").filter(has_text="Needs manual review (1)")
            await playwright_async.expect(
                page.get_by_role("link", name="Contrast calculation needs review", exact=False)
            ).to_be_hidden()
            await review.focus()
            await page.keyboard.press("Enter")
            await playwright_async.expect(
                page.get_by_role("link", name="Contrast calculation needs review", exact=False)
            ).to_be_visible()
            await page.keyboard.press("Space")
            await playwright_async.expect(
                page.get_by_role("link", name="Contrast calculation needs review", exact=False)
            ).to_be_hidden()
            search = page.get_by_label("Search issues")
            await search.focus()
            await page.keyboard.type("Contrast")
            await playwright_async.expect(search).to_have_value("Contrast")
            await playwright_async.expect(
                page.get_by_role("link", name="Contrast calculation needs review", exact=False)
            ).to_be_visible()
            await playwright_async.expect(search).to_be_focused()
            # A pending search must preserve a filter changed during its debounce.
            await search.fill("Decorative")
            await page.get_by_label("WCAG level", exact=True).select_option("A")
            await playwright_async.expect(
                page.get_by_role("link", name="Decorative image note", exact=False)
            ).to_be_visible()
            url_params = parse_qs(urlparse(page.url).query)
            assert url_params["q"] == ["Decorative"]
            assert url_params["conformance"] == ["A"]
            assert await page.evaluate("document.body.scrollWidth <= innerWidth")
            violations = await _run_axe(page)
            assert not violations, _render_violations(violations)
        finally:
            await browser.close()


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


@pytest.mark.asyncio
@pytest.mark.parametrize("width", [1280, 320])
async def test_verify_changes_keyboard_filters_links_and_axe(
    live_server: tuple[str, int], width: int
) -> None:
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": width, "height": 900})
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
            await page.wait_for_url(f"**/app/scans/{scan_id}/pages/1#finding-77")
            await playwright_async.expect(page.locator("#finding-77")).to_be_focused()
            await playwright_async.expect(
                page.get_by_text("Incomplete evidence.", exact=True)
            ).to_be_visible()
            await playwright_async.expect(
                page.get_by_text("Text in the first paragraph", exact=False)
            ).to_be_visible()
            violations = await _run_axe(page)
            assert not violations, _render_violations(violations)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_finding_anchor_waits_for_scan_metadata(live_server: tuple[str, int]) -> None:
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            scan = await (await page.request.get(f"{base}/api/scans/{scan_id}")).json()

            async def metadata(route: Any) -> None:
                await asyncio.sleep(0.2)
                await route.fulfill(json=scan)

            await page.route(f"**/api/scans/{scan_id}", metadata)
            await page.route(
                f"**/api/scans/{scan_id}/pages/1",
                lambda route: route.fulfill(json=_page_evidence(scan_id)),
            )
            await page.goto(
                f"{base}/app/scans/{scan_id}/pages/1#finding-77", wait_until="networkidle"
            )
            await playwright_async.expect(page.locator("#finding-77")).to_be_focused()
        finally:
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("width", [1280, 320])
async def test_actual_comparison_links_reach_stored_finding(
    seeded_db: tuple[Path, Path, int],
    live_server: tuple[str, int],
    width: int,
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
        new_page = int(
            conn.execute(
                "INSERT INTO pages(scan_id,url_normalized,status_code,render_mode,title) "
                "VALUES(?,'http://example.com/',200,'js','Home')",
                (new,),
            ).lastrowid
            or 0
        )
        old_page = conn.execute(
            "SELECT id FROM pages WHERE scan_id=? ORDER BY id", (old,)
        ).fetchone()[0]
        for report, page_id, outcome in [(old, old_page, "cant_tell"), (new, new_page, "failed")]:
            conn.execute(
                "INSERT INTO page_a11y_findings(scan_id,page_id,pipeline,rule_id,help,"
                "target_selector,target_hash,engine_outcome,engine_evidence_json,status) "
                "VALUES(?,?,'alfa','sia-r69','Text contrast','#text',?,?, '{}','new')",
                (report, page_id, f"target-{report}", outcome),
            )
        conn.commit()
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": width, "height": 900})
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
            link = page.locator(f'a[href="/app{target}"]')
            await link.locator("xpath=ancestor::details[1]").locator("summary").focus()
            await page.keyboard.press("Enter")
            await playwright_async.expect(link).to_be_visible()
            await link.focus()
            await page.keyboard.press("Enter")
            await page.wait_for_url(f"{base}/app{target}")
            await playwright_async.expect(page.locator(f"#{target.split('#')[1]}")).to_be_focused()
        finally:
            await browser.close()
