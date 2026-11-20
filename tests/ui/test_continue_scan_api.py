"""Scan again makes a new report; Continue scan carries on an unfinished one.

Until 2026-11-20, starting a scan of an address with an unfinished report
quietly continued that report: "Scan again" from report #70 gave back
report #71, three days old. The developer's decision: a new scan always
makes a new report, and continuing is its own action (audit.web.continuing).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.db.schema import connect

SEED = "https://continue.example.test/"
DOC = "https://docs.google.com/document/d/1ZgSJQ3EuyzIiNEN2C2xdgm_eAQ2sVBkGIBLPiWEBMkE/edit"


@pytest.fixture
def no_crawl(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Never crawl; keep each config the server would have crawled with."""
    from audit.web import server

    started: list[Any] = []

    async def _record(db_path: Path, config: object) -> None:
        started.append(config)

    monkeypatch.setattr(server, "_run_background_crawl", _record)
    return started


def _interrupted(db_path: Path, *, waiting: bool, config: dict[str, Any] | None = None) -> int:
    """A report that ended ``interrupted``: cut off (pages waiting) or stopped."""
    stored = {"max_pages": 50, "max_depth": 4, "rps": 1.0, "workers": 2, **(config or {})}
    with connect(db_path) as conn:
        scan_id = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, page_count, config_json) "
                "VALUES (?, 'interrupted', 3, ?)",
                (SEED, json.dumps(stored)),
            ).lastrowid
            or 0
        )
        if waiting:
            conn.execute(
                "INSERT INTO jobs (kind, payload_json, state, dedupe_key) "
                "VALUES ('fetch', ?, 'pending', ?)",
                (json.dumps({"scan_id": scan_id, "url": f"{SEED}later"}), f"{scan_id}:later"),
            )
        conn.commit()
    return scan_id


def _new_scan(client: TestClient) -> int:
    response = client.post(
        "/api/scans",
        json={
            "url": SEED,
            "max_pages": 10,
            "max_depth": 2,
            "skip_vlm": True,
            "skip_semantic": True,
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["scan_id"])


def test_a_new_scan_never_takes_over_an_unfinished_report(
    client: TestClient, seeded_db: tuple[Path, Path, int], no_crawl: list[Any]
) -> None:
    unfinished = _interrupted(seeded_db[0], waiting=True)
    new_id = _new_scan(client)
    assert new_id != unfinished
    # Handed to the crawler by ID, so it never looks for a report to continue.
    assert no_crawl[-1].scan_id == new_id
    with connect(seeded_db[0]) as conn:
        status = conn.execute("SELECT status FROM scans WHERE id = ?", (unfinished,)).fetchone()
    assert status[0] == "interrupted"


def test_the_lists_say_which_reports_can_be_continued(
    client: TestClient, seeded_db: tuple[Path, Path, int], no_crawl: list[Any]
) -> None:
    stopped = _interrupted(seeded_db[0], waiting=False)
    unfinished = _interrupted(seeded_db[0], waiting=True)
    flags = {row["id"]: row["can_continue"] for row in client.get("/api/scans").json()}
    assert flags[unfinished] is True
    assert flags[stopped] is False
    assert client.get(f"/api/scans/{unfinished}").json()["can_continue"] is True
    assert client.get(f"/api/scans/{stopped}").json()["can_continue"] is False
    site = next(
        group
        for group in client.get("/api/sites").json()
        if "continue.example.test" in group["site_url"]
    )
    assert site["most_recent"]["id"] == unfinished
    assert site["most_recent"]["can_continue"] is True


def test_continue_scan_carries_on_the_same_report_with_its_own_settings(
    client: TestClient, seeded_db: tuple[Path, Path, int], no_crawl: list[Any]
) -> None:
    scan_id = _interrupted(
        seeded_db[0],
        waiting=True,
        config={"user_agent": "Agreed-Scanner/1.0", "user_agent_choice": "custom"},
    )
    with connect(seeded_db[0]) as conn:
        conn.execute(
            "INSERT INTO linked_files (scan_id, url, file_type, found_by, status, reason) "
            "VALUES (?, ?, 'google_doc', 'host', 'could_not_check', 'google_file')",
            (scan_id, DOC),
        )
        conn.commit()

    response = client.post(f"/api/scans/{scan_id}/continue")

    assert response.status_code == 202, response.text
    assert response.json() == {"scan_id": scan_id}
    config = no_crawl[-1]
    assert config.scan_id == scan_id
    assert (config.max_pages, config.max_depth, config.rps) == (50, 4, 1.0)
    assert config.user_agent == "Agreed-Scanner/1.0"
    with connect(seeded_db[0]) as conn:
        scan = conn.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone()
        doc = conn.execute(
            "SELECT status, reason FROM linked_files WHERE scan_id = ?", (scan_id,)
        ).fetchone()
    assert scan[0] == "running"
    assert tuple(doc) == ("pending", None)


def test_a_stopped_report_is_not_continued(
    client: TestClient, seeded_db: tuple[Path, Path, int], no_crawl: list[Any]
) -> None:
    scan_id = _interrupted(seeded_db[0], waiting=False)
    response = client.post(f"/api/scans/{scan_id}/continue")
    assert response.status_code == 409
    assert "Scan again" in response.json()["error"]
    assert no_crawl == []


def test_a_missing_report_is_not_found(
    client: TestClient, seeded_db: tuple[Path, Path, int], no_crawl: list[Any]
) -> None:
    assert client.post("/api/scans/999999/continue").status_code == 404
