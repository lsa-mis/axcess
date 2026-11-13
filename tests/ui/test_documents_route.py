"""The Documents tab: ``GET /api/scans/{id}/documents``.

The seeded report gets one file of each kind the screen must show: two
Mostly sure PDFs (one a form linked from two pages, one also revealed by a
click), a Not sure PDF shown in a frame, and four that could not be checked
for four different reasons. The API tests pin the order, the counts and scan
isolation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.db import linked_files as store
from audit.db import repo

pytestmark = pytest.mark.ui

HOME = "http://example.com/"
ABOUT = "http://example.com/about"


def _file(
    conn: sqlite3.Connection,
    scan_id: int,
    url: str,
    file_type: str,
    result: store.CheckResult | None,
    refs: list[tuple[int, str, str, str | None]],
    *,
    off_site: bool = False,
) -> int:
    file_id = store.upsert_file(
        conn,
        scan_id=scan_id,
        url=url,
        file_type=file_type,  # type: ignore[arg-type]
        found_by="extension",
        off_site=off_site,
    )
    assert file_id is not None
    if result is not None:
        store.set_result(conn, scan_id=scan_id, file_id=file_id, result=result)
    for page_id, how, text, revealed_by in refs:
        store.add_ref(
            conn,
            scan_id=scan_id,
            file_id=file_id,
            page_id=page_id,
            how=how,  # type: ignore[arg-type]
            link_text=text,
            revealed_by=revealed_by,
        )
    return file_id


def _page_id(conn: sqlite3.Connection, scan_id: int, url: str) -> int:
    row = conn.execute(
        "SELECT id FROM pages WHERE scan_id = ? AND url_normalized = ?", (scan_id, url)
    ).fetchone()
    return int(row[0])


def _seed_documents(db_path: Path, scan_id: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE scans SET config_json = json_set(config_json, '$.linked_files_enabled', "
            "json('true')) WHERE id = ?",
            (scan_id,),
        )
        home = _page_id(conn, scan_id, HOME)
        about = _page_id(conn, scan_id, ABOUT)
        _file(
            conn,
            scan_id,
            "http://example.com/files/no-title.pdf",
            "pdf",
            store.CheckResult("mostly_sure", failed_checks=["no_title"], http_status=200),
            [(home, "link", "Price list (PDF)", None)],
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/permit-form.pdf",
            "pdf",
            store.CheckResult(
                "mostly_sure",
                failed_checks=["not_tagged", "no_language"],
                is_form=True,
                http_status=200,
            ),
            [
                (home, "link", "Apply for a permit (PDF)", None),
                (about, "revealed_link", "Permit form", "More forms"),
            ],
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/map.pdf",
            "pdf",
            store.CheckResult("not_sure", http_status=200),
            [(home, "iframe", "Course map", None)],
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/report.docx",
            "docx",
            None,
            [(home, "link", "Committee report (Word)", None)],
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/budget.xls",
            "xls",
            None,
            [(about, "link", "Budget 2003 (Excel)", None)],
        )
        _file(
            conn,
            scan_id,
            "https://docs.google.com/document/d/abc/edit",
            "google_doc",
            None,
            [(about, "link", "Meeting notes", None)],
            off_site=True,
        )
        _file(
            conn,
            scan_id,
            "http://example.com/files/missing.pdf",
            "pdf",
            store.CheckResult("could_not_check", "http_error", http_status=404),
            [(home, "link", "Old newsletter (PDF)", None)],
        )


@pytest.fixture
def documents(seeded_db: tuple[Path, Path, int]) -> int:
    db_path, _, scan_id = seeded_db
    _seed_documents(db_path, scan_id)
    return scan_id


def test_files_come_in_the_recommended_order(client: TestClient, documents: int) -> None:
    body = client.get(f"/api/scans/{documents}/documents").json()
    assert body["recorded"] is True
    assert body["total"] == 7
    assert body["counts"] == {"mostly_sure": 2, "not_sure": 1, "could_not_check": 4}
    assert [(f["name"], f["status"], f["reason"]) for f in body["files"]] == [
        # Mostly sure: the form on two pages before the one on one page.
        ("permit-form.pdf", "mostly_sure", None),
        ("no-title.pdf", "mostly_sure", None),
        ("map.pdf", "not_sure", None),
        # Could not check: one page each, so by address.
        ("budget.xls", "could_not_check", "old_format"),
        ("missing.pdf", "could_not_check", "http_error"),
        ("report.docx", "could_not_check", "type_not_checked_yet"),
        # A Google address has no file name, so the link's text names it.
        ("Meeting notes", "could_not_check", "google_file"),
    ]
    form = body["files"][0]
    assert form["failed_checks"] == ["not_tagged", "no_language"]
    assert (form["is_form"], form["referring_page_count"]) == (True, 2)
    assert form["refs"] == [
        {
            "page_id": form["refs"][0]["page_id"],
            "page_url": HOME,
            "page_title": "Home",
            "how": "link",
            "link_text": "Apply for a permit (PDF)",
            "revealed_by": None,
        },
        {
            "page_id": form["refs"][1]["page_id"],
            "page_url": ABOUT,
            "page_title": "About",
            "how": "revealed_link",
            "link_text": "Permit form",
            "revealed_by": "More forms",
        },
    ]


def test_a_report_that_did_not_look_says_so(client: TestClient, seeded_db: Any) -> None:
    _, _, scan_id = seeded_db
    body = client.get(f"/api/scans/{scan_id}/documents").json()
    assert (body["recorded"], body["total"], body["files"]) == (False, 0, [])


def test_a_file_still_pending_shows_as_not_checked(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    with sqlite3.connect(seeded_db[0]) as conn:
        _file(conn, documents, "http://example.com/files/late.pdf", "pdf", None, [])
    body = client.get(f"/api/scans/{documents}/documents?limit=200").json()
    late = next(f for f in body["files"] if f["name"] == "late.pdf")
    assert (late["status"], late["reason"], late["refs"]) == ("could_not_check", "not_checked", [])
    assert body["counts"]["could_not_check"] == 5


def test_files_are_paged(client: TestClient, documents: int) -> None:
    first = client.get(f"/api/scans/{documents}/documents?limit=3&offset=0").json()
    rest = client.get(f"/api/scans/{documents}/documents?limit=3&offset=3").json()
    names = [f["name"] for f in first["files"] + rest["files"]]
    assert len(names) == 6 and len(set(names)) == 6
    assert first["total"] == rest["total"] == 7


@pytest.mark.parametrize("query", ["limit=201", "limit=0", "offset=-1"])
def test_out_of_bounds_requests_are_refused(client: TestClient, documents: int, query: str) -> None:
    assert client.get(f"/api/scans/{documents}/documents?{query}").status_code == 422


def test_unknown_scan_is_404(client: TestClient) -> None:
    assert client.get("/api/scans/999999/documents").status_code == 404


def test_one_report_never_lists_another_reports_files(
    client: TestClient, seeded_db: tuple[Path, Path, int], documents: int
) -> None:
    with sqlite3.connect(seeded_db[0]) as conn:
        conn.row_factory = sqlite3.Row
        other = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, config_json) "
                "VALUES ('http://other.example/', 'completed', '{\"linked_files_enabled\": true}')"
            ).lastrowid
            or 0
        )
        page = repo.upsert_page(
            conn,
            scan_id=other,
            url_normalized="http://other.example/",
            status_code=200,
            title="Other",
            render_mode="js",
            html_hash=None,
        )
        _file(
            conn,
            other,
            "http://other.example/secret.pdf",
            "pdf",
            store.CheckResult("not_sure"),
            [(page, "link", "Secret", None)],
        )
    mine = client.get(f"/api/scans/{documents}/documents?limit=200").json()
    assert "secret.pdf" not in {f["name"] for f in mine["files"]}
    theirs = client.get(f"/api/scans/{other}/documents").json()
    assert [f["name"] for f in theirs["files"]] == ["secret.pdf"]
    assert theirs["files"][0]["refs"][0]["page_url"] == "http://other.example/"
