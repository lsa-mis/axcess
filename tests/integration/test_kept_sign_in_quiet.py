"""Keeping the sign-in never opens a tab in the person's sign-in window.

The kept copy refreshes every few seconds while the sign-in window is open.
It used Playwright's ``storage_state()``, which reads each site the browser
has visited and, for one that is no longer open in a tab (the U-M or Duo
sign-in page the person passed through), opens a tab, loads the site and
closes it: in the visible sign-in window, a tab flashing open and shut every
few seconds. ``_quiet_storage`` reads cookies and the open tabs' local
storage instead, and keeps what it read earlier for sites that are gone.

A real headless Chromium; both sites are fulfilled locally.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.async_api import Route, async_playwright

from audit.protected.session import _KeptSignIn, _quiet_storage

pytestmark = pytest.mark.integration

IDP = "https://idp.example.test"
APP = "https://app.example.test"
PAGE = """<!doctype html><title>{name}</title><script>
localStorage.setItem('{name}-token', 'signed-in');
document.cookie = '{name}=yes; path=/';
</script>"""


async def test_refreshing_the_kept_sign_in_opens_no_tab() -> None:
    async def serve(route: Route) -> None:
        name = "idp" if route.request.url.startswith(IDP) else "app"
        await route.fulfill(status=200, content_type="text/html", body=PAGE.format(name=name))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        await context.route("**/*", serve)
        opened: list[Any] = []
        page = await context.new_page()

        # Sign-in passes through the identity provider, then lands on the app.
        await page.goto(f"{IDP}/login")
        first = _KeptSignIn(storage=await _quiet_storage(context, None), tab_storage={}, url="")
        await page.goto(f"{APP}/dashboard")

        # Chromium's own record of every tab created, including the ones
        # Playwright opens for itself and does not report as page events.
        cdp = await browser.new_browser_cdp_session()
        cdp.on(
            "Target.targetCreated",
            lambda event: opened.append(event) if event["targetInfo"]["type"] == "page" else None,
        )
        await cdp.send("Target.setDiscoverTargets", {"discover": True})
        opened.clear()  # setDiscoverTargets reports the tab that is already open
        storage = await _quiet_storage(context, first)
        assert opened == [], "the refresh opened a tab in the sign-in window"

        assert {c["name"] for c in storage["cookies"]} >= {"idp", "app"}
        local = {o["origin"]: {i["name"] for i in o["localStorage"]} for o in storage["origins"]}
        # The provider's tab is gone, so its storage is the copy read earlier.
        assert local[IDP] == {"idp-token"}
        assert local[APP] == {"app-token"}

        # The cause: Playwright's own capture opens a tab for the closed site.
        await context.storage_state()
        assert opened, "storage_state() no longer opens a tab; revisit _quiet_storage"
        await browser.close()
