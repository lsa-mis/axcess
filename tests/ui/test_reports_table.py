"""Reports navigation and table semantics, with an entirely intercepted browser origin."""

import re
from pathlib import Path
from typing import Any

import pytest

from .test_accessibility_axe import _render_violations, _run_axe

playwright_async = pytest.importorskip("playwright.async_api")
# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
DIST = Path(__file__).resolve().parents[2] / "src/audit/web/frontend/dist"


def _scan(scan_id: int, status: str, *, site: str, findings: int = 0) -> dict[str, Any]:
    return {
        "id": scan_id,
        "seed_url": site,
        "status": status,
        "page_count": 2 if status == "completed" else 0,
        "dom_state_count": 4 if status == "completed" else 0,
        "finding_count": findings,
        "started_at": None,
        "finished_at": None,
    }


def _site(index: int, findings: int) -> dict[str, Any]:
    """Site ``index``: a completed report, then a newer interrupted one.

    Site 0 has only a failed report, so it has no headline scan.
    """
    url = f"https://site{index}.example/"
    if index == 0:
        failed = _scan(1, "failed", site=url)
        return {
            "site_url": url,
            "scan_count": 1,
            "completed_count": 0,
            "most_recent": failed,
            "most_recent_completed": None,
            "most_recent_completed_issue_count": None,
            "scans": [failed],
        }
    completed = _scan(7 + 2 * (index - 1), "completed", site=url, findings=findings)
    interrupted = _scan(8 + 2 * (index - 1), "interrupted", site=url)
    return {
        "site_url": url,
        "scan_count": 2,
        "completed_count": 1,
        "most_recent": interrupted,
        "most_recent_completed": completed,
        "most_recent_completed_issue_count": 5,
        "scans": [interrupted, completed],
    }


async def _open_reports(
    new_page: Any, sites: list[dict[str, Any]], api_paths: list[str] | None = None
) -> Any:
    page = await new_page(viewport={"width": 320, "height": 900})

    async def respond(route: Any) -> None:
        path = route.request.url.split("reports.test", 1)[-1].split("?", 1)[0]
        if api_paths is not None and path.startswith("/api/"):
            api_paths.append(path)
        if path == "/api/sites":
            await route.fulfill(json=sites)
        elif path.startswith("/api/"):
            await route.fulfill(status=404, json={"detail": "Unavailable"})
        elif path.startswith("/app/assets/"):
            await route.fulfill(path=str(DIST / path.removeprefix("/app/")))
        else:
            await route.fulfill(path=str(DIST / "index.html"))

    await page.route("**/*", respond)
    await page.goto("http://reports.test/app/scans", wait_until="networkidle")
    return page


@pytest.mark.parametrize("count", [0, 3])
@pytest.mark.parametrize("site_count", [2, 23])
async def test_reports_table_keyboard_and_columns(
    count: int, site_count: int, new_page: Any
) -> None:
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    # Newest site first, as the API returns them; site 0 (failed only) is oldest.
    sites = [_site(index, count) for index in reversed(range(site_count))]
    page = await _open_reports(new_page, sites)
    table = page.get_by_role("table", name="Public reports by site", exact=False)
    # One header row (a simple table: scope="col" only, no column group),
    # and every column after Site is about the latest completed scan, as the
    # sentence over the table and its caption say.
    await playwright_async.expect(table.locator("thead tr")).to_have_count(1)
    await playwright_async.expect(table.locator("thead th[scope='colgroup']")).to_have_count(0)
    await playwright_async.expect(table.locator("td[headers]")).to_have_count(0)
    # The sorted header also carries its direction chip, so match the labels.
    await playwright_async.expect(table.locator("thead tr").first.locator("th")).to_contain_text(
        ["Site", "Completed", "Pages", "Issues", "Images with text", "Page states", "Report"]
    )
    await playwright_async.expect(
        page.get_by_text(
            "Each row shows the report from the site\u2019s most recent completed scan.", exact=True
        )
    ).to_be_visible()
    completed = table.locator("thead th").nth(1)
    await playwright_async.expect(completed).to_have_attribute("aria-sort", "descending")
    await playwright_async.expect(completed).to_contain_text("new → old")
    # The order is still announced, in a live region, though no longer shown
    # as a line of its own: the chip shows it.
    order = page.get_by_role("status").filter(has_text="Sorted by")
    await playwright_async.expect(order).to_have_text("Sorted by Completed, newest first.")
    box = await order.bounding_box()
    assert box and box["width"] <= 1 and box["height"] <= 1, box
    await playwright_async.expect(table.locator(":scope > tbody > tr")).to_have_count(
        min(10, site_count)
    )
    row = table.locator(":scope > tbody > tr").first
    newest = site_count - 1
    await playwright_async.expect(row.get_by_role("rowheader")).to_contain_text(
        f"site{newest}.example"
    )
    # How many scans the site has sits under its name, not in a column.
    await playwright_async.expect(row.get_by_role("rowheader")).to_contain_text(
        "2 scans, 1 completed"
    )
    headline_id = 7 + 2 * (newest - 1)
    # The site's newest run was interrupted ("Stopped"); the row shows only
    # the completed one.
    await playwright_async.expect(row).not_to_contain_text("Stopped")
    await playwright_async.expect(row.locator("td")).to_have_count(6)
    await playwright_async.expect(row.locator("td").nth(0)).to_have_text("Not recorded")
    await playwright_async.expect(row.locator("td").nth(1)).to_have_text("2")
    # The count says what it counts; "in Report #N" is screen-reader-only text.
    await playwright_async.expect(row.locator("td").nth(2)).to_have_text(
        f"5 issues in Report #{headline_id}"
    )
    await playwright_async.expect(row.locator("td").nth(3)).to_have_text(str(count))
    await playwright_async.expect(row.locator("td").nth(4)).to_have_text("4")
    open_link = row.get_by_role(
        "link",
        name=f"Open latest scan of site{newest}.example, the most recent completed scan",
    )
    await playwright_async.expect(open_link).to_have_attribute("href", f"/app/scans/{headline_id}")
    await playwright_async.expect(table.locator('a[href$="/findings"]')).to_have_count(0)
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # Expand by keyboard: the site's scans appear in their own captioned table.
    toggle = row.get_by_role("button", name=f"Show all 2 scans for site{newest}.example")
    await toggle.focus()
    await page.keyboard.press("Enter")
    expanded = row.get_by_role("button", name=f"Hide all 2 scans for site{newest}.example")
    await playwright_async.expect(expanded).to_have_attribute("aria-expanded", "true")
    await playwright_async.expect(expanded).to_be_focused()
    scans = page.get_by_role("table", name=f"All scans for site{newest}.example, most recent first")
    await playwright_async.expect(scans.locator("tbody tr")).to_have_count(2)
    # Only the expanded list shows the interrupted run, as "Stopped".
    await playwright_async.expect(scans).to_contain_text("Stopped")
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # The site's name is part of the toggle: clicking it closes and reopens
    # the list, not only the chevron.
    name = row.get_by_text(f"site{newest}.example", exact=True)
    await name.click()
    await playwright_async.expect(scans).to_have_count(0)
    await name.click()
    await playwright_async.expect(scans.locator("tbody tr")).to_have_count(2)

    region = page.get_by_role("region", name="Public reports table")
    await region.focus()
    await page.keyboard.press("ArrowRight")
    await playwright_async.expect(region).to_be_focused()
    pagination = page.get_by_role("navigation", name="Public reports: page controls")
    previous = pagination.get_by_role("button", name="Previous page of public reports")
    next_page = pagination.get_by_role("button", name="Next page of public reports")
    if site_count > 10:
        # The pager sits in the bar above the table, so a reader learns there
        # is more before reading the rows, and it comes before them in the
        # tab order.
        region_box = await region.bounding_box()
        pager_box = await pagination.bounding_box()
        assert region_box and pager_box and pager_box["y"] < region_box["y"]
        notice_link = page.get_by_role("link", name="Go to page controls")
        await playwright_async.expect(notice_link).to_have_count(0)
        await playwright_async.expect(previous).to_have_attribute("aria-disabled", "true")
        numbered = pagination.get_by_role("button", name=re.compile(r"^Page \d of"))
        await playwright_async.expect(numbered).to_have_text(["1", "2", "3"])
        await playwright_async.expect(numbered.first).to_have_attribute("aria-current", "page")
        await next_page.focus()
        await page.keyboard.press("Enter")
        await playwright_async.expect(next_page).to_be_focused()
        await playwright_async.expect(pagination.get_by_role("status")).to_contain_text(
            f"Showing 11\u201320 of {site_count} sites"
        )
        await playwright_async.expect(numbered.nth(1)).to_have_attribute("aria-current", "page")
        await pagination.get_by_role("button", name="Page 3 of public reports").click()
        await playwright_async.expect(table.locator(":scope > tbody > tr")).to_have_count(3)
        await playwright_async.expect(next_page).to_have_attribute("aria-disabled", "true")
        # The failed-only site is last: no completed scan, so no numbers.
        last = table.locator(":scope > tbody > tr").last
        await playwright_async.expect(last).to_contain_text("No completed scan yet")
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
        await previous.click()
        await previous.click()
    else:
        # One page: no pager at all.
        await playwright_async.expect(pagination).to_have_count(0)
        await playwright_async.expect(page.get_by_text("Page 1 of", exact=False)).to_have_count(0)

    # One small search in the table bar filters sites by address as you type,
    # and the count of matches is announced.
    search = page.get_by_role("searchbox", name="Search sites")
    status = page.get_by_role("status").filter(has_text="match")
    # Site rows only: an expanded site adds a row holding its scan list.
    site_rows = table.locator(":scope > tbody > tr > th[scope='row']")
    await search.fill(f"site{newest}.example")
    await playwright_async.expect(status).to_have_text(
        f"1 of {site_count} sites match \u201csite{newest}.example\u201d."
    )
    await playwright_async.expect(site_rows).to_have_count(1)
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
    await search.fill("no-such-site")
    await playwright_async.expect(table).to_contain_text("No sites match \u201cno-such-site\u201d.")
    # Escape clears it and brings every site back.
    await search.press("Escape")
    await playwright_async.expect(search).to_have_value("")
    await playwright_async.expect(site_rows).to_have_count(min(10, site_count))

    link = scans.get_by_role("link", name=f"All issues for Report #{headline_id}")
    await link.focus()
    await playwright_async.expect(link).to_be_focused()
    await page.keyboard.press("Enter")
    await page.wait_for_url(f"**/app/scans/{headline_id}/issues")


async def test_a_new_sort_order_is_announced(new_page: Any) -> None:
    """The order is said in a live region (SC 4.1.3), not in a visible line."""
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    page = await _open_reports(new_page, [_site(index, 1) for index in reversed(range(3))])
    order = page.get_by_role("status").filter(has_text="Sorted by")
    await playwright_async.expect(order).to_have_text("Sorted by Completed, newest first.")
    table = page.get_by_role("table", name="Public reports by site", exact=False)
    await table.get_by_role("button", name="Pages", exact=False).click()
    await playwright_async.expect(order).to_contain_text("Sorted by Pages")
    await playwright_async.expect(table.locator("thead th").nth(2)).not_to_have_attribute(
        "aria-sort", "none"
    )
    # The Scans column, and sorting by it, are gone.
    await playwright_async.expect(
        table.locator("thead").get_by_role("button", name=re.compile(r"^Scans\b"))
    ).to_have_count(0)


async def test_reports_page_leads_with_the_last_scanned_site(new_page: Any) -> None:
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    running = _scan(20, "running", site="https://site3.example/")
    # Listed first but older: the card picks the newest completed report by
    # id, not the table's first row.
    sites = [
        _site(1, 0),
        _site(2, 0),
        {
            "site_url": "https://site3.example/",
            "scan_count": 1,
            "completed_count": 0,
            "most_recent": running,
            "most_recent_completed": None,
            "most_recent_completed_issue_count": None,
            "scans": [running],
        },
    ]
    api_paths: list[str] = []
    page = await _open_reports(new_page, sites, api_paths)
    card = page.get_by_role("region", name="Last scanned site")
    # The site is the heading: it is what the reader recognises first.
    await playwright_async.expect(card.get_by_role("heading", level=2)).to_have_text(
        "site2.example"
    )
    await playwright_async.expect(card).to_have_text(
        re.compile(r"^Last scanned\s*site2\.example\s*Open latest scan of site2\.example$")
    )
    await playwright_async.expect(
        card.get_by_role("link", name="Open latest scan of site2.example", exact=True)
    ).to_have_attribute("href", "/app/scans/9/issues")
    # No findings summary, so the landing page never loads a report's issues.
    assert not any(re.fullmatch(r"/api/scans/\d+/issues", path) for path in api_paths), api_paths
    # The running scan's banner names the site; its page count joins once the
    # scan's own progress loads, which this test's stubbed API does not serve.
    await playwright_async.expect(
        page.get_by_text(re.compile(r"^Scanning site3\.example"))
    ).to_be_visible()
    await playwright_async.expect(
        page.get_by_role("link", name="View progress of the scan of site3.example", exact=True)
    ).to_have_attribute("href", "/app/scans/20")
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


async def test_back_brings_the_table_back_as_it_was(new_page: Any) -> None:
    """Sort, search, open sites and scroll survive going to a report and back.

    Back used to bring the table back sorted by date, with every site
    closed, so the reader had to find their place again.
    """
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    sites = [_site(index, 1) for index in reversed(range(8))]
    page = await new_page(viewport={"width": 1280, "height": 600})

    async def respond(route: Any) -> None:
        path = route.request.url.split("reports.test", 1)[-1].split("?", 1)[0]
        if path == "/api/sites":
            await route.fulfill(json=sites)
        elif path.startswith("/api/"):
            await route.fulfill(status=404, json={"detail": "Unavailable"})
        elif path.startswith("/app/assets/"):
            await route.fulfill(path=str(DIST / path.removeprefix("/app/")))
        else:
            await route.fulfill(path=str(DIST / "index.html"))

    await page.route("**/*", respond)
    await page.goto("http://reports.test/app/scans", wait_until="networkidle")
    table = page.get_by_role("table", name="Public reports by site", exact=False)
    await table.locator("thead").get_by_role("button", name=re.compile(r"^Site\b")).click()
    toggle = table.get_by_role("button", name="Show all 2 scans for site3.example")
    await toggle.click()
    await playwright_async.expect(
        table.get_by_role("button", name="Hide all 2 scans for site3.example")
    ).to_have_attribute("aria-expanded", "true")
    # The view is in the URL, and changing it added no history entries.
    await playwright_async.expect(page).to_have_url(re.compile(r"sort=site_asc"))
    await playwright_async.expect(page).to_have_url(re.compile(r"open=https%3A%2F%2Fsite3"))
    assert await page.evaluate("history.length") == 2
    await page.evaluate("window.scrollTo(0, 400)")
    link = table.get_by_role("link", name=re.compile(r"^Open latest scan of site5\.example"))
    # Clicking scrolls the link into view first; the place to come back to
    # is where the page is when the reader leaves it.
    await link.scroll_into_view_if_needed()
    scrolled = await page.evaluate("window.scrollY")
    assert scrolled > 0, scrolled

    await link.click()
    await page.wait_for_url(re.compile(r"/app/scans/\d+$"))
    await page.go_back()

    await playwright_async.expect(
        table.get_by_role("button", name="Hide all 2 scans for site3.example")
    ).to_have_attribute("aria-expanded", "true")
    await playwright_async.expect(table.locator("thead th").first).to_have_attribute(
        "aria-sort", "ascending"
    )
    await page.wait_for_function(f"Math.abs(window.scrollY - {scrolled}) < 40")
    await page.context.close()
