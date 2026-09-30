"""Headless handoff ownership, failure cleanup, and confirmation guards."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from audit.protected.egress import LoopbackEgressProxy
from audit.protected.session import (
    ManualAuthenticationError,
    ManualAuthenticationSession,
    ManualAuthState,
)


def prepared_session(monkeypatch):  # type: ignore[no-untyped-def]
    session = ManualAuthenticationSession(
        seed_url="https://app.example.test/",
        approved_target_origins=("https://app.example.test",),
        resolver=lambda _: ("8.8.8.8",),
    )
    monkeypatch.setattr(
        LoopbackEgressProxy, "server_url", property(lambda _: "http://127.0.0.1:1234")
    )
    old = SimpleNamespace(
        close=AsyncMock(), storage_state=AsyncMock(return_value={"cookies": [], "origins": []})
    )
    context = SimpleNamespace(
        close=AsyncMock(),
        add_init_script=AsyncMock(),
        route=AsyncMock(),
        route_web_socket=AsyncMock(),
        on=Mock(),
        new_page=AsyncMock(),
    )
    browser = SimpleNamespace(close=AsyncMock(), new_context=AsyncMock(return_value=context))
    pw = SimpleNamespace(
        chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)), stop=AsyncMock()
    )
    session._context = old
    session._page = SimpleNamespace(frames=[])
    session._playwright = pw
    session._state = ManualAuthState.AUTHENTICATED
    session._route_guard.activate_scan_mode()
    return session, old, browser, context, pw


async def test_transferred_context_is_owned_and_closed(monkeypatch):  # type: ignore[no-untyped-def]
    session, old, browser, context, pw = prepared_session(monkeypatch)
    pages = await session.switch_to_headless(2)
    assert len(pages) == 2
    assert session.context is context
    assert session._browser is browser
    assert session._page is None
    old.storage_state.assert_awaited_once_with(indexed_db=True)
    old.close.assert_awaited_once()
    assert pw.chromium.launch.call_args.kwargs["headless"] is True
    assert browser.new_context.call_args.kwargs["storage_state"] == old.storage_state.return_value
    assert browser.new_context.call_args.kwargs["service_workers"] == "block"
    assert browser.new_context.call_args.kwargs["accept_downloads"] is False
    assert browser.new_context.call_args.kwargs["proxy"]["server"] == "http://127.0.0.1:1234"
    context.route.assert_awaited_once_with("**/*", session._route_guard.handle_route)
    context.route_web_socket.assert_awaited_once()
    with pytest.raises(ManualAuthenticationError, match="already running"):
        await session.switch_to_headless(2)
    await session.close()
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.parametrize("failure", ["capture", "launch", "context", "page", "cancel"])
async def test_failed_handoff_never_starts_an_anonymous_crawl(monkeypatch, failure):  # type: ignore[no-untyped-def]
    session, old, browser, context, pw = prepared_session(monkeypatch)
    target = {
        "capture": old.storage_state,
        "launch": pw.chromium.launch,
        "context": browser.new_context,
        "page": context.new_page,
        "cancel": context.new_page,
    }[failure]
    target.side_effect = asyncio.CancelledError() if failure == "cancel" else RuntimeError("failed")
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else RuntimeError):
        await session.switch_to_headless(2)
    assert session.context is old
    old.close.assert_not_awaited()
    if failure not in {"capture", "launch"}:
        browser.close.assert_awaited_once()
    await session.close()
    old.close.assert_awaited_once()


async def test_handoff_requires_confirmation_and_bounded_workers(monkeypatch):  # type: ignore[no-untyped-def]
    session, old, _, _, pw = prepared_session(monkeypatch)
    session._state = ManualAuthState.AWAITING_MANUAL_AUTHENTICATION
    with pytest.raises(ManualAuthenticationError, match="Confirm sign-in"):
        await session.switch_to_headless(1)
    session._state = ManualAuthState.AUTHENTICATED
    for count in (0, 17):
        with pytest.raises(ValueError):
            await session.switch_to_headless(count)
    old.storage_state.assert_not_awaited()
    pw.chromium.launch.assert_not_awaited()


async def test_handoff_timeout_closes_new_browser(monkeypatch):  # type: ignore[no-untyped-def]
    session, old, browser, context, _ = prepared_session(monkeypatch)
    real_timeout = asyncio.timeout
    monkeypatch.setattr(asyncio, "timeout", lambda _: real_timeout(0.01))

    async def stalled_page():  # type: ignore[no-untyped-def]
        await asyncio.sleep(10)

    context.new_page.side_effect = stalled_page
    with pytest.raises(TimeoutError):
        await session.switch_to_headless(1)
    browser.close.assert_awaited_once()
    assert session.context is old
    await session.close()
