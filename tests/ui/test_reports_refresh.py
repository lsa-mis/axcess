"""A site's very first scan shows on Reports while it runs.

Starting a scan from New scan used only to navigate, so Reports showed its
cached list for the five seconds it counts as fresh, and a list with no
running scan does not refresh itself. Before a first scan that list is
empty: open Reports, start a scan, go back, and it said "No reports yet".
Now it shows as any later scan does: the site's row, and in its list of
scans the report marked as scanning.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")

NEW_SITE = "https://first.example/"


def _first_scan_running() -> list[dict[str, Any]]:
    scan = {
        "id": 99,
        "seed_url": NEW_SITE,
        "status": "running",
        "page_count": 0,
        "dom_state_count": 0,
        "finding_count": 0,
        "started_at": None,
        "finished_at": None,
    }
    return [
        {
            "site_url": NEW_SITE,
            "scan_count": 1,
            "completed_count": 0,
            "most_recent": scan,
            "most_recent_completed": None,
            "most_recent_completed_issue_count": None,
            "scans": [scan],
        }
    ]


async def test_a_first_scan_shows_on_reports_while_it_runs(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """Reports, New scan, start, and straight back, all inside the app."""
    base, _ = live_server
    page = await new_page(viewport={"width": 1280, "height": 900})
    started = False

    # The real app, except that no report exists yet and starting the scan
    # is answered here, so nothing is crawled.
    async def create(route: Any) -> None:
        nonlocal started
        if route.request.method != "POST":
            await route.continue_()
            return
        started = True
        await route.fulfill(status=201, json={"scan_id": 99})

    async def sites(route: Any) -> None:
        await route.fulfill(json=_first_scan_running() if started else [])

    await page.route("**/api/scans", create)
    await page.route("**/api/sites", sites)
    await page.goto(f"{base}/app/scans", wait_until="networkidle")
    main = page.get_by_role("main")
    await playwright_async.expect(main.get_by_text("No reports yet")).to_be_visible()

    # In-app navigation throughout: a page load would empty the cache.
    await main.get_by_role("link", name="Start a new scan").click()
    await main.get_by_role("textbox").first.fill(NEW_SITE)
    await page.locator("main button[type=submit]").first.click()
    await page.wait_for_url(re.compile(r"/app/scans/99"))
    await (
        page.get_by_role("navigation").get_by_role("link", name="Reports", exact=True).first.click()
    )
    await page.wait_for_url(re.compile(r"/app/scans$"))

    # Well inside the five seconds the old list counted as fresh: the site's
    # row, and in its list of scans the report, marked as scanning.
    table = page.get_by_role("table", name="Public reports by site", exact=False)
    site = table.get_by_role("button", name=re.compile("first.example"))
    await playwright_async.expect(site).to_be_visible(timeout=3000)
    await site.click()
    scans = page.get_by_role("table", name=re.compile("All scans for first.example"))
    report = scans.get_by_role("row").filter(has=page.get_by_role("link", name="Report #99"))
    await playwright_async.expect(report.get_by_label("Scan status: Scanning")).to_be_visible()
