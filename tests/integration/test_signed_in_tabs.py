"""Sign-in scans with several tabs, each holding a copy of the sign-in.

A real Chromium and the real handoff (``switch_to_headless``) and crawl. The
site keeps its sign-in in sessionStorage, the kind that used to get one tab
only. Three cases:

* the copies work: every tab is used and every page is signed in;
* the site signs the copies out partway: the first copy that lands on a
  sign-in page is checked in the first tab, the scan falls back to the first
  tab, and every page is still the signed-in page;
* a page that really is a sign-in page: no fall-back, and it is recorded as
  a sign-in page, as before.

Only transport is synthetic: every response is fulfilled locally.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from playwright.async_api import Route, async_playwright

from audit.crawler.orchestrator import CrawlConfig, run_crawl
from audit.protected.session import ManualAuthenticationSession, ManualAuthState

pytestmark = pytest.mark.integration

ORIGIN = "https://app.example.test"
ROUTES = ["/dashboard", "/a", "/b", "/c", "/d", "/e", "/f"]

# Signed in when this tab's sessionStorage says so. Once the server turns
# "strict" on, a tab also needs the "fresh" key, which only the first scan
# tab is given: the copies are now stale, as after a token refresh. A
# signed-out tab shows a password field, as a real sign-in page does.
_APP = """<!doctype html><html lang="en"><title>Fixture</title><body><main></main><script>
const strict = STRICT;
const signedIn = sessionStorage.getItem('fixture') === 'yes' &&
    (!strict || sessionStorage.getItem('fresh') === 'yes');
const main = document.querySelector('main');
if (!signedIn || location.pathname === '/account/password') {
  // Split, so only the rendered page holds a password field, not this source.
  main.innerHTML = '<h1>Sign in</h1><label>Password <input type="pass' + 'word"></label>';
} else {
  const links = ROUTES.map(r => '<a href="' + r + '">' + r + '</a>').join(' ');
  document.title = location.pathname;
  main.innerHTML = '<h1>' + location.pathname + '</h1>' + links + LINK_EXTRA;
}
</script></body></html>"""


async def _scan(
    tmp_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    *,
    strict_after: int | None,
    password_page: bool = False,
    tabs: int = 3,
):  # type: ignore[no-untyped-def]
    served = 0
    routes = json.dumps(ROUTES + (["/account/password"] if password_page else []))

    async def serve(route: Route) -> None:
        nonlocal served
        served += 1
        strict = strict_after is not None and served > strict_after
        html = (
            _APP.replace("STRICT", "true" if strict else "false")
            .replace("ROUTES", routes)
            .replace("LINK_EXTRA", "''")
        )
        await route.fulfill(status=200, content_type="text/html", body=html)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        await context.route(f"{ORIGIN}/**", serve)
        page = await context.new_page()
        await page.goto(ORIGIN + "/dashboard")
        await page.evaluate("sessionStorage.setItem('fixture', 'yes')")
        session = ManualAuthenticationSession(
            seed_url=ORIGIN,
            approved_target_origins=(ORIGIN,),
            resolver=lambda _host: ("8.8.8.8",),
        )
        session._playwright = pw
        monkeypatch.setattr(session._route_guard, "handle_route", serve)
        session._context = context
        session._page = page
        session._auth_pages = [page]
        session._state = ManualAuthState.AWAITING_MANUAL_AUTHENTICATION
        try:
            session.enter_scan_mode()
            pages = await session.switch_to_headless(tabs)
            # Only the first tab gets the fresh token; the copies keep the
            # one they were given, which "strict" no longer accepts.
            await pages[0].goto(ORIGIN + "/dashboard")
            await pages[0].evaluate("sessionStorage.setItem('fresh', 'yes')")
            fetcher = session.create_shared_js_fetcher(shared_pages=pages)
            summary = await run_crawl(
                tmp_db,
                CrawlConfig(
                    seed_url=ORIGIN,
                    start_url=ORIGIN + "/dashboard",
                    browser_only=True,
                    whole_host=True,
                    max_pages=20,
                    workers=tabs,
                    concurrency_per_host=tabs,
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
            titles = dict(
                tmp_db.execute(
                    "SELECT url_normalized, title FROM pages WHERE scan_id = ?",
                    (summary.scan_id,),
                ).fetchall()
            )
            used = sum(1 for tab in pages if tab.is_closed() or tab.url != "about:blank")
            assert fetcher.tab_pool is not None
            return summary, titles, fetcher.tab_pool, len(pages), used
        finally:
            await session.close()
            await browser.close()


async def test_copied_tabs_are_all_used_and_signed_in(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary, titles, pool, opened, used = await _scan(tmp_db, monkeypatch, strict_after=None)

    assert opened == 3, "a sessionStorage sign-in must get one tab per worker now"
    assert pool.copied_session and not pool.fell_back
    assert used == 3, "every tab should have loaded a page"
    assert summary.pages_auth_wall == 0
    assert set(titles.values()) == set(ROUTES)


async def test_a_signed_out_copy_falls_back_to_the_first_tab(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two setup loads (sign-in tab, first scan tab), two crawl pages that
    # load normally, then the copies go stale.
    summary, titles, pool, _, _ = await _scan(tmp_db, monkeypatch, strict_after=4)

    assert pool.fell_back, "a copy landed on a sign-in page; the scan must fall back"
    assert summary.pages_auth_wall == 0, "a page was kept as the stale copy saw it"
    assert set(titles.values()) == set(ROUTES), "every page must be the signed-in page"


async def test_a_real_sign_in_page_is_kept_and_does_not_fall_back(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, titles, pool, _, _ = await _scan(
        tmp_db, monkeypatch, strict_after=None, password_page=True
    )

    assert not pool.fell_back, "the first tab showed a sign-in page too: no fall-back"
    assert summary.pages_auth_wall == 1
    assert titles[ORIGIN + "/account/password"] == "Fixture"
