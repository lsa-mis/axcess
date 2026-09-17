"""Temporary network guard for automatic control exploration.

This is defense in depth, not a transaction sandbox: sites can mutate state
through GET or pre-existing sockets. Label filtering and manual review still
matter. Configured search journeys have a separate authorization boundary.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Dialog, Page, Request, Route

log = get_logger(__name__)

# Pages being explored right now, and where each one's discovered URLs go.
_REFUSED_POPUP_SINKS: dict[Page, Callable[[str], None]] = {}


def report_refused_popup(page: Page, url: str) -> None:
    """Remember where a popup was headed when it was refused before it existed.

    The guard below learns a new-tab destination from the popup's first
    request. A browser that must not open tabs at all (a login scan keeps its
    window hidden, and a new tab raises it) refuses ``window.open`` in the
    page, so there is no request to learn from. Whoever refused it reports
    the destination here instead, and it is remembered exactly as the request
    would have been. Outside exploration there is nothing to feed, as before.
    """
    sink = _REFUSED_POPUP_SINKS.get(page)
    if sink is not None:
        sink(url)


def safe_url(url: str, blocked_labels: Sequence[str]) -> bool:
    """Only queue ordinary web links without credentials or action words."""
    try:
        parts = urlsplit(url)
        if (
            len(url) > 2048
            or parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            return False
        text = re.sub(r"[-_+/]+", " ", unquote(parts.path + " " + parts.query)).casefold()
        return not any(
            re.sub(r"[-_+/]+", " ", word).casefold().strip() in text
            for word in blocked_labels
            if word.strip()
        )
    except ValueError:
        return False


@asynccontextmanager
async def exploration_guard(
    page: Page, urls: set[str], blocked_labels: Sequence[str]
) -> AsyncIterator[None]:
    """Block writes, new windows and document navigation before dispatch.

    A context route catches the first popup request, which page routes miss.
    Filter by owning page so concurrent crawl workers retain their guards.
    Allowed requests fall through to existing scope/egress policy.
    """
    blocked = 0
    popups: set[Page] = set()
    pinned = urlsplit(page.url)

    def remember(request: Request) -> None:
        """Keep a destination the guard is about to refuse, for the frontier.

        Refusing the request and forgetting where it pointed are separate
        decisions. Every check that governs crawling still runs later, at
        enqueue: scope, the blocklist, and whether the URL was already fetched
        or queued for this scan.
        """
        with suppress(Exception):
            if request.is_navigation_request() and request.method == "GET":
                remember_url(request.url)

    def remember_url(url: str) -> None:
        if len(urls) < 1000 and safe_url(url, blocked_labels):
            urls.add(url)

    async def guard(route: Route) -> None:
        nonlocal blocked
        request = route.request
        try:
            owner = request.frame.page
        except Exception:
            # A popup's first request can precede its frame. Never let an
            # unattributable request bypass the guard. Crawl contexts block
            # service workers, so no worker request should need this path.
            #
            # Remember it anyway. This is the path every new-tab control takes,
            # window.open and target="_blank" alike, and it is the only record
            # of those pages: a button that opens a tab leaves no href in the
            # DOM for link extraction to find, so dropping the request dropped
            # the page from the crawl entirely, even inside the scan's scope.
            remember(request)
            blocked += 1
            await route.abort("blockedbyclient")
            return
        opener = await owner.opener() if owner != page else None
        popup = owner in popups or opener == page or opener in popups
        if popup:
            popups.add(owner)
        if owner != page and not popup:
            await route.fallback()
            return
        is_navigation = request.is_navigation_request()
        permitted = safe_url(request.url, blocked_labels)
        destination = urlsplit(request.url)
        same_origin = (destination.scheme, destination.netloc) == (pinned.scheme, pinned.netloc)
        if (
            popup
            or is_navigation
            or request.method not in {"GET", "HEAD", "OPTIONS"}
            or not permitted
            or not same_origin
        ):
            remember(request)
            blocked += 1
            if is_navigation:
                # Aborting top-level navigation can replace the current DOM
                # with Chromium's error page. A 204 keeps it available for
                # the remaining sibling controls without contacting the site.
                await route.fulfill(status=204, body="")
            else:
                await route.abort("blockedbyclient")
            return
        await route.fallback()

    async def dismiss(dialog: Dialog) -> None:
        nonlocal blocked
        blocked += 1
        with suppress(Exception):
            await dialog.dismiss()

    def remember_popup(popup: Page) -> None:
        # Do not close before its first request is attributed: closing can
        # discard opener information before the route callback runs.
        popups.add(popup)

    if page.context.service_workers:
        # Their requests bypass routing; do not pretend the write guard holds.
        raise RuntimeError("Interaction exploration requires blocked service workers")
    page.on("dialog", dismiss)
    page.on("popup", remember_popup)
    await page.context.route("**/*", guard)
    _REFUSED_POPUP_SINKS[page] = remember_url
    try:
        yield
    finally:
        _REFUSED_POPUP_SINKS.pop(page, None)
        for popup in popups:
            with suppress(Exception):
                await popup.close()
        await page.context.unroute("**/*", guard)
        page.remove_listener("dialog", dismiss)
        page.remove_listener("popup", remember_popup)
        if blocked:
            log.info("interaction.guard", blocked_requests_or_dialogs=blocked)
