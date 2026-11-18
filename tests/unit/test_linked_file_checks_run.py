"""Which checks ran on a file (migration 0045): stored, shared by copies, and
read back, with a file checked before 0045 reading as the first five."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from audit.db import linked_files as store
from audit.linked_files.pdf_check import BASE_CHECKS, check_pdf
from audit.web.linked_files_queries import list_scan_documents

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0045_linked_file_checks_run.sql"
FILES = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "documents" / "files"


def _file(conn: sqlite3.Connection, url: str = "https://a.test/x.pdf") -> tuple[int, int]:
    scan = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('https://a.test/', 'completed', '{}')"
    ).lastrowid
    file_id = store.upsert_file(
        conn, scan_id=int(scan or 0), url=url, file_type="pdf", found_by="extension", off_site=False
    )
    assert file_id is not None
    return int(scan or 0), file_id


def test_the_seeded_files_run_the_checks_that_apply() -> None:
    clean = check_pdf((FILES / "clean.pdf").read_bytes())
    assert set(clean.checks_run) == set(BASE_CHECKS) | {"untagged_text"}
    form = check_pdf((FILES / "form.pdf").read_bytes())
    assert set(form.checks_run) == set(BASE_CHECKS) | {"untagged_text", "field_no_name"}
    untagged = check_pdf((FILES / "untagged.pdf").read_bytes())
    assert set(untagged.checks_run) == set(BASE_CHECKS)


def test_checks_run_is_stored_and_read_back(tmp_db: sqlite3.Connection) -> None:
    scan, file_id = _file(tmp_db)
    store.set_result(
        tmp_db,
        scan_id=scan,
        file_id=file_id,
        result=store.CheckResult(
            status="mostly_sure",
            failed_checks=("field_no_name",),
            checks_run=(*BASE_CHECKS, "field_no_name"),
            sha256="a" * 64,
        ),
    )
    row = list_scan_documents(tmp_db, scan).files[0]
    assert row.failed_checks == ["field_no_name"]
    assert set(row.checks_run) == {*BASE_CHECKS, "field_no_name"}


def test_a_copy_shares_the_checks_run(tmp_db: sqlite3.Connection) -> None:
    scan, file_id = _file(tmp_db)
    store.set_result(
        tmp_db,
        scan_id=scan,
        file_id=file_id,
        result=store.CheckResult(status="not_sure", checks_run=("not_tagged",), sha256="b" * 64),
    )
    other = store.upsert_file(
        tmp_db,
        scan_id=scan,
        url="https://a.test/copy.pdf",
        file_type="pdf",
        found_by="extension",
        off_site=False,
    )
    assert other is not None
    copy = store.checked_copy(tmp_db, scan_id=scan, sha256="b" * 64, file_id=other)
    assert copy is not None
    assert tuple(copy.checks_run or ()) == ("not_tagged",)


def test_a_file_checked_before_0045_ran_the_first_five(tmp_db: sqlite3.Connection) -> None:
    scan, file_id = _file(tmp_db)
    # As a report made before 0045 stored it: no checks_run.
    tmp_db.execute(
        "UPDATE linked_files SET status = 'not_sure', checks_run = NULL WHERE id = ?", (file_id,)
    )
    row = list_scan_documents(tmp_db, scan).files[0]
    assert row.checks_run == list(BASE_CHECKS)


def test_a_file_not_checked_ran_nothing(tmp_db: sqlite3.Connection) -> None:
    scan, _ = _file(tmp_db)
    row = list_scan_documents(tmp_db, scan).files[0]
    assert row.checks_run == []


def test_rollback_drops_the_column(tmp_db: sqlite3.Connection) -> None:
    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    columns = {row[1] for row in tmp_db.execute("PRAGMA table_info(linked_files)")}
    assert "checks_run" not in columns
    tmp_db.executescript(MIGRATION.read_text())
    columns = {row[1] for row in tmp_db.execute("PRAGMA table_info(linked_files)")}
    assert "checks_run" in columns
