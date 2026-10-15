"""A person's review of an occurrence: their decision, and issue notes.

The auditor reviews in the page inspector, one circled element at a time,
and chooses one of three: not checked yet (no decision), checked and put
in the report (``"report"``), or checked and a repeat of one already
reported (``"repeat"``), which stays out of the report. Which elements are
repeats is the person's call; Axcess does not decide it.

One element can carry several occurrences of the issue under review (two
rules on one element, or an image placed twice), so a save names every
occurrence on that element and each gets the same review.

Every write is scoped to one report and one page: each occurrence must
belong to that page of that scan, or nothing is written. Notes are trimmed,
bounded, and redacted (email addresses, phone numbers, sign-in tokens and
headers) before they are stored, the same rule as status reasons, because
they are written to be handed to a vendor.

Protected reports are refused by the route. Their ordinary tables hold only
opaque aliases by design, and notes about their pages would be the
plaintext evidence that design keeps out.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal, get_args

from audit.logging import get_logger
from audit.protected.redaction import redact_text

log = get_logger(__name__)

#: What a person decided about an occurrence; None means not checked yet.
Decision = Literal["report", "repeat"]
DECISIONS: tuple[str, ...] = get_args(Decision)

MAX_NOTES_LENGTH = 2000
#: Occurrences one save may name. One element rarely carries more than a
#: few; the bound keeps a request from touching a whole page.
MAX_OCCURRENCES_PER_SAVE = 50


class ReviewError(ValueError):
    """The review cannot be saved as asked."""


class ReviewScopeError(ReviewError):
    """An occurrence is not part of this page of this report."""


@dataclass(frozen=True)
class OccurrenceReview:
    decision: Decision | None
    notes: str
    updated_at: str


@contextmanager
def _write(conn: sqlite3.Connection) -> Iterator[None]:
    """One atomic write, joining a transaction that is already open."""
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def normalize_notes(notes: str) -> str:
    """Trim, bound, and redact issue notes."""
    trimmed = notes.strip()
    if len(trimmed) > MAX_NOTES_LENGTH:
        raise ReviewError(f"Issue notes must be at most {MAX_NOTES_LENGTH:,} characters.")
    safe = redact_text(trimmed) if trimmed else ""
    return safe[:MAX_NOTES_LENGTH].rstrip()


def _check_scope(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page_id: int,
    a11y_finding_ids: list[int],
    page_image_ids: list[int],
) -> None:
    page = conn.execute(
        "SELECT 1 FROM pages WHERE id = ? AND scan_id = ?", (page_id, scan_id)
    ).fetchone()
    if page is None:
        raise ReviewScopeError("This page is not part of this report.")
    if a11y_finding_ids:
        marks = ",".join("?" for _ in a11y_finding_ids)
        found = conn.execute(
            f"SELECT COUNT(*) FROM page_a11y_findings "  # noqa: S608, placeholders only
            f"WHERE scan_id = ? AND page_id = ? AND id IN ({marks})",
            (scan_id, page_id, *a11y_finding_ids),
        ).fetchone()[0]
        if found != len(a11y_finding_ids):
            raise ReviewScopeError("An occurrence is not on this page of this report.")
    if page_image_ids:
        marks = ",".join("?" for _ in page_image_ids)
        found = conn.execute(
            f"SELECT COUNT(*) FROM page_images "  # noqa: S608, placeholders only
            f"WHERE page_id = ? AND id IN ({marks})",
            (page_id, *page_image_ids),
        ).fetchone()[0]
        if found != len(page_image_ids):
            raise ReviewScopeError("An image is not on this page of this report.")


def save_review(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page_id: int,
    a11y_finding_ids: list[int],
    page_image_ids: list[int],
    decision: Decision | None,
    notes: str,
) -> OccurrenceReview:
    """Give every named occurrence this review, all or nothing."""
    a11y_ids = sorted(set(a11y_finding_ids))
    image_ids = sorted(set(page_image_ids))
    if not a11y_ids and not image_ids:
        raise ReviewError("Name at least one occurrence to review.")
    if len(a11y_ids) + len(image_ids) > MAX_OCCURRENCES_PER_SAVE:
        raise ReviewError(f"One save can cover at most {MAX_OCCURRENCES_PER_SAVE} occurrences.")
    if decision is not None and decision not in DECISIONS:
        raise ReviewError("Unknown decision.")
    safe_notes = normalize_notes(notes)

    with _write(conn):
        _check_scope(
            conn,
            scan_id=scan_id,
            page_id=page_id,
            a11y_finding_ids=a11y_ids,
            page_image_ids=image_ids,
        )
        for finding_id in a11y_ids:
            conn.execute(
                """
                INSERT INTO occurrence_reviews
                    (scan_id, page_id, a11y_finding_id, decision, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (a11y_finding_id) WHERE a11y_finding_id IS NOT NULL
                DO UPDATE SET decision = excluded.decision, notes = excluded.notes,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (scan_id, page_id, finding_id, decision, safe_notes),
            )
        for image_id in image_ids:
            conn.execute(
                """
                INSERT INTO occurrence_reviews
                    (scan_id, page_id, page_image_id, decision, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (page_image_id) WHERE page_image_id IS NOT NULL
                DO UPDATE SET decision = excluded.decision, notes = excluded.notes,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (scan_id, page_id, image_id, decision, safe_notes),
            )
        # Every named occurrence now holds the same review; read one back for
        # the time it was saved.
        column, first = (
            ("a11y_finding_id", a11y_ids[0]) if a11y_ids else ("page_image_id", image_ids[0])
        )
        row = conn.execute(
            f"SELECT updated_at FROM occurrence_reviews WHERE {column} = ?",  # noqa: S608
            (first,),
        ).fetchone()
    return OccurrenceReview(decision=decision, notes=safe_notes, updated_at=str(row[0]))


def reviews_for_page(
    conn: sqlite3.Connection, *, scan_id: int, page_id: int
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """This page's reviews, keyed by rule-check finding id and by page image id.

    Reviews are extra to the page's evidence, so a database whose review
    table is missing or out of date (migrations not yet applied) answers
    with none rather than failing: the inspector must still show the page
    and outline its elements.
    """
    by_finding: dict[int, dict[str, Any]] = {}
    by_image: dict[int, dict[str, Any]] = {}
    try:
        rows = conn.execute(
            "SELECT a11y_finding_id, page_image_id, decision, notes, updated_at "
            "FROM occurrence_reviews WHERE scan_id = ? AND page_id = ?",
            (scan_id, page_id),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        log.warning("occurrence_reviews.unreadable", error=str(exc))
        return by_finding, by_image
    for row in rows:
        review = {"decision": row[2], "notes": str(row[3]), "updated_at": str(row[4])}
        if row[0] is not None:
            by_finding[int(row[0])] = review
        else:
            by_image[int(row[1])] = review
    return by_finding, by_image
