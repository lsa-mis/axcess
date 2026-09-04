"""Temporary network guard for automatic control exploration.

This is defense in depth, not a transaction sandbox: sites can mutate state
through GET or pre-existing sockets. Label filtering and manual review still
matter. Configured search journeys have a separate authorization boundary.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Dialog, Page, Route

log = get_logger(__name__)


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

    async def guard(route: Route) -> None:
        nonlocal blocked
        request = route.request
        try:
            owner = request.frame.page
        except Exception:
            # A popup's first request can precede its frame. Never let an
            # unattributable request bypass the guard. Crawl contexts block
            # service workers, so no worker request should need this path.
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
            if is_navigation and request.method == "GET" and permitted and len(urls) < 1000:
                urls.add(request.url)
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
    try:
        yield
    finally:
        for popup in popups:
            with suppress(Exception):
                await popup.close()
        await page.context.unroute("**/*", guard)
        page.remove_listener("dialog", dismiss)
        page.remove_listener("popup", remember_popup)
        if blocked:
            log.info("interaction.guard", blocked_requests_or_dialogs=blocked)
