"""How the Documents report shows Word and PowerPoint results (2026-11-18).

A Google Doc or Slides deck is checked as the file Google exports, which
never carries a document title the author could set, so "No document title"
is left out for Google files. Migration 0046 re-decides "Mostly sure" for
files checked before "Table without a header row" became a possible problem.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from audit.db import linked_files as store
from audit.web import linked_files_queries as q

MIGRATIONS = Path(__file__).parents[2] / "src/audit/db/migrations"


def _scan(conn: sqlite3.Connection) -> int:
    scan_id = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://site.test/', 'completed', '{\"linked_files_enabled\": true}')"
    ).lastrowid
    assert scan_id is not None
    return int(scan_id)


def _file(
    conn: sqlite3.Connection, scan_id: int, url: str, file_type: str, failed: list[str]
) -> int:
    file_id = store.upsert_file(
        conn,
        scan_id=scan_id,
        url=url,
        file_type=file_type,  # type: ignore[arg-type]
        found_by="host",
        off_site=True,
    )
    assert file_id is not None
    status = "mostly_sure" if set(failed) & {"no_alt_text", "table_no_header"} else "not_sure"
    conn.execute(
        "UPDATE linked_files SET status = ?, reason = NULL, failed_checks = json(?), "
        "checked_as = 'docx' WHERE id = ?",
        (status, __import__("json").dumps(failed), file_id),
    )
    return file_id


def test_a_google_doc_does_not_list_a_title_its_author_cannot_set(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _scan(tmp_db)
    _file(
        tmp_db,
        scan_id,
        "https://docs.google.com/document/d/1abcdefghijk/edit",
        "google_doc",
        ["no_alt_text", "no_title"],
    )
    _file(
        tmp_db,
        scan_id,
        "https://drive.google.com/file/d/1abcdefghijk/view",
        "google_drive",
        ["no_title"],
    )
    rows = {
        row.file_type: row
        for row in q.list_scan_documents(tmp_db, scan_id, limit=50, offset=0).files
    }
    doc, drive = rows["google_doc"], rows["google_drive"]
    assert "no_title" not in doc.possible_problems and "no_title" not in doc.checks_run
    assert doc.failed_checks == ["no_alt_text"]
    # A Word file kept in Drive is the author's own file, whose title they can set.
    assert drive.possible_problems == ["no_title"] and "no_title" in drive.checks_run


def test_migration_0046_re_decides_files_whose_only_barrier_was_a_table(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _scan(tmp_db)
    table_only = _file(
        tmp_db, scan_id, "https://site.test/a.docx", "docx", ["table_no_header", "no_title"]
    )
    with_alt = _file(
        tmp_db, scan_id, "https://site.test/b.docx", "docx", ["table_no_header", "no_alt_text"]
    )
    forward = (MIGRATIONS / "0046_office_table_header_possible.sql").read_text()
    rollback = (MIGRATIONS / "0046_office_table_header_possible.rollback.sql").read_text()

    def status(file_id: int) -> str:
        return str(
            tmp_db.execute("SELECT status FROM linked_files WHERE id = ?", (file_id,)).fetchone()[0]
        )

    tmp_db.executescript(forward)
    assert (status(table_only), status(with_alt)) == ("not_sure", "mostly_sure")
    tmp_db.executescript(rollback)
    assert (status(table_only), status(with_alt)) == ("mostly_sure", "mostly_sure")
