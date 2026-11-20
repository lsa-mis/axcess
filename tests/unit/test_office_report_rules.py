"""How the Documents report shows Word and PowerPoint results (2026-11-18).

A Google Doc or Slides deck is checked as the file Google exports, which
never carries a document title the author could set, so "No document title"
is left out for Google files. Migration 0046 re-decides "Mostly sure" for
files checked before "Table without a header row" became a possible problem,
and 0049 for files checked before the two tiers of 2026-11-20 (tables and
headings possible problems).
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


def test_migrations_0046_then_0047_leave_table_barriers_mostly_sure(
    tmp_db: sqlite3.Connection,
) -> None:
    """0046 made a table without a header row a possible problem; 0047 counts
    it again (2026-11-19). A database that ran both ends where it started."""
    scan_id = _scan(tmp_db)
    table_only = _file(
        tmp_db, scan_id, "https://site.test/a.docx", "docx", ["table_no_header", "no_title"]
    )
    title_only = _file(tmp_db, scan_id, "https://site.test/b.docx", "docx", ["no_title"])

    def status(file_id: int) -> str:
        row = tmp_db.execute("SELECT status FROM linked_files WHERE id = ?", (file_id,)).fetchone()
        return str(row[0])

    for name in ("0046_office_table_header_possible", "0047_office_table_header_counts_again"):
        tmp_db.executescript((MIGRATIONS / f"{name}.sql").read_text())
    assert (status(table_only), status(title_only)) == ("mostly_sure", "not_sure")
    tmp_db.executescript(
        (MIGRATIONS / "0047_office_table_header_counts_again.rollback.sql").read_text()
    )
    assert status(table_only) == "not_sure"


def test_migration_0049_leaves_only_counted_checks_mostly_sure(
    tmp_db: sqlite3.Connection,
) -> None:
    """0049 (2026-11-20): only images without alt text, no language and
    slides without a title make a Word or PowerPoint file "Mostly sure";
    a table without a header row or no headings alone is a possible
    problem. The rollback puts them back as 0047 had them."""
    scan_id = _scan(tmp_db)
    table_only = _file(
        tmp_db, scan_id, "https://site.test/a.docx", "docx", ["table_no_header", "no_title"]
    )
    headings_only = _file(tmp_db, scan_id, "https://site.test/b.docx", "docx", ["no_headings"])
    tmp_db.execute("UPDATE linked_files SET status = 'mostly_sure' WHERE id = ?", (headings_only,))
    image = _file(
        tmp_db, scan_id, "https://site.test/c.docx", "docx", ["no_alt_text", "no_headings"]
    )

    def status(file_id: int) -> str:
        row = tmp_db.execute("SELECT status FROM linked_files WHERE id = ?", (file_id,)).fetchone()
        return str(row[0])

    tmp_db.executescript((MIGRATIONS / "0049_office_two_tiers.sql").read_text())
    assert [status(i) for i in (table_only, headings_only, image)] == [
        "not_sure",
        "not_sure",
        "mostly_sure",
    ]
    tmp_db.executescript((MIGRATIONS / "0049_office_two_tiers.rollback.sql").read_text())
    assert [status(i) for i in (table_only, headings_only, image)] == ["mostly_sure"] * 3


def test_the_report_lists_tables_and_headings_as_possible_problems(
    tmp_db: sqlite3.Connection,
) -> None:
    """The Documents list splits a Word file's failed checks by
    office_check.COUNTED: images without alt text count; a table without
    a header row and no headings are possible problems (2026-11-20)."""
    scan_id = _scan(tmp_db)
    _file(
        tmp_db,
        scan_id,
        "https://site.test/a.docx",
        "docx",
        ["no_alt_text", "table_no_header", "no_headings", "no_title"],
    )
    (row,) = q.list_scan_documents(tmp_db, scan_id, limit=50, offset=0).files
    assert row.failed_checks == ["no_alt_text"]
    assert row.possible_problems == ["table_no_header", "no_headings", "no_title"]
