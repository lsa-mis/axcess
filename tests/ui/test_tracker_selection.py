"""The tracker is one table narrowed by keyboard-operable group and status filters."""

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ._paging import all_pages_text
from .test_accessibility_axe import _render_violations, _run_axe
from .test_reports_table import DIST, playwright_async

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]


async def test_tracker_selection(client: TestClient, new_page: Any, choose_filter: Any) -> None:
    # The pages are served from the built SPA, as in test_reports_table.
    if not (DIST / "index.html").exists():
        pytest.skip("Build the frontend first")
    payload = client.get("/api/tracking").json()
    page = await new_page()

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
    matrix = page.get_by_role("table", name="WCAG 2.2 A/AA coverage and AI roadmap")
    criteria = payload["coverage"]["criteria"]
    expected_by_view = {
        "Current Coverage": {c["sc"] for c in criteria if c["method"] != "manual"},
        "Future Coverage": {c["sc"] for c in criteria if c["method"] == "manual"},
        "AI Coverage": {item["wcag"] for item in payload["roadmap"]},
    }
    expected_by_view["All"] = set().union(*expected_by_view.values())
    # Every section and the AI roadmap share one table; the Section group
    # of the Filter menu narrows it in place, and Escape hands focus back
    # to the menu's button.
    filter_button = page.get_by_role("button", name=re.compile(r"^Filter\b"))
    views = {
        "AI Coverage": "ai",
        "Current Coverage": "current",
        "Future Coverage": "future",
        "All": "",
    }
    for label, value in views.items():
        await choose_filter(page, "Section", value)
        await playwright_async.expect(filter_button).to_be_focused()
        # Ten rows a page: read every page of the table.
        actual_scs = set(
            await all_pages_text(page, matrix.locator("tbody th[scope=row]"), "Criteria")
        )
        assert actual_scs == expected_by_view[label], label
        # Let transitions (the menu's chevron, the Filter button's fill)
        # settle before axe samples a mid-transition foreground against
        # background.
        await page.evaluate("Promise.all(document.getAnimations().map((a) => a.finished))")
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    # The status sub-filter only exists inside AI Coverage, and it
    # survives a reload because it lives in the URL.
    await playwright_async.expect(
        page.get_by_role("group", name="Status", exact=True, include_hidden=True)
    ).to_have_count(0)
    await choose_filter(page, "Section", "ai")
    await choose_filter(page, "Status", "planned")
    expected = sum(item["status"] == "planned" for item in payload["roadmap"])
    await playwright_async.expect(matrix.locator("tbody tr")).to_have_count(min(expected, 10))
    await page.reload(wait_until="networkidle")
    await playwright_async.expect(matrix.locator("tbody tr")).to_have_count(min(expected, 10))
    # Leaving the section drops its sub-filter rather than carrying a
    # status that no coverage row could match.
    await choose_filter(page, "Section", "current")
    current = expected_by_view["Current Coverage"]
    await playwright_async.expect(matrix.locator("tbody th[scope=row]")).to_have_count(
        min(len(current), 10)
    )
    rows = await all_pages_text(page, matrix.locator("tbody th[scope=row]"), "Criteria")
    assert set(rows) == current
    assert "status=" not in page.url
