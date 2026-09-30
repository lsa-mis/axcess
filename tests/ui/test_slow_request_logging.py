"""Slow API requests get logged; ordinary ones stay quiet.

Nothing timed a request before this, so a projection that grew with a
report's size was indistinguishable from a fast one until somebody waited
for it. The threshold keeps a normal session silent, which is what makes
the line worth reading when it does appear.

These assert on the logger rather than on captured output. Where the
rendered line lands depends on whether ``configure_logging`` has run yet,
which depends on what else the suite has done, so reading stdout here
passes alone and fails in a full run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.web import server
from audit.web.server import create_app

pytestmark = pytest.mark.ui


class _RecordingLogger:
    """Stands in for the module logger, keeping the warning keyword args."""

    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, Any]]] = []

    def warning(self, event: str, **kwargs: Any) -> None:
        self.warnings.append((event, kwargs))

    def __getattr__(self, _name: str) -> Any:
        # Every other level is a no-op; this logger exists for one assertion.
        return lambda *args, **kwargs: None


@pytest.fixture
def recorded_warnings(monkeypatch: pytest.MonkeyPatch) -> _RecordingLogger:
    recorder = _RecordingLogger()
    monkeypatch.setattr(server, "log", recorder)
    return recorder


def _client(seeded_db: tuple[Path, Path, int]) -> TestClient:
    db_path, blob_dir, _ = seeded_db
    return TestClient(create_app(db_path=db_path, blob_dir=blob_dir))


def _slow_requests(recorder: _RecordingLogger) -> list[dict[str, Any]]:
    return [kwargs for event, kwargs in recorder.warnings if event == "http.slow_request"]


def test_fast_request_logs_nothing(
    seeded_db: tuple[Path, Path, int], recorded_warnings: _RecordingLogger
) -> None:
    """A normal request must not add a line to the operator's log."""
    client = _client(seeded_db)

    assert client.get("/api/scans/1/issues").status_code == 200

    assert _slow_requests(recorded_warnings) == []


def test_threshold_zero_logs_every_request(
    seeded_db: tuple[Path, Path, int],
    recorded_warnings: _RecordingLogger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero times every request, which is also how to get a full request log."""
    monkeypatch.setenv("AUDIT_SLOW_REQUEST_MS", "0")
    client = _client(seeded_db)

    assert client.get("/api/scans/1/issues").status_code == 200

    logged = _slow_requests(recorded_warnings)
    assert len(logged) == 1
    assert logged[0]["status"] == 200
    assert logged[0]["method"] == "GET"
    assert isinstance(logged[0]["duration_ms"], float)


def test_slow_request_reports_the_route_not_the_path(
    seeded_db: tuple[Path, Path, int],
    recorded_warnings: _RecordingLogger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scan id must not reach the log, so a report's requests group up."""
    monkeypatch.setenv("AUDIT_SLOW_REQUEST_MS", "0")
    client = _client(seeded_db)

    assert client.get("/api/scans/1/issues").status_code == 200

    route = _slow_requests(recorded_warnings)[0]["route"]
    assert route == "/api/scans/{scan_id:int}/issues"
    assert "/api/scans/1/" not in route


def test_unmatched_path_is_still_timed(
    seeded_db: tuple[Path, Path, int],
    recorded_warnings: _RecordingLogger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 has no route to name, and must not crash the middleware."""
    monkeypatch.setenv("AUDIT_SLOW_REQUEST_MS", "0")
    client = _client(seeded_db)

    assert client.get("/api/definitely-not-a-route").status_code == 404

    assert _slow_requests(recorded_warnings)[0]["route"] == "unmatched"
