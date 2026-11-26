"""The Google sign-in routes for a public scan's Google files (2026-11-26).

``POST /api/scans`` with ``google_sign_in`` opens a Google window and
answers with a sign-in, not a scan; ``/api/google-sign-ins/{id}/start``
checks the sign-in and starts the crawl with the session; cancel, expiry
and quitting close it. The session is ``FakeGoogleSession``: no browser
opens and nothing contacts Google.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.db.schema import connect

from ._fake_google_sign_in import FakeGoogleSession

LOCAL = "http://127.0.0.1:8765"
ORIGIN = {"origin": LOCAL}
SCAN_BODY: dict[str, Any] = {
    "url": "https://www.example.edu/",
    "max_pages": 5,
    "google_sign_in": True,
}


@pytest.fixture
def fake_google(monkeypatch: pytest.MonkeyPatch) -> type[FakeGoogleSession]:
    monkeypatch.setattr(FakeGoogleSession, "instances", [])
    monkeypatch.setattr(FakeGoogleSession, "signed_in", False)
    monkeypatch.setattr(FakeGoogleSession, "fail_start", False)
    monkeypatch.setattr(FakeGoogleSession, "fail_handover", False)
    monkeypatch.setattr(FakeGoogleSession, "fail_reopen", False)
    return FakeGoogleSession


@pytest.fixture
def started_crawls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stand in for the crawl: record what it was started with, never crawl."""
    from audit.web import server

    started: list[dict[str, Any]] = []

    async def _no_crawl(_db: Path, config: Any, *, google_files: Any = None) -> None:
        started.append({"config": config, "google_files": google_files})
        await asyncio.sleep(0)
        if google_files is not None:
            await google_files.close()

    monkeypatch.setattr(server, "_run_background_crawl", _no_crawl)
    return started


def _app(seeded_db: tuple[Path, Path, int]) -> Any:
    from audit.web import server

    db_path, blob_dir, _ = seeded_db
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    app.state.google_session_factory = FakeGoogleSession
    return app


def _local(app: Any) -> TestClient:
    return TestClient(app, base_url=LOCAL, client=("127.0.0.1", 45678))


def _wait(client: TestClient, sign_in_id: str, status: str = "awaiting_authentication") -> Any:
    deadline = time.monotonic() + 5
    while True:
        body = client.get(f"/api/google-sign-ins/{sign_in_id}").json()
        if body.get("status") == status or time.monotonic() > deadline:
            return body
        time.sleep(0.02)


def _scan_count(seeded_db: tuple[Path, Path, int]) -> int:
    with connect(seeded_db[0]) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0])


def test_starting_with_google_gives_a_sign_in_not_a_scan(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    before = _scan_count(seeded_db)
    with _local(_app(seeded_db)) as client:
        response = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY)
        assert response.status_code == 202, response.text
        body = response.json()
        assert "scan_id" not in body
        sign_in = body["google_sign_in"]
        assert sign_in["status"] == "opening_browser"
        assert sign_in["settings"]["google_sign_in"] is True
        state = _wait(client, sign_in["sign_in_id"])
        assert state["window_open"] is True
        # Asking again gives back the one that waits: one window at a time.
        again = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY)
        assert again.status_code == 200
        assert again.json()["google_sign_in"]["sign_in_id"] == sign_in["sign_in_id"]
        assert again.json()["google_sign_in"]["already_waiting"] is True
    assert len(fake_google.instances) == 1
    assert _scan_count(seeded_db) == before
    assert started_crawls == []


def test_the_waiting_google_sign_in_can_be_found_again(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    """``/current``, as for a site sign-in: New scan returns to the Google
    sign-in still waiting after the person left the page (2026-11-26)."""
    with _local(_app(seeded_db)) as client:
        assert client.get("/api/google-sign-ins/current", headers=ORIGIN).json() == {
            "sign_in": None
        }
        sign_in = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()["google_sign_in"]
        _wait(client, sign_in["sign_in_id"])
        current = client.get("/api/google-sign-ins/current", headers=ORIGIN)
        assert current.headers["cache-control"] == "no-store"
        found = current.json()["sign_in"]
        assert found["sign_in_id"] == sign_in["sign_in_id"]
        assert found["status"] == "awaiting_authentication"
        # The form's entries, to refill the form if the person cancels.
        assert found["settings"]["url"] == SCAN_BODY["url"]
        client.post(f"/api/google-sign-ins/{sign_in['sign_in_id']}/cancel", headers=ORIGIN)
        assert client.get("/api/google-sign-ins/current", headers=ORIGIN).json() == {
            "sign_in": None
        }
    assert started_crawls == []


def test_without_google_a_public_scan_starts_as_before(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    with _local(_app(seeded_db)) as client:
        response = client.post("/api/scans", json={**SCAN_BODY, "google_sign_in": False})
        assert response.status_code == 201
        assert isinstance(response.json()["scan_id"], int)
    assert fake_google.instances == []
    assert started_crawls and started_crawls[0]["google_files"] is None
    assert started_crawls[0]["config"].google_sign_in is False


def test_google_sign_in_needs_the_document_check(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    with _local(_app(seeded_db)) as client:
        response = client.post("/api/scans", json={**SCAN_BODY, "skip_documents": True})
        assert response.status_code == 201
    assert fake_google.instances == []
    assert started_crawls[0]["config"].google_sign_in is False


def test_start_is_refused_until_google_says_signed_in(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    before = _scan_count(seeded_db)
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        refused = client.post(f"/api/google-sign-ins/{sign_in_id}/start", headers=ORIGIN)
        assert refused.status_code == 409
        assert refused.json()["error"] == (
            "Google says you are not signed in yet. Finish signing in in the Google "
            "window, then try again."
        )
        # Still waiting, and no scan.
        assert _wait(client, sign_in_id)["status"] == "awaiting_authentication"
        assert _scan_count(seeded_db) == before

        fake_google.signed_in = True
        started = client.post(f"/api/google-sign-ins/{sign_in_id}/start", headers=ORIGIN)
        assert started.status_code == 201, started.text
        scan_id = started.json()["scan_id"]
        deadline = time.monotonic() + 5
        while not started_crawls and time.monotonic() < deadline:
            time.sleep(0.02)
    session = fake_google.instances[0]
    assert session.scanning, "the window was closed and the profile reopened headless"
    assert started_crawls[0]["google_files"] is session
    assert started_crawls[0]["config"].scan_id == scan_id
    assert started_crawls[0]["config"].google_sign_in is True
    assert session.closed >= 1
    assert _scan_count(seeded_db) == before + 1
    with connect(seeded_db[0]) as conn:
        stored = conn.execute("SELECT config_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
    assert '"google_sign_in": true' in stored[0]


def test_start_with_the_window_closed_asks_google_and_starts_when_signed_in(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    """A closed window no longer refuses the start (2026-11-26): the session
    asks Google through a hidden browser on the same profile."""
    fake_google.signed_in = True
    before = _scan_count(seeded_db)
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        fake_google.instances[0].close_window()
        state = client.get(f"/api/google-sign-ins/{sign_in_id}").json()
        assert state["window_open"] is False
        started = client.post(f"/api/google-sign-ins/{sign_in_id}/start", headers=ORIGIN)
        assert started.status_code == 201, started.text
        deadline = time.monotonic() + 5
        while not started_crawls and time.monotonic() < deadline:
            time.sleep(0.02)
    session = fake_google.instances[0]
    assert session.hidden_checks == 1
    assert session.scanning
    assert session.reopens == 0, "no window opens for the start"
    assert started_crawls[0]["google_files"] is session
    assert _scan_count(seeded_db) == before + 1


def test_start_with_the_window_closed_and_signed_out_is_refused_and_kept(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    before = _scan_count(seeded_db)
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        fake_google.instances[0].close_window()
        client.get(f"/api/google-sign-ins/{sign_in_id}")
        refused = client.post(f"/api/google-sign-ins/{sign_in_id}/start", headers=ORIGIN)
        assert refused.status_code == 409
        assert refused.json()["error"] == (
            "Google says you are not signed in yet. Finish signing in in the Google "
            "window, then try again."
        )
        kept = client.get(f"/api/google-sign-ins/{sign_in_id}").json()
        assert kept["status"] == "awaiting_authentication"
        assert kept["window_open"] is False
    session = fake_google.instances[0]
    assert session.hidden_checks == 1
    assert not session.scanning
    assert started_crawls == []
    assert _scan_count(seeded_db) == before


def test_reopen_opens_the_window_again_and_the_clock_stops(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    """As a closed site sign-in window (2026-11-26): reopen keeps the
    sign-in, stops the clock, restarts it from zero if the reopen fails,
    and is refused while the window is open."""
    app = _app(seeded_db)
    with _local(app) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        registry = app.state.google_sign_ins
        now = [10_000.0]
        registry.clock = lambda: now[0]

        open_now = client.post(f"/api/google-sign-ins/{sign_in_id}/reopen", headers=ORIGIN)
        assert open_now.status_code == 409
        assert open_now.json()["error"] == "The Google window is already open."

        fake_google.instances[0].close_window()
        client.get(f"/api/google-sign-ins/{sign_in_id}")
        now[0] += 100
        assert registry.seconds_left(sign_in_id) == 1700

        fake_google.fail_reopen = True
        failed = client.post(f"/api/google-sign-ins/{sign_in_id}/reopen", headers=ORIGIN)
        assert failed.status_code == 503
        assert failed.json()["error"] == (
            "Axcess could not reopen the Google window. Your Google sign-in is still kept. "
            "Try again, or start the scan."
        )
        kept = client.get(f"/api/google-sign-ins/{sign_in_id}").json()
        assert kept["status"] == "awaiting_authentication"
        assert kept["window_open"] is False
        # Restarted from zero.
        assert registry.seconds_left(sign_in_id) == 1800

        fake_google.fail_reopen = False
        reopened = client.post(f"/api/google-sign-ins/{sign_in_id}/reopen", headers=ORIGIN)
        assert reopened.status_code == 200, reopened.text
        assert reopened.headers["cache-control"] == "no-store"
        assert reopened.json()["status"] == "awaiting_authentication"
        assert reopened.json()["window_open"] is True
        assert registry.seconds_left(sign_in_id) is None
        now[0] += 10_000
        assert client.get(f"/api/google-sign-ins/{sign_in_id}").json()["window_open"] is True
    session = fake_google.instances[0]
    assert session.reopens == 2
    assert len(fake_google.instances) == 1, "the same session, the same profile"
    assert started_crawls == []


def test_reopen_is_for_this_computer_only_and_for_a_waiting_sign_in(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    app = _app(seeded_db)
    with _local(app) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        fake_google.instances[0].close_window()
        client.get(f"/api/google-sign-ins/{sign_in_id}")
        no_origin = client.post(f"/api/google-sign-ins/{sign_in_id}/reopen")
        foreign = client.post(
            f"/api/google-sign-ins/{sign_in_id}/reopen", headers={"origin": "https://evil.example"}
        )
        # Not entered: entering would run the app's shutdown, ending the sign-in.
        lan = TestClient(app, base_url="http://192.168.1.20:8765", client=("192.168.1.30", 4000))
        remote = lan.post(
            f"/api/google-sign-ins/{sign_in_id}/reopen",
            headers={"origin": "http://192.168.1.20:8765"},
        )
        for refused in (no_origin, foreign, remote):
            assert refused.status_code == 403
            assert "only on the computer that runs Axcess" in refused.json()["error"]
        assert fake_google.instances[0].reopens == 0
        client.post(f"/api/google-sign-ins/{sign_in_id}/cancel", headers=ORIGIN)
        ended = client.post(f"/api/google-sign-ins/{sign_in_id}/reopen", headers=ORIGIN)
        assert ended.status_code == 404
    assert fake_google.instances[0].reopens == 0


def test_start_respects_the_crawl_lock(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from audit.web import server

    async def _long_crawl(_db: Path, _config: Any, *, google_files: Any = None) -> None:
        # Runs until the app's shutdown stops it.
        await asyncio.sleep(3600)

    monkeypatch.setattr(server, "_run_background_crawl", _long_crawl)
    fake_google.signed_in = True
    with _local(_app(seeded_db)) as client:
        running = client.post("/api/scans", json={**SCAN_BODY, "google_sign_in": False})
        assert running.status_code == 201
        # The form refuses a second scan before any window opens.
        blocked = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY)
        assert blocked.status_code == 409
        assert fake_google.instances == []
    # A sign-in opened before the other scan started waits for it.
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        running = client.post("/api/scans", json={**SCAN_BODY, "google_sign_in": False})
        assert running.status_code == 201
        refused = client.post(f"/api/google-sign-ins/{sign_in_id}/start", headers=ORIGIN)
        assert refused.status_code == 409
        assert "already running" in refused.json()["error"]
        assert _wait(client, sign_in_id)["status"] == "awaiting_authentication"
        assert fake_google.instances[0].scanning is False


def test_cancel_closes_the_session(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        cancelled = client.post(f"/api/google-sign-ins/{sign_in_id}/cancel", headers=ORIGIN)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert client.get(f"/api/google-sign-ins/{sign_in_id}").json()["status"] == "cancelled"
        start = client.post(f"/api/google-sign-ins/{sign_in_id}/start", headers=ORIGIN)
        assert start.status_code == 404
    assert fake_google.instances[0].closed == 1
    assert started_crawls == []


def test_a_failed_handover_signs_out_and_starts_nothing(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    fake_google.signed_in = True
    fake_google.fail_handover = True
    before = _scan_count(seeded_db)
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        response = client.post(f"/api/google-sign-ins/{sign_in_id}/start", headers=ORIGIN)
        assert response.status_code == 503
    assert fake_google.instances[0].closed == 1
    assert started_crawls == []
    assert _scan_count(seeded_db) == before


def test_a_window_that_cannot_open_ends_the_sign_in(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    fake_google.fail_start = True
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        state = _wait(client, sign_in_id, "failed")
        assert state["status"] == "failed"
        assert "could not open the Google window" in state["error"]


def test_google_sign_in_is_for_this_computer_only(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    app = _app(seeded_db)
    with TestClient(app, base_url="http://192.168.1.20:8765", client=("192.168.1.30", 4000)) as lan:
        response = lan.post(
            "/api/scans", headers={"origin": "http://192.168.1.20:8765"}, json=SCAN_BODY
        )
        assert response.status_code == 403
        assert "only on the computer that runs Axcess" in response.json()["error"]
    # A request from this computer but another page's origin is refused too.
    with _local(app) as client:
        foreign = client.post(
            "/api/scans", headers={"origin": "https://evil.example"}, json=SCAN_BODY
        )
        assert foreign.status_code == 403
    assert fake_google.instances == []
    assert started_crawls == []


def test_quitting_axcess_closes_a_waiting_google_sign_in(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
    # Leaving the ``with`` ran the app's shutdown hooks.
    assert fake_google.instances[0].closed == 1


def test_a_closed_window_is_forgotten_after_the_limit(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from audit.web import local_sign_in

    monkeypatch.setattr(local_sign_in, "SIGN_IN_KEEP_SECONDS", 0.3)
    with _local(_app(seeded_db)) as client:
        sign_in_id = client.post("/api/scans", headers=ORIGIN, json=SCAN_BODY).json()[
            "google_sign_in"
        ]["sign_in_id"]
        _wait(client, sign_in_id)
        fake_google.instances[0].close_window()
        client.get(f"/api/google-sign-ins/{sign_in_id}")
        assert _wait(client, sign_in_id, "expired")["status"] == "expired"
    assert fake_google.instances[0].closed == 1


def test_continuing_a_scan_never_signs_in_to_google(
    seeded_db: tuple[Path, Path, int],
    fake_google: type[FakeGoogleSession],
    started_crawls: list[dict[str, Any]],
) -> None:
    from audit.crawler.orchestrator import CrawlConfig, config_json_for_scan

    config = CrawlConfig(seed_url="https://www.example.edu/", google_sign_in=True)
    with connect(seeded_db[0]) as conn:
        scan_id = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'interrupted', ?)",
                ("https://www.example.edu/", config_json_for_scan(config)),
            ).lastrowid
            or 0
        )
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state, dedupe_key) "
            "VALUES ('fetch', ?, 'pending', ?)",
            (json.dumps({"scan_id": scan_id, "url": "https://www.example.edu/a"}), f"{scan_id}:a"),
        )
        conn.commit()
    with _local(_app(seeded_db)) as client:
        settings = client.get(f"/api/scans/{scan_id}/settings").json()["settings"]
        assert settings["google_sign_in"] is True
        response = client.post(f"/api/scans/{scan_id}/continue")
        assert response.status_code == 202, response.text
    assert fake_google.instances == []
    assert started_crawls[0]["google_files"] is None
    assert started_crawls[0]["config"].google_sign_in is False
