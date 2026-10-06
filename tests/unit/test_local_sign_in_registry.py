"""The registry of sign-ins waiting for "I'm signed in, start scan".

One sign-in at a time; a clock that runs only while the sign-in window is
closed and restarts when it reopens; forgotten after 30 minutes of that; and
erased completely on cancel and on expiry, with only a one-word reason left
behind for the page to explain itself.
"""

from __future__ import annotations

import asyncio

import pytest

from audit.web.local_sign_in import (
    SIGN_IN_KEEP_MINUTES,
    SIGN_IN_KEEP_SECONDS,
    SignInInProgressError,
    SignInRegistry,
)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeSession:
    """Stands in for the browser session; records being closed."""

    def __init__(self) -> None:
        self.closed = False
        self.kept: dict[str, str] | None = {"cookie": "signed-in"}

    async def close(self) -> None:
        self.closed = True
        self.kept = None


def _registry() -> tuple[SignInRegistry[_FakeSession], _FakeClock]:
    clock = _FakeClock()
    return SignInRegistry(clock=clock), clock


def _waiting(registry: SignInRegistry[_FakeSession]) -> tuple[str, _FakeSession]:
    session = _FakeSession()
    pending = registry.add(site="accessibility.umich.edu", session=session, payload={"x": 1})
    registry.window_opened(pending.id)
    return pending.id, session


def test_the_limit_is_thirty_minutes() -> None:
    assert SIGN_IN_KEEP_MINUTES == 30
    assert SIGN_IN_KEEP_SECONDS == 30 * 60


def test_only_one_sign_in_waits_at_a_time() -> None:
    registry, _ = _registry()
    first = registry.add(site="a.example.edu", session=_FakeSession(), payload=None)

    with pytest.raises(SignInInProgressError) as raised:
        registry.add(site="b.example.edu", session=_FakeSession(), payload=None)

    assert raised.value.existing is first
    assert registry.current() is first


def test_a_new_sign_in_is_opening_and_its_clock_is_stopped() -> None:
    registry, clock = _registry()
    pending = registry.add(site="a.example.edu", session=_FakeSession(), payload=None)

    assert pending.status == "opening_browser"
    clock.advance(SIGN_IN_KEEP_SECONDS * 2)
    assert registry.seconds_left(pending.id) is None


async def test_the_clock_does_not_run_while_the_window_is_open() -> None:
    registry, clock = _registry()
    sign_in_id, session = _waiting(registry)

    clock.advance(SIGN_IN_KEEP_SECONDS * 10)

    assert await registry.expire_due() == []
    assert registry.get(sign_in_id) is not None
    assert not session.closed


async def test_it_expires_thirty_minutes_after_the_window_closed() -> None:
    registry, clock = _registry()
    sign_in_id, session = _waiting(registry)
    registry.window_closed(sign_in_id)

    clock.advance(SIGN_IN_KEEP_SECONDS - 1)
    assert await registry.expire_due() == []
    assert registry.seconds_left(sign_in_id) == pytest.approx(1)

    clock.advance(1)
    assert await registry.expire_due() == [sign_in_id]

    # Erased: no sign-in, the session closed (which drops its kept copy),
    # and the registry holds nothing of it but the one-word reason.
    assert registry.current() is None
    assert registry.get(sign_in_id) is None
    assert session.closed
    assert session.kept is None
    assert registry.ended_reason(sign_in_id) == "expired"


async def test_a_second_close_does_not_restart_the_clock() -> None:
    registry, clock = _registry()
    sign_in_id, _ = _waiting(registry)
    registry.window_closed(sign_in_id)
    clock.advance(SIGN_IN_KEEP_SECONDS - 10)

    registry.window_closed(sign_in_id)
    clock.advance(10)

    assert await registry.expire_due() == [sign_in_id]


async def test_reopening_restarts_the_clock() -> None:
    registry, clock = _registry()
    sign_in_id, session = _waiting(registry)
    registry.window_closed(sign_in_id)
    clock.advance(SIGN_IN_KEEP_SECONDS - 60)

    registry.reopening(sign_in_id)
    clock.advance(600)
    # Stopped while the window reopens.
    assert registry.seconds_left(sign_in_id) is None
    registry.window_opened(sign_in_id)
    clock.advance(SIGN_IN_KEEP_SECONDS * 3)
    assert await registry.expire_due() == []

    # Closed again: a full 30 minutes from now, not what was left before.
    registry.window_closed(sign_in_id)
    clock.advance(SIGN_IN_KEEP_SECONDS - 1)
    assert await registry.expire_due() == []
    clock.advance(1)
    assert await registry.expire_due() == [sign_in_id]
    assert session.closed


async def test_a_reopen_that_fails_restarts_the_clock_from_zero() -> None:
    registry, clock = _registry()
    sign_in_id, _ = _waiting(registry)
    registry.window_closed(sign_in_id)
    clock.advance(SIGN_IN_KEEP_SECONDS - 60)

    registry.reopening(sign_in_id)
    registry.window_closed(sign_in_id)  # the reopen failed

    assert registry.seconds_left(sign_in_id) == pytest.approx(SIGN_IN_KEEP_SECONDS)


async def test_cancel_erases_the_sign_in_and_records_only_why() -> None:
    registry, _ = _registry()
    sign_in_id, session = _waiting(registry)
    pending = registry.get(sign_in_id)
    assert pending is not None

    assert await registry.cancel(sign_in_id) is True

    assert registry.current() is None
    assert session.closed
    assert session.kept is None
    assert pending.payload is None
    assert registry.ended_reason(sign_in_id) == "cancelled"
    # A second cancel finds nothing to end.
    assert await registry.cancel(sign_in_id) is False


async def test_cancel_stops_the_work_tied_to_the_sign_in() -> None:
    registry, _ = _registry()
    pending = registry.add(site="a.example.edu", session=_FakeSession(), payload=None)
    opening = asyncio.create_task(asyncio.sleep(3600))
    pending.tasks.append(opening)

    await registry.cancel(pending.id)
    await asyncio.sleep(0)

    assert opening.cancelled()


async def test_after_it_ends_a_new_sign_in_can_start() -> None:
    registry, _ = _registry()
    sign_in_id, _ = _waiting(registry)
    await registry.cancel(sign_in_id)

    fresh = registry.add(site="a.example.edu", session=_FakeSession(), payload=None)

    assert fresh.id != sign_in_id
    assert registry.current() is fresh


async def test_taking_it_for_a_scan_keeps_the_session_open() -> None:
    registry, _ = _registry()
    sign_in_id, session = _waiting(registry)

    taken = registry.take(sign_in_id)

    assert taken is not None and taken.session is session
    assert not session.closed
    assert registry.current() is None
    assert registry.ended_reason(sign_in_id) is None


async def test_a_wrong_id_reads_nothing() -> None:
    registry, _ = _registry()
    _waiting(registry)

    assert registry.get("not-the-id-of-this-sign-in") is None
    assert await registry.cancel("not-the-id-of-this-sign-in") is False
    assert registry.current() is not None


async def test_quitting_ends_the_sign_in_at_once() -> None:
    registry, _ = _registry()
    _, session = _waiting(registry)

    await registry.close_all()

    assert registry.current() is None
    assert session.closed


async def test_only_a_few_reasons_are_remembered() -> None:
    registry, _ = _registry()
    ids = []
    for _ in range(40):
        sign_in_id, _session = _waiting(registry)
        ids.append(sign_in_id)
        await registry.cancel(sign_in_id)

    assert registry.ended_reason(ids[0]) is None
    assert registry.ended_reason(ids[-1]) == "cancelled"
