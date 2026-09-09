"""Integration tests for the live-page error-identification probe (SC 3.3.1).

Real Playwright against hand-built fixtures in
``tests/fixtures/site/error_id/``:

  * ``clean.html``          — invalid field whose error is shown in text and
    tied to it (aria-invalid + aria-describedby) → zero findings (FP guard).
  * ``not_identified.html`` — a ``novalidate`` form with an invalid field and
    no error text → exactly one ``error-not-identified-in-text``.
  * ``not_associated.html`` — a visible error message not linked to the field
    → exactly one ``error-not-programmatically-associated``.

These also prove the safety contract implicitly: the probe calls
``reportValidity()`` (never submits), so navigating away is never triggered
and the ``file://`` page stays put.

Skipped when Playwright / chromium aren't installed; uses ``file://`` URLs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from audit.analyzer.error_id import ErrorIdentificationProbe
from audit.analyzer.error_id.base import RULE_NOT_ASSOCIATED, RULE_NOT_IDENTIFIED

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "error_id"


def _file_url(name: str) -> str:
    return (FIXTURE_DIR / name).resolve().as_uri()


playwright = pytest.importorskip("playwright.async_api")


@pytest.fixture
async def browser():  # type: ignore[no-untyped-def]
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            await browser.close()
    finally:
        await pw.stop()


@pytest.fixture
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


@pytest.mark.asyncio
async def test_properly_associated_error_is_not_flagged(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("clean.html"))
    findings = await ErrorIdentificationProbe().run(page)
    assert findings == [], "clean fixture flagged: " + ", ".join(
        f"{f.rule_id}@{f.target_selector}" for f in findings
    )


@pytest.mark.asyncio
async def test_flags_error_not_identified(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("not_identified.html"))
    findings = await ErrorIdentificationProbe().run(page)
    assert [f.rule_id for f in findings] == [RULE_NOT_IDENTIFIED], findings
    f = findings[0]
    assert f.target_selector == "input#email"
    assert f.criterion_sc == "3.3.1"
    assert f.to_repo_kwargs()["pipeline"] == "error_id"


@pytest.mark.asyncio
async def test_flags_error_not_associated(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("not_associated.html"))
    findings = await ErrorIdentificationProbe().run(page)
    assert [f.rule_id for f in findings] == [RULE_NOT_ASSOCIATED], findings
    assert findings[0].target_selector == "input#email"


@pytest.mark.asyncio
async def test_probe_never_navigates_away(page) -> None:  # type: ignore[no-untyped-def]
    # reportValidity() must not submit: the URL stays on the fixture.
    url = _file_url("not_identified.html")
    await page.goto(url)
    await ErrorIdentificationProbe().run(page)
    assert page.url == url, f"probe navigated away: {page.url}"
