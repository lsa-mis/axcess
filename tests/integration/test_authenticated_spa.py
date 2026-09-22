"""Real-browser route traversal after a synthetic local sign-in handoff."""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import Browser, BrowserContext, Playwright, Route, async_playwright

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe
from audit.crawler.orchestrator import CrawlConfig, run_crawl
from audit.protected.egress import LoopbackEgressProxy
from audit.protected.session import ManualAuthenticationSession, ManualAuthState

pytestmark = pytest.mark.integration


async def test_headless_handoff_restores_storage_without_replaying_old_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transfer real cookies, localStorage, IndexedDB and frame sessionStorage."""
    origin = "https://app.example.test"
    frame_origin = "https://frame.example.test"
    new_context = Browser.new_context

    async def fixture_context(browser: Browser, **kwargs: Any) -> BrowserContext:
        kwargs.pop("proxy", None)
        return await new_context(browser, **kwargs)

    async def serve(route: Route) -> None:
        body = "<h1>Protected application</h1>"
        if route.request.url.startswith(origin):
            body += f'<iframe src="{frame_origin}/"></iframe>'
        await route.fulfill(status=200, content_type="text/html", body=body)

    monkeypatch.setattr(Browser, "new_context", fixture_context)
    monkeypatch.setattr(LoopbackEgressProxy, "server_url", property(lambda _: "http://127.0.0.1:1"))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        await context.route("**/*", serve)
        await context.add_cookies(
            [
                {
                    "name": "session",
                    "value": "cookie-token",
                    "domain": "app.example.test",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ]
        )
        page = await context.new_page()
        await page.goto(origin + "/dashboard")
        await page.evaluate("""async () => {
            localStorage.setItem('token', 'local-token');
            sessionStorage.setItem('token', 'tab-token');
            await new Promise((resolve, reject) => {
                const request = indexedDB.open('auth', 1);
                request.onupgradeneeded = () => request.result.createObjectStore('tokens');
                request.onerror = () => reject(request.error);
                request.onsuccess = () => {
                    const db = request.result;
                    const tx = db.transaction('tokens', 'readwrite');
                    tx.objectStore('tokens').put('idb-token', 'token');
                    tx.oncomplete = () => { db.close(); resolve(); };
                    tx.onerror = () => reject(tx.error);
                };
            });
        }""")
        await page.frames[1].evaluate("sessionStorage.setItem('token', 'frame-token')")
        session = ManualAuthenticationSession(
            seed_url=origin,
            approved_target_origins=(origin,),
            resolver=lambda _: ("8.8.8.8",),
        )
        session._context = context
        session._playwright = pw
        session._page = page
        session._auth_pages = [page]
        session._state = ManualAuthState.AWAITING_MANUAL_AUTHENTICATION
        monkeypatch.setattr(session._route_guard, "handle_route", serve)
        try:
            landed = session.enter_scan_mode()
            pages = await session.switch_to_headless(4)
            assert len(pages) == 1
            assert page.is_closed()
            scan_page = pages[0]
            await scan_page.goto(landed)
            assert await scan_page.evaluate("localStorage.getItem('token')") == "local-token"
            assert await scan_page.evaluate("sessionStorage.getItem('token')") == "tab-token"
            assert (
                await scan_page.frames[1].evaluate("sessionStorage.getItem('token')")
                == "frame-token"
            )
            cookies = await session.context.cookies(origin)
            assert any(
                c["name"] == "session" and c["value"] == "cookie-token" and c["httpOnly"]
                for c in cookies
            )
            stored_value = await scan_page.evaluate("""() => new Promise((resolve, reject) => {
                const request = indexedDB.open('auth');
                request.onsuccess = () => {
                    const db = request.result;
                    const read = db.transaction('tokens').objectStore('tokens').get('token');
                    read.onsuccess = () => { db.close(); resolve(read.result); };
                    read.onerror = () => reject(read.error);
                };
                request.onerror = () => reject(request.error);
            })""")
            assert stored_value == "idb-token"
            await scan_page.evaluate("sessionStorage.setItem('token', 'rotated')")
            await scan_page.reload()
            assert await scan_page.evaluate("sessionStorage.getItem('token')") == "rotated"
            await scan_page.evaluate("sessionStorage.clear()")
            await scan_page.reload()
            assert await scan_page.evaluate("sessionStorage.getItem('token')") is None
            await scan_page.goto("https://other.example.test/")
            assert await scan_page.evaluate("sessionStorage.length") == 0
        finally:
            await session.close()
            await browser.close()


_APP = """<!doctype html><html lang="en"><title>Fixture sign in</title><body>
<main></main><script>
const prefix = 'ROUTER_PREFIX';
const tabSession = TAB_SESSION;
const signedIn = () => tabSession ? sessionStorage.getItem('fixture') === 'yes'
    : document.cookie.includes('fixture=yes');
function render() {
  if (!signedIn()) {
    document.querySelector('main').innerHTML = '<button>Sign in</button>';
    document.querySelector('button').onclick = () => {
      if (tabSession) sessionStorage.setItem('fixture', 'yes');
      else document.cookie = 'fixture=yes; path=/';
      history.replaceState(null, '', prefix + '/dashboard');
      render();
    };
    return;
  }
  const route = prefix ? location.hash.slice(prefix.length) : location.pathname;
  document.title = route;
  const next = route === '/dashboard' ? '/projects' :
      route === '/projects' ? '/projects/detail' : null;
  document.querySelector('main').innerHTML = '<h1>' + route + '</h1>' +
      (next ? '<a href="' + prefix + next + '">Next page</a>' : '') +
      '<button id="expand" aria-expanded="false">Show options</button><div id="options"></div>';
  document.querySelector('#expand').onclick = () => {
    document.querySelector('#expand').setAttribute('aria-expanded', 'true');
    document.querySelector('#options').innerHTML = '<input id="unlabelled">';
  };
}
window.addEventListener('hashchange', () => setTimeout(render, 75));
setTimeout(render, 75);
</script></body></html>"""


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["#", "#!", ""])
@pytest.mark.parametrize("tab_session", [False, True])
async def test_login_traverses_nested_spa_routes_with_session_intact(
    tmp_db: sqlite3.Connection, prefix: str, tab_session: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = "https://app.example.test"
    html = _APP.replace("ROUTER_PREFIX", prefix).replace("TAB_SESSION", str(tab_session).lower())

    async def serve(route: Route) -> None:
        await route.fulfill(status=200, content_type="text/html", body=html)

    # Route all target responses locally, including the newly launched browser.
    # No network listener or real identity provider is needed for this test.
    new_context = Browser.new_context

    async def fixture_context(browser: Browser, **kwargs: Any) -> BrowserContext:
        kwargs.pop("proxy", None)
        return await new_context(browser, **kwargs)

    monkeypatch.setattr(Browser, "new_context", fixture_context)
    monkeypatch.setattr(
        LoopbackEgressProxy, "server_url", property(lambda _self: "http://127.0.0.1:1")
    )
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        await context.route(f"{origin}/**", serve)
        page = await context.new_page()
        await page.goto(origin)
        await page.get_by_role("button", name="Sign in").click()
        # Inject only this test's browser into the production handoff. All
        # target requests are fulfilled above, with no real identity provider.
        session = ManualAuthenticationSession(
            seed_url=origin,
            approved_target_origins=(origin,),
            resolver=lambda _host: ("8.8.8.8",),
        )
        session._playwright = pw
        monkeypatch.setattr(session._route_guard, "handle_route", serve)
        session._context = context
        session._page = page
        session._auth_pages = [page]
        session._state = ManualAuthState.AWAITING_MANUAL_AUTHENTICATION
        try:
            landed_url = session.enter_scan_mode()
            pages = await session.switch_to_headless(2)
            assert session.context is not context
            assert page.is_closed(), "the original sign-in context was left open"
            assert all(p.viewport_size == {"width": 1440, "height": 900} for p in pages)
            axe = AxeAnalyzer.from_bundled()
            fetcher = session.create_shared_js_fetcher(
                shared_pages=pages,
                axe_analyzer=axe,
                interaction_probe=InteractionProbe(axe=axe),
            )
            summary = await run_crawl(
                tmp_db,
                CrawlConfig(
                    seed_url=origin,
                    start_url=landed_url,
                    browser_only=True,
                    whole_host=True,
                    max_pages=10,
                    workers=2,
                    rps=100,
                    ignore_robots=True,
                    image_extraction_enabled=False,
                    vlm_enabled=False,
                    semantic_enabled=False,
                    synthesize_enabled=False,
                    keyboard_probe_enabled=False,
                    responsive_checks_enabled=False,
                    focus_checks_enabled=False,
                    visual_checks_enabled=False,
                    interaction_checks_enabled=True,
                    capture_screenshots=False,
                ),
                js_fetcher=fetcher,
            )
            rows = tmp_db.execute(
                "SELECT url_normalized, title, status_code FROM pages WHERE scan_id = ?",
                (summary.scan_id,),
            ).fetchall()
            route_base = origin + ("/" + prefix if prefix else "")
            assert {row["url_normalized"] for row in rows} == {
                route_base + path for path in ("/dashboard", "/projects", "/projects/detail")
            }
            assert {row["title"] for row in rows} == {"/dashboard", "/projects", "/projects/detail"}
            assert all(row["status_code"] == 200 for row in rows)
            assert summary.axe_pages_scanned == 3
            assert summary.pages_auth_wall == 0
            assert summary.interaction_pages_probed == 3
            assert summary.interaction_states_total == 3
            revealed = tmp_db.execute(
                "SELECT COUNT(DISTINCT page_id) FROM page_a11y_findings "
                "WHERE scan_id = ? AND rule_id = 'label' AND revealed_by = 'Show options'",
                (summary.scan_id,),
            ).fetchone()[0]
            assert revealed == 3
            assert len(pages) == (1 if tab_session else 2)
        finally:
            await session.close()
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("survivor", ["original", "popup", "all"])
@pytest.mark.parametrize("headless_handoff", [False, True])
async def test_login_tab_closure_does_not_close_the_authenticated_scan_tab(
    tmp_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    survivor: str,
    headless_handoff: bool,
) -> None:
    """Exercise the real context page/close events through the production start.

    The initial page event can run before new_page returns. Registering that
    tab twice meant closing the extra sign-in tabs, then retaining the initial
    tab for its sessionStorage, left a duplicate for sign-in cleanup to close.
    """
    origin = "https://app.example.test"
    html = _APP.replace("ROUTER_PREFIX", "").replace("TAB_SESSION", "true")

    async def serve(route: Route) -> None:
        await route.fulfill(status=200, content_type="text/html", body=html)

    new_context = Browser.new_context

    async def fixture_context(browser: Browser, **kwargs: Any) -> BrowserContext:
        kwargs.pop("proxy", None)
        return await new_context(browser, **kwargs)

    monkeypatch.setattr(Browser, "new_context", fixture_context)
    async with async_playwright() as pw:
        launch = pw.chromium.launch_persistent_context

        async def launch_fixture_context(user_data_dir: str, **kwargs: Any) -> BrowserContext:
            # Only browser transport is synthetic: no listener or external
            # requests. Page creation and close events remain real Chromium.
            kwargs["headless"] = True
            kwargs.pop("proxy", None)
            return await launch(user_data_dir, **kwargs)

        async def started_playwright() -> Playwright:
            return pw

        monkeypatch.setattr(pw.chromium, "launch_persistent_context", launch_fixture_context)
        monkeypatch.setattr(LoopbackEgressProxy, "start", AsyncMock())
        monkeypatch.setattr(
            LoopbackEgressProxy, "server_url", property(lambda _self: "http://127.0.0.1:1")
        )
        session = ManualAuthenticationSession(
            seed_url=origin,
            approved_target_origins=(origin,),
            resolver=lambda _host: ("8.8.8.8",),
            playwright_start=started_playwright,
        )
        # Replace HTTP responses, preserving the real installed page listener.
        monkeypatch.setattr(session._route_guard, "handle_route", serve)
        try:
            original = await session.start()
            await original.get_by_role("button", name="Sign in").click()
            popups = []
            for _ in range(2):
                async with session.context.expect_page() as opened:
                    await original.evaluate("window.open('/dashboard', '_blank')")
                popup = await opened.value
                await popup.get_by_role("heading", name="/dashboard", exact=True).wait_for()
                popups.append(popup)
            if survivor == "original":
                for popup in reversed(popups):
                    await popup.close()
                expected = original
            elif survivor == "popup":
                await original.close()
                await popups[-1].close()
                expected = popups[0]
            else:
                expected = popups[-1]

            assert session.page is expected
            landed_url = session.enter_scan_mode()
            if headless_handoff:
                pages = await session.switch_to_headless(2)
                assert len(pages) == 1
                assert expected.is_closed(), "the sign-in window was left open"
            else:
                pages = await session.prepare_background_scan_pages(2)
                await session.discard_manual_auth_page()
                assert pages == (expected,)
                assert not expected.is_closed(), "sign-in cleanup closed the scanner's tab"

            fetcher = session.create_shared_js_fetcher(shared_pages=pages)
            summary = await run_crawl(
                tmp_db,
                CrawlConfig(
                    seed_url=origin,
                    start_url=landed_url,
                    browser_only=True,
                    whole_host=True,
                    max_pages=1,
                    workers=2,
                    rps=100,
                    ignore_robots=True,
                    image_extraction_enabled=False,
                    vlm_enabled=False,
                    semantic_enabled=False,
                    synthesize_enabled=False,
                    keyboard_probe_enabled=False,
                    responsive_checks_enabled=False,
                    focus_checks_enabled=False,
                    visual_checks_enabled=False,
                    interaction_checks_enabled=False,
                    capture_screenshots=False,
                ),
                js_fetcher=fetcher,
            )
            assert summary.pages_fetched == 1
            assert summary.pages_auth_wall == 0
            row = tmp_db.execute(
                "SELECT status_code, title FROM pages WHERE scan_id = ?", (summary.scan_id,)
            ).fetchone()
            assert row["status_code"] == 200
            assert row["title"] == "/dashboard"
        finally:
            await session.close()
