"""A file's own creation and modified dates (migration 0050): stored, shared by
copies, read back for the Documents tab, and none for a file not read."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from audit.db import linked_files as store
from audit.web.linked_files_queries import list_scan_documents

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0050_linked_file_dates.sql"


def _file(conn: sqlite3.Connection, url: str = "https://a.test/x.docx") -> tuple[int, int]:
    scan = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://a.test/', 'completed', '{}')"
    ).lastrowid
    file_id = store.upsert_file(
        conn,
        scan_id=int(scan or 0),
        url=url,
        file_type="docx",
        found_by="extension",
        off_site=False,
    )
    assert file_id is not None
    return int(scan or 0), file_id


def test_the_dates_are_stored_and_read_back(tmp_db: sqlite3.Connection) -> None:
    scan, file_id = _file(tmp_db)
    store.set_result(
        tmp_db,
        scan_id=scan,
        file_id=file_id,
        result=store.CheckResult(
            status="not_sure",
            checked_as="docx",
            sha256="a" * 64,
            file_created_at="2018-07-17T09:30:00+00:00",
            file_modified_at="2025-05-23T16:17:00+00:00",
        ),
    )
    row = list_scan_documents(tmp_db, scan).files[0]
    assert (row.created_at, row.modified_at) == (
        "2018-07-17T09:30:00+00:00",
        "2025-05-23T16:17:00+00:00",
    )
    # The table's own created_at (when Axcess recorded the row) is untouched.
    recorded = tmp_db.execute("SELECT created_at FROM linked_files WHERE id = ?", (file_id,))
    assert recorded.fetchone()[0] != "2018-07-17T09:30:00+00:00"


def test_a_copy_shares_the_dates(tmp_db: sqlite3.Connection) -> None:
    scan, file_id = _file(tmp_db)
    store.set_result(
        tmp_db,
        scan_id=scan,
        file_id=file_id,
        result=store.CheckResult(
            status="not_sure", sha256="b" * 64, file_created_at="2010-11-17T08:00:00"
        ),
    )
    other = store.upsert_file(
        tmp_db,
        scan_id=scan,
        url="https://a.test/copy.docx",
        file_type="docx",
        found_by="extension",
        off_site=False,
    )
    assert other is not None
    copy = store.checked_copy(tmp_db, scan_id=scan, sha256="b" * 64, file_id=other)
    assert copy is not None
    assert copy.file_created_at == "2010-11-17T08:00:00"


def test_a_file_not_read_has_no_dates(tmp_db: sqlite3.Connection) -> None:
    scan, file_id = _file(tmp_db)
    store.set_result(
        tmp_db,
        scan_id=scan,
        file_id=file_id,
        result=store.CheckResult(status="could_not_check", reason="damaged"),
    )
    row = list_scan_documents(tmp_db, scan).files[0]
    assert (row.created_at, row.modified_at) == (None, None)


def test_rollback_drops_the_columns(tmp_db: sqlite3.Connection) -> None:
    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    columns = {row[1] for row in tmp_db.execute("PRAGMA table_info(linked_files)")}
    assert not {"file_created_at", "file_modified_at"} & columns
    assert "created_at" in columns
    tmp_db.executescript(MIGRATION.read_text())
    columns = {row[1] for row in tmp_db.execute("PRAGMA table_info(linked_files)")}
    assert {"file_created_at", "file_modified_at"} <= columns
