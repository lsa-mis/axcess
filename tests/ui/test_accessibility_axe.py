"""Playwright + axe-core a11y tests against the React SPA.

Launches a live uvicorn server against a seeded DB, drives the React
bundle under ``/app/`` in a real chromium instance, injects the vendored
axe-core build, runs a scan, and fails on any violations.

Gated on three things, each skipped cleanly when missing: Playwright, the
vendored axe build, and a built SPA bundle (``npm run build``). The legacy
Jinja pages these tests used to cover are gone — the SPA is the only UI.

The rule pack is WCAG 2.2 **AAA** (the product target), so AAA contrast
and target-size regressions fail here, not just AA.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.ui

playwright_async = pytest.importorskip("playwright.async_api")

_WEB = Path(__file__).resolve().parents[2] / "src" / "audit" / "web"
_AXE_SCRIPT_PATH = _WEB / "static" / "axe.min.js"
_DIST_INDEX = _WEB / "frontend" / "dist" / "index.html"

if not _AXE_SCRIPT_PATH.exists():  # pragma: no cover - gated
    pytest.skip("axe-core bundle not vendored", allow_module_level=True)
if not _DIST_INDEX.exists():  # pragma: no cover - gated
    pytest.skip("SPA bundle not built (run `npm run build`)", allow_module_level=True)

_AXE_TEXT = _AXE_SCRIPT_PATH.read_text(encoding="utf-8")

# Tags scanned. Mirrors the broader set used by the baseline scanner so the
# in-tree gate and the baseline stay in sync.
_AXE_TAGS = [
    "wcag2a",
    "wcag2aa",
    "wcag2aaa",
    "wcag21a",
    "wcag21aa",
    "wcag22aa",
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


async def _axe_clean(base: str, path: str) -> None:
    """Open a SPA route, wait for React to settle, assert no axe violations."""
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}{path}", wait_until="networkidle")
            # The SPA renders into #main; wait for it to have content so axe
            # doesn't scan an empty shell.
            await page.wait_for_selector("main#main *", timeout=5000)
            violations = await _run_axe(page)
            assert not violations, f"{path}:\n{_render_violations(violations)}"
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_dashboard_has_no_axe_violations(live_server: tuple[str, int]) -> None:
    base, _ = live_server
    await _axe_clean(base, "/app/")


@pytest.mark.asyncio
async def test_scans_list_has_no_axe_violations(live_server: tuple[str, int]) -> None:
    base, _ = live_server
    await _axe_clean(base, "/app/scans")


@pytest.mark.asyncio
async def test_tracking_page_has_no_axe_violations(live_server: tuple[str, int]) -> None:
    # The tool's own coverage page must clear axe — status badges carry
    # text labels (not colour alone) and the tables are properly headed.
    base, _ = live_server
    await _axe_clean(base, "/app/tracking")


@pytest.mark.asyncio
async def test_findings_list_has_no_axe_violations(live_server: tuple[str, int]) -> None:
    base, scan_id = live_server
    await _axe_clean(base, f"/app/scans/{scan_id}/findings")


@pytest.mark.asyncio
async def test_new_scan_form_has_no_axe_violations(live_server: tuple[str, int]) -> None:
    base, _ = live_server
    await _axe_clean(base, "/app/scans/new")


@pytest.mark.asyncio
async def test_skip_link_reachable_by_tab(live_server: tuple[str, int]) -> None:
    """The SPA's skip-link must be the first Tab stop and point at #main."""
    base, _ = live_server
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/app/scans", wait_until="networkidle")
            await page.keyboard.press("Tab")
            href = await page.evaluate(
                "() => document.activeElement && document.activeElement.getAttribute('href')"
            )
            assert href == "#main"
        finally:
            await browser.close()
