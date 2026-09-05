"""Route-level tests for the on-demand Page/DOM inspector endpoint.

The live re-render (Playwright + a real fetch) is exercised manually against
the fixture site; these tests cover the HTTP contract and the guard railings
that do not need a browser — unknown scan, page not in scan, non-completed
scan, and the success payload with a monkeypatched renderer (so no network
request is made). The renderer returns the DOM only and stores nothing.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.db.schema import connect
from audit.web import page_inspector as pi

pytestmark = pytest.mark.ui


def _page_id(conn: sqlite3.Connection, scan_id: int, url: str) -> int:
    row = conn.execute(
        "SELECT id FROM pages WHERE scan_id = ? AND url_normalized = ?",
        (scan_id, url),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def test_inspect_refuses_unknown_scan(client: TestClient) -> None:
    resp = client.get("/api/scans/999999/pages/1/inspect")
    assert resp.status_code == 404


def test_inspect_refuses_page_not_in_scan(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/pages/999999/inspect")
    assert resp.status_code == 404


def test_inspect_refuses_running_scan(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db, _, _ = seeded_db
    conn = connect(db)
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('http://example.com/', 'running', '{}')"
        )
        running_id = int(cur.lastrowid or 0)
    finally:
        conn.close()
    resp = client.get(f"/api/scans/{running_id}/pages/1/inspect")
    assert resp.status_code == 409


def test_inspect_returns_render_payload_without_storing(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _, scan_id = seeded_db
    conn = connect(db)
    try:
        page_id = _page_id(conn, scan_id, "http://example.com/")
    finally:
        conn.close()

    async def fake_render(
        url: str,
        *,
        user_agent: str,
        viewport: dict[str, int],
        nav_timeout_ms: int,
        idle_timeout_ms: int,
    ) -> tuple[dict[str, Any], None]:
        return (
            {
                "dom_html": "<!doctype html><html><body><h1>Hi</h1></body></html>",
                "final_url": url,
                "status_code": 200,
            },
            None,
        )

    monkeypatch.setattr(pi, "_render_page", fake_render)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")
    assert resp.status_code == 200
    body = resp.json()

    assert body["page"]["id"] == page_id
    assert body["render"]["ok"] is True
    assert body["render"]["source"] == "live"
    assert body["render"]["dom_html"].startswith("<!doctype html>")
    assert body["render"]["dom_truncated"] is False
    # The inspector returns HTML only — no screenshot field.
    assert "screenshot_hash" not in body["render"]

    # And nothing was persisted: the image blob index is unchanged.
    conn = connect(db)
    try:
        before = conn.execute("SELECT count(*) AS n FROM images").fetchone()["n"]
    finally:
        conn.close()
    assert before == 2  # the two seeded banner/logo images, and only those


def test_inspect_serves_stored_html_without_render(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored rendered HTML is served instantly — the renderer never runs."""
    db, _, scan_id = seeded_db
    html = "<!doctype html><html><body><h1>Stored</h1></body></html>"
    conn = connect(db)
    try:
        page_id = _page_id(conn, scan_id, "http://example.com/")
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(html.encode()), page_id),
        )
    finally:
        conn.close()

    calls = {"n": 0}

    async def boom_render(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        raise AssertionError("renderer must not run when HTML is already stored")

    monkeypatch.setattr(pi, "_render_page", boom_render)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["render"]["ok"] is True
    assert body["render"]["source"] == "stored"
    assert body["render"]["dom_html"] == html
    assert calls["n"] == 0


def test_inspect_reports_render_failure_honestly(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _, scan_id = seeded_db
    conn = connect(db)
    try:
        page_id = _page_id(conn, scan_id, "http://example.com/")
    finally:
        conn.close()

    async def failing_render(
        url: str,
        *,
        user_agent: str,
        viewport: dict[str, int],
        nav_timeout_ms: int,
        idle_timeout_ms: int,
    ) -> tuple[None, str]:
        return None, "The page returned 403 (text/html), so there is no rendered HTML to show."

    monkeypatch.setattr(pi, "_render_page", failing_render)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["render"]["ok"] is False
    assert "403" in body["render"]["error"]


def test_inspect_flags_rendered_storage_disabled(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scan configured not to store rendered pages re-renders live, and the
    payload says so the UI can explain the on-demand render."""
    db, _, scan_id = seeded_db
    conn = connect(db)
    try:
        page_id = _page_id(conn, scan_id, "http://example.com/")
        conn.execute(
            "UPDATE scans SET config_json = ? WHERE id = ?",
            ('{"store_rendered_html": false}', scan_id),
        )
    finally:
        conn.close()

    async def fake_render(
        url: str,
        *,
        user_agent: str,
        viewport: dict[str, int],
        nav_timeout_ms: int,
        idle_timeout_ms: int,
    ) -> tuple[dict[str, Any], None]:
        return (
            {
                "dom_html": "<!doctype html><html><body><h1>Live</h1></body></html>",
                "final_url": url,
                "status_code": 200,
            },
            None,
        )

    monkeypatch.setattr(pi, "_render_page", fake_render)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["store_rendered_html"] is False
    assert body["render"]["ok"] is True
    assert body["render"]["source"] == "live"
    assert body["render"]["dom_html"].startswith("<!doctype html>")


def test_inspect_defaults_to_storing_rendered_pages(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scans whose config predates the toggle keep the storing default."""
    db, _, scan_id = seeded_db
    conn = connect(db)
    try:
        page_id = _page_id(conn, scan_id, "http://example.com/")
    finally:
        conn.close()

    async def fake_render(
        url: str,
        *,
        user_agent: str,
        viewport: dict[str, int],
        nav_timeout_ms: int,
        idle_timeout_ms: int,
    ) -> tuple[dict[str, Any], None]:
        return (
            {
                "dom_html": "<!doctype html><html><body><h1>Live</h1></body></html>",
                "final_url": url,
                "status_code": 200,
            },
            None,
        )

    monkeypatch.setattr(pi, "_render_page", fake_render)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")
    assert resp.status_code == 200
    body = resp.json()
    # The seeded fixture stores its config as "{}" — the flag defaults on.
    assert body["store_rendered_html"] is True
    assert body["render"]["source"] == "live"


def test_inspect_serves_existing_capture_when_storage_toggled_off(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The toggle governs what the crawl writes, not what it may read: a
    resumed scan keeps serving captures it stored before the toggle changed."""
    db, _, scan_id = seeded_db
    html = "<!doctype html><html><body><h1>Kept</h1></body></html>"
    conn = connect(db)
    try:
        page_id = _page_id(conn, scan_id, "http://example.com/")
        conn.execute(
            "UPDATE scans SET config_json = ? WHERE id = ?",
            ('{"store_rendered_html": false}', scan_id),
        )
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(html.encode()), page_id),
        )
    finally:
        conn.close()

    async def boom_render(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a stored capture must be served without a render")

    monkeypatch.setattr(pi, "_render_page", boom_render)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["render"]["source"] == "stored"
    assert body["render"]["dom_html"] == html
    assert body["store_rendered_html"] is False


def test_inspect_large_payload_is_gzipped(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The multi-megabyte rendered-DOM payload is gzip-compressed in transit
    (small JSON responses pass through uncompressed)."""
    db, _, scan_id = seeded_db
    big = "<!doctype html><html><body>" + ("<p>fill</p>" * 400) + "</body></html>"
    conn = connect(db)
    try:
        page_id = _page_id(conn, scan_id, "http://example.com/")
    finally:
        conn.close()

    async def fake_render(
        url: str,
        *,
        user_agent: str,
        viewport: dict[str, int],
        nav_timeout_ms: int,
        idle_timeout_ms: int,
    ) -> tuple[dict[str, Any], None]:
        return ({"dom_html": big, "final_url": url, "status_code": 200}, None)

    monkeypatch.setattr(pi, "_render_page", fake_render)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
    assert "accept-encoding" in resp.headers.get("vary", "").lower()
    body = resp.json()  # httpx decodes transparently
    assert body["render"]["dom_html"] == big


def test_inspect_small_payload_is_not_gzipped(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Below the size floor the JSON goes out uncompressed — the gzip CPU
    cost is not worth it for tiny payloads."""
    db, _, scan_id = seeded_db
    conn = connect(db)
    try:
        page_id = _page_id(conn, scan_id, "http://example.com/")
    finally:
        conn.close()

    async def fake_render(
        url: str,
        *,
        user_agent: str,
        viewport: dict[str, int],
        nav_timeout_ms: int,
        idle_timeout_ms: int,
    ) -> tuple[dict[str, Any], None]:
        return ({"dom_html": "<p>tiny</p>", "final_url": url, "status_code": 200}, None)

    monkeypatch.setattr(pi, "_render_page", fake_render)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") is None
    assert resp.json()["render"]["dom_html"] == "<p>tiny</p>"
