"""A person's review of an occurrence: scoped to one page of one report."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from support.rich_scan import seed_rich_scan
from test_audit_report import _scan_with_real_findings  # tests/unit on sys.path

from audit import evaluation
from audit.occurrence_reviews import (
    MAX_NOTES_LENGTH,
    MAX_OCCURRENCES_PER_SAVE,
    ReviewError,
    ReviewScopeError,
    reviews_for_page,
    save_review,
)

MIGRATIONS = Path(__file__).parents[2] / "src/audit/db/migrations"


def _finding(conn: sqlite3.Connection, scan_id: int, rule_id: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT id, page_id FROM page_a11y_findings WHERE scan_id = ? AND rule_id = ? "
        "ORDER BY id LIMIT 1",
        (scan_id, rule_id),
    ).fetchone()
    return int(row[0]), int(row[1])


def _count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM occurrence_reviews").fetchone()[0])


def test_saves_and_updates_one_review_per_occurrence(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    finding_id, page_id = _finding(tmp_db, scan_id, "color-contrast")
    common: dict[str, Any] = {
        "scan_id": scan_id,
        "page_id": page_id,
        "a11y_finding_ids": [finding_id],
        "page_image_ids": [],
    }

    first = save_review(
        tmp_db, decision="report", notes="  Muted grey text fails contrast.  ", **common
    )
    assert (first.decision, first.notes) == ("report", "Muted grey text fails contrast.")

    second = save_review(tmp_db, decision="repeat", notes="Same as the footer.", **common)
    assert (second.decision, second.notes) == ("repeat", "Same as the footer.")

    third = save_review(tmp_db, decision=None, notes="", **common)
    assert (third.decision, third.notes) == (None, "")
    assert _count(tmp_db) == 1  # updated in place, not added again

    by_finding, by_image = reviews_for_page(tmp_db, scan_id=scan_id, page_id=page_id)
    assert by_finding[finding_id]["decision"] is None
    assert by_image == {}


def test_page_evidence_carries_each_occurrences_review(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    finding_id, page_id = _finding(tmp_db, scan_id, "color-contrast")
    save_review(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        a11y_finding_ids=[finding_id],
        page_image_ids=[],
        decision="report",
        notes="Checked.",
    )

    evidence = evaluation.get_page_evidence(tmp_db, scan_id=scan_id, page_id=page_id)
    assert evidence is not None
    reviews = {f["id"]: f["review"] for f in evidence["a11y_findings"]}
    assert reviews[finding_id] == {
        "decision": "report",
        "notes": "Checked.",
        "updated_at": reviews[finding_id]["updated_at"],
    }
    assert all(review is None for fid, review in reviews.items() if fid != finding_id)


def test_page_evidence_survives_an_unreadable_review_table(tmp_db: sqlite3.Connection) -> None:
    """Reviews are extra: an out-of-date table must not take the inspector down.

    A database with 0032 applied but not 0033 has ``confirmed`` where the
    code reads ``decision``. The page's evidence still loads, with no reviews.
    """
    scan_id = seed_rich_scan(tmp_db)
    _, page_id = _finding(tmp_db, scan_id, "color-contrast")
    rollback = (MIGRATIONS / "0033_review_decision.rollback.sql").read_text()
    tmp_db.executescript(rollback)

    evidence = evaluation.get_page_evidence(tmp_db, scan_id=scan_id, page_id=page_id)
    assert evidence is not None
    assert evidence["a11y_findings"]
    assert all(f["review"] is None for f in evidence["a11y_findings"])

    tmp_db.execute("DROP TABLE occurrence_reviews")
    evidence = evaluation.get_page_evidence(tmp_db, scan_id=scan_id, page_id=page_id)
    assert evidence is not None and evidence["a11y_findings"]


def test_0033_turns_confirmed_into_a_decision(tmp_db: sqlite3.Connection) -> None:
    """Reviews saved under 0032 keep their notes; confirmed becomes "report"."""
    scan_id = seed_rich_scan(tmp_db)
    rows = tmp_db.execute(
        "SELECT id, page_id FROM page_a11y_findings WHERE scan_id = ? ORDER BY id LIMIT 2",
        (scan_id,),
    ).fetchall()
    tmp_db.executescript((MIGRATIONS / "0033_review_decision.rollback.sql").read_text())
    for (finding_id, page_id), confirmed in zip(rows, (1, 0), strict=True):
        tmp_db.execute(
            "INSERT INTO occurrence_reviews (scan_id, page_id, a11y_finding_id, confirmed, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (scan_id, page_id, finding_id, confirmed, f"note {confirmed}"),
        )

    tmp_db.executescript((MIGRATIONS / "0033_review_decision.sql").read_text())

    converted = tmp_db.execute(
        "SELECT a11y_finding_id, decision, notes FROM occurrence_reviews ORDER BY id"
    ).fetchall()
    assert [tuple(row) for row in converted] == [
        (rows[0][0], "report", "note 1"),
        (rows[1][0], None, "note 0"),
    ]
    assert tmp_db.execute("PRAGMA foreign_key_check(occurrence_reviews)").fetchall() == []
    # The same keys still hold after the rebuild: one review per occurrence.
    with pytest.raises(sqlite3.IntegrityError):
        tmp_db.execute(
            "INSERT INTO occurrence_reviews (scan_id, page_id, a11y_finding_id) VALUES (?, ?, ?)",
            (scan_id, rows[0][1], rows[0][0]),
        )


def test_reviews_image_occurrences(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan_with_real_findings(tmp_db)
    row = tmp_db.execute(
        "SELECT pi.id, pi.page_id FROM page_images pi JOIN pages p ON p.id = pi.page_id "
        "WHERE p.scan_id = ? ORDER BY pi.id LIMIT 1",
        (scan_id,),
    ).fetchone()
    image_id, page_id = int(row[0]), int(row[1])

    save_review(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        a11y_finding_ids=[],
        page_image_ids=[image_id],
        decision="repeat",
        notes="Same banner as the home page.",
    )

    evidence = evaluation.get_page_evidence(tmp_db, scan_id=scan_id, page_id=page_id)
    assert evidence is not None
    images = [i for i in evidence["image_occurrences"] if i["occurrence_id"] == image_id]
    assert images and images[0]["review"]["decision"] == "repeat"


def test_never_writes_outside_this_page_of_this_report(tmp_db: sqlite3.Connection) -> None:
    scan_a = seed_rich_scan(tmp_db)
    scan_b = seed_rich_scan(tmp_db)
    finding_a, page_a = _finding(tmp_db, scan_a, "color-contrast")
    finding_b, page_b = _finding(tmp_db, scan_b, "color-contrast")
    other_page = tmp_db.execute(
        "SELECT id FROM pages WHERE scan_id = ? AND id != ? LIMIT 1", (scan_a, page_a)
    ).fetchone()[0]

    cases: list[dict[str, Any]] = [
        # Scan B's finding named under scan A.
        {"scan_id": scan_a, "page_id": page_a, "a11y_finding_ids": [finding_a, finding_b]},
        # Scan B's page under scan A.
        {"scan_id": scan_a, "page_id": page_b, "a11y_finding_ids": [finding_b]},
        # The right report, the wrong page.
        {"scan_id": scan_a, "page_id": other_page, "a11y_finding_ids": [finding_a]},
    ]
    for case in cases:
        with pytest.raises(ReviewScopeError):
            save_review(tmp_db, page_image_ids=[], decision="report", notes="x", **case)
    # All or nothing: the in-scope occurrence of the first case was not saved.
    assert _count(tmp_db) == 0


def test_notes_and_requests_are_bounded_and_redacted(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    finding_id, page_id = _finding(tmp_db, scan_id, "color-contrast")
    common: dict[str, Any] = {
        "scan_id": scan_id,
        "page_id": page_id,
        "a11y_finding_ids": [finding_id],
        "page_image_ids": [],
    }

    with pytest.raises(ReviewError):
        save_review(tmp_db, decision="report", notes="x" * (MAX_NOTES_LENGTH + 1), **common)
    with pytest.raises(ReviewError):
        save_review(tmp_db, decision="maybe", notes="", **common)  # type: ignore[arg-type]
    with pytest.raises(ReviewError):
        save_review(
            tmp_db,
            scan_id=scan_id,
            page_id=page_id,
            a11y_finding_ids=list(range(1, MAX_OCCURRENCES_PER_SAVE + 2)),
            page_image_ids=[],
            decision="report",
            notes="",
        )
    with pytest.raises(ReviewError):
        save_review(
            tmp_db,
            scan_id=scan_id,
            page_id=page_id,
            a11y_finding_ids=[],
            page_image_ids=[],
            decision="report",
            notes="",
        )

    saved = save_review(
        tmp_db,
        decision="report",
        notes="Signed in with Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789",
        **common,
    )
    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in saved.notes
    stored = tmp_db.execute("SELECT notes FROM occurrence_reviews").fetchone()[0]
    assert stored == saved.notes


def test_deleting_a_report_deletes_its_reviews(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    finding_id, page_id = _finding(tmp_db, scan_id, "color-contrast")
    save_review(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        a11y_finding_ids=[finding_id],
        page_image_ids=[],
        decision="report",
        notes="",
    )
    # As the delete route does: this column has no ON DELETE action.
    tmp_db.execute(
        "UPDATE images SET first_seen_scan_id = NULL WHERE first_seen_scan_id = ?", (scan_id,)
    )
    tmp_db.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    assert _count(tmp_db) == 0
