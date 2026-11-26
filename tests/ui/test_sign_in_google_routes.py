"""A sign-in scan with "Sign in to Google for Google files" (2026-11-26).

One flow, two separate browsers, one after another: the site's sign-in
window as before, then, from "I'm signed in to the site, next: sign in to
Google" (``POST /api/local-sign-ins/{id}/google``), a second, separate Google
window tied to the same sign-in. "I'm signed in to Google, start scan" (the
same ``/start``) checks Google, hands the site session to the scan as
before and the Google session to the document check only. Cancel, expiry,
a failed start and quitting close both.

Fakes only: ``FakeSignInSession`` for the site's browser,
``FakeGoogleSession`` for Google's. No browser opens and nothing is
contacted.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.db.schema import connect

from ._fake_google_sign_in import FakeGoogleSession
from ._fake_sign_in import (
    LOCAL_ORIGIN,
    SIGN_IN_BODY,
    local_client,
    open_sign_in,
    start_sign_in_scan,
)

NOT_SIGNED_IN = (
    "Google says you are not signed in yet. Finish signing in in the Google window, then try again."
)


@pytest.fixture
def fake_google(monkeypatch: pytest.MonkeyPatch) -> type[FakeGoogleSession]:
    monkeypatch.setattr(FakeGoogleSession, "instances", [])
    monkeypatch.setattr(FakeGoogleSession, "signed_in", False)
    monkeypatch.setattr(FakeGoogleSession, "fail_start", False)
    monkeypatch.setattr(FakeGoogleSession, "fail_handover", False)
    monkeypatch.setattr(FakeGoogleSession, "fail_reopen", False)
    return FakeGoogleSession


def _app(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, list[tuple[Any, Any]]]:
    """The app with both fake browsers and a crawl that only records itself."""
    from audit.web import server

    db_path, blob_dir, _ = seeded_db
    runs: list[tuple[Any, Any]] = []

    async def _recorded_run(_db: object, _blobs: object, config: object, run: object) -> None:
        runs.append((config, run))

    monkeypatch.setattr(server, "_run_local_login_background", _recorded_run)
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    app.state.google_session_factory = FakeGoogleSession
    return app, runs


def _scan_count(db_path: Path) -> int:
    with connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0])


def _open_google(client: TestClient, sign_in_id: str) -> dict[str, Any]:
    response = client.post(f"/api/local-sign-ins/{sign_in_id}/google", headers=LOCAL_ORIGIN)
    assert response.status_code == 200, response.text
    deadline = time.monotonic() + 5
    while True:
        body: dict[str, Any] = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
        google = body.get("google") or {}
        if google.get("status") != "opening_browser" or time.monotonic() > deadline:
            return body
        time.sleep(0.02)


def test_the_request_takes_the_switch_and_the_config_carries_it(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch, fake_sign_in: type
) -> None:
    app, _runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        pending = app.state.local_sign_ins.get(state["sign_in_id"])
        assert pending.payload.google_sign_in is True
        # The form's own settings come back with it, to refill the form.
        assert state["settings"]["google_sign_in"] is True
        # No Google window until "next: sign in to Google".
        assert state["google"] is None
    assert FakeGoogleSession.instances == []


def test_the_switch_needs_the_document_check(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch, fake_sign_in: type
) -> None:
    app, _runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        refused = client.post(
            "/api/local-login-scans",
            headers=LOCAL_ORIGIN,
            json={**SIGN_IN_BODY, "google_sign_in": True, "skip_documents": True},
        )
    assert refused.status_code == 422
    assert "needs the check of the documents" in refused.text
    assert fake_sign_in.instances == []


def test_google_opens_a_second_separate_session_and_is_idempotent(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        sign_in_id = state["sign_in_id"]
        opened = _open_google(client, sign_in_id)
        assert opened["google"] == {
            "status": "awaiting_authentication",
            "window_open": True,
            "error": None,
        }
        # The site sign-in waits as it was, its window untouched.
        assert opened["status"] == "awaiting_authentication"
        assert opened["window_open"] is True
        again = client.post(f"/api/local-sign-ins/{sign_in_id}/google", headers=LOCAL_ORIGIN)
        assert again.status_code == 200
        assert again.json()["google"]["status"] == "awaiting_authentication"
        current = client.get("/api/local-sign-ins/current").json()["sign_in"]
        assert current["google"]["window_open"] is True
    assert len(fake_google.instances) == 1
    site = fake_sign_in.instances[0]
    google = fake_google.instances[0]
    assert google is not site
    assert google.started and site.started
    assert fake_google.instances[0].signed_in_checks == 0, "opening checks nothing about Google"
    assert runs == []


def test_google_is_refused_without_the_switch(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, _runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client)
        refused = client.post(
            f"/api/local-sign-ins/{state['sign_in_id']}/google", headers=LOCAL_ORIGIN
        )
    assert refused.status_code == 409
    assert "does not sign in to Google" in refused.json()["detail"]
    assert fake_google.instances == []


def test_google_is_loopback_only(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, _runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        sign_in_id = state["sign_in_id"]
        # Same computer, but without its own origin: a page elsewhere.
        no_origin = client.post(f"/api/local-sign-ins/{sign_in_id}/google")
        foreign = client.post(
            f"/api/local-sign-ins/{sign_in_id}/google",
            headers={"origin": "http://evil.example.test"},
        )
    with TestClient(app, base_url="http://192.168.1.20:8765", client=("192.168.1.30", 1)) as lan:
        remote = lan.post(
            f"/api/local-sign-ins/{sign_in_id}/google",
            headers={"origin": "http://192.168.1.20:8765"},
        )
    assert no_origin.status_code == 403
    assert foreign.status_code == 403
    assert remote.status_code == 403
    assert fake_google.instances == []


def test_start_is_refused_before_google_and_while_google_says_signed_out(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    db_path = seeded_db[0]
    before = _scan_count(db_path)
    app, runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        sign_in_id = state["sign_in_id"]
        first = start_sign_in_scan(client, sign_in_id)
        assert first.status_code == 409
        assert first.json()["error"] == "Sign in to Google first."
        _open_google(client, sign_in_id)
        signed_out = start_sign_in_scan(client, sign_in_id)
        assert signed_out.status_code == 409
        assert signed_out.json()["error"] == NOT_SIGNED_IN
        # Both still waiting.
        kept = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
        assert kept["status"] == "awaiting_authentication"
        assert kept["google"]["status"] == "awaiting_authentication"
        assert not fake_sign_in.instances[0].closed
        assert fake_google.instances[0].closed == 0
        assert not fake_google.instances[0].scanning
    assert runs == []
    assert _scan_count(db_path) == before


def test_start_with_the_google_window_closed_asks_google_and_starts(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    """A closed Google window no longer refuses the start (2026-11-26): the
    session asks Google through a hidden browser on the same profile."""
    app, runs = _app(seeded_db, monkeypatch)
    fake_google.signed_in = True
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        _open_google(client, state["sign_in_id"])
        fake_google.instances[0].close_window()
        closed = client.get(f"/api/local-sign-ins/{state['sign_in_id']}").json()
        assert closed["google"] == {
            "status": "awaiting_authentication",
            "window_open": False,
            "error": None,
        }
        started = start_sign_in_scan(client, state["sign_in_id"])
    assert started.status_code == 201, started.text
    google = fake_google.instances[0]
    assert google.hidden_checks == 1
    assert google.reopens == 0
    assert google.scanning
    assert len(runs) == 1 and runs[0][1].google is google


def test_start_with_the_google_window_closed_and_signed_out_is_refused_and_kept(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    db_path = seeded_db[0]
    before = _scan_count(db_path)
    app, runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        sign_in_id = state["sign_in_id"]
        _open_google(client, sign_in_id)
        fake_google.instances[0].close_window()
        client.get(f"/api/local-sign-ins/{sign_in_id}")
        refused = start_sign_in_scan(client, sign_in_id)
        kept = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
        # Checked before leaving: quitting closes both.
        assert fake_google.instances[0].closed == 0
        assert not fake_sign_in.instances[0].closed
    assert refused.status_code == 409
    assert refused.json()["error"] == NOT_SIGNED_IN
    assert kept["status"] == "awaiting_authentication"
    assert kept["google"] == {
        "status": "awaiting_authentication",
        "window_open": False,
        "error": None,
    }
    google = fake_google.instances[0]
    assert google.hidden_checks == 1
    assert not google.scanning
    assert runs == []
    assert _scan_count(db_path) == before


def test_reopen_google_opens_it_again_on_the_same_clock(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    """As the site's own reopen (2026-11-26): one sign-in, one clock, which
    stops while either window is open and restarts from zero if a reopen
    fails. The site's window is left as it is."""
    app, runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        sign_in_id = state["sign_in_id"]
        _open_google(client, sign_in_id)
        reopen = f"/api/local-sign-ins/{sign_in_id}/google/reopen"

        open_now = client.post(reopen, headers=LOCAL_ORIGIN)
        assert open_now.status_code == 409
        assert open_now.json()["error"] == "The Google window is already open."

        registry = app.state.local_sign_ins
        now = [10_000.0]
        registry.clock = lambda: now[0]
        fake_sign_in.instances[0].close_window()
        fake_google.instances[0].close_window()
        client.get(f"/api/local-sign-ins/{sign_in_id}")
        now[0] += 100
        assert client.get(f"/api/local-sign-ins/{sign_in_id}").json()["forget_in_seconds"] == 1700

        fake_google.fail_reopen = True
        failed = client.post(reopen, headers=LOCAL_ORIGIN)
        assert failed.status_code == 503
        assert failed.json()["error"] == (
            "Axcess could not reopen the Google window. Your Google sign-in is still kept. "
            "Try again, or start the scan."
        )
        kept = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
        assert kept["status"] == "awaiting_authentication"
        assert kept["google"]["status"] == "awaiting_authentication"
        assert kept["google"]["window_open"] is False
        assert kept["forget_in_seconds"] == 1800, "restarted from zero"

        fake_google.fail_reopen = False
        reopened = client.post(reopen, headers=LOCAL_ORIGIN)
        assert reopened.status_code == 200, reopened.text
        body = reopened.json()
        assert body["google"]["window_open"] is True
        assert body["forget_in_seconds"] is None
        # The site's window was not touched.
        assert body["window_open"] is False
        assert not fake_sign_in.instances[0].window_open
        now[0] += 10_000
        still = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
        assert still["status"] == "awaiting_authentication"
        assert still["google"]["window_open"] is True
    assert fake_google.instances[0].reopens == 2
    assert len(fake_google.instances) == 1
    assert runs == []


def test_reopen_google_is_loopback_only_and_needs_a_google_window(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, _runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        sign_in_id = state["sign_in_id"]
        reopen = f"/api/local-sign-ins/{sign_in_id}/google/reopen"
        before_google = client.post(reopen, headers=LOCAL_ORIGIN)
        assert before_google.status_code == 409
        assert before_google.json()["error"] == "Sign in to Google first."
        _open_google(client, sign_in_id)
        fake_google.instances[0].close_window()
        client.get(f"/api/local-sign-ins/{sign_in_id}")
        no_origin = client.post(reopen)
        foreign = client.post(reopen, headers={"origin": "http://evil.example.test"})
        # Not entered: entering would run the app's shutdown, ending the sign-in.
        lan = TestClient(app, base_url="http://192.168.1.20:8765", client=("192.168.1.30", 1))
        remote = lan.post(reopen, headers={"origin": "http://192.168.1.20:8765"})
    assert no_origin.status_code == 403
    assert foreign.status_code == 403
    assert remote.status_code == 403
    assert fake_google.instances[0].reopens == 0


def test_start_with_both_hands_each_session_to_its_place(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    db_path = seeded_db[0]
    before = _scan_count(db_path)
    app, runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        _open_google(client, state["sign_in_id"])
        fake_google.signed_in = True
        started = start_sign_in_scan(client, state["sign_in_id"])
        after = client.get("/api/local-sign-ins/current").json()
    assert started.status_code == 201, started.text
    assert _scan_count(db_path) == before + 1
    assert after == {"sign_in": None}
    assert len(runs) == 1
    config, run = runs[0]
    # The site session as before; the Google session beside it, moved to its
    # headless scan browser, for the document check.
    assert run.session is fake_sign_in.instances[0]
    assert run.google is fake_google.instances[0]
    assert fake_google.instances[0].scanning
    assert config.google_sign_in is True
    assert config.documents_signed_in is True
    assert not fake_sign_in.instances[0].closed
    assert fake_google.instances[0].closed == 0


def test_a_failed_google_handover_keeps_the_site_sign_in(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    db_path = seeded_db[0]
    before = _scan_count(db_path)
    app, runs = _app(seeded_db, monkeypatch)
    fake_google.signed_in = True
    fake_google.fail_handover = True
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        sign_in_id = state["sign_in_id"]
        _open_google(client, sign_in_id)
        failed = start_sign_in_scan(client, sign_in_id)
        kept = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
        assert fake_google.instances[0].closed == 1
        assert not fake_sign_in.instances[0].closed
        # "next: sign in to Google" again opens a new Google window.
        fake_google.fail_handover = False
        retried = _open_google(client, sign_in_id)
    assert failed.status_code == 503
    assert "could not move your Google sign-in" in failed.json()["error"]
    assert kept["status"] == "awaiting_authentication"
    assert kept["google"]["status"] == "failed"
    assert "Your sign-in to the site is still kept" in kept["google"]["error"]
    assert retried["google"]["status"] == "awaiting_authentication"
    assert len(fake_google.instances) == 2
    assert runs == []
    assert _scan_count(db_path) == before


def test_a_google_window_that_cannot_open_keeps_the_site_sign_in(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, _runs = _app(seeded_db, monkeypatch)
    fake_google.fail_start = True
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        body = _open_google(client, state["sign_in_id"])
        assert not fake_sign_in.instances[0].closed
    assert body["status"] == "awaiting_authentication"
    assert body["google"]["status"] == "failed"
    assert "could not open the Google window" in body["google"]["error"]
    assert fake_google.instances[0].closed >= 1


def test_cancel_closes_both_sessions(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        _open_google(client, state["sign_in_id"])
        cancelled = client.post(
            f"/api/local-sign-ins/{state['sign_in_id']}/cancel", headers=LOCAL_ORIGIN
        )
    assert cancelled.json()["status"] == "cancelled"
    assert fake_sign_in.instances[0].closed
    assert fake_google.instances[0].closed == 1
    assert runs == []


def test_expiry_closes_both_sessions(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, _runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        sign_in_id = state["sign_in_id"]
        _open_google(client, sign_in_id)
        registry = app.state.local_sign_ins
        now = [10_000.0]
        registry.clock = lambda: now[0]
        fake_sign_in.instances[0].close_window()
        fake_google.instances[0].close_window()
        waiting = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
        assert waiting["forget_in_seconds"] == 1800
        now[0] += 1800
        ended = client.get(f"/api/local-sign-ins/{sign_in_id}").json()
    assert ended["status"] == "expired"
    assert fake_sign_in.instances[0].closed
    assert fake_google.instances[0].closed == 1


def test_quitting_closes_both_sessions(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, _runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client, google_sign_in=True)
        _open_google(client, state["sign_in_id"])
    # Leaving the ``with`` runs the app's shutdown hooks.
    assert fake_sign_in.instances[0].closed
    assert fake_google.instances[0].closed == 1


def test_without_the_switch_nothing_google_is_made(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    fake_sign_in: type,
    fake_google: type[FakeGoogleSession],
) -> None:
    app, runs = _app(seeded_db, monkeypatch)
    with local_client(app) as client:
        state = open_sign_in(client)
        assert state["google"] is None
        started = start_sign_in_scan(client, state["sign_in_id"])
    assert started.status_code == 201, started.text
    config, run = runs[0]
    assert run.google is None
    assert config.google_sign_in is False
    assert run.session is fake_sign_in.instances[0]
    assert fake_google.instances == []


async def test_the_scan_gives_the_google_session_to_run_crawl_and_closes_it(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_run_local_login_background`` passes the site's fetchers as before
    and the Google session as ``google_files`` only, and closes the Google
    session however the scan ends (here: the crawl fails)."""
    from audit.crawler.orchestrator import CrawlConfig
    from audit.db.schema import connect as db_connect
    from audit.web import server

    seen: dict[str, Any] = {}

    async def _fake_run_crawl(_conn: Any, _config: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        raise RuntimeError("the crawl failed")

    class _Site:
        window_open = True
        closed = False

        def enter_scan_mode(self) -> str:
            return "https://app.example.test/home"

        async def switch_to_headless(self, _workers: int) -> list[Any]:
            return []

        def create_shared_js_fetcher(self, **_kwargs: Any) -> Any:
            return type("F", (), {"tab_pool": None})()

        def create_authenticated_file_fetcher(self) -> str:
            return "site-file-fetcher"

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(server, "run_crawl", _fake_run_crawl)
    db_path, blob_dir, _ = seeded_db
    with db_connect(db_path) as conn:
        scan_id = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, config_json) VALUES "
                "('https://app.example.test/', 'running', '{}')"
            ).lastrowid
            or 0
        )
    config = CrawlConfig(
        seed_url="https://app.example.test/",
        scan_id=scan_id,
        documents_signed_in=True,
        google_sign_in=True,
        axe_enabled=False,
        alfa_enabled=False,
        keyboard_probe_enabled=False,
        responsive_checks_enabled=False,
        focus_checks_enabled=False,
        markup_checks_enabled=False,
        visual_checks_enabled=False,
        interaction_checks_enabled=False,
        form_error_checks_enabled=False,
        image_extraction_enabled=False,
        vlm_enabled=False,
    )
    site = _Site()
    google = FakeGoogleSession()
    run = server._LocalLoginRun(scan_id=scan_id, session=site, google=google)  # type: ignore[arg-type]
    await server._run_local_login_background(db_path, blob_dir, config, run)
    assert seen["google_files"] is google
    assert seen["file_fetcher"] == "site-file-fetcher"
    assert run.status == "failed"
    assert google.closed == 1
    assert site.closed
