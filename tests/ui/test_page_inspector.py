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


def _unfinished_scan_with_page(
    db_path: Path, status: str, *, stored: bytes | None
) -> tuple[int, int]:
    """A scan that did not complete, holding one page with or without a capture."""
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) "
            "VALUES ('http://example.com/', ?, '{}')",
            (status,),
        )
        scan_id = int(cur.lastrowid or 0)
        cur = conn.execute(
            "INSERT INTO pages (scan_id, url_normalized, status_code, title, "
            "render_mode, html_hash, rendered_html) "
            "VALUES (?, 'http://example.com/', 200, 'Home', 'js', ?, ?)",
            (scan_id, "0" * 64, stored),
        )
        page_id = int(cur.lastrowid or 0)
        conn.commit()
        return scan_id, page_id
    finally:
        conn.close()


def test_inspect_refuses_to_render_a_page_an_unfinished_scan_never_stored(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    """The on-demand render is what needs a finished report.

    It leaves this machine to fetch a page a partial report cannot vouch for,
    so with nothing stored there is nothing to show and nothing safe to fetch.
    """
    db, _, _ = seeded_db
    scan_id, page_id = _unfinished_scan_with_page(db, "running", stored=None)

    resp = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect")

    assert resp.status_code == 409
    assert "no stored capture" in resp.json()["detail"]


def test_a_stopped_scan_can_still_show_what_it_captured(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    """A stopped scan's evidence is still its evidence.

    Refusing it applied a rule about re-rendering to reading: the status check
    ran before the page row was even loaded, so a capture the scan had already
    taken was unreadable for a reason that never applied to it.
    """
    db, _, _ = seeded_db
    html = "<!doctype html><html><body>partial evidence</body></html>"
    scan_id, page_id = _unfinished_scan_with_page(
        db, "interrupted", stored=gzip.compress(html.encode())
    )

    payload = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect").json()

    assert payload["render"]["ok"] is True
    assert payload["render"]["source"] == "stored"
    assert "partial evidence" in payload["render"]["dom_html"]


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


def _first_page_id(db_path: Path, scan_id: int) -> int:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        assert row is not None
        return int(row[0])
    finally:
        conn.close()


def _store_state(
    db_path: Path, page_id: int, scan_id: int, key: str, body: str = "<p>revealed</p>"
) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO page_dom_states (page_id, scan_id, state_key, revealed_by, "
            "path_labels, encoding, dom) VALUES (?, ?, ?, 'Open dialog', "
            "'[\"Menu\",\"Open dialog\"]', 'gzip', ?)",
            (
                page_id,
                scan_id,
                key,
                gzip.compress(f"<!doctype html><html>{body}</html>".encode()),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_inspect_lists_the_states_a_click_revealed(
    seeded_db: tuple[Path, Path, int],
    client: TestClient,
) -> None:
    """The picker needs to know what exists before it can offer it."""
    db_path, _, scan_id = seeded_db
    page_id = _first_page_id(db_path, scan_id)
    _store_state(db_path, page_id, scan_id, "s|#a|Open dialog")

    payload = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect").json()

    assert [state["state_key"] for state in payload["states"]] == ["s|#a|Open dialog"]
    assert payload["states"][0]["path_labels"] == ["Menu", "Open dialog"]
    # Metadata only: one reviewer reads one state at a time, and the documents
    # are far too large to ship together.
    assert "dom" not in payload["states"][0]
    # Without ?state= this is still the page as it loaded.
    assert payload["render"]["source"] in {"stored", "live"}


def test_inspect_serves_a_requested_state_instead_of_the_load_capture(
    seeded_db: tuple[Path, Path, int],
    client: TestClient,
) -> None:
    db_path, _, scan_id = seeded_db
    page_id = _first_page_id(db_path, scan_id)
    _store_state(db_path, page_id, scan_id, "s|#a|Open dialog", "<dialog>hi</dialog>")

    payload = client.get(
        f"/api/scans/{scan_id}/pages/{page_id}/inspect",
        params={"state": "s|#a|Open dialog"},
    ).json()

    assert payload["render"]["ok"] is True
    assert payload["render"]["source"] == "state"
    assert payload["render"]["state_key"] == "s|#a|Open dialog"
    assert "<dialog>hi</dialog>" in payload["render"]["dom_html"]


def test_a_state_that_was_never_captured_is_not_faked_with_a_live_render(
    seeded_db: tuple[Path, Path, int],
    client: TestClient,
) -> None:
    """Older reports cannot recover historical interaction DOM.

    A live render is the page loading *now*, which is exactly the state the
    reviewer said they did not want. Offering it as the dialog they asked for
    would be a more convincing version of the bug this all exists to fix, so
    the absence is reported instead.
    """
    db_path, _, scan_id = seeded_db
    page_id = _first_page_id(db_path, scan_id)

    payload = client.get(
        f"/api/scans/{scan_id}/pages/{page_id}/inspect",
        params={"state": "s|#missing|Gone"},
    ).json()

    assert payload["render"]["ok"] is False
    assert payload["render"]["source"] == "state"
    assert "not captured" in payload["render"]["error"]
    assert "dom_html" not in payload["render"]


def test_state_list_carries_the_whole_reproduction_path(
    seeded_db: tuple[Path, Path, int],
    client: TestClient,
) -> None:
    """A nested state takes more than one click to reach.

    The picker labels each state with the chain, so an auditor reproducing it
    by hand repeats every step rather than only the last one.
    """
    db_path, _, scan_id = seeded_db
    page_id = _first_page_id(db_path, scan_id)
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO page_dom_states (page_id, scan_id, state_key, revealed_by, "
            "path_labels, encoding, dom) VALUES (?, ?, 'k|#deep|Level two', 'Level two', "
            "'[\"Level one\",\"Level two\"]', 'gzip', ?)",
            (page_id, scan_id, gzip.compress(b"<!doctype html><html></html>")),
        )
        conn.commit()
    finally:
        conn.close()

    payload = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect").json()

    assert payload["states"][0]["path_labels"] == ["Level one", "Level two"]
    assert payload["states"][0]["revealed_by"] == "Level two"
