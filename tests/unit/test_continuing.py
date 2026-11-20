"""Which reports Continue scan may carry on, and what it checks again.

audit.web.continuing: a report is "not finished" when Axcess closed
mid-scan and its queue still holds the addresses it had to visit; a report a
person stopped has an empty queue and is over. Continuing also puts back
the files an older build closed only because it could not check them yet:
report #71 (2026-11-17) listed 53 Google Docs as "could not check" that
today's build downloads, and continuing it left them so.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from audit.crawler.orchestrator import CrawlConfig, config_json_for_scan
from audit.db import linked_files as store
from audit.db import queue
from audit.web import continuing

SEED = "https://continue.example.test/"


def _scan(conn: sqlite3.Connection, status: str, *, config_json: str = "{}") -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, config_json) VALUES (?, ?, 3, ?)",
        (SEED, status, config_json),
    )
    return int(cur.lastrowid or 0)


def _waiting(conn: sqlite3.Connection, scan_id: int) -> None:
    queue.enqueue(
        conn,
        "fetch",
        {"scan_id": scan_id, "url": f"{SEED}later", "depth": 1},
        dedupe_key=f"{scan_id}:later",
    )


def test_a_scan_cut_off_with_pages_waiting_can_be_continued(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db, "interrupted")
    _waiting(tmp_db, scan_id)
    assert continuing.can_continue(tmp_db, scan_id)
    assert continuing.continuable_ids(tmp_db) == {scan_id}


def test_a_scan_a_person_stopped_cannot(tmp_db: sqlite3.Connection) -> None:
    """Stop empties the queue: the same status, nothing waiting."""
    scan_id = _scan(tmp_db, "interrupted")
    assert not continuing.can_continue(tmp_db, scan_id)
    assert continuing.continuable_ids(tmp_db) == set()


@pytest.mark.parametrize("status", ["completed", "failed", "running"])
def test_only_an_interrupted_scan_can_be_continued(tmp_db: sqlite3.Connection, status: str) -> None:
    scan_id = _scan(tmp_db, status)
    _waiting(tmp_db, scan_id)
    assert not continuing.can_continue(tmp_db, scan_id)


def test_a_sign_in_scan_cannot_be_continued(tmp_db: sqlite3.Connection) -> None:
    """Its signed-in browser died with the process."""
    config = config_json_for_scan(CrawlConfig(seed_url=SEED, resumable=False))
    scan_id = _scan(tmp_db, "interrupted", config_json=config)
    _waiting(tmp_db, scan_id)
    assert not continuing.can_continue(tmp_db, scan_id)


def test_another_scans_waiting_work_does_not_count(tmp_db: sqlite3.Connection) -> None:
    stopped = _scan(tmp_db, "interrupted")
    other = _scan(tmp_db, "interrupted")
    _waiting(tmp_db, other)
    assert not continuing.can_continue(tmp_db, stopped)
    assert continuing.continuable_ids(tmp_db) == {other}


def _file(
    conn: sqlite3.Connection, scan_id: int, url: str, file_type: str, reason: str | None
) -> int:
    cur = conn.execute(
        "INSERT INTO linked_files (scan_id, url, file_type, found_by, status, reason) "
        "VALUES (?, ?, ?, 'host', ?, ?)",
        (scan_id, url, file_type, "could_not_check" if reason else "not_sure", reason),
    )
    return int(cur.lastrowid or 0)


def test_continuing_puts_back_the_files_this_build_can_check(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db, "interrupted")
    doc = "https://docs.google.com/document/d/1ZgSJQ3EuyzIiNEN2C2xdgm_eAQ2sVBkGIBLPiWEBMkE/edit"
    reopened = {
        _file(tmp_db, scan_id, doc, "google_doc", "google_file"),
        _file(
            tmp_db,
            scan_id,
            "https://docs.google.com/presentation/d/1IMem7ZZ7guQCRpoS4X17k6ubg4mv1JDoYd37D93-l-8/edit",
            "google_slides",
            "google_file",
        ),
        _file(tmp_db, scan_id, f"{SEED}form.docx", "docx", "type_not_checked_yet"),
        _file(tmp_db, scan_id, f"{SEED}guide.pdf", "pdf", "not_checked"),
    }
    kept = {
        # A copy published to the web has no file to download.
        _file(
            tmp_db,
            scan_id,
            "https://docs.google.com/document/d/e/2PACX-1vQabcdefghij/pub",
            "google_doc",
            "google_file",
        ),
        # Google asks scanners not to download Sheets.
        _file(
            tmp_db,
            scan_id,
            "https://docs.google.com/spreadsheets/d/1abcdefghijklmnop/edit",
            "google_sheet",
            "google_file",
        ),
        _file(tmp_db, scan_id, f"{SEED}old.doc", "doc", "old_format"),
        _file(tmp_db, scan_id, f"{SEED}book.xlsx", "xlsx", "type_not_checked_yet"),
        _file(tmp_db, scan_id, f"{SEED}gone.pdf", "pdf", "http_error"),
        _file(tmp_db, scan_id, f"{SEED}done.pdf", "pdf", None),
    }

    assert store.reopen_for_continuing(tmp_db, scan_id) == len(reopened)

    rows = {
        int(row[0]): (row[1], row[2])
        for row in tmp_db.execute(
            "SELECT id, status, reason FROM linked_files WHERE scan_id = ?", (scan_id,)
        )
    }
    assert {file_id for file_id, (status, _) in rows.items() if status == "pending"} == reopened
    assert all(rows[file_id][0] != "pending" for file_id in kept)
    assert all(rows[file_id][1] is None for file_id in reopened)


def test_continuing_one_report_leaves_another_reports_files_alone(
    tmp_db: sqlite3.Connection,
) -> None:
    mine = _scan(tmp_db, "interrupted")
    other = _scan(tmp_db, "interrupted")
    theirs = _file(tmp_db, other, f"{SEED}guide.pdf", "pdf", "not_checked")
    assert store.reopen_for_continuing(tmp_db, mine) == 0
    status = tmp_db.execute("SELECT status FROM linked_files WHERE id = ?", (theirs,)).fetchone()
    assert status[0] == "could_not_check"


def test_continuing_sends_the_browser_name_the_report_started_with() -> None:
    """Including a typed one, which New scan never fills back in."""
    stored = json.dumps({"user_agent": "Agreed-Scanner/1.0", "user_agent_choice": "custom"})
    config = continuing.with_stored_user_agent(
        CrawlConfig(seed_url=SEED, user_agent="Axcess/1"), stored, server_user_agent="Axcess/1"
    )
    assert config.user_agent == "Agreed-Scanner/1.0"
    assert config.user_agent_choice == "custom"
    # robots.txt is still read for Axcess's own name.
    assert config.robots_user_agent == "Axcess/1"


def test_a_report_that_sent_axcess_own_name_keeps_it() -> None:
    config = continuing.with_stored_user_agent(
        CrawlConfig(seed_url=SEED, user_agent="Axcess/1"),
        json.dumps({"user_agent": "Axcess/1"}),
        server_user_agent="Axcess/1",
    )
    assert (config.user_agent, config.robots_user_agent, config.user_agent_choice) == (
        "Axcess/1",
        None,
        None,
    )
