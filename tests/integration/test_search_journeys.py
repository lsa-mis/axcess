"""Bounded search behavior in real browser DOMs, with no external traffic."""

from __future__ import annotations

import pytest
from playwright.async_api import Route, async_playwright

from audit.analyzer.axe import AxeAnalyzer
from audit.crawler.orchestrator import CrawlConfig, build_search_explorer
from audit.crawler.search import SearchConfig, SearchField, SearchTarget

pytestmark = pytest.mark.integration
BASE = "https://search.example.test/"


@pytest.mark.parametrize("scenario", ["delayed_route", "dom_state", "empty", "unsafe", "limit"])
async def test_search_submits_selected_fields_and_records_outcomes(scenario: str) -> None:
    actions = {
        "delayed_route": "setTimeout(()=>location.href='/report',700)",
        "dom_state": (
            "document.querySelector('aside').innerHTML="
            "'<img src=/image><a href=/details>Details</a>'"
        ),
        "limit": "location.href='/report'",
    }
    results = ""
    if scenario in actions:
        results = (
            f'<button type="button" role="option" onclick="{actions[scenario]}">'
            "Open report</button>"
        )
    if scenario == "limit":
        results += '<a role="option" href="/second">Second report</a>'
    input_type = "password" if scenario == "unsafe" else "search"
    html = f"""<!doctype html><html lang=en><title>Search fixture</title><main><h1>Reports</h1>
    <form onsubmit="event.preventDefault(); window.submitted++;
      document.querySelector('section').innerHTML=document.querySelector('template').innerHTML">
    <label>Search<input type={input_type}></label>
    <label>Category<select><option>All</option><option>Reports</option></select></label>
    <button>Find reports</button></form><section></section><aside></aside>
    <template>{results}</template><script>window.submitted=0</script></main></html>"""
    search = SearchConfig(
        confirmed=True,
        fields=(
            SearchField(target="Search", value="sample"),
            SearchField(target="Category", value="Reports", kind="select"),
        ),
        submit=SearchTarget(target="Find reports"),
        results_selector="section [role=option]",
        max_results=1 if scenario == "limit" else 10,
        timeout_ms=1200,
    )
    axe = AxeAnalyzer.from_bundled()
    explorer = build_search_explorer(CrawlConfig(seed_url=BASE, search=search), axe)
    assert explorer is not None
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()

            async def serve(route: Route) -> None:
                await route.fulfill(content_type="text/html", body=html)

            await page.route("**/*", serve)
            await page.goto(BASE)
            result = await explorer.run(page, baseline=())
            if scenario == "unsafe":
                assert result.outcome.status == "failed"
                assert await page.evaluate("window.submitted") == 0
                assert await page.get_by_label("Search", exact=True).input_value() == ""
            elif scenario == "empty":
                assert result.outcome.status == "no_results"
                assert result.outcome.states == 0
            elif scenario == "dom_state":
                assert result.outcome.status == "completed"
                assert result.outcome.states == 2
                assert BASE + "details" in result.urls
                assert any(item.violation.rule_id == "image-alt" for item in result.findings)
            else:
                assert result.outcome.status == ("limited" if scenario == "limit" else "completed")
                assert BASE + "report" in result.urls
                assert BASE + "second" not in result.urls
            assert "sample" not in result.outcome.detail
        finally:
            await browser.close()
