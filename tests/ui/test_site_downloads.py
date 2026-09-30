"""Get started's download links reach the newest release's own files.

Each release holds one file per platform named with its version, so the
page cannot link to a fixed file name. Its links open the newest release's
page, which works without scripts; site.js then points each at its file and
fills the version into the file names the steps show.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]
pytest.importorskip("playwright.async_api")

PAGE = Path(__file__).resolve().parents[2] / "site" / "get-started" / "index.html"
LATEST = "https://github.com/lsa-mis/axcess/releases/latest"
DOWNLOAD = "https://github.com/lsa-mis/axcess/releases/download/desktop-v0.64"
KINDS = {
    "Download for macOS": "Mac-Apple-Silicon.dmg",
    "Download for Windows": "Windows-Installer.exe",
    "Download for Linux": "Linux.AppImage",
    "Download the portable Windows zip (no install)": "Windows-Portable.zip",
}


async def _open(new_page: Any, release: dict[str, Any] | None) -> Any:
    page = await new_page()

    async def api(route: Any) -> None:
        if release is None:
            await route.fulfill(status=503, body="unavailable")
        else:
            await route.fulfill(content_type="application/json", body=json.dumps(release))

    await page.route("https://api.github.com/**", api)
    await page.goto(PAGE.as_uri(), wait_until="networkidle")
    return page


async def test_links_point_at_the_newest_release_files(new_page: Any) -> None:
    names = [f"Axcess-0.64-{kind}" for kind in KINDS.values()]
    release = {
        "tag_name": "desktop-v0.64",
        "html_url": f"{LATEST}",
        "published_at": "2026-09-30T12:00:00Z",
        "assets": [{"name": n, "browser_download_url": f"{DOWNLOAD}/{n}"} for n in names]
        + [{"name": "latest.yml", "browser_download_url": f"{DOWNLOAD}/latest.yml"}],
    }
    page = await _open(new_page, release)
    try:
        for text, kind in KINDS.items():
            link = page.get_by_role("link", name=text, exact=True)
            assert await link.get_attribute("href") == f"{DOWNLOAD}/Axcess-0.64-{kind}"
        shown = await page.locator("code[data-release-name]").all_inner_texts()
        assert shown == [
            "Axcess-0.64-Mac-Apple-Silicon.dmg",
            "Axcess-0.64-Windows-Installer.exe",
            "Axcess-0.64-Linux.AppImage",
        ]
    finally:
        await page.context.close()


async def test_without_the_api_links_open_the_release_page(new_page: Any) -> None:
    page = await _open(new_page, None)
    try:
        for text in KINDS:
            link = page.get_by_role("link", name=text, exact=True)
            assert await link.get_attribute("href") == LATEST
        shown = await page.locator("code[data-release-name]").first.inner_text()
        assert shown == "Axcess-(version)-Mac-Apple-Silicon.dmg"
    finally:
        await page.context.close()
