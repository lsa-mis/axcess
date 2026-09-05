"""Reports navigation and table semantics, with an entirely intercepted browser origin."""

from pathlib import Path
from typing import Any

import pytest

from .test_accessibility_axe import _render_violations, _run_axe

playwright_async = pytest.importorskip("playwright.async_api")
pytestmark = pytest.mark.ui
DIST = Path(__file__).resolve().parents[2] / "src/audit/web/frontend/dist"


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 3])
@pytest.mark.parametrize("report_count", [1, 23])
async def test_reports_table_keyboard_and_columns(count: int, report_count: int) -> None:
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 320, "height": 900})

            async def respond(route: Any) -> None:
                path = route.request.url.split("reports.test", 1)[-1].split("?", 1)[0]
                if path == "/api/scans":
                    await route.fulfill(
                        json=[
                            {
                                "id": 7 + index,
                                "seed_url": "https://example.com/long/path",
                                "status": "completed",
                                "page_count": 2,
                                "dom_state_count": 4,
                                "finding_count": count,
                                "started_at": None,
                                "finished_at": None,
                            }
                            for index in range(report_count)
                        ]
                    )
                elif path.startswith("/api/"):
                    await route.fulfill(status=404, json={"detail": "Unavailable"})
                elif path.startswith("/app/assets/"):
                    await route.fulfill(path=str(DIST / path.removeprefix("/app/")))
                else:
                    await route.fulfill(path=str(DIST / "index.html"))

            await page.route("**/*", respond)
            await page.goto("http://reports.test/app/scans", wait_until="networkidle")
            table = page.get_by_role("table", name="Public reports, newest first")
            await playwright_async.expect(table.get_by_role("columnheader")).to_have_text(
                [
                    "Report",
                    "Site URL",
                    "Status",
                    "Pages",
                    "DOM states",
                    "Image findings",
                    "Started",
                    "Actions",
                ]
            )
            await playwright_async.expect(table.locator("tbody tr")).to_have_count(
                min(10, report_count)
            )
            row = table.locator("tbody tr").first
            await playwright_async.expect(row.get_by_role("rowheader")).to_contain_text("#7")
            await playwright_async.expect(row.locator("td").nth(3)).to_have_text("4")
            await playwright_async.expect(row.locator("td").nth(4)).to_have_text(str(count))
            await playwright_async.expect(table.locator('a[href$="/findings"]')).to_have_count(0)
            violations = await _run_axe(page)
            assert not violations, _render_violations(violations)
            region = page.get_by_role("region", name="Public reports table")
            await region.focus()
            await page.keyboard.press("ArrowRight")
            await playwright_async.expect(region).to_be_focused()
            pagination = page.get_by_role("navigation", name="Public reports pagination")
            previous = pagination.get_by_role("button", name="Previous page of public reports")
            next_page = pagination.get_by_role("button", name="Next page of public reports")
            await playwright_async.expect(previous).to_have_attribute("aria-disabled", "true")
            if report_count > 10:
                await next_page.focus()
                await page.keyboard.press("Enter")
                await playwright_async.expect(next_page).to_be_focused()
                await playwright_async.expect(pagination.get_by_role("status")).to_contain_text(
                    "Showing 11\u201320 of 23"
                )
                await playwright_async.expect(row.get_by_role("rowheader")).to_contain_text("#17")
                await page.keyboard.press("Enter")
                await playwright_async.expect(table.locator("tbody tr")).to_have_count(3)
                await playwright_async.expect(next_page).to_have_attribute("aria-disabled", "true")
                await page.keyboard.press("Enter")
                await playwright_async.expect(pagination.get_by_role("status")).to_contain_text(
                    "Page 3 of 3"
                )
                await previous.click()
                await previous.click()
            else:
                await playwright_async.expect(next_page).to_have_attribute("aria-disabled", "true")
            search = page.get_by_role("searchbox", name="Search reports")
            await search.fill("#7")
            await search.press("Enter")
            await playwright_async.expect(table.locator("tbody tr")).to_have_count(1)
            await playwright_async.expect(row.get_by_role("rowheader")).to_contain_text("#7")
            await playwright_async.expect(search).to_be_focused()
            await search.fill("no-such-site")
            await page.get_by_role("button", name="Search", exact=True).click()
            await playwright_async.expect(table).to_contain_text("No public reports match")
            await page.get_by_role("button", name="Clear search", exact=True).click()
            await playwright_async.expect(search).to_have_value("")
            await playwright_async.expect(table.locator("tbody tr")).to_have_count(
                min(10, report_count)
            )
            link = table.get_by_role("link", name="All issues for report 7")
            await link.focus()
            await playwright_async.expect(link).to_be_focused()
            await page.keyboard.press("Enter")
            await page.wait_for_url("**/app/scans/7/issues")
        finally:
            await browser.close()
