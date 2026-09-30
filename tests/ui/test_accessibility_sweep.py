"""Every screen of the review app, in both themes and at both widths, passes axe.

test_accessibility_axe.py and the route tests scan the screens they drive,
mostly in the light theme at 1280 px. This sweep adds the rest: every
route in App.tsx with the seeded report, each in the light and the dark
theme (contrast differs, SC 1.4.3 and 1.4.6), at 1280 px and at 320 px,
the width SC 1.4.10 Reflow (Level AA) names. The rules are WCAG 2.2 Level
A and AA (``_AXE_TAGS_AA``); the screens the other tests drive also hold
the stricter AAA pack there.

A pass means axe found nothing it can detect. It does not mean a screen
meets WCAG: automated rules cover part of it, and the rest (reading order,
meaningful text alternatives, keyboard use) needs a person.
"""

from __future__ import annotations

from typing import Any

import pytest

from .test_accessibility_axe import _AXE_TAGS_AA, _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

# Every route in src/audit/web/frontend/src/App.tsx, with the seeded
# report's IDs (tests/ui/conftest.py seeds page 1, image finding 1 and the
# image:logo_adequate issue). Redirect-only routes are left out: they land
# on a screen listed here.
_ROUTES = [
    "/app/scans",
    "/app/scans/new",
    "/app/scans/{scan_id}/issues",
    "/app/scans/{scan_id}/issues/image:logo_adequate",
    "/app/scans/{scan_id}/issues/image:logo_adequate/pages",
    "/app/scans/{scan_id}/pages/1",
    "/app/scans/{scan_id}/pages/1/inspect",
    "/app/scans/{scan_id}/findings",
    "/app/scans/{scan_id}/findings/grouped",
    "/app/scans/{scan_id}/a11y",
    "/app/scans/{scan_id}/a11y/by-rule",
    "/app/scans/{scan_id}/compare",
    "/app/scans/{scan_id}/protected",
    "/app/scans/{scan_id}/protected/manual-checks",
    "/app/scans/{scan_id}/protected/issues",
    "/app/findings/1",
    "/app/tracking",
    "/app/about",
    "/app/settings",
    "/app/not-a-real-route",
]


@pytest.mark.parametrize("width", [1280, 320])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("route", _ROUTES)
async def test_screen_has_no_axe_violations(
    live_server: tuple[str, int], new_page: Any, route: str, theme: str, width: int
) -> None:
    base, scan_id = live_server
    path = route.format(scan_id=scan_id)
    page = await new_page()
    try:
        await page.set_viewport_size({"width": width, "height": 800})
        await page.add_init_script(
            f"localStorage.setItem('axcess.preferences', JSON.stringify({{theme: '{theme}'}}))"
        )
        await page.goto(f"{base}{path}", wait_until="networkidle")
        await page.wait_for_selector("main#main *", timeout=5000)
        assert await page.evaluate("document.documentElement.dataset.theme") == theme
        violations = await _run_axe(page, _AXE_TAGS_AA)
        assert not violations, f"{path} ({theme}, {width}px):\n{_render_violations(violations)}"
    finally:
        await page.context.close()
