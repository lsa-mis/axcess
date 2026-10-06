"""Sign-ins waiting for "I'm signed in, start scan", kept in memory only.

A sign-in scan begins with a person signing in to the site in a browser
window Axcess opens. Until they press "I'm signed in, start scan" that is a
sign-in in progress, not a scan: it has its own ID, and there is no ``scans``
row, no Reports entry, no scan count and no history. The ``scans`` row is
created only when the scan really starts (see ``server.py``).

This registry holds those sign-ins. Its rules are the product's:

* One at a time. Asking for another while one waits gives back the one that
  waits, never a second browser.
* It does not take the one-crawl lock. A sign-in can wait while a public scan
  runs; the lock is taken when the sign-in scan starts.
* While the sign-in window is open, the sign-in lives until the person starts,
  cancels or quits Axcess. While the window is closed, a clock runs, and after
  :data:`SIGN_IN_KEEP_MINUTES` without use the sign-in is forgotten: the
  session, with the copy of the signed-in state it kept, is closed and erased.
  Reopening the window restarts the clock.
* Ending one (cancel, expiry, quitting) records nothing anywhere. To tell the
  page *why* its sign-in ended, the registry remembers the reason for the few
  most recent IDs: the ID and one word ("cancelled", "expired", "failed"), no
  site, no settings and no browser state.

Nothing here touches FastAPI, SQLite or Playwright, so unit tests drive it
with a fake session and a fake clock.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, Protocol, TypeVar

#: How long a sign-in is kept, in minutes, while its window is closed.
SIGN_IN_KEEP_MINUTES = 30
SIGN_IN_KEEP_SECONDS = SIGN_IN_KEEP_MINUTES * 60

# How many ended sign-ins keep their one-word reason. A page polls only its
# own, so a handful is plenty; the bound keeps the memory constant.
_ENDED_REMEMBERED = 16

SignInStatus = Literal["opening_browser", "awaiting_authentication"]
EndedReason = Literal["cancelled", "expired", "failed"]


class KeptSignInSession(Protocol):
    """What the registry needs from a sign-in browser session."""

    async def close(self) -> None:
        """Close every sign-in window and erase the kept signed-in state."""


SessionT = TypeVar("SessionT", bound=KeptSignInSession)


@dataclass(eq=False)
class PendingSignIn(Generic[SessionT]):
    """One sign-in in progress. ``payload`` is the caller's, opaque here."""

    id: str
    site: str
    session: SessionT
    payload: Any
    status: SignInStatus = "opening_browser"
    window_open: bool = False
    # When the window was last seen closing, on the registry's clock. None
    # while it is open, while it is opening, and while it is reopening.
    window_closed_at: float | None = None
    # Background work the caller tied to this sign-in (opening the window),
    # cancelled if the sign-in ends first.
    tasks: list[Any] = field(default_factory=list)


class SignInInProgressError(Exception):
    """A sign-in is already waiting; carries it."""

    def __init__(self, existing: PendingSignIn[Any]) -> None:
        super().__init__("A sign-in is already in progress.")
        self.existing = existing


class SignInRegistry(Generic[SessionT]):
    """The one sign-in in progress, with its expiry clock."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        keep_for_s: float = SIGN_IN_KEEP_SECONDS,
    ) -> None:
        self.clock = clock
        self.keep_for_s = keep_for_s
        self._current: PendingSignIn[SessionT] | None = None
        self._ended: OrderedDict[str, EndedReason] = OrderedDict()

    # ------------------------------------------------------------ reading

    def current(self) -> PendingSignIn[SessionT] | None:
        """The sign-in in progress, if there is one."""
        return self._current

    def get(self, sign_in_id: str) -> PendingSignIn[SessionT] | None:
        current = self._current
        if current is not None and secrets.compare_digest(current.id, sign_in_id):
            return current
        return None

    def ended_reason(self, sign_in_id: str) -> EndedReason | None:
        """Why the sign-in with this ID ended, if it ended recently."""
        return self._ended.get(sign_in_id)

    def seconds_left(self, sign_in_id: str) -> float | None:
        """Seconds until the sign-in is forgotten; None while the clock is stopped."""
        pending = self.get(sign_in_id)
        closed_at = self._closed_at(pending) if pending is not None else None
        if closed_at is None:
            return None
        return max(0.0, closed_at + self.keep_for_s - self.clock())

    # ------------------------------------------------------------ changing

    def add(self, *, site: str, session: SessionT, payload: Any) -> PendingSignIn[SessionT]:
        """Register a new sign-in, or raise with the one already waiting."""
        if self._current is not None:
            raise SignInInProgressError(self._current)
        pending = PendingSignIn(
            id=secrets.token_urlsafe(16), site=site, session=session, payload=payload
        )
        self._current = pending
        return pending

    def window_opened(self, sign_in_id: str) -> None:
        """The sign-in window is open: the sign-in is waiting, the clock stops."""
        pending = self.get(sign_in_id)
        if pending is None:
            return
        pending.status = "awaiting_authentication"
        pending.window_open = True
        pending.window_closed_at = None

    def window_closed(self, sign_in_id: str) -> None:
        """The last sign-in window closed: the clock starts (once)."""
        pending = self.get(sign_in_id)
        if pending is None:
            return
        pending.window_open = False
        if pending.window_closed_at is None:
            pending.window_closed_at = self.clock()

    def reopening(self, sign_in_id: str) -> None:
        """A reopen started: stop the clock so it restarts from zero."""
        pending = self.get(sign_in_id)
        if pending is not None:
            pending.window_closed_at = None

    def take(self, sign_in_id: str) -> PendingSignIn[SessionT] | None:
        """Hand the sign-in over to a scan. Its session stays open."""
        pending = self.get(sign_in_id)
        if pending is None:
            return None
        self._current = None
        pending.tasks.clear()
        return pending

    async def cancel(self, sign_in_id: str) -> bool:
        """End the sign-in at the person's request. False if it was not waiting."""
        return await self._end(sign_in_id, "cancelled")

    async def fail(self, sign_in_id: str) -> bool:
        """End a sign-in whose window could not open."""
        return await self._end(sign_in_id, "failed")

    async def expire_due(self) -> list[str]:
        """Forget a sign-in whose window has been closed for the whole limit."""
        current = self._current
        closed_at = self._closed_at(current) if current is not None else None
        if current is None or closed_at is None:
            return []
        if self.clock() - closed_at < self.keep_for_s:
            return []
        await self._end(current.id, "expired")
        return [current.id]

    async def close_all(self) -> None:
        """Axcess is quitting: end the sign-in at once, in memory only."""
        current = self._current
        if current is not None:
            await self._end(current.id, "cancelled")

    # ------------------------------------------------------------ internals

    def _closed_at(self, pending: PendingSignIn[SessionT]) -> float | None:
        """When the clock started, or None while it is stopped."""
        if pending.status != "awaiting_authentication" or pending.window_open:
            return None
        return pending.window_closed_at

    async def _end(self, sign_in_id: str, reason: EndedReason) -> bool:
        pending = self.get(sign_in_id)
        if pending is None:
            return False
        # Forget it first, so nothing can pick it up while it closes.
        self._current = None
        self._remember(pending.id, reason)
        tasks, pending.tasks = pending.tasks, []
        this_task = asyncio.current_task()
        for task in tasks:
            if task is not this_task and not task.done():
                task.cancel()
        session = pending.session
        # Drop every reference the registry held: the settings and the
        # session, which owns the only copy of the signed-in state.
        pending.payload = None
        with contextlib.suppress(Exception):
            await session.close()
        return True

    def _remember(self, sign_in_id: str, reason: EndedReason) -> None:
        self._ended[sign_in_id] = reason
        self._ended.move_to_end(sign_in_id)
        while len(self._ended) > _ENDED_REMEMBERED:
            self._ended.popitem(last=False)
