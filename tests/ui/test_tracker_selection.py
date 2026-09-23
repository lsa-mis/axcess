"""The tracker is one table narrowed by keyboard-operable group and status filters."""

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from .test_accessibility_axe import _render_violations, _run_axe
from .test_reports_table import DIST, playwright_async

# One browser per module (tests/ui/conftest.py), so the tests run on the
# module's event loop. Each ``new_page`` call still opens its own context.
pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]


async def test_tracker_selection(client: TestClient, new_page: Any) -> None:
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
    # Every group and the AI roadmap share one table; the group chips
    # narrow it in place and keep focus on the chip that was pressed.
    sections = page.get_by_role("group", name="Tracker sections")
    for label in ("AI Coverage", "Current Coverage", "Future Coverage", "All"):
        button = sections.get_by_role("button", name=re.compile(rf"^{label} \(\d+\)$"))
        await button.focus()
        await page.keyboard.press("Enter")
        await playwright_async.expect(button).to_be_focused()
        await playwright_async.expect(button).to_have_attribute("aria-pressed", "true")
        actual_scs = set(await matrix.locator("tbody th[scope=row]").all_text_contents())
        assert {sc.strip() for sc in actual_scs} == expected_by_view[label], label
        # The chips cross-fade their colours; let that settle before
        # axe samples a mid-transition foreground against background.
        await page.evaluate("Promise.all(document.getAnimations().map((a) => a.finished))")
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    # The status sub-filter only exists inside AI Coverage, and it
    # survives a reload because it lives in the URL.
    await playwright_async.expect(
        page.get_by_role("group", name="Filter AI coverage by status")
    ).to_have_count(0)
    await sections.get_by_role("button", name=re.compile(r"^AI Coverage")).click()
    filters = page.get_by_role("group", name="Filter AI coverage by status")
    await filters.get_by_role("button", name="Planned", exact=False).click()
    expected = sum(item["status"] == "planned" for item in payload["roadmap"])
    await playwright_async.expect(matrix.locator("tbody tr")).to_have_count(expected)
    await page.reload(wait_until="networkidle")
    await playwright_async.expect(matrix.locator("tbody tr")).to_have_count(expected)
    # Leaving the group drops its sub-filter rather than carrying a
    # status that no coverage row could match.
    await sections.get_by_role("button", name=re.compile(r"^Current Coverage")).click()
    await playwright_async.expect(matrix.locator("tbody th[scope=row]")).to_have_count(
        len(expected_by_view["Current Coverage"])
    )
    assert "status=" not in page.url
