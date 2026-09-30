"""``GET /api/scans/{id}/settings`` and the public create route's limits.

Starting again after a failed or stopped scan reads the old scan's settings
back from the server. These tests go through the real routes: what a scan
was created with is what comes back, each scan answers only for itself, a
protected report is refused, and nothing credential-shaped is in the body.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.db.schema import connect

pytestmark = pytest.mark.ui


@pytest.fixture
def no_crawl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create the scan row, but never start a crawl."""
    from audit.web import server

    async def _noop(db_path: Path, config: object) -> None:
        return None

    monkeypatch.setattr(server, "_run_background_crawl", _noop)


def _create(client: TestClient, **overrides: Any) -> int:
    body = {
        "url": "https://settings.example.test/section/",
        "max_pages": 300,
        "max_depth": 3,
        "rps": 1.5,
        "workers": 4,
        "whole_host": True,
        "skip_ocr": True,
        "skip_vlm": True,
        "skip_keyboard": True,
        "scan_engine": "axe",
        "axe_level": "AAA",
        "wcag_version": "2.2",
        **overrides,
    }
    response = client.post("/api/scans", json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["scan_id"])


def _stop(db_path: Path, scan_id: int, status: str) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE scans SET status = ? WHERE id = ?", (status, scan_id))


@pytest.mark.parametrize("status", ["failed", "interrupted"])
def test_a_failed_or_stopped_scan_returns_its_own_settings(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    no_crawl: None,
    status: str,
) -> None:
    scan_id = _create(client)
    _stop(seeded_db[0], scan_id, status)

    response = client.get(f"/api/scans/{scan_id}/settings")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["scan_id"] == scan_id
    assert body["mode"] == "public"
    settings = body["settings"]
    assert settings["url"] == "https://settings.example.test/section/"
    assert (settings["max_pages"], settings["max_depth"]) == (300, 3)
    assert (settings["rps"], settings["workers"]) == (1.5, 4)
    assert settings["whole_host"] is True
    assert settings["skip_keyboard"] is True
    assert (settings["axe_level"], settings["wcag_version"]) == ("AAA", "2.2")


def test_the_advanced_keyboard_check_is_stored_and_returned(
    client: TestClient, seeded_db: tuple[Path, Path, int], no_crawl: None
) -> None:
    scan_id = _create(client, skip_keyboard=False, keyboard_advanced=True)
    _stop(seeded_db[0], scan_id, "failed")
    with connect(seeded_db[0]) as conn:
        stored = json.loads(
            conn.execute("SELECT config_json FROM scans WHERE id = ?", (scan_id,)).fetchone()[0]
        )
    assert (stored["keyboard_probe_enabled"], stored["keyboard_advanced"]) == (True, True)
    settings = client.get(f"/api/scans/{scan_id}/settings").json()["settings"]
    assert (settings["skip_keyboard"], settings["keyboard_advanced"]) == (False, True)


def test_each_scan_answers_only_for_itself(
    client: TestClient, seeded_db: tuple[Path, Path, int], no_crawl: None
) -> None:
    first = _create(client, max_pages=11, url="https://a.example.test/")
    _stop(seeded_db[0], first, "failed")
    second = _create(client, max_pages=22, url="https://b.example.test/")
    _stop(seeded_db[0], second, "failed")

    a = client.get(f"/api/scans/{first}/settings").json()["settings"]
    b = client.get(f"/api/scans/{second}/settings").json()["settings"]
    assert (a["url"], a["max_pages"]) == ("https://a.example.test/", 11)
    assert (b["url"], b["max_pages"]) == ("https://b.example.test/", 22)


def test_no_session_or_credential_detail_is_returned(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, _ = seeded_db
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'failed', ?)",
            (
                "https://reviewer:hunter2@login.example.test/courses/",
                '{"browser_only": true, "resumable": false, "js_eager": true,'
                ' "start_url": "https://login.example.test/cb?code=sso-secret",'
                ' "user_agent": "AgentString/9", "cookies": "cookie-secret"}',
            ),
        )
        scan_id = int(cursor.lastrowid or 0)

    response = client.get(f"/api/scans/{scan_id}/settings")
    assert response.status_code == 200
    assert response.json()["mode"] == "login"
    assert response.json()["settings"]["url"] == "https://login.example.test/courses/"
    for needle in ("hunter2", "sso-secret", "AgentString", "cookie-secret", "start_url"):
        assert needle not in response.text


def test_unknown_scan_is_404(client: TestClient) -> None:
    assert client.get("/api/scans/999999/settings").status_code == 404


def test_protected_report_settings_are_refused(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    with connect(db_path) as conn:
        conn.execute("ALTER TABLE protected_scans RENAME TO saved_protected_scans")
        conn.execute("CREATE TABLE protected_scans(scan_id INTEGER, authorized_by TEXT)")
        conn.execute("INSERT INTO protected_scans VALUES(?, 'private-reviewer')", (scan_id,))
    response = client.get(f"/api/scans/{scan_id}/settings")
    # The protected-report middleware answers first (404 while protected
    # scans are not enabled on this server, 401/403 without an owner's
    # identity); the route's own 409 is behind it. Either way, no settings.
    assert response.status_code in {401, 403, 404, 409}
    assert "settings" not in response.json()
    assert "private-reviewer" not in response.text


def test_create_scans_every_page_when_asked(
    client: TestClient, seeded_db: tuple[Path, Path, int], no_crawl: None
) -> None:
    """With all_pages the crawl has no page limit, and the box's value is not checked."""
    import json

    scan_id = _create(client, all_pages=True, max_pages=0)
    with connect(seeded_db[0]) as conn:
        row = conn.execute("SELECT config_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
    assert json.loads(row[0])["max_pages"] is None
    _stop(seeded_db[0], scan_id, "failed")
    settings = client.get(f"/api/scans/{scan_id}/settings").json()["settings"]
    assert settings["all_pages"] is True


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"max_pages": 0}, "max_pages"),
        ({"max_pages": 10_001}, "max_pages"),
        ({"max_pages": 2.5}, "max_pages"),
        ({"max_depth": 0}, "max_depth"),
        ({"max_depth": 21}, "max_depth"),
    ],
)
def test_create_refuses_limits_out_of_range(
    client: TestClient, no_crawl: None, overrides: dict[str, Any], field: str
) -> None:
    response = client.post("/api/scans", json={"url": "https://limits.example.test/", **overrides})
    assert response.status_code == 422
    assert response.json()["fields"] == [field]
