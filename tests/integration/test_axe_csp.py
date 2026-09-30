"""axe-core remains usable on applications with a strict script CSP."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from audit.analyzer.axe import AxeAnalyzer

pytest.importorskip("playwright.async_api")
# One browser per module (tests/integration/conftest.py), so the test runs on
# the module's event loop. It still gets its own context from ``page``.
pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):  # type: ignore[no-untyped-def]
    context = await browser.new_context()
    try:
        yield await context.new_page()
    finally:
        await context.close()


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
