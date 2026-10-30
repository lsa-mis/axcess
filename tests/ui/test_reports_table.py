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
        "rule_checks": ["axe", "alfa"] if status == "completed" else [],
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
            "most_recent_completed_occurrence_count": None,
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
        "most_recent_completed_occurrence_count": 5 + findings,
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
        elif counts := re.fullmatch(r"/api/scans/(\d+)/issue-counts", path):
            # Only completed reports are counted, as the server does.
            completed = {
                s["most_recent_completed"]["id"]: s
                for s in sites
                if s["most_recent_completed"] is not None
            }
            site = completed.get(int(counts.group(1)))
            if site is None:
                await route.fulfill(status=409, json={"detail": "Not finished"})
            else:
                await route.fulfill(
                    json={
                        "issue_count": site["most_recent_completed_issue_count"],
                        "occurrence_count": site["most_recent_completed_occurrence_count"],
                    }
                )
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
    # caption says.
    await playwright_async.expect(table.locator("thead tr")).to_have_count(1)
    await playwright_async.expect(table.locator("thead th[scope='colgroup']")).to_have_count(0)
    await playwright_async.expect(table.locator("td[headers]")).to_have_count(0)
    # The sorted header also carries its direction chip, so match the labels.
    await playwright_async.expect(table.locator("thead tr").first.locator("th")).to_contain_text(
        ["Site", "Scanned", "Pages", "Occurrences", "Kinds of issues", "Rule check", "Actions"]
    )
    # The caption says where a site row's numbers come from; the sentence
    # that repeated it over the table was removed after user testing.
    await playwright_async.expect(table).to_have_accessible_name(
        "Public reports by site. A site\u2019s row shows its most recent completed scan. "
        "Open a site to list each of its scans under it."
    )
    await playwright_async.expect(page.get_by_text("Each row shows", exact=False)).to_have_count(0)
    completed = table.locator("thead th").nth(1)
    await playwright_async.expect(completed).to_have_attribute("aria-sort", "descending")
    await playwright_async.expect(completed).to_contain_text("new → old")
    # The order is still announced, in a live region, though no longer shown
    # as a line of its own: the chip shows it.
    order = page.get_by_role("status").filter(has_text="Sorted by")
    await playwright_async.expect(order).to_have_text("Sorted by Scanned, newest first.")
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
    # Occurrences counts every place a problem appears; Kinds of issues counts
    # the report's rows. Both plain numbers, as in the scan rows: the count is
    # no longer a second link to the report "Open latest scan" opens.
    await playwright_async.expect(row.locator("td").nth(2)).to_have_text(f"{5 + count}")
    await playwright_async.expect(row.locator("td").nth(2).get_by_role("link")).to_have_count(0)
    await playwright_async.expect(row.locator("td").nth(3)).to_have_text("5")
    # Which rule checks tested pages, and, on the header, who makes each.
    await playwright_async.expect(row.locator("td").nth(4)).to_have_text("axe and Alfa")
    await playwright_async.expect(
        table.locator("thead").get_by_role("button", name=re.compile(r"^Rule check"))
    ).to_have_attribute("title", re.compile(r"Alfa \(made by Siteimprove\)"))
    # The places' column went back to "Occurrences" on 2026-10-28; no
    # header is the bare "Issues" of 2026-10-26 to 2026-10-28.
    await playwright_async.expect(
        table.locator("thead th").filter(has_text=re.compile(r"^\s*Issues\b"))
    ).to_have_count(0)
    # Images with text and page states are no longer columns.
    await playwright_async.expect(table.locator("thead")).not_to_contain_text("Images with text")
    await playwright_async.expect(table.locator("thead")).not_to_contain_text("Page states")
    open_link = row.get_by_role(
        "link",
        name=f"Open latest scan of site{newest}.example, the most recent completed scan",
    )
    await playwright_async.expect(open_link).to_have_attribute("href", f"/app/scans/{headline_id}")
    # Both actions are shown, no menu to open: "Scan again" sits beside
    # "Open latest scan" and starts from the same report's settings.
    scan_again = row.get_by_role(
        "link",
        name=re.compile(
            rf"^Scan again\W+site{newest}\.example, "
            rf"starting from the settings of report #{headline_id}$"
        ),
    )
    await playwright_async.expect(scan_again).to_be_visible()
    await playwright_async.expect(scan_again).to_have_attribute(
        "href", f"/app/scans/new?from={headline_id}"
    )
    actions_menu = row.get_by_role("button", name=re.compile("^Actions"))
    await playwright_async.expect(actions_menu).to_have_count(0)
    # Keyboard order follows the reading order: open first, then scan again.
    await open_link.focus()
    await page.keyboard.press("Tab")
    await playwright_async.expect(scan_again).to_be_focused()
    await playwright_async.expect(table.locator('a[href$="/findings"]')).to_have_count(0)
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # Expand by keyboard: the site's scans appear as rows of the same table,
    # under its own column headers, so their columns line up with the site's.
    toggle = row.get_by_role("button", name=f"Show all 2 scans for site{newest}.example")
    await toggle.focus()
    await page.keyboard.press("Enter")
    expanded = row.get_by_role("button", name=f"Hide all 2 scans for site{newest}.example")
    await playwright_async.expect(expanded).to_have_attribute("aria-expanded", "true")
    await playwright_async.expect(expanded).to_be_focused()
    scans = table.locator(":scope > tbody > tr").filter(
        has=page.get_by_role("link", name=re.compile(r"^Open Report #\d+$"))
    )
    await playwright_async.expect(scans).to_have_count(2)
    # No table inside the table, and still one header row.
    await playwright_async.expect(table.locator("table")).to_have_count(0)
    await playwright_async.expect(table.locator("thead tr")).to_have_count(1)
    # The toggle names the rows it shows.
    controlled = (await expanded.get_attribute("aria-controls") or "").split()
    assert len(controlled) == 2, controlled
    for row_id in controlled:
        await playwright_async.expect(table.locator(f"tr#{row_id}")).to_have_count(1)
    # Fetched when the rows are shown. The completed scan is counted; the
    # interrupted one says so in words rather than showing a 0. Its cells
    # sit under the site's: Scanned, Pages, Occurrences, Kinds of issues, Rule
    # check, Actions.
    stopped, done = scans.nth(0), scans.nth(1)
    await playwright_async.expect(done.locator("td")).to_have_count(6)
    await playwright_async.expect(done.locator("td").nth(2)).to_have_text(str(5 + count))
    await playwright_async.expect(done.locator("td").nth(3)).to_have_text("5")
    await playwright_async.expect(stopped.locator("td").nth(2)).to_have_text("Not counted")
    await playwright_async.expect(stopped.locator("td").nth(3)).to_have_text("Not counted")
    await playwright_async.expect(done.locator("td").nth(4)).to_have_text("axe and Alfa")
    await playwright_async.expect(stopped.locator("td").nth(4)).to_have_text("None")
    # A status shows only when the scan did not complete: "Stopped" beside
    # the interrupted run's number, nothing beside the completed one.
    await playwright_async.expect(stopped.get_by_role("rowheader")).to_contain_text("Stopped")
    await playwright_async.expect(done.get_by_role("rowheader")).to_have_text(
        f"Open Report #{headline_id}"
    )
    await playwright_async.expect(table).not_to_contain_text("shown in the site row")
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # The site's name is part of the toggle: clicking it closes and reopens
    # the list, not only the chevron.
    name = row.get_by_text(f"site{newest}.example", exact=True)
    await name.click()
    await playwright_async.expect(scans).to_have_count(0)
    await name.click()
    await playwright_async.expect(scans).to_have_count(2)

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
        # A short last page leaves the table short: no block of empty rows
        # held from the full page before it (removed 2026-10-30).
        region_box = await region.bounding_box()
        table_box = await table.bounding_box()
        assert region_box and table_box
        assert region_box["height"] <= table_box["height"] + 2, (region_box, table_box)
        # The failed-only site is last: no completed scan, so no numbers.
        last = table.locator(":scope > tbody > tr").last
        await playwright_async.expect(last).to_contain_text("No completed scan yet")
        # Nothing to open yet, so only "Scan again", from its latest scan.
        await playwright_async.expect(
            last.get_by_role("link", name=re.compile(r"^Scan again\W+site\d+\.example"))
        ).to_have_attribute("href", re.compile(r"/app/scans/new\?from=\d+$"))
        await playwright_async.expect(
            last.get_by_role("link", name=re.compile(r"^Open latest scan"))
        ).to_have_count(0)
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
    # Site rows only: an expanded site adds a row per scan.
    site_rows = table.locator(":scope > tbody > tr").filter(
        has=page.locator("button[aria-expanded]")
    )
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

    # The report number is the one way into a scan: a completed scan's goes
    # straight to its Issues page, and no "All issues" link repeats it.
    await playwright_async.expect(
        table.get_by_role("link", name=re.compile(r"^All issues"))
    ).to_have_count(0)
    link = table.get_by_role("link", name=f"Open Report #{headline_id}", exact=True)
    await playwright_async.expect(link).to_have_attribute(
        "href", f"/app/scans/{headline_id}/issues"
    )
    stopped_link = table.get_by_role("link", name=f"Open Report #{headline_id + 1}", exact=True)
    await playwright_async.expect(stopped_link).to_have_attribute(
        "href", f"/app/scans/{headline_id + 1}"
    )
    await link.focus()
    await playwright_async.expect(link).to_be_focused()
    await page.keyboard.press("Enter")
    await page.wait_for_url(f"**/app/scans/{headline_id}/issues")


def _comparable_site() -> dict[str, Any]:
    """A site with two completed reports (21 the latest) and a stopped one."""
    url = "https://compared.example/"
    latest = _scan(21, "completed", site=url, findings=2)
    earlier = _scan(20, "completed", site=url, findings=4)
    stopped = _scan(22, "interrupted", site=url)
    return {
        "site_url": url,
        "scan_count": 3,
        "completed_count": 2,
        "most_recent": stopped,
        "most_recent_completed": latest,
        "most_recent_completed_issue_count": 3,
        "most_recent_completed_occurrence_count": 6,
        "scans": [stopped, latest, earlier],
    }


@pytest.mark.parametrize("width", [320, 1280])
async def test_compare_with_on_each_completed_scan_row(width: int, new_page: Any) -> None:
    """A completed scan row offers "Compare with" and the site's other completed reports.

    The developer chose the scan rows for comparing (2026-10-29). The
    button shows a list of links (the APG disclosure pattern), never a
    select that navigates on choice (SC 3.2.2), and it does not close when
    the page scrolls.
    """
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    page = await _open_reports(new_page, [_comparable_site(), _site(1, 0)])
    await page.set_viewport_size({"width": width, "height": 700})
    table = page.get_by_role("table", name="Public reports by site", exact=False)
    rows = table.locator(":scope > tbody > tr")
    compared = rows.nth(0)
    # The site row has no compare link any more: its two links stay.
    await playwright_async.expect(
        table.get_by_role("link", name=re.compile(r"^Compare"))
    ).to_have_count(0)
    await playwright_async.expect(
        table.get_by_role("button", name=re.compile(r"^Compare with"))
    ).to_have_count(0)
    open_link = compared.get_by_role("link", name=re.compile(r"^Open latest scan of compared"))
    scan_again = compared.get_by_role("link", name=re.compile(r"^Scan again\W+compared\.example"))
    await open_link.focus()
    await page.keyboard.press("Tab")
    await playwright_async.expect(scan_again).to_be_focused()

    await compared.get_by_role("button", name=re.compile(r"^Show all 3 scans")).click()
    scan_rows = rows.filter(has=page.get_by_role("link", name=re.compile(r"^Open Report #\d+$")))
    await playwright_async.expect(scan_rows).to_have_count(3)
    latest = scan_rows.filter(has=page.get_by_role("link", name="Open Report #21", exact=True))
    stopped = scan_rows.filter(has=page.get_by_role("link", name="Open Report #22", exact=True))
    earlier = scan_rows.filter(has=page.get_by_role("link", name="Open Report #20", exact=True))
    # Only on a completed scan with another completed scan in the site; a
    # stopped scan has nothing, not a disabled control.
    await playwright_async.expect(
        stopped.get_by_role("button", name=re.compile(r"^Compare with"))
    ).to_have_count(0)
    await playwright_async.expect(
        earlier.get_by_role(
            "button", name="Compare with another report, for Report #20", exact=True
        )
    ).to_have_count(1)

    # The visible words lead the name; the row's report is screen-reader-only
    # text inside it (technique C7), not an aria-label.
    button = latest.get_by_role(
        "button", name="Compare with another report, for Report #21", exact=True
    )
    await playwright_async.expect(button).to_be_visible()
    await playwright_async.expect(button).not_to_have_attribute("aria-label", re.compile(".*"))
    assert (await button.inner_text()).strip().startswith("Compare with")
    await playwright_async.expect(button).to_have_attribute("aria-expanded", "false")
    panel_id = await button.get_attribute("aria-controls")
    assert panel_id
    button_box = await button.bounding_box()
    assert button_box and button_box["height"] >= 44, button_box

    # Reading order: the report's link, Compare with, then Delete.
    report_link = latest.get_by_role("link", name="Open Report #21", exact=True)
    delete = latest.get_by_role("button", name="Delete report 21")
    await report_link.focus()
    await page.keyboard.press("Tab")
    await playwright_async.expect(button).to_be_focused()
    await page.keyboard.press("Tab")
    await playwright_async.expect(delete).to_be_focused()

    # Enter opens it; the links follow the button in the tab order.
    await button.focus()
    await page.keyboard.press("Enter")
    await playwright_async.expect(button).to_have_attribute("aria-expanded", "true")
    panel = page.locator(f"[id='{panel_id}']")
    await playwright_async.expect(panel).to_be_visible()
    link = panel.get_by_role("link", name="Report #20 (compare with Report #21)", exact=True)
    await playwright_async.expect(panel.get_by_role("link")).to_have_count(1)
    await playwright_async.expect(link).to_have_attribute(
        "href", "/app/scans/21/compare?compare_to=20"
    )
    assert (await link.inner_text()).strip().startswith("Report #20")
    link_box = await link.bounding_box()
    assert link_box and link_box["height"] >= 44, link_box
    await page.keyboard.press("Tab")
    await playwright_async.expect(link).to_be_focused()
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
    # Escape closes it and puts focus back on the button.
    await page.keyboard.press("Escape")
    await playwright_async.expect(button).to_have_attribute("aria-expanded", "false")
    await playwright_async.expect(panel).to_be_hidden()
    await playwright_async.expect(button).to_be_focused()

    # Down arrow opens it on the first link.
    await page.keyboard.press("ArrowDown")
    await playwright_async.expect(link).to_be_focused()
    # Scrolling never closes it (screen-magnifier users pan by scrolling);
    # the list moves with its button.
    before, button_before = await panel.bounding_box(), await button.bounding_box()
    await page.evaluate("document.querySelector('main').scrollBy(0, 40); window.scrollBy(0, 40)")
    await page.mouse.wheel(0, 60)
    await page.wait_for_timeout(150)
    await playwright_async.expect(button).to_have_attribute("aria-expanded", "true")
    await playwright_async.expect(panel).to_be_visible()
    after = await panel.bounding_box()
    button_after = await button.bounding_box()
    assert before and after and button_before and button_after
    assert button_after["y"] != button_before["y"], "the page did not scroll"
    # Still right under or right over its button, wherever that is now: it
    # followed (it may flip to the side with more room).

    def beside(panel_box: dict[str, float], anchor: dict[str, float]) -> bool:
        under = abs(panel_box["y"] - (anchor["y"] + anchor["height"]) - 6) < 2
        over = abs(panel_box["y"] + panel_box["height"] - anchor["y"] + 6) < 2
        return under or over

    assert beside(before, button_before), (before, button_before)
    assert beside(after, button_after), (after, button_after)
    # A press outside closes it.
    await page.get_by_role("heading", name="Reports", level=1).click()
    await playwright_async.expect(button).to_have_attribute("aria-expanded", "false")
    if width == 320:
        assert await page.evaluate("document.body.scrollWidth <= innerWidth")

    # From the older row, the same pair opens the same address: the newer
    # report goes in the path, the older is compare_to (the comparison needs
    # the baseline to be the earlier report).
    older_button = earlier.get_by_role(
        "button", name="Compare with another report, for Report #20", exact=True
    )
    # By keyboard: at 320 pixels a click would land on the sticky Site
    # column, which the scrolled region slides the Actions cell under.
    await older_button.focus()
    await page.keyboard.press("Enter")
    older_panel = page.locator(f"[id='{await older_button.get_attribute('aria-controls')}']")
    await playwright_async.expect(
        older_panel.get_by_role("link", name="Report #21 (compare with Report #20)", exact=True)
    ).to_have_attribute("href", "/app/scans/21/compare?compare_to=20")
    await page.keyboard.press("Escape")

    # Following a link opens Compare reports for the pair.
    await button.focus()
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Enter")
    await page.wait_for_url("**/app/scans/21/compare?compare_to=20")


async def test_a_new_sort_order_is_announced(new_page: Any) -> None:
    """The order is said in a live region (SC 4.1.3), not in a visible line."""
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    page = await _open_reports(new_page, [_site(index, 1) for index in reversed(range(3))])
    order = page.get_by_role("status").filter(has_text="Sorted by")
    await playwright_async.expect(order).to_have_text("Sorted by Scanned, newest first.")
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
            "most_recent_completed_occurrence_count": None,
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


async def test_sites_stay_open_when_coming_back_by_the_navigation(new_page: Any) -> None:
    """The navigation's "Reports" carries no view; the tab remembers it.

    Testers opened a site, went to a report, came back by the navigation
    and had to open the site again every time (2026-10-28).
    """
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    sites = [_site(index, 1) for index in reversed(range(4))]
    page = await new_page(viewport={"width": 1280, "height": 800})

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
    reports_nav = page.get_by_role("navigation").get_by_role("link", name="Reports", exact=True)

    async def leave_and_come_back() -> None:
        await table.get_by_role("link", name=re.compile(r"^Open latest scan of site1\.")).click()
        await page.wait_for_url(re.compile(r"/app/scans/\d+$"))
        await reports_nav.first.click()
        await page.wait_for_url(re.compile(r"/app/scans(\?|$)"))

    await table.get_by_role("button", name="Show all 2 scans for site2.example").click()
    await table.locator("thead").get_by_role("button", name=re.compile(r"^Pages\b")).click()
    await leave_and_come_back()
    await playwright_async.expect(
        table.get_by_role("button", name="Hide all 2 scans for site2.example")
    ).to_have_attribute("aria-expanded", "true")
    await playwright_async.expect(table.locator("thead th").nth(2)).not_to_have_attribute(
        "aria-sort", "none"
    )
    # Put back by replacing the entry, so Back still leaves the page.
    await playwright_async.expect(page).to_have_url(re.compile(r"open=https%3A%2F%2Fsite2"))

    # Closing is remembered the same way.
    await table.get_by_role("button", name="Hide all 2 scans for site2.example").click()
    await leave_and_come_back()
    await playwright_async.expect(
        table.get_by_role("button", name="Show all 2 scans for site2.example")
    ).to_have_attribute("aria-expanded", "false")

    # A link that names a view opens that view, not the remembered one.
    await table.get_by_role("button", name="Show all 2 scans for site3.example").click()
    await page.goto("http://reports.test/app/scans?open=https%3A%2F%2Fsite1.example%2F")
    await playwright_async.expect(
        table.get_by_role("button", name="Hide all 2 scans for site1.example")
    ).to_be_visible()
    await playwright_async.expect(
        table.get_by_role("button", name="Show all 2 scans for site3.example")
    ).to_be_visible()
    await page.context.close()
