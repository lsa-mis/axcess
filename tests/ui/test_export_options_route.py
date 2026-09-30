"""``GET /api/scans/{id}/exports``: what each Export panel download delivers.

The panel shows these sizes and the draft notice before anyone downloads, so
they must describe the very files the download route serves, under the same
refusals.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from .test_routes import _complete_evaluation


def _downloaded(client: TestClient, scan_id: int, fmt: str) -> tuple[str, int]:
    response = client.get(f"/api/scans/{scan_id}/export/{fmt}", params={"draft": "acknowledged"})
    assert response.status_code == 200, response.text
    disposition = response.headers["content-disposition"]
    return disposition.split('filename="', 1)[1].rstrip('"'), len(response.content)


def test_sizes_and_names_match_the_draft_downloads(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    _, _, scan_id = seeded_db

    response = client.get(f"/api/scans/{scan_id}/exports")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scan_id"] == scan_id
    assert body["draft"] is True
    assert [option["format"] for option in body["formats"]] == ["xlsx", "audit", "csv", "json"]
    for option in body["formats"]:
        filename, size = _downloaded(client, scan_id, option["format"])
        assert option["filename"] == filename
        assert "_DRAFT." in filename
        if option["format"] == "xlsx":
            # A workbook is a zip whose entries carry their write time, so two
            # renders can differ by a few bytes; the size is shown as "about".
            assert abs(option["size_bytes"] - size) <= 64
        else:
            assert option["size_bytes"] == size


def test_a_completed_evaluation_offers_final_files(
    client: TestClient, seeded_db: tuple[object, object, int]
) -> None:
    db_path, _, scan_id = seeded_db
    _complete_evaluation(client, db_path, scan_id)

    body = client.get(f"/api/scans/{scan_id}/exports").json()

    assert body["draft"] is False
    assert body["evaluation_status"] == "completed"
    assert {option["filename"] for option in body["formats"]} == {
        f"scan_{scan_id}.xlsx",
        f"scan_{scan_id}.audit.md",
        f"scan_{scan_id}.csv",
        f"scan_{scan_id}.json",
    }


def test_unknown_scan_is_not_found(client: TestClient) -> None:
    assert client.get("/api/scans/99999/exports").status_code == 404
