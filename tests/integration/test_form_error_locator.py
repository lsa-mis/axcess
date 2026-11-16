"""Each form's element locator (CSS selector) matches that form alone.

The report points a reviewer at a failing form by this locator, and the
before/after screenshots find the form with it. It used to stop after five
steps, and on primevue.org that matched four forms, so the pictures showed
the wrong one. Here two identical forms sit seven wrappers deep.
"""

from __future__ import annotations

import pytest

from audit.analyzer.forms import ErrorIdentificationProbe

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

_DEEP = "<div><div><div><div><div><div><div>{form}</div></div></div></div></div></div></div>"
# Labels differ only because the check presents identical forms once.
_FORM = """<form novalidate><label for="{id}">{label}</label><input id="{id}">
<button type="submit">Send</button></form>"""
_PAGE = (
    '<!doctype html><html lang="en"><head><title>Twins</title></head><body><main>'
    + "<section>"
    + _DEEP.format(form=_FORM.format(id="a", label="Name"))
    + "</section><section>"
    + _DEEP.format(form=_FORM.format(id="b", label="Email"))
    + "</section></main></body></html>"
)


async def test_each_form_locator_matches_one_form(browser) -> None:  # type: ignore[no-untyped-def]
    context = await browser.new_context(service_workers="block")
    page = await context.new_page()
    await page.route(
        "http://twins.test/", lambda r: r.fulfill(body=_PAGE, content_type="text/html")
    )
    try:
        await page.goto("http://twins.test/")
        results = await ErrorIdentificationProbe().run(page)
        selectors = [r.selector for r in results]
        assert len(selectors) == 2 and selectors[0] != selectors[1], selectors
        for selector in selectors:
            assert await page.locator(selector).count() == 1, selector
    finally:
        await context.close()
