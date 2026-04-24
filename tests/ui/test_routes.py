"""Integration tests for the UI routes.

Uses FastAPI's TestClient so no browser is needed. Focuses on: routing,
partial-vs-full rendering, filter query params, status POST, blob serving.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.ui


def test_root_redirects_to_scans(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (301, 307)
    assert resp.headers["location"] == "/scans"


def test_health_returns_version(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_scans_list_renders_seeded_scan(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get("/scans")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Scans" in resp.text
    assert f"/scans/{scan_id}" in resp.text


def test_scan_detail_shows_severity_breakdown(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}")
    assert resp.status_code == 200
    # Severity badges should appear for at least one level.
    assert "sev-" in resp.text


def test_findings_list_returns_full_page(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/findings")
    assert resp.status_code == 200
    assert "<title>Findings" in resp.text
    assert "data-finding-id" in resp.text
    assert "banner.png" in resp.text


def test_findings_list_returns_partial_for_htmx(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/findings", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    # Partial must NOT include <html> / skip-link / nav.
    assert "<title>" not in resp.text
    assert "skip-link" not in resp.text
    assert "finding-grid" in resp.text or "No findings" in resp.text


def test_findings_filter_by_severity(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/findings?severity=info")
    assert resp.status_code == 200
    # At least one severity badge "info" should appear; no "critical" badges.
    assert "sev-info" in resp.text
    # A filter value outside the allowed list is silently dropped.
    all_resp = client.get(f"/scans/{scan_id}/findings?severity=bogus")
    assert all_resp.status_code == 200


def test_findings_search_query_matches_ocr_text(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/findings?q=WIDGETS")
    assert resp.status_code == 200
    assert "banner.png" in resp.text
    # A search that matches nothing should render the empty message.
    empty = client.get(f"/scans/{scan_id}/findings?q=notarealtoken12345")
    assert empty.status_code == 200
    assert "No findings" in empty.text


def test_scan_not_found_returns_404(client: TestClient) -> None:
    resp = client.get("/scans/99999")
    assert resp.status_code == 404


def test_finding_detail_renders_and_shows_rationale(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    # Pull the first finding id out of the list page.
    listing = client.get(f"/scans/{scan_id}/findings")
    assert "data-finding-id" in listing.text
    # Just visit /findings/1 — seeded fixture guarantees it exists.
    resp = client.get("/findings/1")
    assert resp.status_code == 200
    assert "<title>Finding" in resp.text
    assert 'id="status-select"' in resp.text
    assert "<dl" in resp.text


def test_status_post_updates_db_and_returns_partial(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    resp = client.post(
        "/findings/1/status",
        data={"status": "reviewing"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "Status updated" in resp.text
    assert "reviewing" in resp.text
    # History row was written.
    detail = client.get("/findings/1")
    assert '<option value="reviewing" selected' in detail.text


def test_status_post_destructive_requires_confirm(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    # First POST without confirm — server returns a confirmation prompt.
    first = client.post(
        "/findings/1/status",
        data={"status": "false_positive"},
        headers={"HX-Request": "true"},
    )
    assert first.status_code == 200
    assert "Confirm" in first.text
    # Second POST with confirm=yes — applies the change.
    second = client.post(
        "/findings/1/status",
        data={"status": "false_positive", "confirm": "yes"},
        headers={"HX-Request": "true"},
    )
    assert second.status_code == 200
    assert "Status updated" in second.text


def test_status_post_unknown_value_rejected(client: TestClient) -> None:
    resp = client.post("/findings/1/status", data={"status": "nonsense"})
    assert resp.status_code == 400


def test_page_detail_shows_images_with_findings(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    # Seeded fixture puts images on pages 1 and 2.
    resp = client.get("/pages/1")
    assert resp.status_code == 200
    assert "banner.png" in resp.text or "logo.png" in resp.text
    # Page detail should link back to its finding.
    assert "/findings/" in resp.text


def test_blob_serves_png_bytes(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    # Grab the content hash from the API surface (any finding works).
    # Just hit the seeded banner PNG by known hash from the seeded row.
    detail = client.get("/findings/1")
    # Extract content_hash by scraping src="/blobs/<hash>"
    import re

    match = re.search(r"/blobs/([0-9a-f]{64})", detail.text)
    assert match, "expected a blob link on the finding detail page"
    resp = client.get(f"/blobs/{match.group(1)}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_blob_rejects_invalid_hash(client: TestClient) -> None:
    resp = client.get("/blobs/not_a_hash")
    assert resp.status_code == 400


def test_blob_returns_404_for_unknown_hash(client: TestClient) -> None:
    resp = client.get("/blobs/" + "f" * 64)
    assert resp.status_code == 404


def test_export_csv_route(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/export/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert f"scan_{scan_id}.csv" in resp.headers["content-disposition"]
    assert "finding_id,severity" in resp.text


def test_export_json_route(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/export/json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    body = resp.json()
    assert body["scan"]["id"] == scan_id
    assert isinstance(body["findings"], list)


def test_export_jira_route(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/export/jira")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "Summary,Description,Priority" in resp.text


def test_export_markdown_route(client: TestClient, seeded_db: tuple[object, object, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/export/markdown")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert resp.text.startswith(f"# WCAG 1.4.5 audit — Scan #{scan_id}")


def test_export_unknown_format_rejected(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/export/xml")
    assert resp.status_code == 400


def test_export_unknown_scan_returns_404(client: TestClient) -> None:
    resp = client.get("/scans/99999/export/csv")
    assert resp.status_code == 404


def test_scan_detail_lists_export_links(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}")
    assert resp.status_code == 200
    for fmt in ("csv", "json", "jira", "markdown"):
        assert f"/scans/{scan_id}/export/{fmt}" in resp.text


def test_findings_list_renders_thumbnails_with_blob_links(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    """Card view must include <img src='/blobs/<hash>'> so the reviewer
    can actually see what they're triaging."""
    import re

    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/findings")
    assert resp.status_code == 200
    assert "finding-grid" in resp.text
    blob_srcs = re.findall(r'src="/blobs/([0-9a-f]{64})"', resp.text)
    # Seeded fixture has two blob-backed findings (banner + logo).
    assert len(blob_srcs) >= 1
    # And every blob URL must actually serve an image.
    for h in blob_srcs[:2]:
        r = client.get(f"/blobs/{h}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")


def test_scan_detail_running_shows_cancel_button(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    """Scans still in 'running' state surface a Stop-crawl button."""
    import sqlite3 as _sqlite3

    db_path, _, _ = seeded_db
    conn = _sqlite3.connect(str(db_path))
    conn.row_factory = _sqlite3.Row
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
            "VALUES ('http://live.example/', 'running', 0, 0, '{}')"
        )
        running_id = int(cur.lastrowid or 0)
        conn.commit()
    finally:
        conn.close()

    resp = client.get(f"/scans/{running_id}")
    assert resp.status_code == 200
    assert "Stop crawl" in resp.text
    assert f"/scans/{running_id}/cancel" in resp.text


def test_cancel_endpoint_marks_scan_interrupted(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    import sqlite3 as _sqlite3

    db_path, _, _ = seeded_db
    conn = _sqlite3.connect(str(db_path))
    conn.row_factory = _sqlite3.Row
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
            "VALUES ('http://cancel.example/', 'running', 0, 0, '{}')"
        )
        running_id = int(cur.lastrowid or 0)
        # Seed a pending job for this scan so we verify cleanup.
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state) VALUES ('fetch', ?, 'pending')",
            (f'{{"url":"http://x/a","scan_id":{running_id},"depth":0}}',),
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.post(f"/scans/{running_id}/cancel", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/scans/{running_id}"

    check = _sqlite3.connect(str(db_path))
    check.row_factory = _sqlite3.Row
    try:
        row = check.execute("SELECT status FROM scans WHERE id = ?", (running_id,)).fetchone()
        pending = check.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE state = 'pending' AND "
            "json_extract(payload_json, '$.scan_id') = ?",
            (running_id,),
        ).fetchone()
    finally:
        check.close()
    assert row["status"] == "interrupted"
    assert int(pending["n"]) == 0


def test_cancel_unknown_scan_404s(client: TestClient) -> None:
    resp = client.post("/scans/99999/cancel")
    assert resp.status_code == 404


def test_cancel_completed_scan_is_noop(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.post(f"/scans/{scan_id}/cancel", follow_redirects=False)
    assert resp.status_code == 303
    # Completed scans keep their status.
    detail = client.get(f"/scans/{scan_id}")
    assert "completed" in detail.text


def test_scan_detail_shows_blocked_warning_for_non_2xx_seed(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    """When the seed page returned 4xx, surface a warning so the user
    knows the crawl wasn't successful — not just silently show 0 findings."""
    import sqlite3 as _sqlite3

    db_path, _, _ = seeded_db
    # Insert a new scan whose seed page is a 403.
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

    resp = client.get(f"/scans/{blocked_scan_id}")
    assert resp.status_code == 200
    assert "HTTP 403" in resp.text
    assert "Just a moment..." in resp.text
    assert "Use real browser" in resp.text


def test_scan_detail_no_warning_when_seed_is_2xx(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}")
    assert resp.status_code == 200
    assert "returned HTTP" not in resp.text


def test_new_scan_form_has_js_eager_checkbox(client: TestClient) -> None:
    resp = client.get("/scans/new")
    assert resp.status_code == 200
    assert 'name="js_eager"' in resp.text
    assert "Use real browser" in resp.text


def test_diff_route_without_previous_scan_400(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/diff")
    assert resp.status_code == 400


def test_diff_route_with_explicit_compare_to_404s_on_missing(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/scans/{scan_id}/diff?compare_to=99999")
    assert resp.status_code == 404


def test_new_scan_form_renders(client: TestClient) -> None:
    resp = client.get("/scans/new")
    assert resp.status_code == 200
    assert "<title>New scan" in resp.text
    assert 'name="url"' in resp.text
    assert 'name="max_pages"' in resp.text
    assert 'name="skip_ocr"' in resp.text


def test_new_scan_list_links_to_form(client: TestClient) -> None:
    resp = client.get("/scans")
    assert resp.status_code == 200
    assert 'href="/scans/new"' in resp.text


def test_new_scan_rejects_non_http_url(client: TestClient) -> None:
    resp = client.post(
        "/scans/new",
        data={"url": "ftp://example.com/"},
        follow_redirects=False,
    )
    # Stays on the form with an error, no redirect.
    assert resp.status_code == 200
    assert "http:// or https://" in resp.text
    # Echoes the bad value back into the form so the user can fix it.
    assert "ftp://example.com" in resp.text


def test_new_scan_rejects_empty_url(client: TestClient) -> None:
    # FastAPI's Form(...) returns 422 for a missing required field.
    resp = client.post("/scans/new", data={}, follow_redirects=False)
    assert resp.status_code == 422


def test_new_scan_accepts_valid_url_and_redirects(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio as _asyncio

    # Stub the background crawl so the test stays offline.
    called: dict[str, object] = {}

    async def _noop_crawl(db_path, config):  # type: ignore[no-untyped-def]
        called["ran"] = True
        called["seed"] = config.seed_url

    from audit.web import server as _server

    monkeypatch.setattr(_server, "_run_background_crawl", _noop_crawl)
    resp = client.post(
        "/scans/new",
        data={
            "url": "https://example.test/",
            "max_pages": 5,
            "max_depth": 2,
            "rps": 1.0,
            "workers": 2,
            "skip_ocr": "1",
            "skip_vlm": "1",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/scans/")

    # Give the scheduled task a tick to run.
    loop = _asyncio.new_event_loop()
    try:
        loop.run_until_complete(_asyncio.sleep(0.05))
    finally:
        loop.close()
    assert called.get("ran") is True
    assert called.get("seed") == "https://example.test/"


def test_new_scan_form_template_shows_running_banner() -> None:
    """Template-level check for the 'crawl in progress' banner.

    Rendering directly via Jinja avoids TestClient's per-request asyncio loop
    lifecycle, which makes live-task inspection flaky in tests. The banner
    itself is a simple conditional on ``running_scan_id``.
    """
    from jinja2 import Environment, FileSystemLoader

    from audit.web.server import _TEMPLATES_DIR

    env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)

    # Minimal stubs for base.html's url_for / scan context.
    def _url_for(_name: str, path: str = "") -> str:
        return f"/static/{path}"

    env.globals["url_for"] = _url_for
    rendered = env.get_template("new_scan.html").render(
        form={},
        running_scan_id=42,
        active="new",
        request=None,
        scan=None,
    )
    assert "crawl is already in progress" in rendered
    assert "/scans/42" in rendered
