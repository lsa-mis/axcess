"""``GET /api/scans/{scan_id}/pages``: the pages one report visited."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit.db import repo

pytestmark = pytest.mark.ui


def _add_scan_with_page(db_path: Path, url: str) -> tuple[int, int]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
            "VALUES (?, 'completed', 1, 0, '{}')",
            (url,),
        )
        scan_id = int(cur.lastrowid or 0)
        page_id = repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized=url,
            status_code=200,
            title="Other site",
            render_mode="js",
            html_hash=None,
        )
    return scan_id, page_id


def _add_page(db_path: Path, scan_id: int, url: str, status: int | None) -> int:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized=url,
            status_code=status,
            title=None,
            render_mode="static",
            html_hash=None,
        )


def test_lists_the_reports_pages_with_totals(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    down = _add_page(db_path, scan_id, "http://example.com/down", None)
    _add_page(db_path, scan_id, "http://example.com/gone", 404)

    resp = client.get(f"/api/scans/{scan_id}/pages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_id"] == scan_id
    assert body["total"] == 4
    assert body["not_loaded_count"] == 1
    assert body["error_status_count"] == 1
    assert body["sort"] == "load_desc"
    assert (body["limit"], body["offset"]) == (50, 0)
    first = body["pages"][0]
    # Problems first: the page that could not be loaded leads.
    assert first["page_id"] == down
    assert first["load_result"] == "not_loaded"
    assert first["status_code"] is None
    assert set(first) == {
        "page_id",
        "url",
        "title",
        "status_code",
        "load_result",
        "occurrence_count",
        "image_count",
        "page_state_count",
    }
    home = next(p for p in body["pages"] if p["url"] == "http://example.com/")
    # The seed puts two images on the home page.
    assert (home["title"], home["load_result"], home["image_count"]) == ("Home", "loaded", 2)


def test_pages_are_paged_and_sorted(client: TestClient, seeded_db: tuple[Path, Path, int]) -> None:
    _, _, scan_id = seeded_db
    first = client.get(f"/api/scans/{scan_id}/pages?limit=1&offset=0&sort=url_asc").json()
    second = client.get(f"/api/scans/{scan_id}/pages?limit=1&offset=1&sort=url_asc").json()
    assert first["total"] == second["total"] == 2
    assert [p["url"] for p in first["pages"] + second["pages"]] == [
        "http://example.com/",
        "http://example.com/about",
    ]


@pytest.mark.parametrize(
    "query",
    ["limit=201", "limit=0", "offset=-1", "sort=id", "sort=url_asc;DROP"],
)
def test_out_of_bounds_requests_are_refused(
    client: TestClient, seeded_db: tuple[Path, Path, int], query: str
) -> None:
    _, _, scan_id = seeded_db
    assert client.get(f"/api/scans/{scan_id}/pages?{query}").status_code == 422


def test_the_largest_page_is_allowed(client: TestClient, seeded_db: tuple[Path, Path, int]) -> None:
    _, _, scan_id = seeded_db
    resp = client.get(f"/api/scans/{scan_id}/pages?limit=200")
    assert resp.status_code == 200
    assert resp.json()["limit"] == 200


def test_unknown_scan_is_404(client: TestClient) -> None:
    assert client.get("/api/scans/999999/pages").status_code == 404


def test_one_report_never_lists_another_reports_pages(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    other_scan, other_page = _add_scan_with_page(db_path, "http://other.example/")

    mine = client.get(f"/api/scans/{scan_id}/pages?limit=200").json()
    assert other_page not in {p["page_id"] for p in mine["pages"]}
    assert all(p["url"].startswith("http://example.com/") for p in mine["pages"])

    theirs = client.get(f"/api/scans/{other_scan}/pages").json()
    assert [p["page_id"] for p in theirs["pages"]] == [other_page]
    assert theirs["total"] == 1


# --- GET /api/scans/{id}/pages/export.csv: the whole list as a CSV file ------


def _csv_rows(text: str) -> list[list[str]]:
    import csv
    import io

    assert text.startswith("\ufeff"), "starts with a byte order mark for Excel"
    return list(csv.reader(io.StringIO(text.removeprefix("\ufeff"))))


def test_csv_holds_every_page_in_the_lists_order(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    down = _add_page(db_path, scan_id, "http://example.com/down", None)
    _add_page(db_path, scan_id, "http://example.com/gone", 404)

    resp = client.get(f"/api/scans/{scan_id}/pages/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert f'filename="report-{scan_id}-pages-visited.csv"' in resp.headers["content-disposition"]
    rows = _csv_rows(resp.text)
    assert rows[0] == [
        "Page title",
        "Page address",
        "Page load result",
        "Server response code (HTTP status)",
        "Issue occurrences",
        "Images checked",
        "Page states opened by clicking",
        "Page details in Axcess",
    ]
    listed = client.get(f"/api/scans/{scan_id}/pages?limit=200").json()
    # Every page, not one page of rows, in the list's default order.
    assert [r[1] for r in rows[1:]] == [p["url"] for p in listed["pages"]]
    first = rows[1]
    # Problems first; a page that did not load reads "Not checked", never 0.
    assert first[1:7] == [
        "http://example.com/down",
        "Could not be loaded",
        "",
        "Not checked",
        "Not checked",
        "Not checked",
    ]
    assert first[7].endswith(f"/app/scans/{scan_id}/pages/{down}")
    gone = next(r for r in rows if r[1] == "http://example.com/gone")
    assert (gone[2], gone[3]) == ("Page not found (HTTP 404)", "404")
    home = next(r for r in rows if r[1] == "http://example.com/")
    assert (home[0], home[5]) == ("Home", "2")


def test_csv_follows_the_chosen_sort(client: TestClient, seeded_db: tuple[Path, Path, int]) -> None:
    _, _, scan_id = seeded_db
    rows = _csv_rows(client.get(f"/api/scans/{scan_id}/pages/export.csv?sort=url_desc").text)
    urls = [r[1] for r in rows[1:]]
    listed = client.get(f"/api/scans/{scan_id}/pages?limit=200&sort=url_desc").json()
    assert urls == [p["url"] for p in listed["pages"]]


def test_csv_keeps_a_page_title_from_running_as_a_formula(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE pages SET title = '=HYPERLINK(\"http://evil.test\")' "
            "WHERE scan_id = ? AND url_normalized = 'http://example.com/'",
            (scan_id,),
        )
    rows = _csv_rows(client.get(f"/api/scans/{scan_id}/pages/export.csv").text)
    home = next(r for r in rows if r[1] == "http://example.com/")
    assert home[0] == '\'=HYPERLINK("http://evil.test")'


def test_csv_never_holds_another_reports_pages(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    _add_scan_with_page(db_path, "http://other.example/")
    text = client.get(f"/api/scans/{scan_id}/pages/export.csv").text
    assert "other.example" not in text
    assert "Other site" not in text


@pytest.mark.parametrize("query", ["sort=id", "sort=url_asc;DROP"])
def test_csv_refuses_an_unknown_sort(
    client: TestClient, seeded_db: tuple[Path, Path, int], query: str
) -> None:
    _, _, scan_id = seeded_db
    assert client.get(f"/api/scans/{scan_id}/pages/export.csv?{query}").status_code == 422


def test_csv_unknown_scan_is_404(client: TestClient) -> None:
    assert client.get("/api/scans/999999/pages/export.csv").status_code == 404


def test_csv_waits_for_a_running_scan_but_serves_a_stopped_one(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE scans SET status = 'running' WHERE id = ?", (scan_id,))
    assert client.get(f"/api/scans/{scan_id}/pages/export.csv").status_code == 409
    with sqlite3.connect(db_path) as conn:
        # A stopped scan with saved pages is a report and gets its file.
        conn.execute(
            "UPDATE scans SET status = 'interrupted', page_count = 3 WHERE id = ?", (scan_id,)
        )
    assert client.get(f"/api/scans/{scan_id}/pages/export.csv").status_code == 200


def test_csv_of_a_protected_report_is_refused(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE protected_scans RENAME TO saved_protected_scans")
        conn.execute("CREATE TABLE protected_scans(scan_id INTEGER, authorized_by TEXT)")
        conn.execute("INSERT INTO protected_scans VALUES(?, 'private-reviewer')", (scan_id,))
    response = client.get(f"/api/scans/{scan_id}/pages/export.csv")
    # The protected-report middleware may answer first; either way, no list.
    assert response.status_code in {401, 403, 404}
    assert "example.com" not in response.text
    assert "private-reviewer" not in response.text
