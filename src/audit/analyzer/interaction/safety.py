"""Temporary network guard for automatic control exploration.

This is defense in depth, not a transaction sandbox: in its default mode,
sites can mutate state through same-origin GET or pre-existing sockets. Label
filtering and manual review still matter. Configured search journeys have a
separate authorization boundary.

``strict=True`` (the form error check) refuses every request the page makes
while the guard is held, GET included, not only writes and navigation. The
form check needs nothing from the network to see a form react, so it gives
the server nothing at all. Sockets are not requests and are not seen here;
the form check holds them in the page itself (``analyzer.forms.probe``).

``submission`` (the form check, only when the person starting the scan let
it send empty forms) lets exactly one request through: that form's own
submission, a top-level navigation from the page to the form's action on
the same site. From then on the page the site sends back may read from the
site (GET and HEAD on the same origin, its styles and scripts), so it can
be judged as the site shows it; every write, every other navigation, and
every other site stay blocked.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Dialog, Page, Request, Route

log = get_logger(__name__)

# How long a cancelled guard keeps trying to remove itself.
_LIFT_TIMEOUT_S = 10.0


@dataclass
class Submission:
    """The one form submission a guard may let through (see the module docstring)."""

    action: str  # the form's action, as an absolute URL
    method: str  # "GET" or "POST"
    # When it was let through, in milliseconds since the epoch; None until then.
    sent_at: float | None = None

    def matches(self, request: Request) -> bool:
        """Whether ``request`` is this submission: same method, same address
        up to the query (a GET form adds its fields there)."""
        try:
            got, want = urlsplit(request.url), urlsplit(self.action)
        except ValueError:
            return False
        return (
            request.method == self.method
            and request.is_navigation_request()
            and (got.scheme, got.netloc, got.path) == (want.scheme, want.netloc, want.path)
        )


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
    page: Page,
    urls: set[str],
    blocked_labels: Sequence[str],
    *,
    strict: bool = False,
    submission: Submission | None = None,
) -> AsyncIterator[None]:
    """Block writes, new windows and document navigation before dispatch.

    A context route catches the first popup request, which page routes miss.
    Filter by owning page so concurrent crawl workers retain their guards.
    Allowed requests fall through to existing scope/egress policy.

    ``strict`` blocks every request of the page and its popups, reads too
    (see the module docstring). ``submission`` lets one form submission
    through, then the reads of the page the site sends back.
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
        if len(urls) >= 1000:
            return
        with suppress(Exception):
            if (
                request.is_navigation_request()
                and request.method == "GET"
                and safe_url(request.url, blocked_labels)
            ):
                urls.add(request.url)

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
            submission is not None
            and submission.sent_at is None
            and not popup
            and same_origin
            and request.frame == page.main_frame
            and submission.matches(request)
        ):
            submission.sent_at = time.time() * 1000
            await route.fallback()
            return
        sent = submission is not None and submission.sent_at is not None
        if (
            (strict and not sent)
            or popup
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

    async def lift() -> None:
        for popup in popups:
            with suppress(Exception):
                await popup.close()
        with suppress(Exception):
            await page.context.unroute("**/*", guard)
        page.remove_listener("dialog", dismiss)
        page.remove_listener("popup", remember_popup)

    page.on("dialog", dismiss)
    page.on("popup", remember_popup)
    try:
        # Inside the try: Playwright records the route before the browser
        # confirms it, so a caller's time limit landing here left the route
        # in place with no cleanup, refusing every later request in the
        # context (seen with the form error check on a real page).
        await page.context.route("**/*", guard)
        yield
    finally:
        # Finish lifting the guard even when a time limit cancels the caller
        # during it, then let the cancellation through. Bounded either way:
        # a time limit cancels only once, so a browser that stopped answering
        # would otherwise hang the caller here for good.
        task = asyncio.ensure_future(lift())
        try:
            await asyncio.wait_for(asyncio.shield(task), _LIFT_TIMEOUT_S)
        except TimeoutError:
            task.cancel()
            log.warning("interaction.guard_not_lifted", timeout_s=_LIFT_TIMEOUT_S)
        except asyncio.CancelledError:
            with suppress(Exception):
                await asyncio.wait_for(task, _LIFT_TIMEOUT_S)
            raise
        if blocked:
            log.info("interaction.guard", blocked_requests_or_dialogs=blocked)
