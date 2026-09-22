"""The protected-path verdict is computed once per request, and only once.

Three middleware layers ask whether a request is protected: the body-size
guard, the access guard and the cache-control guard. Each used to open its
own SQLite connection to answer, so an ordinary report request paid for
several connections and several cold page caches before routing began.

The memo lives in the ASGI scope, which is per request. These tests pin both
halves of that: it is reused within one request, and it is not reused across
requests, because a process-wide cache of "this scan is not protected" would
be an authorization bug rather than a slow page.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit.web import server

pytestmark = pytest.mark.ui


@pytest.fixture
def verdict_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every uncached protected-path computation."""
    calls: list[str] = []
    real = server._compute_is_protected_request_path

    def spy(path: str, db_path: Path) -> bool:
        calls.append(path)
        return real(path, db_path)

    monkeypatch.setattr(server, "_compute_is_protected_request_path", spy)
    return calls


def test_verdict_is_computed_once_per_request(
    client: TestClient, verdict_calls: list[str]
) -> None:
    """One report request must not re-resolve its own protected status."""
    assert client.get("/api/scans/1/issues").status_code == 200
    assert verdict_calls.count("/api/scans/1/issues") == 1, (
        f"the three middleware layers should share one verdict, saw {verdict_calls}"
    )


def test_verdict_is_not_reused_across_requests(
    client: TestClient, verdict_calls: list[str]
) -> None:
    """A second request re-resolves, so a scan turning protected takes effect."""
    assert client.get("/api/scans/1/issues").status_code == 200
    assert client.get("/api/scans/1/issues").status_code == 200
    assert verdict_calls.count("/api/scans/1/issues") == 2, (
        "each request must compute its own verdict, never inherit the last one's"
    )


def test_memo_is_keyed_on_the_path(tmp_path: Path) -> None:
    """A verdict cached for one path is never returned for another."""
    scope: dict[str, object] = {}
    db_path = tmp_path / "audit.db"

    # Resolves True without touching the database.
    assert server._is_protected_request_path("/api/protected-scans/1", db_path, scope) is True
    assert scope[server._PROTECTED_PATH_SCOPE_KEY] == ("/api/protected-scans/1", True)

    # A different path on the same scope must not read the stored verdict.
    # /api/health matches neither the scan nor the finding route pattern.
    assert server._is_protected_request_path("/api/health", db_path, scope) is False
    assert scope[server._PROTECTED_PATH_SCOPE_KEY] == ("/api/health", False)


def test_memo_is_reused_for_the_same_path(tmp_path: Path, verdict_calls: list[str]) -> None:
    """Repeating the same path on one scope does not recompute."""
    scope: dict[str, object] = {}
    db_path = tmp_path / "audit.db"

    for _ in range(3):
        server._is_protected_request_path("/api/protected-scans/1", db_path, scope)
    assert verdict_calls.count("/api/protected-scans/1") == 1


def test_no_scope_means_no_caching(tmp_path: Path, verdict_calls: list[str]) -> None:
    """Callers that pass no scope keep the original uncached behavior."""
    db_path = tmp_path / "audit.db"
    for _ in range(3):
        server._is_protected_request_path("/api/protected-scans/1", db_path)
    assert verdict_calls.count("/api/protected-scans/1") == 3
