"""The About page names the build that is running.

The desktop app's version goes up with every release, but the web bundle
inside it is built before the release stamps that number, so the page reads
it from the app's user agent ("Axcess/0.2.3") rather than from the bundle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

FRONTEND_PACKAGE = Path(__file__).parents[2] / "src/audit/web/frontend/package.json"
# The user agent Electron 43 sends from a release stamped 0.2.37.
DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Axcess/0.2.37 Chrome/150.0.7871.224 Electron/43.4.0 "
    "Safari/537.36"
)


async def _build_fact(new_page: Any, base: str, **options: Any) -> str:
    page = await new_page(viewport={"width": 1280, "height": 900}, **options)
    await page.goto(f"{base}/app/about")
    facts = page.get_by_role("list", name="At a glance").get_by_role("listitem")
    return str(await facts.last.inner_text())


async def test_desktop_app_shows_its_own_release_version(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _scan_id = live_server
    assert await _build_fact(new_page, base, user_agent=DESKTOP_UA) == "Desktop preview 0.2.37"


async def test_browser_shows_the_web_bundle_version(
    live_server: tuple[str, int], new_page: Any
) -> None:
    base, _scan_id = live_server
    version = json.loads(FRONTEND_PACKAGE.read_text())["version"]
    assert await _build_fact(new_page, base) == f"Preview {version}"
