"""The report's Export panel, driven the way a keyboard or screen-reader user would.

The panel names the report and says, before any download, how large each
file is, that every file covers the whole report whatever the table's
filters, and when the files will be marked DRAFT. Each download then reports
its progress and its outcome in words, in the row and in a live region.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from .test_accessibility_axe import _AXE_TAGS, _AXE_TEXT, _render_violations

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect

_FORMATS = ("Remediation workbook", "Audit report", "Issue table", "Raw findings")


async def _open_by_keyboard(page: Any) -> Any:
    trigger = page.get_by_role("button", name="Export")
    await trigger.focus()
    await page.keyboard.press("ArrowDown")
    await expect(trigger).to_have_attribute("aria-expanded", "true")
    return trigger


async def test_panel_says_what_each_download_delivers(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await _open_by_keyboard(page)

    panel = page.get_by_role("group", name=f"Export Scan {scan_id}")
    await expect(panel.get_by_role("heading", name=f"Export Scan {scan_id}")).to_be_visible()
    # Each link's name is its label alone; the format and the size are its
    # description, so a links list stays short.
    for name in _FORMATS:
        link = panel.get_by_role("link", name=name, exact=True)
        await expect(link).to_have_accessible_description(
            re.compile(r" about \d+(\.\d)? (B|KB|MB)$")
        )
    # The seeded scan's expert review is unfinished.
    await expect(panel).to_contain_text("each file is marked DRAFT")
    await expect(panel).to_contain_text("whatever the table\u2019s filters")
    await expect(panel).to_contain_text("not a conformance verdict")

    # Scoped to the panel: the rest of the page has its own axe coverage.
    await page.add_script_tag(content=_AXE_TEXT)
    violations = await page.evaluate(
        """async (tags) => (await window.axe.run(
            document.querySelector('[role=group][aria-labelledby]'),
            { runOnly: { type: 'tag', values: tags } },
        )).violations""",
        _AXE_TAGS,
    )
    assert not violations, _render_violations(violations)


async def test_arrow_keys_move_between_downloads(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page()
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    trigger = await _open_by_keyboard(page)

    link = lambda name: page.get_by_role("link", name=name, exact=True)  # noqa: E731
    await expect(link("Remediation workbook")).to_be_focused()
    await page.keyboard.press("ArrowDown")
    await expect(link("Audit report")).to_be_focused()
    await page.keyboard.press("End")
    await expect(link("Raw findings")).to_be_focused()
    await page.keyboard.press("ArrowUp")
    await expect(link("Issue table")).to_be_focused()
    await page.keyboard.press("Home")
    await expect(link("Remediation workbook")).to_be_focused()
    await page.keyboard.press("Escape")
    await expect(trigger).to_be_focused()
    await expect(trigger).to_have_attribute("aria-expanded", "false")


async def test_download_reports_its_outcome_and_keeps_focus(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page(accept_downloads=True)
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await _open_by_keyboard(page)
    workbook = page.get_by_role("link", name="Remediation workbook", exact=True)

    async with page.expect_download() as download_info:
        await page.keyboard.press("Enter")
    download = await download_info.value

    assert download.suggested_filename == f"scan_{scan_id}_DRAFT.xlsx"
    await expect(workbook).to_contain_text(f"Downloaded scan_{scan_id}_DRAFT.xlsx")
    await expect(page.get_by_role("status").filter(has_text="Downloading")).to_have_text(
        re.compile(rf"^Downloading scan_{scan_id}_DRAFT\.xlsx, \d+ KB\.$")
    )
    # The panel stays open with focus where it was, ready for a second file.
    await expect(workbook).to_be_focused()


async def test_a_failed_download_is_reported_in_words(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, scan_id = live_server
    page = await new_page(accept_downloads=True)
    await page.route(
        re.compile(r"/api/scans/\d+/export/csv"),
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"detail": "Export renderer crashed."}',
        ),
    )
    downloads: list[Any] = []
    page.on("download", lambda download: downloads.append(download))
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await page.get_by_role("button", name="Export").click()

    table = page.get_by_role("link", name="Issue table", exact=True)
    await table.click()

    await expect(table).to_contain_text("Couldn\u2019t download. Export renderer crashed.")
    announcement = page.get_by_role("status").filter(has_text="download the issue table")
    await expect(announcement).to_have_text(
        "Couldn\u2019t download the issue table. Export renderer crashed."
    )
    assert downloads == []


async def test_panel_stays_beside_the_content_when_the_header_wraps(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """A right-hung panel reached back under the sidebar once the button wrapped."""
    base, scan_id = live_server
    page = await new_page(viewport={"width": 900, "height": 800})
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await page.get_by_role("button", name="Export").click()

    panel = await page.get_by_role("group", name=f"Export Scan {scan_id}").bounding_box()
    main = await page.locator("main").bounding_box()
    assert panel is not None and main is not None
    assert panel["x"] >= main["x"]
    assert panel["x"] + panel["width"] <= main["x"] + main["width"]


async def test_missing_sizes_are_explained_and_downloads_still_offered(
    live_server: tuple[str, int], new_page: Any
) -> None:
    """A server without the sizes endpoint left the size column silently blank."""
    base, scan_id = live_server
    page = await new_page()
    await page.route(
        re.compile(r"/api/scans/\d+/exports$"),
        lambda route: route.fulfill(
            status=404, content_type="application/json", body='{"detail": "Not Found"}'
        ),
    )
    await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
    await page.get_by_role("button", name="Export").click()

    panel = page.get_by_role("group", name=f"Export Scan {scan_id}")
    await expect(panel).to_contain_text(
        "Couldn\u2019t check file sizes or draft status. The downloads still work."
    )
    for name in _FORMATS:
        await expect(panel.get_by_role("link", name=name, exact=True)).to_be_visible()
