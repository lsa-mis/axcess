"""A public scan sends the chosen browser name, but reads robots.txt for Axcess.

A real crawl, browser included, against a local site that records the
``User-Agent`` of every request and what the page's scripts read from
``navigator.userAgent``. Its robots.txt shuts Axcess out of /private/ and lets
every other agent in, so a crawl that matched rules against the browser name
it sends would visit the private page.
"""

from __future__ import annotations

import asyncio
import http.server
import socketserver
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import unquote

import pytest

from audit.crawler.orchestrator import CrawlConfig, run_crawl

pytestmark = pytest.mark.integration

SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/27.2 Safari/605.1.15"
)
AXCESS = "axcess/0.1 (+local accessibility audit)"

_PAGES = {
    "/": (
        "<!doctype html><html lang='en'><head><title>Home</title></head><body>"
        "<main><h1>Home</h1><a href='/about.html'>About</a> "
        "<a href='/private/secret.html'>Private</a></main>"
        "<script>fetch('/seen?ua=' + encodeURIComponent(navigator.userAgent))</script>"
        "</body></html>"
    ),
    "/about.html": (
        "<!doctype html><html lang='en'><head><title>About</title></head>"
        "<body><main><h1>About</h1></main></body></html>"
    ),
    "/private/secret.html": (
        "<!doctype html><html lang='en'><head><title>Private</title></head>"
        "<body><main><h1>Private</h1></main></body></html>"
    ),
    "/robots.txt": "User-agent: axcess\nDisallow: /private/\n\nUser-agent: *\nAllow: /\n",
}


@contextmanager
def _serve() -> Iterator[tuple[str, list[tuple[str, str]], list[str]]]:
    requests: list[tuple[str, str]] = []
    scripts_saw: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("#", 1)[0]
            requests.append((path, self.headers.get("User-Agent", "")))
            if path.startswith("/seen?ua="):
                scripts_saw.append(unquote(path.removeprefix("/seen?ua=")))
                body, kind = b"", "text/plain"
            elif path in _PAGES:
                body = _PAGES[path].encode()
                kind = "text/plain" if path.endswith(".txt") else "text/html; charset=utf-8"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as httpd:
        httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}", requests, scripts_saw
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize("js_eager", [False, True])
def test_the_site_sees_the_chosen_browser_and_axcess_robots_rules_hold(
    tmp_db: sqlite3.Connection, js_eager: bool
) -> None:
    with _serve() as (base, requests, scripts_saw):
        config = CrawlConfig(
            seed_url=f"{base}/",
            max_pages=10,
            rps=100.0,
            workers=1,
            js_eager=js_eager,
            user_agent=SAFARI,
            robots_user_agent=AXCESS,
            user_agent_choice="safari_mac",
            axe_enabled=js_eager,
            ocr_enabled=False,
            vlm_enabled=False,
            semantic_enabled=False,
            keyboard_probe_enabled=False,
            responsive_checks_enabled=False,
            focus_checks_enabled=False,
            markup_checks_enabled=False,
            visual_checks_enabled=False,
            interaction_checks_enabled=False,
            capture_screenshots=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    assert summary.status == "completed"
    paths = {path for path, _ in requests}
    assert "/about.html" in paths
    assert not any(path.startswith("/private/") for path in paths)
    # Every request, robots.txt included, carried the chosen name.
    assert requests
    assert {agent for _, agent in requests} == {SAFARI}
    if js_eager:
        # And the page's own scripts read it too.
        assert scripts_saw and set(scripts_saw) == {SAFARI}
    stored = tmp_db.execute(
        "SELECT json_extract(config_json, '$.user_agent') AS ua, "
        "json_extract(config_json, '$.user_agent_choice') AS choice "
        "FROM scans WHERE id = ?",
        (summary.scan_id,),
    ).fetchone()
    assert (stored["ua"], stored["choice"]) == (SAFARI, "safari_mac")
