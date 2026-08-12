"""axe-core remains usable on applications with a strict script CSP."""

from __future__ import annotations

from pathlib import Path

import pytest

from audit.analyzer.axe import AxeAnalyzer

pytest.importorskip("playwright.async_api")
pytestmark = pytest.mark.integration


@pytest.fixture
async def page():  # type: ignore[no-untyped-def]
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context()
    try:
        yield await context.new_page()
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


@pytest.mark.asyncio
async def test_axe_runs_without_weakening_strict_content_security_policy(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content(
        "<!doctype html>"
        '<meta http-equiv="Content-Security-Policy" content="script-src \'self\'">'
        '<html lang="en"><head><title>CSP fixture</title></head>'
        '<body><main><h1>Fixture</h1><img src="missing.png"></main></body></html>'
    )

    bundle = Path(__file__).resolve().parents[2] / "src/audit/web/static/axe.min.js"
    findings = await AxeAnalyzer.from_bundled(bundle).run(page)

    assert any(finding.rule_id == "image-alt" for finding in findings)
    assert await page.evaluate("document.querySelectorAll('script').length") == 0
