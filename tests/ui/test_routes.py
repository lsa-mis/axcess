"""Integration tests for the API + SPA-shell routes.

Uses FastAPI's TestClient so no browser is needed. The legacy Jinja/HTMX
server-rendered pages were removed — the UI is now the React SPA under
``/app/`` plus this ``/api/*`` surface, blob serving, exports, favicon,
and the optional shared-token gate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.ui


# ----------------------------------------------------------- shell + health


def test_root_redirects_to_spa(client: TestClient) -> None:
    # The SPA is the only UI now; / always redirects to /app/ (which itself
    # serves a 503 "build the frontend" notice if the bundle isn't built).
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (301, 307)
    assert resp.headers["location"] == "/app/"


def test_app_shell_redirect_when_bundle_missing(client: TestClient) -> None:
    """Without a built bundle, /app/ returns a helpful 503; with it, 200."""
    resp = client.get("/app/", follow_redirects=False)
    assert resp.status_code in (200, 503)


def test_health_returns_version(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_favicon_svg_served(client: TestClient) -> None:
    """The brand favicon must serve from /favicon.svg with the SVG mime."""
    resp = client.get("/favicon.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    # The actual mark is a UMich-blue rounded rect with a maize T — assert
    # the maize hex is present so a swap to a placeholder (or an empty
    # file) is caught loudly rather than rendering a blank tab icon.
    assert b"#FFCB05" in resp.content


def test_favicon_ico_aliased_to_svg(client: TestClient) -> None:
    """Browsers and devtools poke /favicon.ico from the root. We serve the
    same SVG payload there so every surface gets a tab icon."""
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert b"#FFCB05" in resp.content


# ------------------------------------------------------------------ /api/scans


def test_api_list_scans(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get("/api/scans")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and len(body) >= 1
    one = next(s for s in body if s["id"] == scan_id)
    assert one["status"] == "completed"
    assert set(one.keys()) >= {
        "id",
        "seed_url",
        "status",
        "page_count",
        "finding_count",
        "started_at",
    }


def test_api_scan_detail(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == scan_id
    assert "by_severity" in body
    assert set(body["by_severity"].keys()) == {
        "critical",
        "major",
        "minor",
        "info",
    }
    assert body["previous_scan_id"] is None  # only one scan seeded
    assert body["blocked"] is None
    assert body["progress"] is None  # not running


def test_api_scan_detail_404(client: TestClient) -> None:
    resp = client.get("/api/scans/99999")
    assert resp.status_code == 404


def test_api_scan_detail_flags_blocked_seed(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    """When the seed page returned 4xx, the detail payload surfaces a
    ``blocked`` block so the SPA can warn the user instead of silently
    showing 0 findings."""
    import sqlite3 as _sqlite3

    db_path, _, _ = seeded_db
    conn = _sqlite3.connect(str(db_path))
    conn.row_factory = _sqlite3.Row
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
            "VALUES ('https://blocked.example/', 'completed', 1, 0, '{}')"
        )
        blocked_scan_id = int(cur.lastrowid or 0)
        conn.execute(
            "INSERT INTO pages (scan_id, url_normalized, status_code, title, "
            "render_mode, html_hash) VALUES (?, ?, 403, 'Just a moment...', "
            "'static', ?)",
            (blocked_scan_id, "https://blocked.example/", "0" * 64),
        )
        conn.commit()
    finally:
        conn.close()

    body = client.get(f"/api/scans/{blocked_scan_id}").json()
    assert body["blocked"] is not None
    assert body["blocked"]["status_code"] == 403


def test_api_list_findings(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/findings?page_size=10")
    assert resp.status_code == 200
    body = resp.json()
    assert "findings" in body
    assert body["total"] >= 1
    # Thumbnails: every listed finding carries its content_hash when blob-backed.
    hashes = {f["content_hash"] for f in body["findings"] if f["content_hash"]}
    assert len(hashes) >= 1


def test_api_finding_detail(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    resp = client.get("/api/findings/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert "occurrences" in body
    assert isinstance(body["occurrences"], list)


def test_api_finding_status_round_trip(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    resp = client.post("/api/findings/1/status", json={"status": "reviewing"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "reviewing"
    detail = client.get("/api/findings/1").json()
    assert detail["status"] == "reviewing"


def test_api_finding_status_rejects_unknown(client: TestClient) -> None:
    resp = client.post("/api/findings/1/status", json={"status": "nope"})
    assert resp.status_code == 400


def test_api_scope_preview_auto_slash(client: TestClient) -> None:
    resp = client.get("/api/scope-preview?url=https://example.com/bicentennial")
    assert resp.status_code == 200
    body = resp.json()
    assert body["path_prefix"] == "/bicentennial/"
    assert body["auto_slash_added"] is True
    assert body["normalized_url"] == "https://example.com/bicentennial/"


def test_api_scope_preview_whole_host(client: TestClient) -> None:
    body = client.get("/api/scope-preview?url=https://example.com/a&whole_host=1").json()
    assert body["whole_host"] is True
    assert body["path_prefix"] == "/"


def test_api_scope_preview_invalid(client: TestClient) -> None:
    body = client.get("/api/scope-preview?url=ftp://example.com/").json()
    assert body["error"] is not None


def test_api_create_scan_rejects_bad_url(client: TestClient) -> None:
    resp = client.post("/api/scans", json={"url": "ftp://nope/"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_api_create_scan_kicks_off_crawl(
    client: TestClient,
    seeded_db: tuple[object, object, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from audit.web import server as _server

    called: dict[str, object] = {}

    async def _noop(db_path, config):  # type: ignore[no-untyped-def]
        called["ran"] = True
        called["seed"] = config.seed_url

    monkeypatch.setattr(_server, "_run_background_crawl", _noop)
    resp = client.post(
        "/api/scans",
        json={
            "url": "https://example.test/",
            "max_pages": 5,
            "max_depth": 2,
            "rps": 1.0,
            "workers": 1,
            "skip_ocr": True,
            "skip_vlm": True,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert isinstance(body["scan_id"], int)
    import asyncio as _asyncio

    loop = _asyncio.new_event_loop()
    try:
        loop.run_until_complete(_asyncio.sleep(0.05))
    finally:
        loop.close()
    assert called.get("ran") is True


def test_api_create_scan_respects_whole_host(
    client: TestClient,
    seeded_db: tuple[object, object, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Posting whole_host=true must reach the built CrawlConfig."""
    from audit.web import server as _server

    captured: dict[str, object] = {}

    async def _capture(db_path, config):  # type: ignore[no-untyped-def]
        captured["whole_host"] = config.whole_host
        captured["seed_url"] = config.seed_url

    monkeypatch.setattr(_server, "_run_background_crawl", _capture)
    resp = client.post(
        "/api/scans",
        json={
            "url": "https://example.test/docs",
            "max_pages": 1,
            "max_depth": 1,
            "rps": 1.0,
            "workers": 1,
            "whole_host": True,
            "skip_ocr": True,
            "skip_vlm": True,
        },
    )
    assert resp.status_code == 201
    import asyncio as _asyncio

    loop = _asyncio.new_event_loop()
    try:
        loop.run_until_complete(_asyncio.sleep(0.05))
    finally:
        loop.close()
    assert captured.get("whole_host") is True
    assert captured.get("seed_url") == "https://example.test/docs"


def test_api_cancel_endpoint(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    import sqlite3 as _sqlite3

    db_path, _, _ = seeded_db
    conn = _sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, "
            "config_json) VALUES ('http://x/', 'running', 0, 0, '{}')"
        )
        running_id = int(cur.lastrowid or 0)
        conn.commit()
    finally:
        conn.close()

    resp = client.post(f"/api/scans/{running_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # Scan should be interrupted in the DB.
    detail = client.get(f"/api/scans/{running_id}").json()
    assert detail["status"] == "interrupted"


def test_api_running_scan_includes_in_flight_and_recent(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    """Running scans must serialize cleanly: pages.fetched_at is a real
    datetime and jobs.lease_until likewise. Both must round-trip through
    JSONResponse without TypeErrors. Also confirm the new in_flight_pages
    field is populated from leased jobs scoped to this scan.
    """
    import json as _json
    import sqlite3 as _sqlite3

    db_path, _, _ = seeded_db
    conn = _sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, "
            "config_json) VALUES ('http://x/', 'running', 1, 0, '{}')"
        )
        running_id = int(cur.lastrowid or 0)
        # A finished page (so recent_pages.fetched_at is a real datetime).
        conn.execute(
            "INSERT INTO pages (scan_id, url_normalized, status_code, "
            "render_mode, fetched_at) VALUES (?, ?, 200, 'static', "
            "CURRENT_TIMESTAMP)",
            (running_id, "http://x/finished"),
        )
        # A leased job (so in_flight_pages picks it up). Write lease_until in
        # the same ISO-8601 format the real queue uses — *not* SQLite's
        # CURRENT_TIMESTAMP which the default converter chokes on.
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state, lease_until) "
            "VALUES ('crawl', ?, 'leased', ?)",
            (
                _json.dumps({"url": "http://x/in-flight", "depth": 2, "scan_id": running_id}),
                "2026-04-27T16:48:53+00:00",
            ),
        )
        # And a pending one to verify the count.
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state) VALUES ('crawl', ?, 'pending')",
            (_json.dumps({"url": "http://x/queued", "depth": 1, "scan_id": running_id}),),
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.get(f"/api/scans/{running_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "running"
    progress = body["progress"]
    assert progress is not None
    assert progress["recent_pages"][0]["url_normalized"] == "http://x/finished"
    assert isinstance(progress["recent_pages"][0]["fetched_at"], str)
    in_flight = progress["in_flight_pages"]
    assert len(in_flight) == 1
    assert in_flight[0]["url"] == "http://x/in-flight"
    assert in_flight[0]["depth"] == 2
    assert in_flight[0]["attempts"] == 0
    assert progress["pending"] == 1
    assert progress["leased"] == 1


def test_api_diff_404s_on_missing_compare_target(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/diff?compare_to=99999")
    assert resp.status_code == 404


# ------------------------------------------------------------ delete cascade


def test_api_delete_scan_removes_scan_and_cascades(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    """DELETE /api/scans/{id} removes the scan plus everything keyed on it.

    The fixture seeds a scan with pages, page_images, analyses, findings,
    and finding_history. After delete: the scan row is gone, the cascading
    children are gone, but the deduped images survive.
    """
    import sqlite3 as _sqlite3

    db_path, _, scan_id = seeded_db

    pre = _sqlite3.connect(str(db_path))
    pre.row_factory = _sqlite3.Row
    try:
        page_n = pre.execute(
            "SELECT COUNT(*) AS n FROM pages WHERE scan_id = ?", (scan_id,)
        ).fetchone()["n"]
        finding_n = pre.execute(
            "SELECT COUNT(*) AS n FROM findings WHERE scan_id = ?", (scan_id,)
        ).fetchone()["n"]
        image_n_before = pre.execute("SELECT COUNT(*) AS n FROM images").fetchone()["n"]
    finally:
        pre.close()
    assert page_n > 0, "fixture should seed at least one page"
    assert finding_n > 0, "fixture should seed at least one finding"

    resp = client.delete(f"/api/scans/{scan_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"ok": True, "deleted_scan_id": scan_id}

    post = _sqlite3.connect(str(db_path))
    post.row_factory = _sqlite3.Row
    try:
        scan_row = post.execute("SELECT id FROM scans WHERE id = ?", (scan_id,)).fetchone()
        page_n_after = post.execute(
            "SELECT COUNT(*) AS n FROM pages WHERE scan_id = ?", (scan_id,)
        ).fetchone()["n"]
        finding_n_after = post.execute(
            "SELECT COUNT(*) AS n FROM findings WHERE scan_id = ?", (scan_id,)
        ).fetchone()["n"]
        history_n_after = post.execute(
            "SELECT COUNT(*) AS n FROM finding_history WHERE scan_id = ?",
            (scan_id,),
        ).fetchone()["n"]
        image_n_after = post.execute("SELECT COUNT(*) AS n FROM images").fetchone()["n"]
        dangling = post.execute(
            "SELECT COUNT(*) AS n FROM images WHERE first_seen_scan_id = ?",
            (scan_id,),
        ).fetchone()["n"]
    finally:
        post.close()

    assert scan_row is None
    assert page_n_after == 0
    assert finding_n_after == 0
    assert history_n_after == 0
    assert image_n_after == image_n_before
    assert dangling == 0


def test_api_delete_scan_404s_for_unknown_id(client: TestClient) -> None:
    resp = client.delete("/api/scans/9999999")
    assert resp.status_code == 404


def test_api_delete_scan_clears_jobs_for_that_scan(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    """Jobs aren't FK-bound (scan_id lives in payload_json), so the delete
    handler must explicitly remove them."""
    import sqlite3 as _sqlite3

    db_path, _, scan_id = seeded_db
    conn = _sqlite3.connect(str(db_path))
    conn.row_factory = _sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state) VALUES ('fetch', ?, 'pending')",
            (f'{{"url":"http://x/a","scan_id":{scan_id},"depth":0}}',),
        )
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state) VALUES ('fetch', ?, 'failed')",
            (f'{{"url":"http://x/b","scan_id":{scan_id},"depth":0}}',),
        )
        conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, "
            "config_json) VALUES ('http://other.example/', 'completed', 0, 0, '{}')"
        )
        other_scan = int(conn.execute("SELECT last_insert_rowid() AS i").fetchone()["i"])
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state) VALUES ('fetch', ?, 'pending')",
            (f'{{"url":"http://x/c","scan_id":{other_scan},"depth":0}}',),
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.delete(f"/api/scans/{scan_id}")
    assert resp.status_code == 200

    check = _sqlite3.connect(str(db_path))
    check.row_factory = _sqlite3.Row
    try:
        for_deleted = check.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE json_extract(payload_json, '$.scan_id') = ?",
            (scan_id,),
        ).fetchone()["n"]
        for_other = check.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE json_extract(payload_json, '$.scan_id') = ?",
            (other_scan,),
        ).fetchone()["n"]
    finally:
        check.close()

    assert for_deleted == 0, "jobs for the deleted scan should be removed"
    assert for_other == 1, "jobs for sibling scans must not be touched"


def test_api_delete_scan_409s_when_scan_is_running(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    """A scan with an active asyncio task must not be deleted out from
    under the worker. The handler returns 409 and the scan stays put."""
    import asyncio
    import sqlite3 as _sqlite3

    db_path, _, _ = seeded_db
    conn = _sqlite3.connect(str(db_path))
    conn.row_factory = _sqlite3.Row
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, "
            "config_json) VALUES ('http://live.example/', 'running', 0, 0, '{}')"
        )
        running_id = int(cur.lastrowid or 0)
        conn.commit()
    finally:
        conn.close()

    # Find the handler's captured crawl_state dict by inspecting the
    # endpoint's closure cells (matched by structure so a rename is safe).
    app = client.app  # type: ignore[attr-defined]
    target: dict[str, object] | None = None
    for route in app.routes:  # type: ignore[attr-defined]
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or endpoint.__name__ != "api_delete_scan":
            continue
        for cell in endpoint.__closure__ or ():
            val = cell.cell_contents
            if isinstance(val, dict) and "task" in val and "scan_id" in val:
                target = val
                break
        if target is not None:
            break
    assert target is not None, "could not locate crawl_state via closure"

    async def _never() -> None:
        await asyncio.sleep(60)

    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(_never())
        target["task"] = task
        target["scan_id"] = running_id
        try:
            resp = client.delete(f"/api/scans/{running_id}")
        finally:
            task.cancel()
            loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
            target["task"] = None
            target["scan_id"] = None
    finally:
        loop.close()

    assert resp.status_code == 409
    detail = resp.json().get("detail", "")
    assert "running" in detail.lower()

    check = _sqlite3.connect(str(db_path))
    try:
        row = check.execute("SELECT status FROM scans WHERE id = ?", (running_id,)).fetchone()
    finally:
        check.close()
    assert row is not None
    assert row[0] == "running"


def test_stale_running_scans_interrupted_on_server_boot(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """When the app boots it marks every DB row stuck in 'running' as
    'interrupted', because the live task driving it is gone after a
    process restart."""
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    from audit.db.schema import connect as _connect

    db_path = tmp_path / "sweep.db"
    migrations_dir = _Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"
    prep = _connect(db_path)
    try:
        for p in sorted(migrations_dir.glob("*.sql")):
            if p.name.endswith(".rollback.sql"):
                continue
            prep.executescript(p.read_text())
        prep.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('http://stuck.example/', 'running', '{}')"
        )
        prep.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('http://done.example/', 'completed', '{}')"
        )
    finally:
        prep.close()

    from audit.web.server import create_app

    create_app(db_path=db_path, blob_dir=tmp_path / "blobs")

    check = _sqlite3.connect(str(db_path))
    check.row_factory = _sqlite3.Row
    try:
        rows = check.execute("SELECT seed_url, status FROM scans ORDER BY id").fetchall()
    finally:
        check.close()
    states = {r["seed_url"]: r["status"] for r in rows}
    assert states["http://stuck.example/"] == "interrupted"
    assert states["http://done.example/"] == "completed"


# --------------------------------------------------------------------- /api/tracking


def test_api_tracking_returns_shipped_and_roadmap(client: TestClient) -> None:
    """The coverage tracker endpoint reports what's shipped vs. planned,
    sourced from coverage_status.py."""
    resp = client.get("/api/tracking")
    assert resp.status_code == 200
    body = resp.json()
    # Shipped pipelines include the axe rule engine and the VLM image one.
    pipelines = {p["pipeline"] for p in body["shipped"]}
    assert {"axe", "image", "semantic", "keyboard", "responsive"} <= pipelines
    # Roadmap carries WCAG-keyed rows with the three-way status.
    by_wcag = {r["wcag"]: r for r in body["roadmap"]}
    assert by_wcag["1.4.5"]["status"] == "shipped"
    assert by_wcag["2.4.4"]["status"] == "shipped"
    # The two rows the original triage mislabelled "in progress" have no
    # code and must read "planned".
    assert by_wcag["1.3.2"]["status"] == "planned"
    assert by_wcag["3.2.3"]["status"] == "planned"
    assert body["counts"]["shipped"] >= 2


# --------------------------------------------------------------- blob serving


def test_blob_serves_png_bytes(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    # Pull a blob-backed finding's content_hash from the API, then fetch it.
    _, _, scan_id = seeded_db
    findings = client.get(f"/api/scans/{scan_id}/findings?page_size=10").json()["findings"]
    content_hash = next(f["content_hash"] for f in findings if f["content_hash"])
    resp = client.get(f"/blobs/{content_hash}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_blob_rejects_invalid_hash(client: TestClient) -> None:
    resp = client.get("/blobs/not_a_hash")
    assert resp.status_code == 400


def test_blob_returns_404_for_unknown_hash(client: TestClient) -> None:
    resp = client.get("/blobs/" + "f" * 64)
    assert resp.status_code == 404


# ------------------------------------------------------------------- exports
# Exports are served only under /api/* now (the React SPA downloads via a
# plain <a download> to that URL). The legacy /scans/{id}/export alias is
# gone with the rest of the Jinja routes.


def test_export_csv_route(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/export/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert f"scan_{scan_id}.csv" in resp.headers["content-disposition"]
    assert "finding_id,severity" in resp.text


def test_export_json_route(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/export/json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    body = resp.json()
    assert body["scan"]["id"] == scan_id
    assert isinstance(body["findings"], list)


def test_export_jira_route(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/export/jira")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "Summary,Description,Priority" in resp.text


def test_export_markdown_route(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/export/markdown")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert resp.text.startswith(f"# Accessibility audit — Scan #{scan_id}")


def test_export_unknown_format_rejected(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/export/xml")
    assert resp.status_code == 400


def test_export_unknown_scan_returns_404(client: TestClient) -> None:
    resp = client.get("/api/scans/99999/export/csv")
    assert resp.status_code == 404


def test_legacy_jinja_export_alias_is_gone(client: TestClient) -> None:
    """The old /scans/{id}/export/{fmt} Jinja alias was removed; only the
    /api/* route remains. The bare path now falls through to the SPA
    catch-all-less router and 404s."""
    _ = client
    resp = client.get("/scans/1/export/csv")
    assert resp.status_code == 404


# --------------------------------------------------------------------
# Hosting: the optional shared-token gate (docs/hosting.md, Path A).
# Routes are checked against /api/scans (a real gated route) now that the
# Jinja /scans page is gone; /health stays open.
# --------------------------------------------------------------------


def test_access_token_unset_is_no_op(
    seeded_db: tuple[object, object, int],
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """With no AUDIT_ACCESS_TOKEN, every route is open (the local default)."""
    from pathlib import Path

    from audit.web.server import create_app

    monkeypatch.delenv("AUDIT_ACCESS_TOKEN", raising=False)
    db_path, blob_dir, _ = seeded_db
    app = create_app(db_path=Path(db_path), blob_dir=Path(blob_dir))
    c = TestClient(app)
    assert c.get("/api/scans").status_code == 200
    assert c.get("/health").status_code == 200


def test_access_token_gate_blocks_and_admits(
    seeded_db: tuple[object, object, int],
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """When the token is set: 401 without it, 200 with it, /health always open."""
    from pathlib import Path

    from audit.web.server import create_app

    monkeypatch.setenv("AUDIT_ACCESS_TOKEN", "s3cret-token")
    db_path, blob_dir, _ = seeded_db
    app = create_app(db_path=Path(db_path), blob_dir=Path(blob_dir))
    c = TestClient(app)

    # No token → 401.
    assert c.get("/api/scans").status_code == 401

    # Health stays open (uptime checks don't carry the token).
    assert c.get("/health").status_code == 200

    # Query-string token → 200, and a cookie is set for next time.
    ok = c.get("/api/scans?token=s3cret-token")
    assert ok.status_code == 200
    assert "aa_access" in ok.cookies

    # Header forms also work (API/CLI clients).
    fresh = TestClient(app)
    assert fresh.get("/api/scans", headers={"X-Access-Token": "s3cret-token"}).status_code == 200
    fresh2 = TestClient(app)
    assert (
        fresh2.get("/api/scans", headers={"Authorization": "Bearer s3cret-token"}).status_code
        == 200
    )

    # Wrong token → 401.
    bad = TestClient(app)
    assert bad.get("/api/scans?token=nope").status_code == 401
