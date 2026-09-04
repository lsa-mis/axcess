"""Search setup is validated before scan creation and retained with its report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit.crawler.orchestrator import CrawlConfig
from audit.crawler.search import SearchOutcome
from audit.db import repo
from audit.db.schema import connect
from audit.web import server

pytestmark = pytest.mark.ui
SEARCH = {
    "confirmed": True,
    "fields": [{"target": "Search", "value": "Tutorial"}],
    "results_selector": "[role=option]",
}


@pytest.mark.parametrize("login", [False, True])
def test_search_configuration_reaches_both_scan_modes(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
    login: bool,
) -> None:
    db_path, blob_dir, _ = seeded_db
    captured: list[CrawlConfig] = []

    async def capture(_db, config):  # type: ignore[no-untyped-def]
        captured.append(config)

    async def capture_login(_db, _blobs, config, _run):  # type: ignore[no-untyped-def]
        captured.append(config)

    monkeypatch.setattr(server, "_run_background_crawl", capture)
    monkeypatch.setattr(server, "_run_local_login_background", capture_login)
    monkeypatch.setattr(server, "ManualAuthenticationSession", lambda **kwargs: object())
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 45000)) as client:
        body = {
            "search": SEARCH,
            "seed_url" if login else "url": "https://example.test/",
            "authorization_acknowledged": True,
        }
        response = client.post(
            "/api/local-login-scans" if login else "/api/scans",
            json=body,
            headers={"origin": "http://127.0.0.1:8765"},
        )
    assert response.status_code == 201, response.text
    assert len(captured) == 1
    assert captured[0].search is not None
    assert captured[0].search.fields[0].value == "Tutorial"
    with connect(db_path) as conn:
        cfg = json.loads(
            conn.execute(
                "SELECT config_json FROM scans WHERE id=?", (response.json()["scan_id"],)
            ).fetchone()[0]
        )
    assert cfg["search"]["fields"][0]["value"] == "Tutorial"


@pytest.mark.parametrize("login", [False, True])
@pytest.mark.parametrize(
    "patch",
    [
        {"confirmed": False},
        {"page_url": "https://outside.test/"},
        {"max_results": 51},
        {"fields": []},
    ],
)
def test_invalid_search_never_creates_a_scan(
    seeded_db: tuple[Path, Path, int],
    login: bool,
    patch: dict[str, object],
) -> None:
    db_path, blob_dir, _ = seeded_db
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 45000)) as client:
        response = client.post(
            "/api/local-login-scans" if login else "/api/scans",
            json={
                "seed_url" if login else "url": "https://example.test/",
                "authorization_acknowledged": True,
                "search": {**SEARCH, **patch},
            },
            headers={"origin": "http://127.0.0.1:8765"},
        )
    assert response.status_code == 422
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0] == before


def test_report_search_coverage_uses_only_its_own_evidence(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
) -> None:
    db_path, _, scan_id = seeded_db
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE scans SET config_json=? WHERE id=?", (json.dumps({"search": SEARCH}), scan_id)
        )
        page_id = conn.execute(
            "SELECT id FROM pages WHERE scan_id=? LIMIT 1", (scan_id,)
        ).fetchone()[0]
        repo.record_search_run(
            conn,
            scan_id=scan_id,
            page_id=page_id,
            outcome=SearchOutcome(status="limited", states=2, discovered=4),
        )
    response = client.get(f"/api/scans/{scan_id}")
    method = next(m for m in response.json()["methods_used"] if m["key"] == "search")
    assert method["state"] == "partial"
    assert method["checked_count"] == 2
    assert "stopped early" in method["result"]


@pytest.mark.parametrize("login", [False, True])
@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        # The reported mistake: a search term typed into the URL box.
        ({"page_url": "lsa"}, "Search page URL"),
        ({"page_url": "https://outside.test/"}, "Search page URL"),
        ({"max_results": 51}, "Maximum results"),
        ({"confirmed": False}, "Search authorization checkbox"),
        ({"fields": [{"target": "Search", "value": "x" * 300}]}, "Search field value #1"),
    ],
)
def test_refusal_names_the_setting_without_echoing_the_request(
    seeded_db: tuple[Path, Path, int],
    login: bool,
    patch: dict[str, object],
    expected: str,
) -> None:
    """A 422 an auditor can act on: which box, not a slice of their payload."""

    db_path, blob_dir, _ = seeded_db
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    submitted = {**SEARCH, "fields": [{"target": "Search", "value": "do-not-echo"}], **patch}
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 45000)) as client:
        response = client.post(
            "/api/local-login-scans" if login else "/api/scans",
            json={
                "seed_url" if login else "url": "https://example.test/",
                "authorization_acknowledged": True,
                "search": submitted,
            },
            headers={"origin": "http://127.0.0.1:8765"},
        )
    assert response.status_code == 422
    body = response.json()
    message = body.get("error") or body.get("detail")
    assert isinstance(message, str)
    assert expected in message
    # The whole message must survive the client's own truncation, and none
    # of it may be the request that was rejected.
    assert len(message) <= 400
    assert "do-not-echo" not in response.text


def test_engine_and_render_refusals_are_distinguishable(
    seeded_db: tuple[Path, Path, int],
) -> None:
    db_path, blob_dir, _ = seeded_db
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 45000)) as client:
        static = client.post(
            "/api/scans",
            json={"url": "https://example.test/", "static_only": True, "search": SEARCH},
            headers={"origin": "http://127.0.0.1:8765"},
        )
        alfa = client.post(
            "/api/scans",
            json={"url": "https://example.test/", "scan_engine": "alfa", "search": SEARCH},
            headers={"origin": "http://127.0.0.1:8765"},
        )
    assert static.status_code == alfa.status_code == 422
    assert "static-only" in static.json()["error"]
    assert "axe-core" in alfa.json()["error"]
    assert static.json()["error"] != alfa.json()["error"]


def test_an_unknown_setting_names_itself_and_points_at_the_server(
    seeded_db: tuple[Path, Path, int],
) -> None:
    """The reported failure: a browser newer than the running server.

    ``model_config = extra="forbid"`` reports this as "Extra inputs are not
    permitted" against a location the default 422 buries under the rejected
    input. The refusal has to say which setting and what to do about it.
    """

    db_path, blob_dir, _ = seeded_db
    app = server.create_app(db_path=db_path, blob_dir=blob_dir)
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 45000)) as client:
        response = client.post(
            "/api/scans",
            json={"url": "https://example.test/", "search": {**SEARCH, "future_option": True}},
            headers={"origin": "http://127.0.0.1:8765"},
        )
    assert response.status_code == 422
    assert "search.future_option" in response.json()["error"]
    assert "restart" in response.json()["error"]
