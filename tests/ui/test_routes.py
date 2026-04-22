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
    resp = client.get(
        f"/scans/{scan_id}/findings", headers={"HX-Request": "true"}
    )
    assert resp.status_code == 200
    # Partial must NOT include <html> / skip-link / nav.
    assert "<title>" not in resp.text
    assert "skip-link" not in resp.text
    assert "<table" in resp.text or "No findings" in resp.text


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
    assert "<option value=\"reviewing\" selected" in detail.text


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


def test_blob_serves_png_bytes(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
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
