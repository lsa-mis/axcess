"""The tracker renders only the selected table, with keyboard-operable filters."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from .test_accessibility_axe import _render_violations, _run_axe
from .test_reports_table import DIST, playwright_async

pytestmark = pytest.mark.ui


@pytest.mark.asyncio
async def test_tracker_selection(client: TestClient) -> None:
    payload = client.get("/api/tracking").json()
    async with playwright_async.async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()

            async def respond(route: Any) -> None:
                path = route.request.url.split("tracker.test", 1)[-1].split("?", 1)[0]
                if path == "/api/tracking":
                    await route.fulfill(json=payload)
                elif path.startswith("/api/"):
                    await route.fulfill(status=404, json={"detail": "Unavailable"})
                elif path.startswith("/app/assets/"):
                    await route.fulfill(path=str(DIST / path.removeprefix("/app/")))
                else:
                    await route.fulfill(path=str(DIST / "index.html"))

            await page.route("**/*", respond)
            await page.goto("http://tracker.test/app/tracking", wait_until="networkidle")
            await playwright_async.expect(page.get_by_role("table")).to_have_count(1)
            sections = page.get_by_role("group", name="Tracker sections")
            for label, heading in [
                ("AI roadmap", "AI Roadmap"),
                ("Shipped pipelines", "Shipped Pipelines"),
                ("Current coverage", "Current Coverage"),
                ("Not covered yet", "Not covered yet"),
            ]:
                button = sections.get_by_role("button", name=label, exact=True)
                await button.focus()
                await page.keyboard.press("Enter")
                await playwright_async.expect(button).to_be_focused()
                await playwright_async.expect(button).to_have_attribute("aria-pressed", "true")
                await playwright_async.expect(page.get_by_role("table")).to_have_count(1)
                await playwright_async.expect(
                    page.get_by_role("heading", name=heading)
                ).to_be_visible()
                if label in ("Current coverage", "Not covered yet"):
                    expected_scs = {
                        item["sc"]
                        for item in payload["coverage"]["criteria"]
                        if (item["method"] == "manual") == (label == "Not covered yet")
                    }
                    actual_scs = set(await page.locator("tbody th[scope=row]").all_text_contents())
                    assert {sc.strip() for sc in actual_scs} == expected_scs
                violations = await _run_axe(page)
                assert not violations, _render_violations(violations)
            await sections.get_by_role("button", name="AI roadmap", exact=True).click()
            filters = page.get_by_role("group", name="Filter roadmap by status")
            await filters.get_by_role("button", name="Planned", exact=False).click()
            expected = sum(item["status"] == "planned" for item in payload["roadmap"])
            await playwright_async.expect(page.locator("tbody tr")).to_have_count(expected)
            await page.reload(wait_until="networkidle")
            await playwright_async.expect(page.locator("tbody tr")).to_have_count(expected)
            await playwright_async.expect(page.get_by_role("table")).to_have_count(1)
        finally:
            await browser.close()
