"""Writes for linked files (migration 0039).

Every write is idempotent on the row's natural key, as in :mod:`audit.db.repo`,
so a resumed crawl that sees a page again adds nothing twice. Every write
also states its scan: a reference from one scan's page to another scan's file
is refused, so one report can never show another's evidence.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from audit.linked_files.formats import (
    FailedCheck,
    FileType,
    FoundBy,
    Reason,
    RefKind,
    Status,
    initial_status,
)

#: Files recorded per scan. A site with more is not unusual (a document
#: library), but the report's list and the checks need a bound.
MAX_FILES_PER_SCAN = 2000
#: References kept per file. A file in a site-wide footer is linked from
#: every page; the count stops being useful long before this.
MAX_REFS_PER_FILE = 500
#: Characters kept of a link's text or a control's name.
MAX_TEXT = 300


@dataclass(frozen=True)
class CheckResult:
    """What one attempt to check a file found."""

    status: Status
    reason: Reason | None = None
    failed_checks: Sequence[FailedCheck] = ()
    http_status: int | None = None
    content_type: str | None = None
    byte_size: int | None = None
    sha256: str | None = None
    is_form: bool | None = None
    page_count: int | None = None


def file_count(conn: sqlite3.Connection, scan_id: int) -> int:
    return int(
        conn.execute("SELECT COUNT(*) FROM linked_files WHERE scan_id = ?", (scan_id,)).fetchone()[
            0
        ]
    )


def upsert_file(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    url: str,
    file_type: FileType,
    found_by: FoundBy,
    off_site: bool,
) -> int | None:
    """The file's id, recording it first if this scan has not seen it.

    A file seen again keeps its first type and status: the first answer is
    the one the checks ran on. Returns None when the scan already holds
    ``MAX_FILES_PER_SCAN`` files and this one is new.
    """
    row = conn.execute(
        "SELECT id FROM linked_files WHERE scan_id = ? AND url = ?", (scan_id, url)
    ).fetchone()
    if row is not None:
        return int(row[0])
    if file_count(conn, scan_id) >= MAX_FILES_PER_SCAN:
        return None
    status, reason = initial_status(file_type)
    cur = conn.execute(
        "INSERT INTO linked_files (scan_id, url, file_type, found_by, off_site, status, reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (scan_id, url, file_type, found_by, int(off_site), status, reason),
    )
    return int(cur.lastrowid or 0)


def add_ref(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    file_id: int,
    page_id: int,
    how: RefKind,
    link_text: str,
    revealed_by: str | None = None,
) -> bool:
    """Record one place a page reaches a file. True when a row was added."""
    owner = conn.execute(
        "SELECT (SELECT scan_id FROM linked_files WHERE id = ?), "
        "(SELECT scan_id FROM pages WHERE id = ?)",
        (file_id, page_id),
    ).fetchone()
    if owner is None or owner[0] != scan_id or owner[1] != scan_id:
        raise ValueError("Linked file and page must belong to the same scan")
    cur = conn.execute(
        "INSERT OR IGNORE INTO linked_file_refs "
        "(file_id, scan_id, page_id, how, link_text, revealed_by) "
        "SELECT ?, ?, ?, ?, ?, ? "
        "WHERE (SELECT COUNT(*) FROM linked_file_refs WHERE file_id = ?) < ?",
        (
            file_id,
            scan_id,
            page_id,
            how,
            link_text[:MAX_TEXT],
            revealed_by[:MAX_TEXT] if revealed_by else None,
            file_id,
            MAX_REFS_PER_FILE,
        ),
    )
    return cur.rowcount > 0


def set_result(
    conn: sqlite3.Connection, *, scan_id: int, file_id: int, result: CheckResult
) -> None:
    """Store what checking a file found. The file must belong to ``scan_id``."""
    if result.status == "could_not_check" and result.reason is None:
        raise ValueError("A file that could not be checked needs a reason")
    cur = conn.execute(
        "UPDATE linked_files SET status = ?, reason = ?, failed_checks = ?, "
        "http_status = ?, content_type = ?, byte_size = ?, sha256 = ?, is_form = ?, "
        "page_count = ?, checked_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND scan_id = ?",
        (
            result.status,
            result.reason if result.status == "could_not_check" else None,
            json.dumps(list(result.failed_checks)),
            result.http_status,
            (result.content_type or "")[:200] or None,
            result.byte_size,
            result.sha256,
            None if result.is_form is None else int(result.is_form),
            result.page_count,
            file_id,
            scan_id,
        ),
    )
    if cur.rowcount != 1:
        raise ValueError("Linked file is not part of this scan")


def file_status(conn: sqlite3.Connection, *, scan_id: int, file_id: int) -> str | None:
    row = conn.execute(
        "SELECT status FROM linked_files WHERE id = ? AND scan_id = ?", (file_id, scan_id)
    ).fetchone()
    return None if row is None else str(row[0])


def pending_files(conn: sqlite3.Connection, scan_id: int) -> list[tuple[int, str]]:
    """``(id, url)`` of every file still waiting to be checked, oldest first."""
    return [
        (int(row[0]), str(row[1]))
        for row in conn.execute(
            "SELECT id, url FROM linked_files WHERE scan_id = ? AND status = 'pending' ORDER BY id",
            (scan_id,),
        )
    ]


def content_type_files(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    """Files found by their server's Content-Type: ``url -> id``.

    A resumed crawl reloads these, so a page fetched after the restart still
    records its link to a file whose address alone does not say it is one.
    """
    return {
        str(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT url, id FROM linked_files WHERE scan_id = ? AND found_by = 'content_type'",
            (scan_id,),
        )
    }


def mark_unchecked(conn: sqlite3.Connection, scan_id: int) -> int:
    """Close every file still pending as "not checked". Returns how many."""
    cur = conn.execute(
        "UPDATE linked_files SET status = 'could_not_check', reason = 'not_checked' "
        "WHERE scan_id = ? AND status = 'pending'",
        (scan_id,),
    )
    return cur.rowcount
