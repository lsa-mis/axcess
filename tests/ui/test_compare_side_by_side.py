"""Compare reports: two reports side by side, each panel the app in a frame.

routes/CompareReports.tsx and lib/framed.ts. Each panel works like its own
browser tab: it filters, opens an issue and goes back without changing the
other panel or the outer page's address. The diff of the two reports moved to
What changed, at ``/compare/changes``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from audit.db.schema import connect

from .conftest import _seed
from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect


@pytest.fixture
def three_reports(seeded_db: tuple[Path, Path, int]) -> tuple[int, int, int]:
    """Three completed reports of example.com, oldest first."""
    db_path, blob_dir, first = seeded_db
    conn = connect(db_path)
    try:
        second = _seed(conn, blob_dir)
        third = _seed(conn, blob_dir)
        for day, scan in enumerate((first, second, third), start=1):
            conn.execute(
                "UPDATE scans SET started_at=?, finished_at=? WHERE id=?",
                (f"2026-10-0{day} 12:00:00", f"2026-10-0{day} 12:30:00", scan),
            )
        conn.commit()
    finally:
        conn.close()
    return first, second, third


async def _open(new_page: Any, base: str, path: str, width: int = 1280, height: int = 800) -> Any:
    page = await new_page(viewport={"width": width, "height": height})
    await page.goto(f"{base}/app{path}", wait_until="networkidle")
    await expect(page.get_by_role("heading", name="Compare reports", level=1)).to_be_visible()
    return page


def _panel(page: Any, report: int) -> Any:
    return page.get_by_role("region", name=re.compile(rf"^Report #{report}\b"))


async def _frame(page: Any, report: int) -> Any:
    """The panel's frame, once its Issues page is drawn."""
    frame = _panel(page, report).frame_locator("iframe")
    await expect(frame.get_by_role("heading", name="Issues", level=1)).to_be_visible()
    return frame


def _frame_url(page: Any, report: int) -> str:
    for frame in page.frames:
        if frame.parent_frame is not None and f"/scans/{report}/" in frame.url:
            return str(frame.url)
    raise AssertionError(f"no frame for report {report}: {[f.url for f in page.frames]}")


async def test_two_panels_show_their_reports_without_the_app_chrome(
    live_server: tuple[str, int], three_reports: tuple[int, int, int], new_page: Any
) -> None:
    base, _ = live_server
    _, second, third = three_reports
    page = await _open(new_page, base, f"/scans/{third}/compare?compare_to={second}")
    left, right = _panel(page, third), _panel(page, second)
    await expect(left).to_have_count(1)
    await expect(right).to_have_count(1)
    # The panel headings name the report and the day it was scanned.
    await expect(left.get_by_role("heading", level=2)).to_contain_text(f"Report #{third}")
    await expect(left.get_by_role("heading", level=2)).to_contain_text("scanned")
    # Each frame's title names its report and page (technique H64).
    await expect(left.locator("iframe")).to_have_attribute(
        "title", f"Report #{third}, Accessibility issues"
    )
    await expect(right.locator("iframe")).to_have_attribute(
        "title", f"Report #{second}, Accessibility issues"
    )
    await expect(left.locator("iframe")).not_to_have_attribute("sandbox", re.compile(".*"))

    for report in (third, second):
        frame = await _frame(page, report)
        # A panel is the page alone: no sidebar, no top bar, no skip link,
        # and no Compare reports tab (so no report tabs at all).
        await expect(frame.get_by_role("complementary", name="Primary")).to_have_count(0)
        await expect(frame.get_by_role("banner")).to_have_count(0)
        await expect(frame.get_by_role("link", name="Skip to main content")).to_have_count(0)
        await expect(frame.get_by_role("navigation", name="Report views")).to_have_count(0)
        await expect(frame.get_by_role("main")).to_have_count(1)

    # Side by side at 1280 with the sidebar open, each about 460 pixels wide,
    # the page inside laid out for that width with nothing sideways.
    left_box = await left.locator("iframe").bounding_box()
    right_box = await right.locator("iframe").bounding_box()
    assert left_box and right_box
    assert abs(left_box["y"] - right_box["y"]) < 2, (left_box, right_box)
    assert right_box["x"] > left_box["x"] + left_box["width"]
    assert 400 < left_box["width"] < 520, left_box
    for frame in page.frames[1:]:
        assert await frame.evaluate("document.documentElement.scrollWidth <= innerWidth"), frame.url

    # The link to What changed: the newer report in the path.
    changes = page.get_by_role("link", name="See what changed between these reports")
    await expect(changes).to_have_attribute(
        "href", f"/app/scans/{third}/compare/changes?compare_to={second}"
    )
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
    # The narrow page inside a panel is clean too.
    inner = next(f for f in page.frames if f"/scans/{third}/issues" in f.url)
    violations = await _run_axe(inner)
    assert not violations, _render_violations(violations)


async def test_each_panel_moves_on_its_own_and_goes_back_in_itself(
    live_server: tuple[str, int], three_reports: tuple[int, int, int], new_page: Any
) -> None:
    """Filter and open an issue in one panel; the other and the address stay put."""
    base, _ = live_server
    _, second, third = three_reports
    address = f"/scans/{third}/compare?compare_to={second}"
    page = await _open(new_page, base, address, height=700)
    left_frame = await _frame(page, third)
    await _frame(page, second)
    right_before = _frame_url(page, second)
    length = await page.evaluate("history.length")
    back = _panel(page, third).get_by_role(
        "button", name=f"Go back in the report #{third} panel", exact=True
    )
    # A fresh panel has nowhere to go back to: available-looking never.
    await expect(back).to_have_attribute("aria-disabled", "true")

    # Filtering in the first panel leaves the second panel alone.
    await left_frame.get_by_role("searchbox", name="Search issues").fill("banner")
    await page.wait_for_function(
        "report => [...document.querySelectorAll('iframe')].some("
        "f => f.contentWindow.location.href.includes(`/scans/${report}/issues?`)"
        " && f.contentWindow.location.search.includes('q=banner'))",
        arg=third,
    )
    assert _frame_url(page, second) == right_before
    await left_frame.get_by_role("searchbox", name="Search issues").fill("")
    await page.wait_for_function(
        "report => [...document.querySelectorAll('iframe')].some("
        "f => f.contentWindow.location.pathname.endsWith(`/scans/${report}/issues`)"
        " && !f.contentWindow.location.search.includes('q='))",
        arg=third,
    )

    # Scroll the panel's page to the issue, then open it.
    inner = next(f for f in page.frames if f"/scans/{third}/issues" in f.url)
    issue = left_frame.locator("table a[href*='/issues/']").first
    await issue.scroll_into_view_if_needed()
    scrolled = await inner.evaluate("window.scrollY")
    await issue.click()
    await expect(left_frame.get_by_role("heading", level=1)).not_to_have_text("Issues")
    assert re.search(rf"/scans/{third}/issues/[^/?]+", _frame_url(page, third))
    await expect(back).not_to_have_attribute("aria-disabled", "true")
    await expect(_panel(page, third).locator("iframe")).to_have_attribute(
        "title", f"Report #{third}, Issue evidence"
    )
    # The other panel, the address and the window's history did not move.
    assert _frame_url(page, second) == right_before
    assert page.url == f"{base}/app{address}"
    assert await page.evaluate("history.length") == length

    # Go back, by keyboard: the panel returns to its table, where it was,
    # and focus stays on the button.
    await back.focus()
    await page.keyboard.press("Enter")
    await expect(left_frame.get_by_role("heading", name="Issues", level=1)).to_be_visible()
    await expect(back).to_have_attribute("aria-disabled", "true")
    await expect(back).to_be_focused()
    inner = next(f for f in page.frames if f"/scans/{third}/issues" in f.url)
    assert scrolled > 0, "the panel's page should scroll at this height"
    await inner.wait_for_function(f"Math.abs(window.scrollY - {scrolled}) <= 1")
    assert _frame_url(page, second) == right_before
    # With nothing left to go back to, pressing it does nothing.
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(200)
    assert re.search(rf"/scans/{third}/issues$", _frame_url(page, third))
    assert page.url == f"{base}/app{address}"


async def test_report_picker_changes_one_panel_and_the_address(
    live_server: tuple[str, int], three_reports: tuple[int, int, int], new_page: Any
) -> None:
    """By keyboard; the report in the other panel cannot be chosen; Back undoes."""
    base, _ = live_server
    first, second, third = three_reports
    address = f"/scans/{third}/compare?compare_to={second}"
    page = await _open(new_page, base, address)
    await _frame(page, third)
    await _frame(page, second)
    right_doc = next(f for f in page.frames if f"/scans/{second}/" in f.url)
    await right_doc.evaluate("window.__untouched = true")

    left = _panel(page, third)
    picker = left.get_by_role("combobox", name="Report")
    show = left.get_by_role(
        "button", name=f"Show this report in place of report #{third}", exact=True
    )
    await expect(picker).to_have_attribute("data-value", str(third))
    # The report in the other panel: an error tied to the picker, focus on it.
    await picker.focus()
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Enter")
    await expect(picker).to_have_attribute("data-value", str(second))
    await page.keyboard.press("Tab")
    await expect(show).to_be_focused()
    await page.keyboard.press("Enter")
    error = left.get_by_text(f"Report #{second} is already in the other panel.")
    await expect(error).to_be_visible()
    await expect(picker).to_be_focused()
    error_id = await error.locator("xpath=..").get_attribute("id")
    assert error_id and error_id in (await picker.get_attribute("aria-describedby") or "")
    assert page.url == f"{base}/app{address}"

    # The oldest report, by keyboard: only the first panel and the path change.
    await page.keyboard.press("End")
    await page.keyboard.press("Enter")
    await expect(picker).to_have_attribute("data-value", str(first))
    await expect(error).to_have_count(0)
    await page.keyboard.press("Tab")
    await page.keyboard.press("Enter")
    await page.wait_for_url(f"**/app/scans/{first}/compare?compare_to={second}")
    await _frame(page, first)
    right_doc = next(f for f in page.frames if f"/scans/{second}/" in f.url)
    assert await right_doc.evaluate("window.__untouched === true")
    # Older first now: What changed still puts the newer report in the path.
    await expect(
        page.get_by_role("link", name="See what changed between these reports")
    ).to_have_attribute("href", f"/app/scans/{second}/compare/changes?compare_to={first}")

    # The browser's Back undoes the choice of report.
    await page.go_back()
    await page.wait_for_url(f"**/app{address}")
    await _frame(page, third)

    # Follow the link to What changed.
    await page.get_by_role("link", name="See what changed between these reports").click()
    await page.wait_for_url(f"**/app/scans/{third}/compare/changes?compare_to={second}")
    await expect(page.get_by_role("heading", name="What changed", level=1)).to_be_visible()
    assert await page.title() == "What changed · Axcess"


@pytest.mark.parametrize("width", [320, 1280])
async def test_opened_from_a_report_the_second_panel_is_empty_until_chosen(
    live_server: tuple[str, int],
    three_reports: tuple[int, int, int],
    new_page: Any,
    width: int,
) -> None:
    """The report's tab opens one report and an empty, dashed second panel.

    The developer asked for this (2026-10-29): the reader chooses the second
    report from a list in the empty panel, and can close it again.
    """
    base, _ = live_server
    first, second, third = three_reports
    page = await _open(new_page, base, f"/scans/{third}/compare", width=width)
    await _frame(page, third)
    # The report's own tab opens this page, with no pair in the address.
    tab = page.get_by_role("navigation", name="Report views").get_by_role(
        "link", name="Compare reports"
    )
    await expect(tab).to_have_attribute("href", f"/app/scans/{third}/compare")
    empty = page.get_by_role("region", name="Choose a report to compare with")
    await expect(empty).to_be_visible()
    await expect(empty.locator("iframe")).to_have_count(0)
    box_of_empty = empty.locator("> div")
    edge = await box_of_empty.evaluate("e => getComputedStyle(e).borderTopStyle")
    assert edge == "dashed", edge
    await expect(
        page.get_by_role("link", name="See what changed between these reports")
    ).to_have_count(0)
    # The site's other reports, newest first, each a link to the pair.
    links = empty.get_by_role("link")
    await expect(links).to_have_count(2)
    for index, report in enumerate((second, first)):
        link = links.nth(index)
        await expect(link).to_have_attribute(
            "href", f"/app/scans/{third}/compare?compare_to={report}"
        )
        name = await link.evaluate("e => e.textContent")
        assert name.startswith(f"Report #{report}"), name
        assert "kinds of issue" in name or "kind of issue" in name, name
        assert name.endswith(f"(compare with Report #{third})"), name
        box = await link.bounding_box()
        assert box and box["height"] >= 44, box
    # As tall as the report's panel beside it, when side by side.
    if width == 1280:
        panel_box = await _panel(page, third).bounding_box()
        empty_box = await box_of_empty.bounding_box()
        assert panel_box and empty_box
        assert abs(panel_box["y"] - empty_box["y"]) < 2
        assert abs(panel_box["height"] - empty_box["height"]) < 2, (panel_box, empty_box)
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)

    # Choose one by keyboard: the pair is in the address, and focus moves to
    # the new panel's heading, not the top of the page.
    await links.nth(0).focus()
    await page.keyboard.press("Enter")
    await page.wait_for_url(f"**/app/scans/{third}/compare?compare_to={second}")
    await _frame(page, second)
    chosen = _panel(page, second)
    await expect(chosen.get_by_role("heading", level=2)).to_be_focused()
    top = await _panel(page, third).bounding_box()
    other = await chosen.bounding_box()
    assert top and other
    if width == 320:
        # Stacked, the first panel first, nothing sideways.
        assert other["y"] >= top["y"] + top["height"], (top, other)
        assert abs(other["x"] - top["x"]) < 2
    else:
        assert abs(other["y"] - top["y"]) < 2
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # The picker's label, "Report", is beside its box when the panel has room
    # (the developer asked for that, 2026-10-29) and above it when it does
    # not; it is a visible label either way, not an aria-label.
    label = chosen.locator("label", has_text=re.compile(r"^Report$"))
    picker = chosen.get_by_role("combobox", name="Report")
    await expect(picker).not_to_have_attribute("aria-label", re.compile(".*"))
    label_box, picker_box = await label.bounding_box(), await picker.bounding_box()
    assert label_box and picker_box
    if width == 320:
        assert label_box["y"] + label_box["height"] <= picker_box["y"], (label_box, picker_box)
    else:
        assert label_box["x"] + label_box["width"] <= picker_box["x"], (label_box, picker_box)
        assert label_box["y"] > picker_box["y"], (label_box, picker_box)
        assert label_box["y"] + label_box["height"] < picker_box["y"] + picker_box["height"]

    # Only the second panel can be closed. Its visible word leads the name;
    # the report is screen-reader-only text, not an aria-label.
    await expect(
        _panel(page, third).get_by_role("button", name=re.compile(r"^Close"))
    ).to_have_count(0)
    close = chosen.get_by_role("button", name=f"Close report #{second}", exact=True)
    await expect(close).to_be_visible()
    await expect(close).not_to_have_attribute("aria-label", re.compile(".*"))
    assert (await close.inner_text()).strip().startswith("Close")
    close_box = await close.bounding_box()
    assert close_box and close_box["height"] >= 44, close_box
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)
    # Closing empties the panel; focus goes to the empty panel's heading.
    await close.focus()
    await page.keyboard.press("Enter")
    await page.wait_for_url(f"**/app/scans/{third}/compare")
    await expect(empty.get_by_role("heading", level=2)).to_be_focused()
    await expect(page.locator("iframe")).to_have_count(1)
    # The browser's Back brings the closed report back.
    await page.go_back()
    await page.wait_for_url(f"**/app/scans/{third}/compare?compare_to={second}")
    await _frame(page, second)


async def test_a_site_with_one_report_has_nothing_to_compare_yet(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await _open(new_page, base, f"/scans/{scan_id}/compare")
    empty = page.get_by_role("region", name="Nothing to compare with yet")
    await expect(empty).to_contain_text("This site has one completed report so far.")
    await expect(empty.get_by_role("link")).to_have_count(0)
    violations = await _run_axe(page)
    assert not violations, _render_violations(violations)


async def test_compare_reports_inside_a_panel_does_not_nest(
    live_server: tuple[str, int], three_reports: tuple[int, int, int], new_page: Any
) -> None:
    base, _ = live_server
    _, second, third = three_reports
    page = await _open(new_page, base, f"/scans/{third}/compare?compare_to={second}")
    await _frame(page, third)
    inner = next(f for f in page.frames if f"/scans/{third}/issues" in f.url)
    await inner.evaluate(f"location.assign('/app/scans/{third}/compare?compare_to={second}')")
    frame = _panel(page, third).frame_locator("iframe")
    link = frame.get_by_role("link", name="Open Compare reports in the whole window")
    await expect(link).to_be_visible()
    await expect(link).to_have_attribute("target", "_top")
    await expect(frame.locator("iframe")).to_have_count(0)
    await link.click()
    await page.wait_for_url(f"**/app/scans/{third}/compare?compare_to={second}")
    await expect(page.locator("iframe")).to_have_count(2)


async def test_saved_verify_changes_link_lands_on_what_changed(
    live_server: tuple[str, int], three_reports: tuple[int, int, int], new_page: Any
) -> None:
    """A saved "Verify changes" link lands on What changed, with its baseline."""
    base, _ = live_server
    _, second, third = three_reports
    page = await new_page(viewport={"width": 1280, "height": 800})
    await page.goto(f"{base}/app/scans/{third}/diff?compare_to={second}", wait_until="networkidle")
    await page.wait_for_url(f"**/app/scans/{third}/compare/changes?compare_to={second}")
    await expect(page.get_by_role("heading", name="What changed", level=1)).to_be_visible()
    # Its tab is still Compare reports, which opens the side-by-side page
    # with the second panel empty.
    tab = page.get_by_role("navigation", name="Report views").get_by_role(
        "link", name="Compare reports"
    )
    await expect(tab).to_have_attribute("aria-current", "page")
    await expect(tab).to_have_attribute("href", f"/app/scans/{third}/compare")
