"""A login scan must stay out of the auditor's way, measured at the OS.

These tests open a real, headed Chromium on the machine that runs them, sign
in to a synthetic application with a second-factor step, and crawl it with the
production session, fetcher and probes. While that happens a thread asks the
window server, not Chromium, whether any of the browser's windows is on a
display. Opt in, on macOS or Windows, with a desktop session:

    AXCESS_HEADED=1 uv run pytest -m headed tests/integration/test_background_login_scan.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sqlite3
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from playwright.async_api import BrowserContext, Playwright, Route, async_playwright

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.focus import FocusProbe
from audit.analyzer.interaction import InteractionProbe
from audit.analyzer.keyboard import KeyboardProbe
from audit.analyzer.responsive import ResponsiveProbe
from audit.crawler.orchestrator import CrawlConfig, run_crawl
from audit.db.schema import connect
from audit.protected.egress import LoopbackEgressProxy
from audit.protected.session import ManualAuthenticationSession

pytestmark = [
    pytest.mark.headed,
    pytest.mark.skipif(
        os.environ.get("AXCESS_HEADED") != "1" or sys.platform not in {"darwin", "win32"},
        reason="Opens a real browser window; set AXCESS_HEADED=1 on macOS or Windows.",
    ),
]

_PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "watch_scan_windows.py"
_MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"
_ORIGIN = "https://app.example.test"
# The OS animates a window into the Dock or taskbar; it is still drawn while
# that plays. Samples are judged from this long after hiding was requested.
_HIDE_ANIMATION_GRACE_S = 1.5

# Sign-in, then a second factor, then an application whose every page does the
# things that have put the browser back on screen: opens a tab (and uses the
# window it gets back, as real code does), follows a new-tab link, clicks an
# anchor it never attached, prints, opens a file picker, asks for focus. One
# control redirects with ``window.open(url, "_self")``, which has to keep
# working. Content also arrives by animation frame and IntersectionObserver,
# and one element appears only if the tab believes it is hidden: a scan tab
# always sits behind the cover tab, so a difference would show up here.
_APP = """<!doctype html><html lang="en"><head><title>Fixture</title></head><body>
<main></main><script>
const tabSession = TAB_SESSION;
const publicSite = PUBLIC_SITE;
const signedIn = () => publicSite || (tabSession ? sessionStorage.getItem('fixture') === 'yes'
    : document.cookie.includes('fixture=yes'));
function render() {
  const main = document.querySelector('main');
  if (!signedIn()) {
    if (location.pathname !== '/mfa') {
      main.innerHTML = '<h1>Sign in</h1><button id="signin">Sign in</button>';
      document.querySelector('#signin').onclick = () => {
        history.replaceState(null, '', '/mfa'); render();
      };
      return;
    }
    main.innerHTML = '<h1>Second factor</h1><button id="approve">Approve push</button>';
    document.querySelector('#approve').onclick = () => {
      if (tabSession) sessionStorage.setItem('fixture', 'yes');
      else document.cookie = 'fixture=yes; path=/';
      history.replaceState(null, '', '/dashboard'); render();
    };
    return;
  }
  const route = location.pathname.replace(/[/]$/, '') || '/';  // a seed gains a slash
  document.title = route;
  const next = { '/dashboard': '/projects', '/projects': '/projects/detail',
      '/projects/detail': '/reports', '/reports': '/settings' }[route];
  main.innerHTML = '<h1>' + route + '</h1>' +
      (next ? '<a href="' + next + '">Next page</a> ' : '') +
      '<a id="blank" href="/help" target="_blank">Help in a new tab</a> ' +
      '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="40" height="40">' +
      '<button id="popup">Open report window</button>' +
      '<button id="export">Export summary</button>' +
      '<button id="legacy">Open legacy view</button>' +
      '<div id="late"></div><div id="sentinel" style="height:1px"></div>' +
      '<button id="print">Print this page</button>' +
      '<button id="attach">Browse attachments</button><input id="file" type="file" hidden>' +
      '<button id="expand" aria-expanded="false">Show options</button><div id="options"></div>';
  document.querySelector('#popup').onclick = () => {
    const opened = window.open('/popup-only', '_blank');
    opened.focus();
    document.querySelector('#popup').dataset.opened = 'yes';
  };
  document.querySelector('#export').onclick = () => {
    const link = document.createElement('a');
    link.href = '/detached-only';
    link.target = '_blank';
    link.click();
  };
  document.querySelector('#legacy').onclick = () => window.open('/legacy-only', '_self');
  const late = document.querySelector('#late');
  const pixel = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';
  requestAnimationFrame(() => late.insertAdjacentHTML(
      'beforeend', '<img id="by-frame" src="' + pixel + '" width="20" height="20">'));
  new IntersectionObserver((entries, observer) => {
    if (!entries.some((entry) => entry.isIntersecting)) return;
    observer.disconnect();
    late.insertAdjacentHTML('beforeend', '<input id="by-observer">');
  }).observe(document.querySelector('#sentinel'));
  if (document.visibilityState !== 'visible') {
    late.insertAdjacentHTML('beforeend', '<select id="only-when-hidden"></select>');
  }
  document.querySelector('#print').onclick = () => window.print();
  document.querySelector('#attach').onclick = () => document.querySelector('#file').click();
  document.querySelector('#expand').onclick = () => {
    document.querySelector('#expand').setAttribute('aria-expanded', 'true');
    document.querySelector('#options').innerHTML = '<input id="unlabelled">';
  };
  window.focus();
}
setTimeout(render, 50);
</script></body></html>"""


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("watch_scan_windows", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _WindowWatcher(threading.Thread):
    """Samples the OS window list off the event loop, so a stall cannot hide a flash."""

    def __init__(self, probe: ModuleType) -> None:
        super().__init__(daemon=True)
        self._probe = probe
        self._stop = threading.Event()
        self.samples: list[tuple[float, float]] = []
        self.saw_browser = False

    def run(self) -> None:
        pids: set[int] = set()
        while not self._stop.is_set():
            if not pids:
                pids = self._probe.browser_pids()
            windows = self._probe.sample_windows(pids)
            if windows:
                self.saw_browser = True
            self.samples.append((time.monotonic(), self._probe.total_visible_area(windows)))
            time.sleep(0.04)

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=5)

    def describe(self, start: float, end: float) -> str:
        """When, on the wall clock, a window was on a display: to set beside the scan log."""

        offset = time.time() - time.monotonic()
        runs: list[list[float]] = []
        for t, area in self.samples:
            if not (start <= t <= end) or area <= 0:
                continue
            if runs and t - runs[-1][1] < 0.2:
                runs[-1][1] = t
            else:
                runs.append([t, t])
        return "; ".join(
            f"{time.strftime('%H:%M:%S', time.localtime(a + offset))}"
            f".{int(((a + offset) % 1) * 1000):03d} for {b - a:.2f}s"
            for a, b in runs
        )

    def shown_between(self, start: float, end: float) -> list[tuple[float, float]]:
        return [(t - start, area) for t, area in self.samples if start <= t <= end and area > 0]

    def count_between(self, start: float, end: float) -> int:
        return sum(1 for t, _ in self.samples if start <= t <= end)


@dataclass
class _Outcome:
    pages: set[str] = field(default_factory=set)
    #: How many nodes each rule caught on each page, by path: origins differ
    #: between a login scan and the public scan it is compared with.
    findings: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    screenshots: int = 0
    states: int = 0
    scan_tabs: int = 0
    hidden_reported: bool = False
    shown_while_visible: int = 0
    started_at: float = 0.0
    hidden_at: float = 0.0
    closed_at: float = 0.0
    events: dict[str, float] = field(default_factory=dict)


async def _login_scan(
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tab_session: bool,
    hide: bool,
    toggle: bool = False,
    watcher: _WindowWatcher | None = None,
) -> _Outcome:
    """The sequence ``_run_local_login_background`` runs, against the fixture."""

    html = _APP.replace("TAB_SESSION", str(tab_session).lower()).replace("PUBLIC_SITE", "false")

    async def serve(route: Route) -> None:
        await route.fulfill(status=200, content_type="text/html", body=html)

    outcome = _Outcome()
    async with async_playwright() as pw:
        launch = pw.chromium.launch_persistent_context

        async def launch_fixture_context(user_data_dir: str, **kwargs: Any) -> BrowserContext:
            # Only browser transport is synthetic. The window, its tabs and
            # everything the OS does with them are real.
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
            seed_url=_ORIGIN,
            approved_target_origins=(_ORIGIN,),
            resolver=lambda _host: ("8.8.8.8",),
            playwright_start=started_playwright,
        )
        monkeypatch.setattr(session._route_guard, "handle_route", serve)
        try:
            page = await session.start()
            outcome.started_at = time.monotonic()
            # The auditor: password step, then the second factor.
            await page.get_by_role("button", name="Sign in").click()
            await page.get_by_role("button", name="Approve push").click()
            await page.get_by_role("heading", name="/dashboard", exact=True).wait_for()

            landed_url = session.enter_scan_mode()
            pages = await session.prepare_background_scan_pages(4)
            outcome.scan_tabs = len(pages)
            await session.discard_manual_auth_page()
            if hide:
                outcome.hidden_reported = await session.hide_for_background_scan()
            outcome.hidden_at = time.monotonic()

            axe = AxeAnalyzer.from_bundled(suppress_diagnostics=True)
            fetcher = session.create_shared_js_fetcher(
                shared_pages=pages,
                axe_analyzer=axe,
                keyboard_probe=KeyboardProbe(suppress_diagnostics=True),
                responsive_probe=ResponsiveProbe(suppress_diagnostics=True),
                focus_probe=FocusProbe(suppress_diagnostics=True),
                interaction_probe=InteractionProbe(axe=axe),
                capture_screenshots=True,
            )

            async def show_then_hide() -> None:
                # The auditor looks at the browser mid-scan, then sends it away.
                await asyncio.sleep(2.0)
                assert await session.show_browser()
                outcome.events["shown"] = time.monotonic()
                await asyncio.sleep(2.5)
                if watcher is not None:
                    outcome.shown_while_visible = len(
                        watcher.shown_between(outcome.events["shown"], time.monotonic())
                    )
                assert await session.hide_for_background_scan()
                outcome.events["hidden_again"] = time.monotonic()

            toggler = asyncio.create_task(show_then_hide()) if toggle else None
            summary = await run_crawl(conn, _scan_config(_ORIGIN, landed_url), js_fetcher=fetcher)
            if toggler is not None:
                await toggler
                # Long enough after hiding again to be judged.
                await asyncio.sleep(_HIDE_ANIMATION_GRACE_S + 1.0)
            if hide:
                outcome.hidden_reported = outcome.hidden_reported and session.backgrounded
            outcome.closed_at = time.monotonic()
            _collect(conn, summary, outcome)
        finally:
            await session.close()
    return outcome


def _path(url: str) -> str:
    return urlsplit(url).path.rstrip("/") or "/"


def _collect(conn: sqlite3.Connection, summary: Any, outcome: _Outcome) -> None:
    outcome.states = summary.interaction_states_total
    outcome.pages = {
        _path(row["url_normalized"])
        for row in conn.execute(
            "SELECT url_normalized FROM pages WHERE scan_id = ?", (summary.scan_id,)
        )
    }
    for row in conn.execute(
        "SELECT p.url_normalized AS url, f.rule_id, COALESCE(f.revealed_by, '') AS via, "
        "f.screenshot_hash FROM page_a11y_findings f JOIN pages p ON p.id = f.page_id "
        "WHERE f.scan_id = ?",
        (summary.scan_id,),
    ):
        outcome.findings[(_path(row["url"]), row["rule_id"], row["via"])] += 1
        outcome.screenshots += 1 if row["screenshot_hash"] else 0


def _scan_config(seed_url: str, start_url: str | None) -> CrawlConfig:
    return CrawlConfig(
        seed_url=seed_url,
        start_url=start_url,
        browser_only=True,
        whole_host=True,
        max_pages=12,
        workers=4,
        rps=100,
        ignore_robots=True,
        image_extraction_enabled=False,
        vlm_enabled=False,
        semantic_enabled=False,
        synthesize_enabled=False,
        keyboard_probe_enabled=True,
        responsive_checks_enabled=True,
        focus_checks_enabled=True,
        visual_checks_enabled=False,
        interaction_checks_enabled=True,
        capture_screenshots=True,
    )


async def _public_headless_scan(conn: sqlite3.Connection) -> _Outcome:
    """The bar: the same application, scanned the way a public site is.

    Headless, its own browser, none of the login session's machinery: no scan
    script in the page, no cover tab, a real popup for the guard to learn from.
    """

    html = _APP.replace("TAB_SESSION", "false").replace("PUBLIC_SITE", "true").encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    outcome = _Outcome()
    try:
        seed = f"http://127.0.0.1:{server.server_address[1]}/dashboard"
        summary = await run_crawl(conn, _scan_config(seed, None))
        _collect(conn, summary, outcome)
    finally:
        server.shutdown()
        server.server_close()
    return outcome


@pytest.fixture
def blob_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "blobs"
    path.mkdir()
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(path))
    return path


# Three of these have no link anywhere. ``/popup-only`` is behind a button that
# opens a tab, ``/detached-only`` behind an anchor the page never attaches, and
# ``/legacy-only`` behind ``window.open(url, "_self")``. Refusing the tabs must
# not lose the pages, and the same-tab redirect must still be one.
_EXPECTED_PAGES = {
    "/dashboard",
    "/projects",
    "/projects/detail",
    "/reports",
    "/settings",
    "/help",
    "/popup-only",
    "/detached-only",
    "/legacy-only",
}


def _assert_the_probe_could_see(watcher: _WindowWatcher, outcome: _Outcome) -> None:
    """Zero sightings prove nothing if the probe could not have had one.

    A locked screen, a sleeping display or another Space all report every
    window as off screen. During sign-in the window is meant to be seen, so
    the same probe has to see it then; and it has to have kept sampling.
    """

    assert watcher.saw_browser, "the probe never found the browser; it proved nothing"
    assert watcher.shown_between(outcome.started_at, outcome.hidden_at), (
        "the probe did not see the sign-in window either: it cannot see windows at all here"
    )
    times = [t for t, _ in watcher.samples if outcome.hidden_at <= t <= outcome.closed_at]
    assert times and max(b - a for a, b in pairwise([*times, outcome.closed_at])) < 1.5, (
        "the probe stopped sampling part of the way through the scan"
    )


@pytest.mark.parametrize(
    "tab_session", [False, True], ids=["cookie-4-tabs", "session-storage-1-tab"]
)
async def test_a_hidden_login_scan_never_puts_a_window_on_screen(
    tmp_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    blob_dir: Path,
    tab_session: bool,
) -> None:
    probe = _load_probe()
    watcher = _WindowWatcher(probe)
    watcher.start()
    try:
        outcome = await _login_scan(
            tmp_db, monkeypatch, tab_session=tab_session, hide=True, watcher=watcher
        )
    finally:
        watcher.stop()

    _assert_the_probe_could_see(watcher, outcome)
    start = outcome.hidden_at + _HIDE_ANIMATION_GRACE_S
    judged = watcher.count_between(start, outcome.closed_at)
    assert judged > 50, "too few samples to claim the window stayed hidden"
    flashes = watcher.shown_between(start, outcome.closed_at)
    assert not flashes, (
        f"{len(flashes)} of {judged} samples had a browser window on a display: "
        f"{watcher.describe(start, outcome.closed_at)}"
    )
    assert outcome.hidden_reported
    assert outcome.scan_tabs == (1 if tab_session else 4)
    # Out of sight must not mean out of work.
    assert outcome.pages == _EXPECTED_PAGES
    assert outcome.states >= len(_EXPECTED_PAGES)
    assert outcome.screenshots > 0, "no element screenshot was captured while hidden"


async def test_a_hidden_login_scan_reports_what_a_public_scan_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blob_dir: Path
) -> None:
    """Out of sight must not change what is found.

    Three scans of one application. ``public`` is the bar: headless, with
    none of the login session's machinery. ``visible`` is a login scan whose
    window is left on screen, which isolates minimizing from everything else
    the session does to the page. ``hidden`` is what ships.
    """

    outcomes: dict[str, _Outcome] = {}
    for label in ("public", "visible", "hidden"):
        conn = connect(tmp_path / f"{label}.db")
        for migration in sorted(_MIGRATIONS.glob("*.sql")):
            if not migration.name.endswith(".rollback.sql"):
                conn.executescript(migration.read_text())
        try:
            if label == "public":
                outcomes[label] = await _public_headless_scan(conn)
            else:
                outcomes[label] = await _login_scan(
                    conn, monkeypatch, tab_session=False, hide=label == "hidden"
                )
        finally:
            conn.close()
    public, visible, hidden = outcomes["public"], outcomes["visible"], outcomes["hidden"]
    assert public.pages == _EXPECTED_PAGES, "the bar itself did not find every page"
    assert hidden.pages == visible.pages == public.pages
    assert public.findings, "the fixture has known defects; an empty result compares nothing"
    assert not any("only-when-hidden" in str(key) for key in hidden.findings)
    assert hidden.findings == public.findings
    assert visible.findings == public.findings
    assert hidden.states == visible.states == public.states
    assert hidden.screenshots == visible.screenshots == public.screenshots > 0


async def test_the_auditor_can_show_the_browser_and_hide_it_again(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, blob_dir: Path
) -> None:
    probe = _load_probe()
    watcher = _WindowWatcher(probe)
    watcher.start()
    try:
        outcome = await _login_scan(
            tmp_db, monkeypatch, tab_session=False, hide=True, toggle=True, watcher=watcher
        )
    finally:
        watcher.stop()

    _assert_the_probe_could_see(watcher, outcome)
    assert outcome.shown_while_visible > 10, "Show browser did not put the window on screen"
    start = outcome.events["hidden_again"] + _HIDE_ANIMATION_GRACE_S
    assert watcher.count_between(start, outcome.closed_at) > 10
    assert not watcher.shown_between(start, outcome.closed_at)
    assert outcome.pages == _EXPECTED_PAGES
