"""A stand-in for the sign-in browser, for route and UI tests.

``ManualAuthenticationSession`` opens a real headed Chromium. These tests
check the server's sign-in flow (no scan row before the start, one sign-in at
a time, the clock while the window is closed), so they swap the session for
this fake through ``server.ManualAuthenticationSession``.

``close_window`` only flips ``window_open``, the way a person closing the
window looks from outside. The server reads that on its next request, as it
does for the real session, so a test thread never calls into the server's
event loop.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, ClassVar

from fastapi.testclient import TestClient

LOCAL_BASE = "http://127.0.0.1:8765"
LOCAL_ORIGIN = {"origin": LOCAL_BASE}
SIGN_IN_BODY: dict[str, Any] = {
    "seed_url": "https://app.example.test/secure/",
    "approved_auth_origins": [],
    "authorization_acknowledged": True,
}


class FakeSignInSession:
    """Records what the server asks of the sign-in browser."""

    instances: ClassVar[list[FakeSignInSession]] = []
    fail_start: ClassVar[bool] = False

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.window_open = False
        self.started = False
        self.closed = False
        self.reopened = 0
        self.kept: dict[str, str] | None = None
        self._listeners: list[Callable[[bool], None]] = []
        FakeSignInSession.instances.append(self)

    def on_window_change(self, callback: Callable[[bool], None]) -> None:
        self._listeners.append(callback)

    async def start(self) -> None:
        if FakeSignInSession.fail_start:
            raise RuntimeError("https://private.example.test/secret could not open")
        self.started = True
        self.kept = {"cookie": "signed-in"}
        self._set(True)

    def close_window(self) -> None:
        self.window_open = False

    async def reopen_window(self) -> None:
        self.reopened += 1
        self._set(True)

    async def close(self) -> None:
        self.closed = True
        self.window_open = False
        self.kept = None

    def _set(self, value: bool) -> None:
        self.window_open = value
        for callback in self._listeners:
            callback(value)


def local_client(app: Any) -> TestClient:
    """A client the server treats as a browser on the Axcess computer."""
    return TestClient(app, base_url=LOCAL_BASE, client=("127.0.0.1", 45678))


def wait_for_sign_in(
    client: TestClient, sign_in_id: str, status: str = "awaiting_authentication"
) -> dict[str, Any]:
    """Poll a sign-in until it reaches ``status``; the window opens in a task."""
    deadline = time.monotonic() + 5
    while True:
        body: dict[str, Any] = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
        if body.get("status") == status or time.monotonic() > deadline:
            return body
        time.sleep(0.02)


def open_sign_in(client: TestClient, **fields: Any) -> dict[str, Any]:
    """Open a sign-in and wait until its window is open."""
    response = client.post(
        "/api/local-login-scans", headers=LOCAL_ORIGIN, json={**SIGN_IN_BODY, **fields}
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    body = wait_for_sign_in(client, created["sign_in_id"])
    assert body["status"] == "awaiting_authentication", body
    return body


def start_sign_in_scan(client: TestClient, sign_in_id: str) -> Any:
    return client.post(f"/api/local-sign-ins/{sign_in_id}/start", headers=LOCAL_ORIGIN)
