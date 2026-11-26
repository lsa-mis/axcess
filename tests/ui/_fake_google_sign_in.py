"""A stand-in for the Google sign-in browser, for route and UI tests.

``GoogleBrowserSession`` opens a real Chromium on Google. These tests check
the server's flow and the New scan card, so the session is swapped for this
fake (``app.state.google_session_factory``, or ``server.GoogleBrowserSession``
for an app a fixture builds). ``signed_in`` is what Google would answer;
``close_window`` flips ``window_open`` as a person closing it would.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar


class FakeGoogleSession:
    instances: ClassVar[list[FakeGoogleSession]] = []
    signed_in: ClassVar[bool] = False
    fail_start: ClassVar[bool] = False
    fail_handover: ClassVar[bool] = False

    site = "accounts.google.com"

    def __init__(self) -> None:
        self.window_open = False
        self.started = False
        self.scanning = False
        self.closed = 0
        self.signed_in_checks = 0
        self._listeners: list[Callable[[bool], None]] = []
        FakeGoogleSession.instances.append(self)

    def on_window_change(self, callback: Callable[[bool], None]) -> None:
        self._listeners.append(callback)

    async def start(self) -> None:
        if FakeGoogleSession.fail_start:
            raise RuntimeError("could not open")
        self.started = True
        self._set(True)

    async def is_signed_in(self) -> bool:
        self.signed_in_checks += 1
        return FakeGoogleSession.signed_in

    async def enter_scan_mode(self) -> None:
        if FakeGoogleSession.fail_handover:
            raise RuntimeError("handover failed")
        self.scanning = True
        self._set(False)

    def close_window(self) -> None:
        self.window_open = False

    async def close(self) -> None:
        self.closed += 1
        self.window_open = False

    def _set(self, value: bool) -> None:
        self.window_open = value
        for callback in self._listeners:
            callback(value)
