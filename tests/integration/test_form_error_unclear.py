"""Which failures the form error check reports Not sure.

The developer's decision, 2026-11-05: a clear failure is Mostly sure; a
failure that shows one of the four kinds of page an expert has yet to decide
is Not sure (``Attempt.unclear``, ``RULE_UNCLEAR``). This holds the line
between them on the cases written for each kind (``a01`` to ``a04``) and on
two clear failures that must stay clear: a border that turns red (``f01``)
and a radio group's question that turns red (``f10``), which the first
version took for a requirement hint.
"""

from __future__ import annotations

from typing import Any

import pytest

from audit.analyzer.forms import ErrorIdentificationProbe, FormFinding

from .form_error_cases import CASES

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

_BY_ID = {case.id: case for case in CASES}
_SIGN = {
    "a01_static_required_turns_red": "turned an error colour",
    "a02_screen_reader_only_text": "only screen readers get",
    "a03_placeholder_message": "placeholder",
    "a04_image_with_alt": "alt text",
}


async def _result(browser: Any, case_id: str) -> Any:
    html = _BY_ID[case_id].html()
    url = f"http://cases.test/{case_id}.html"

    async def serve(route: Any) -> None:
        await route.fulfill(body=html, content_type="text/html")

    context = await browser.new_context(service_workers="block")
    await context.route(url, serve)
    page = await context.new_page()
    try:
        await page.goto(url)
        results = await ErrorIdentificationProbe().run(page)
    finally:
        await context.close()
    assert len(results) == 1, results
    return results[0]


@pytest.mark.parametrize("case_id", sorted(_SIGN))
async def test_an_undecided_kind_of_page_is_not_sure(browser: Any, case_id: str) -> None:
    result = await _result(browser, case_id)
    assert result.outcome == "fail", result
    assert any(_SIGN[case_id] in sign for sign in result.unclear), result.unclear
    assert FormFinding.from_result(result).rule_id == "form-error-identification-unclear"


@pytest.mark.parametrize("case_id", ["f01_border_only", "f10_radio_legend_red"])
async def test_a_clear_failure_is_mostly_sure(browser: Any, case_id: str) -> None:
    result = await _result(browser, case_id)
    assert result.outcome == "fail", result
    assert result.unclear == [], result.unclear
    assert FormFinding.from_result(result).rule_id == "form-error-identification"
