"""The saved-styles route: one report's CSS, never another's, cacheable.

``GET /api/scans/{scan}/pages/{page}/saved-styles.css`` serves the CSS the
scan saved with one saved copy, and the inspect payload says where to find it.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit.blob_store import BlobStore
from audit.crawler.style_snapshot import SheetRef, StoredStyles
from audit.db import repo
from audit.db.schema import connect
from audit.web.server import create_app

pytestmark = pytest.mark.ui

FINGERPRINT = {"scheme": "light", "forced_colors": False, "samples": [{"index": 0}]}


def _seed_styles(
    db_path: Path,
    blob_dir: Path,
    scan_id: int,
    *,
    sheets: list[tuple[str, str]],
    state_key: str = "",
    complete: bool = True,
) -> int:
    """Give the scan's first page a saved copy with these ``(css, media)`` sheets."""
    store = BlobStore(blob_dir)
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        page_id = int(
            conn.execute(
                "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
            ).fetchone()["id"]
        )
        conn.execute(
            "UPDATE pages SET rendered_html = ? WHERE id = ?",
            (gzip.compress(b"<!doctype html><html><head></head><body>x</body></html>"), page_id),
        )
        refs = tuple(
            SheetRef(sha256=store.store(css.encode(), "text/css")[0], media=media, source_url=None)
            for css, media in sheets
        )
        styles = StoredStyles(sheets=refs, complete=complete, fingerprint=FINGERPRINT)
        if state_key:
            conn.execute(
                "INSERT INTO page_dom_states (page_id, scan_id, state_key, revealed_by, "
                "path_labels, encoding, dom) VALUES (?, ?, ?, 'Menu', '[\"Menu\"]', 'gzip', ?)",
                (page_id, scan_id, state_key, gzip.compress(b"<html><body>s</body></html>")),
            )
            repo.replace_state_styles(
                conn, scan_id=scan_id, page_id=page_id, styles={state_key: styles}
            )
        else:
            repo.set_page_styles(conn, scan_id=scan_id, page_id=page_id, styles=styles)
        conn.commit()
        return page_id
    finally:
        conn.close()


def _second_scan(db_path: Path) -> tuple[int, int]:
    conn = connect(db_path)
    try:
        scan_id = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
                "VALUES ('http://example.com/', 'completed', 1, 0, '{}')"
            ).lastrowid
            or 0
        )
        page_id = repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized="http://example.com/other",
            status_code=200,
            title="Other",
            render_mode="js",
            html_hash="1" * 64,
        )
        conn.commit()
        return scan_id, page_id
    finally:
        conn.close()


def test_serves_the_sheets_in_order_with_media_wrapped(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    page_id = _seed_styles(
        db_path, blob_dir, scan_id, sheets=[("a{color:red}", ""), ("b{color:blue}", "print")]
    )

    response = client.get(f"/api/scans/{scan_id}/pages/{page_id}/saved-styles.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.text.index("a{color:red}") < response.text.index("@media print {")
    assert "@media print {\nb{color:blue}\n}" in response.text


def test_the_inspect_payload_points_at_it_and_the_etag_holds(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    page_id = _seed_styles(db_path, blob_dir, scan_id, sheets=[("a{}", "")], complete=False)

    payload = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect").json()
    saved = payload["saved_styles"]
    assert payload["render"]["source"] == "stored"
    assert saved["complete"] is False
    assert saved["fingerprint"] == FINGERPRINT
    assert saved["url"].startswith(f"/api/scans/{scan_id}/pages/{page_id}/saved-styles.css?v=")

    first = client.get(saved["url"])
    etag = first.headers["etag"]
    assert first.status_code == 200
    # The versioned URL never changes content, so it is kept without asking.
    assert "immutable" in first.headers["cache-control"]
    assert etag.strip('"') == saved["url"].split("v=")[1]

    again = client.get(saved["url"], headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""

    # Any other URL revalidates.
    plain = client.get(f"/api/scans/{scan_id}/pages/{page_id}/saved-styles.css")
    assert plain.headers["cache-control"] == "private, no-cache"
    assert plain.headers["etag"] == etag


def test_page_states_have_their_own_styles(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    page_id = _seed_styles(
        db_path, blob_dir, scan_id, sheets=[("dialog{color:green}", "")], state_key="menu|#m|Menu"
    )

    payload = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect").json()
    assert payload["saved_styles"] is None
    (state,) = payload["states"]
    assert "state=menu%7C%23m%7CMenu" in state["saved_styles"]["url"]

    css = client.get(state["saved_styles"]["url"])
    assert css.status_code == 200
    assert "dialog{color:green}" in css.text
    # The page as it loaded has no saved styles of its own here.
    assert client.get(f"/api/scans/{scan_id}/pages/{page_id}/saved-styles.css").status_code == 404


def test_unknown_page_state_or_report_is_404(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    page_id = _seed_styles(db_path, blob_dir, scan_id, sheets=[("a{}", "")])

    assert client.get(f"/api/scans/{scan_id}/pages/999999/saved-styles.css").status_code == 404
    assert (
        client.get(f"/api/scans/{scan_id}/pages/{page_id}/saved-styles.css?state=nope").status_code
        == 404
    )
    assert client.get(f"/api/scans/999999/pages/{page_id}/saved-styles.css").status_code == 404


def test_one_report_cannot_read_another_reports_styles(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    page_a = _seed_styles(db_path, blob_dir, scan_id, sheets=[("secret{color:red}", "")])
    scan_b, page_b = _second_scan(db_path)

    # Scan B's id with scan A's page: the page is not part of report B.
    crossed = client.get(f"/api/scans/{scan_b}/pages/{page_a}/saved-styles.css")
    assert crossed.status_code == 404
    assert "secret" not in crossed.text
    # Scan B's own page has none.
    assert client.get(f"/api/scans/{scan_b}/pages/{page_b}/saved-styles.css").status_code == 404


def test_older_reports_without_the_table_still_inspect(
    seeded_db: tuple[Path, Path, int],
) -> None:
    """A database that stopped before migration 0030 reads as no saved styles."""
    db_path, blob_dir, scan_id = seeded_db
    page_id = _seed_styles(db_path, blob_dir, scan_id, sheets=[("a{}", "")])
    conn = connect(db_path)
    try:
        conn.execute("DROP TABLE saved_copy_styles")
        conn.commit()
    finally:
        conn.close()
    client = TestClient(create_app(db_path=db_path, blob_dir=blob_dir))

    payload = client.get(f"/api/scans/{scan_id}/pages/{page_id}/inspect").json()
    assert payload["render"]["ok"] is True
    assert payload["saved_styles"] is None
    assert client.get(f"/api/scans/{scan_id}/pages/{page_id}/saved-styles.css").status_code == 404


def test_the_access_token_gate_covers_it(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    page_id = _seed_styles(db_path, blob_dir, scan_id, sheets=[("a{}", "")])
    monkeypatch.setenv("AUDIT_ACCESS_TOKEN", "test-token")
    client = TestClient(create_app(db_path=db_path, blob_dir=blob_dir))
    url = f"/api/scans/{scan_id}/pages/{page_id}/saved-styles.css"

    assert client.get(url).status_code == 401
    # The cookie the gate sets is what a <link> in the frame sends.
    assert client.get(f"{url}?token=test-token").status_code == 200
    assert client.get(url).status_code == 200
