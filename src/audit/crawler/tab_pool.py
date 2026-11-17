"""The signed-in tabs a sign-in scan's workers share.

A sign-in scan reuses tabs that already hold the session, one per worker. A
site that keeps its sign-in in ``sessionStorage`` keeps it per tab, so
every tab after the first starts from a copy of the first tab's storage
(``audit.protected.handoff``). A copy can stop working: a site that issues
a new token on every refresh can sign out the tabs whose copy is now stale,
and their pages then load as the sign-in page.

So a page that lands on a sign-in page in a copied tab is never taken at its
word. The fetcher loads it again in the first tab (``primary``). If the
first tab shows the real page, the copy was signed out: ``fall_back`` closes
every other tab and the rest of the scan runs in the first tab alone, as
sign-in scans of these sites did before. If the first tab shows a sign-in
page too, the page really is one (or the whole sign-in has ended), the copy
was not at fault, and nothing changes.

The first tab's own copy of the session is never at risk from this: it is
the tab the auditor signed in with, or the first copy, and the other tabs
are only ever compared against it.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Page

log = get_logger(__name__)


class TabPool:
    """Lend tabs to workers; on request, shrink to the first tab for good."""

    def __init__(self, pages: tuple[Page, ...], *, copied_session: bool = False) -> None:
        if not pages:
            raise ValueError("A tab pool needs at least one tab.")
        self._primary = pages[0]
        self._idle: list[Page] = list(pages)
        self._size = len(pages)
        #: True when the tabs after the first hold a copy of its
        #: sessionStorage, which is what can go stale.
        self.copied_session = copied_session and len(pages) > 1
        #: Set once the pool has fallen back to the first tab.
        self.fell_back = False
        self._changed = asyncio.Condition()

    @property
    def primary(self) -> Page:
        return self._primary

    @property
    def size(self) -> int:
        """How many tabs the scan started with."""
        return self._size

    @property
    def checks_copies(self) -> bool:
        """Whether a sign-in page in a copied tab should be checked again."""
        return self.copied_session and not self.fell_back

    async def acquire(self, *, primary: bool = False) -> Page:
        """Wait for a free tab; with ``primary``, for the first tab only."""
        async with self._changed:
            while True:
                if primary:
                    if self._primary in self._idle:
                        self._idle.remove(self._primary)
                        return self._primary
                elif self._idle:
                    return self._idle.pop(0)
                await self._changed.wait()

    async def release(self, page: Page) -> None:
        """Give a tab back. After a fall-back, any tab but the first closes."""
        async with self._changed:
            if self.fell_back and page is not self._primary:
                await _close(page)
            else:
                self._idle.append(page)
            self._changed.notify_all()

    async def fall_back(self) -> bool:
        """Use only the first tab from now on. True the first time only.

        Idle copies close now; copies a worker holds close when it gives them
        back. A worker already loading a page in a copy finishes that page.
        """
        async with self._changed:
            if self.fell_back:
                return False
            self.fell_back = True
            for page in [tab for tab in self._idle if tab is not self._primary]:
                self._idle.remove(page)
                await _close(page)
            self._changed.notify_all()
        log.warning("signed_in_tabs.fell_back", tabs=self._size)
        return True


async def _close(page: Page) -> None:
    with contextlib.suppress(Exception):
        await page.close(run_before_unload=False)
