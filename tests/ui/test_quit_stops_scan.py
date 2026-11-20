"""Quitting Axcess stops a running scan before anything else shuts down.

Left to Python's final sweep, the scan was cancelled together with
Playwright's own connection, so a worker waiting on the browser waited
forever: the backend never exited and its Chromium windows kept running
(2026-11-20). The app's shutdown now stops the scan first, while the
browser can still be closed, and the report is left "Not finished".
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit.web import server


def test_shutting_down_stops_a_running_scan_and_waits_for_it(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    async def crawl(db_path: Path, config: object) -> None:
        events.append("started")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # The crawl's own cleanup (closing the browser) still gets to run.
            await asyncio.sleep(0.05)
            events.append("cleaned up")
            raise

    monkeypatch.setattr(server, "_run_background_crawl", crawl)
    db_path, blob_dir, _ = seeded_db
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    with TestClient(app) as client:
        response = client.post(
            "/api/scans",
            json={"url": "https://quit.example.test/", "max_pages": 5, "max_depth": 1},
        )
        assert response.status_code == 201, response.text
        for _ in range(100):
            if events:
                break
            client.get("/api/scans")
        assert events == ["started"]
    # Leaving the client runs the app's shutdown.
    assert events == ["started", "cleaned up"]


def test_shutting_down_with_no_scan_running_is_quick(seeded_db: tuple[Path, Path, int]) -> None:
    db_path, blob_dir, _ = seeded_db
    with TestClient(server.create_app(db_path=db_path, blob_dir=blob_dir)) as client:
        assert client.get("/api/scans").status_code == 200
