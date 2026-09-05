"""Keyboard and state-safety tests for the simplified expert report."""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.ui

playwright_async = pytest.importorskip("playwright.async_api")


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_suffix", ("review", "manual-checks", "handoff"))
async def test_removed_workflow_routes_redirect_to_the_issue_table(
    live_server: tuple[str, int],
    legacy_suffix: str,
) -> None:
    """Saved links remain safe without preserving the removed multi-step UI."""
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(
                f"{base}/app/scans/{scan_id}/{legacy_suffix}",
                wait_until="networkidle",
            )
            await page.wait_for_url(f"**/app/scans/{scan_id}/issues")
            await playwright_async.expect(
                page.get_by_role("heading", name="Issues", exact=True, level=1)
            ).to_be_visible()
            assert await page.get_by_role("listbox").count() == 0
            assert await page.get_by_role("button", name="Apply decision").count() == 0
            assert await page.get_by_role("button", name="Save decision").count() == 0
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_export_menu_offers_every_format_with_the_draft_label_in_urls(
    live_server: tuple[str, int],
) -> None:
    """One control carries all four downloads, each acknowledging draft state."""
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
            trigger = page.get_by_role("button", name="Export")
            await playwright_async.expect(trigger).to_have_attribute("aria-expanded", "false")
            await trigger.click()
            await playwright_async.expect(trigger).to_have_attribute("aria-expanded", "true")
            for name, fmt in (
                ("Remediation workbook", "xlsx"),
                ("Audit report", "audit"),
                ("Issue table", "csv"),
                ("Raw findings", "json"),
            ):
                link = page.get_by_role("link", name=name)
                await playwright_async.expect(link).to_be_visible()
                href = await link.get_attribute("href")
                assert href is not None
                assert f"/export/{fmt}" in href
                assert "draft=acknowledged" in href
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_export_menu_closes_on_escape_and_returns_focus(
    live_server: tuple[str, int],
) -> None:
    """Dismissing the disclosure never drops focus to the top of the document."""
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
            trigger = page.get_by_role("button", name="Export")
            await trigger.click()
            await playwright_async.expect(
                page.get_by_role("link", name="Remediation workbook")
            ).to_be_visible()
            await page.keyboard.press("Escape")
            await playwright_async.expect(
                page.get_by_role("link", name="Remediation workbook")
            ).to_be_hidden()
            await playwright_async.expect(trigger).to_be_focused()
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_issue_table_filters_are_keyboard_operable(
    live_server: tuple[str, int],
) -> None:
    """The simplified table needs only ordinary form and link interactions."""
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/app/scans/{scan_id}/issues", wait_until="networkidle")
            search = page.get_by_label("Search issues")
            await search.focus()
            await search.fill("logo")
            await page.wait_for_url("**?q=logo")
            await playwright_async.expect(
                page.get_by_role("link", name="Logo image, adequate alt")
            ).to_be_visible()
            await search.press("Tab")
            await playwright_async.expect(
                page.get_by_label("WCAG level", exact=True)
            ).to_be_focused()
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_cancelled_legacy_rationale_prompt_keeps_the_persisted_status(
    live_server: tuple[str, int],
) -> None:
    """Specialized legacy evidence remains safe even though it is not primary navigation."""
    base, _ = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/app/findings/1", wait_until="networkidle")
            status = page.get_by_label("Status:")
            persisted = await status.input_value()
            await status.select_option("in_progress")
            page.once(
                "dialog",
                lambda dialog: asyncio.create_task(dialog.dismiss()),
            )
            await page.get_by_role("button", name="Save", exact=True).click()
            await page.get_by_text("Status unchanged", exact=True).wait_for()
            assert await status.input_value() == persisted
        finally:
            await browser.close()
