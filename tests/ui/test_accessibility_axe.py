"""Playwright + axe-core a11y tests.

Launches a live uvicorn server against a seeded DB, visits each view in a
real chromium instance, injects the vendored axe-core build, runs scan, and
fails if any violations are reported. Also exercises the keyboard-only
navigation flow (j/k, ?, Enter).

Gated on Playwright + vendored axe — skipped cleanly when either is missing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.ui

playwright_async = pytest.importorskip("playwright.async_api")

_AXE_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "audit" / "web" / "static" / "axe.min.js"
)

if not _AXE_SCRIPT_PATH.exists():  # pragma: no cover - gated
    pytest.skip("axe-core bundle not vendored", allow_module_level=True)

_AXE_TEXT = _AXE_SCRIPT_PATH.read_text(encoding="utf-8")


async def _run_axe(page: Any) -> list[dict[str, Any]]:
    """Return the list of axe violations for the current page."""
    await page.add_script_tag(content=_AXE_TEXT)
    result = await page.evaluate(
        """async () => {
            const res = await window.axe.run(document, {
                runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
            });
            return res.violations;
        }"""
    )
    return list(result)


def _render_violations(violations: list[dict[str, Any]]) -> str:
    lines = []
    for v in violations:
        lines.append(f"{v.get('id')} ({v.get('impact')}): {v.get('help')}")
        for node in v.get("nodes", [])[:3]:
            target = node.get("target", ["?"])
            lines.append(f"  target: {target}")
    return "\n".join(lines) or "(no details)"


@pytest.mark.asyncio
async def test_scan_list_has_no_axe_violations(
    live_server: tuple[str, int],
) -> None:
    base, _ = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/scans", wait_until="networkidle")
            violations = await _run_axe(page)
            assert not violations, _render_violations(violations)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_findings_list_has_no_axe_violations(
    live_server: tuple[str, int],
) -> None:
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/scans/{scan_id}/findings", wait_until="networkidle")
            violations = await _run_axe(page)
            assert not violations, _render_violations(violations)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_finding_detail_has_no_axe_violations(
    live_server: tuple[str, int],
) -> None:
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/scans/{scan_id}/findings", wait_until="networkidle")
            # Follow the first finding link.
            await page.locator("table.data a").first.click()
            await page.wait_for_load_state("networkidle")
            violations = await _run_axe(page)
            assert not violations, _render_violations(violations)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_page_detail_has_no_axe_violations(
    live_server: tuple[str, int],
) -> None:
    base, _ = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/pages/1", wait_until="networkidle")
            violations = await _run_axe(page)
            assert not violations, _render_violations(violations)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_keyboard_navigation_j_k_opens_finding(
    live_server: tuple[str, int],
) -> None:
    base, scan_id = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/scans/{scan_id}/findings", wait_until="networkidle")

            # j highlights the first row.
            await page.keyboard.press("j")
            await asyncio.sleep(0.1)
            current = page.locator('tr[aria-current="true"]')
            assert await current.count() == 1

            # Pressing j again advances, k goes back.
            await page.keyboard.press("j")
            second_id = await page.locator('tr[aria-current="true"]').get_attribute(
                "data-finding-id"
            )
            await page.keyboard.press("k")
            first_id = await page.locator('tr[aria-current="true"]').get_attribute(
                "data-finding-id"
            )
            assert first_id != second_id

            # Enter on the focused link should navigate to the finding page.
            await page.keyboard.press("Enter")
            await page.wait_for_url("**/findings/**", timeout=5000)
            assert "/findings/" in page.url
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_skip_link_reachable_by_tab(live_server: tuple[str, int]) -> None:
    base, _ = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/scans", wait_until="networkidle")
            await page.keyboard.press("Tab")
            active = await page.evaluate("() => document.activeElement.className")
            assert "skip-link" in active
        finally:
            await browser.close()
