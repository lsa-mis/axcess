"""The desktop app's own screens and the public site pass axe.

Outside the review app, people meet three more kinds of screen: the
desktop app's loading screen, its "Axcess could not start" screen, and
the public site (site/), where they download it. None had an axe scan.
Each is a static file, opened here from disk in both colour schemes (the
site and the desktop screens follow ``prefers-color-scheme``) and at
1280 px and 320 px (SC 1.4.10 Reflow, Level AA), against WCAG 2.2 Level
A and AA (``_AXE_TAGS_AA``).

A pass means axe found nothing it can detect, not that a page meets WCAG.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from .test_accessibility_axe import _AXE_TAGS_AA, _render_violations, _run_axe

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

_ROOT = Path(__file__).resolve().parents[2]
_SITE_PAGES = sorted((_ROOT / "site").glob("**/index.html"))
_DESKTOP = _ROOT / "desktop" / "static"

# The error screen fills itself from its query string (desktop/static/
# error.js): the reason, the backend's last output and the log path. All
# three are shown, as they are when the app fails to start.
_ERROR_QUERY = urlencode(
    {
        "reason": "The backend did not start within 60 seconds.",
        "output": "Traceback (most recent call last):\n  OSError: address in use",
        "log": r"C:\Users\someone\AppData\Roaming\Axcess\data\logs\launcher.log",
        "packaged": "1",
    }
)

_PAGES = [
    *(pytest.param(page.as_uri(), id=str(page.relative_to(_ROOT))) for page in _SITE_PAGES),
    pytest.param((_DESKTOP / "loading.html").as_uri(), id="desktop/static/loading.html"),
    pytest.param(
        f"{(_DESKTOP / 'loading.html').as_uri()}#first-launch",
        id="desktop/static/loading.html#first-launch",
    ),
    pytest.param(
        f"{(_DESKTOP / 'error.html').as_uri()}?{_ERROR_QUERY}", id="desktop/static/error.html"
    ),
]


def test_the_site_pages_are_found() -> None:
    assert len(_SITE_PAGES) >= 8


@pytest.mark.parametrize("width", [1280, 320])
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("url", _PAGES)
async def test_static_page_has_no_axe_violations(
    new_page: Any, url: str, scheme: str, width: int
) -> None:
    # The desktop screens forbid inline scripts (a Content-Security-Policy
    # of default-src 'none'), which would block injecting axe itself.
    page = await new_page(
        bypass_csp=True, color_scheme=scheme, viewport={"width": width, "height": 800}
    )
    try:
        await page.goto(url, wait_until="load")
        violations = await _run_axe(page, _AXE_TAGS_AA)
        assert not violations, f"{url} ({scheme}, {width}px):\n{_render_violations(violations)}"
    finally:
        await page.context.close()


@pytest.mark.parametrize("first", [False, True])
async def test_the_loading_screen_mentions_a_first_launch_only_then(
    new_page: Any, first: bool
) -> None:
    """main.cjs opens loading.html#first-launch when there is no database yet."""
    page = await new_page(bypass_csp=True)
    try:
        url = (_DESKTOP / "loading.html").as_uri() + ("#first-launch" if first else "")
        await page.goto(url, wait_until="load")
        note = page.get_by_role("status").get_by_text("The first time Axcess opens")
        assert await note.is_visible() is first
    finally:
        await page.context.close()
