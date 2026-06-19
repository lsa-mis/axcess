"""Playwright + axe-core a11y tests.

Launches a live uvicorn server against a seeded DB, visits each view in a
real chromium instance, injects the vendored axe-core build, runs scan, and
fails if any violations are reported. Also exercises the keyboard-only
navigation flow (j/k, ?, Enter).

Gated on Playwright + vendored axe — skipped cleanly when either is missing.

**Phase 2:** the rule pack is now WCAG 2.2 **AAA** (the actual product
target). Previously the gate was ``wcag2a + wcag2aa`` only, which let AAA
regressions land silently. The discovery audit found 60 nodes failing
``color-contrast-enhanced`` (AAA, 7:1) and 5 failing ``target-size``
(AA, 24 by 24 CSS px) under the broader rule set; both classes are now gated.
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

# Tags scanned. Mirrors the broader set used by ``audits/baseline/.../run_baseline.py``
# so the in-tree gate and the baseline scanner stay in sync.
_AXE_TAGS = [
    "wcag2a",
    "wcag2aa",
    "wcag2aaa",  # 1.4.6 contrast (enhanced), 1.4.8 visual presentation, 2.4.10 section headings, …
    "wcag21a",
    "wcag21aa",
    "wcag22aa",  # 2.5.7 dragging, 2.5.8 target size, 3.2.6 consistent help, ...
    "best-practice",
]


async def _run_axe(page: Any) -> list[dict[str, Any]]:
    """Return the list of axe violations for the current page."""
    await page.add_script_tag(content=_AXE_TEXT)
    result = await page.evaluate(
        """async (tags) => {
            const res = await window.axe.run(document, {
                runOnly: { type: 'tag', values: tags }
            });
            return res.violations;
        }""",
        _AXE_TAGS,
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
async def test_tracking_page_has_no_axe_violations(
    live_server: tuple[str, int],
) -> None:
    # The tool's own coverage page must clear axe — status badges carry
    # text labels (not colour alone) and the tables are properly headed.
    base, _ = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/tracking", wait_until="networkidle")
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
            # Follow the first finding card's title link.
            await page.locator("[data-finding-id] a").first.click()
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

            # j highlights the first card.
            await page.keyboard.press("j")
            await asyncio.sleep(0.1)
            current = page.locator('[data-finding-id][aria-current="true"]')
            assert await current.count() == 1

            # Pressing j again advances; k goes back.
            await page.keyboard.press("j")
            second_id = await page.locator('[data-finding-id][aria-current="true"]').get_attribute(
                "data-finding-id"
            )
            await page.keyboard.press("k")
            first_id = await page.locator('[data-finding-id][aria-current="true"]').get_attribute(
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
async def test_new_scan_form_has_no_axe_violations(
    live_server: tuple[str, int],
) -> None:
    base, _ = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/scans/new", wait_until="networkidle")
            violations = await _run_axe(page)
            assert not violations, _render_violations(violations)
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
