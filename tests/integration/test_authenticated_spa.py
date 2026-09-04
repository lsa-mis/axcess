"""Real-browser route traversal after a synthetic local sign-in handoff."""

from __future__ import annotations

import sqlite3

import pytest
from playwright.async_api import Route, async_playwright

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe
from audit.crawler.orchestrator import CrawlConfig, run_crawl
from audit.protected.session import ManualAuthenticationSession, ManualAuthState

pytestmark = pytest.mark.integration

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
    tmp_db: sqlite3.Connection, prefix: str, tab_session: bool
) -> None:
    origin = "https://app.example.test"
    html = _APP.replace("ROUTER_PREFIX", prefix).replace("TAB_SESSION", str(tab_session).lower())

    async def serve(route: Route) -> None:
        await route.fulfill(status=200, content_type="text/html", body=html)

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
        session._context = context
        session._page = page
        session._auth_pages = [page]
        session._state = ManualAuthState.AWAITING_MANUAL_AUTHENTICATION
        try:
            landed = session.verify_authenticated_target()
            pages = await session.prepare_background_scan_pages(2)
            await session.discard_manual_auth_page()
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
                    start_url=landed.url,
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
