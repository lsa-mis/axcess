"""Offline fixture serving through Playwright request routing.

No listening socket. Every request the page makes is intercepted and answered
from the checked-in fixture directory, and **anything not matched is aborted**.
That default-deny is the point: it guarantees the experiment cannot silently
depend on the network, so a run on a disconnected machine produces the same
numbers as a run on a connected one. A fixture that quietly fetched a CDN script
would otherwise make results depend on the weather.

The one synthesized endpoint is ``/api/ping``, fulfilled in memory. Fixtures need
*some* network effect to exercise the ``net`` channel — a handler whose only
observable consequence is a ``fetch`` is exactly the case a DOM-only oracle
misses — and pointing that at a real host would defeat the paragraph above.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from playwright.async_api import BrowserContext, Route, WebSocketRoute

# The fixtures' own origin. Nothing resolves it; every request to it is answered
# from disk by the router below.
BASE_URL = "https://tabbing.axcess.test"

# Requests we answer without touching the filesystem.
PING_BODY = '{"ok":true}'
REQUEST_TIMEOUT_MS = 15_000


def is_fixture_origin(url: str) -> bool:
    """Compare the actual origin, rejecting credentials and lookalike hosts."""
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "tabbing.axcess.test"
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def page_url(relative_path: str) -> str:
    """The URL a fixture page is served at."""
    return f"{BASE_URL}/{relative_path.lstrip('/')}"


def _guess_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    return "application/octet-stream"


async def install_routes(
    context: BrowserContext, fixtures_root: Path, counters: dict[str, int]
) -> None:
    """Route every request in this context, accumulating into shared counters.

    Counters are shared across every context in a run so the runner can record
    totals in ``raw.json``. A run with unexpected blocks is a run whose fixtures
    wanted something we did not give them, and the report should say so rather
    than the fact being invisible.
    """
    root = fixtures_root.resolve()

    async def handler(route: Route) -> None:
        url = route.request.url

        if not is_fixture_origin(url):
            # Default deny. Anything off-origin is aborted, not fetched.
            counters["blocked"] += 1
            await route.abort()
            return

        path_part = unquote(urlsplit(url).path)

        if path_part.rstrip("/") == "/api/ping":
            counters["ping"] += 1
            await route.fulfill(status=200, content_type="application/json", body=PING_BODY)
            return

        candidate = (root / path_part.lstrip("/")).resolve()
        # Path traversal guard: a fixture must not be able to read outside its
        # own tree, however it spells the URL.
        if not candidate.is_relative_to(root) or not candidate.is_file():
            counters["missing"] += 1
            await route.abort()
            return

        counters["served"] += 1
        await route.fulfill(
            status=200,
            content_type=_guess_type(candidate),
            body=candidate.read_bytes(),
        )

    await context.route("**/*", handler)

    async def block_websocket(socket: WebSocketRoute) -> None:
        # Never call connect_to_server(): this route has no network peer.
        counters["blocked"] += 1
        counters["websocket"] += 1
        await socket.close(code=1008, reason="offline fixture experiment")

    await context.route_web_socket("**/*", block_websocket)


class ContextFactory:
    """Makes fresh, identically configured, fully offline contexts on demand.

    The differential needs a new context per trial (so storage cannot leak
    between the mouse run and the keyboard run). This centralizes what "the
    same conditions" means, so no trial can differ from another by accident.
    """

    def __init__(self, browser: Any, viewport: dict[str, int], fixtures_root: Path) -> None:
        self._browser = browser
        self._viewport = viewport
        self._fixtures_root = fixtures_root
        # One dict shared by every context this factory makes, so the run-level
        # totals are simply this object.
        self.totals: dict[str, int] = {
            "served": 0,
            "ping": 0,
            "blocked": 0,
            "missing": 0,
            "websocket": 0,
        }
        self._contexts: set[BrowserContext] = set()

    async def __call__(self) -> BrowserContext:
        context: BrowserContext = await self._browser.new_context(
            viewport=self._viewport,
            # Fixed so text metrics and any locale-dependent rendering cannot
            # drift between runs on different machines.
            locale="en-US",
            timezone_id="UTC",
            reduced_motion="reduce",
            service_workers="block",
        )
        self._contexts.add(context)
        context.on("close", lambda _: self._contexts.discard(context))
        context.set_default_timeout(REQUEST_TIMEOUT_MS)
        context.set_default_navigation_timeout(REQUEST_TIMEOUT_MS)
        try:
            await install_routes(context, self._fixtures_root, self.totals)
        except BaseException:
            await context.close()
            raise
        return context

    async def close_open_contexts(self) -> None:
        """Reclaim contexts when a trial failed before returning its page."""
        for context in tuple(self._contexts):
            await context.close()
