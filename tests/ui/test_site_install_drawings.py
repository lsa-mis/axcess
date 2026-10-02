"""Get started's install drawings work for every reader.

Each drawing of a macOS or Windows screen is one picture with a text
description (site/build.py, "Drawings of the install screens"). These checks
hold that in a real browser: a screen reader meets one named image and no
fake buttons, the keyboard never stops inside a drawing, nothing scrolls
sideways at 320 px, and axe finds nothing on the page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .test_accessibility_axe import _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

PAGE = Path(__file__).resolve().parents[2] / "site" / "get-started" / "index.html"


async def _open(new_page: Any, width: int) -> Any:
    page = await new_page()
    await page.set_viewport_size({"width": width, "height": 900})
    await page.route("https://api.github.com/**", lambda route: route.abort())
    await page.goto(PAGE.as_uri(), wait_until="networkidle")
    return page


async def test_each_drawing_is_one_named_picture(new_page: Any) -> None:
    page = await _open(new_page, 1280)
    try:
        drawings = page.get_by_role("img", name="Drawing of", exact=False)
        assert await drawings.count() == 7
        assert await page.get_by_role("img", name="Two drawings of", exact=False).count() == 1
        # The drawn buttons are part of the picture, not controls.
        for name in ("Open Anyway", "Run anyway", "Done", "Next >", "Install", "Finish"):
            assert await page.get_by_role("button", name=name, exact=True).count() == 0, name
        focusable = await page.locator(
            ".mock a, .mock button, .mock input, .mock [tabindex]"
        ).count()
        assert focusable == 0
    finally:
        await page.context.close()


@pytest.mark.parametrize("width", [320, 1280])
async def test_drawings_fit_and_pass_axe(new_page: Any, width: int) -> None:
    page = await _open(new_page, width)
    try:
        assert await page.evaluate("document.documentElement.scrollWidth") <= width
        overflow = await page.evaluate(
            """() => [...document.querySelectorAll('.mock')]
                 .filter(m => m.scrollWidth > m.clientWidth + 1).length"""
        )
        assert overflow == 0
        violations = await _run_axe(page)
        assert not violations, _render_violations(violations)
    finally:
        await page.context.close()
