"""Storage rules for the frames saved with a page (``page_frames``, migration 0031).

The rows are the documents of a page's frames, placed by parent and position.
They are only right while they describe the same fetch as the saved copy, and
only safe while one report can never read another's, so replacement, the scan
checks and what the inspector is sent are what is tested here.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path

import pytest

from audit.crawler.frame_snapshot import SavedFrame
from audit.db import repo
from audit.web import page_inspector

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0031_saved_frames"


def _scan(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES ('https://x.test/', 'completed', 1, 0, '{}')"
    )
    return int(cur.lastrowid or 0)


def _page(conn: sqlite3.Connection, scan_id: int, url: str = "https://x.test/") -> int:
    return repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized=url,
        status_code=200,
        title="Page",
        render_mode="js",
        html_hash="0" * 64,
    )


def _frame(frame_id: int, parent_id: int = 0, index: int = 0, text: str = "x") -> SavedFrame:
    return SavedFrame(
        frame_id=frame_id,
        parent_id=parent_id,
        index=index,
        url=f"https://embed.test/{frame_id}",
        html=gzip.compress(f"<p>{text}</p>".encode(), mtime=0),
    )


def test_frames_round_trip_in_order(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    frames = [_frame(1, index=0), _frame(2, parent_id=1, index=0), _frame(3, index=1)]

    assert repo.replace_page_frames(tmp_db, scan_id=scan_id, page_id=page_id, frames=frames) == 3

    assert repo.page_frames(tmp_db, scan_id=scan_id, page_id=page_id) == frames


def test_a_refetch_replaces_rather_than_merges(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.replace_page_frames(
        tmp_db, scan_id=scan_id, page_id=page_id, frames=[_frame(1), _frame(2, index=1)]
    )

    repo.replace_page_frames(
        tmp_db, scan_id=scan_id, page_id=page_id, frames=[_frame(1, text="new")]
    )
    assert repo.page_frames(tmp_db, scan_id=scan_id, page_id=page_id) == [_frame(1, text="new")]

    repo.replace_page_frames(tmp_db, scan_id=scan_id, page_id=page_id, frames=[])
    assert repo.page_frames(tmp_db, scan_id=scan_id, page_id=page_id) == []


def test_one_scan_cannot_write_or_read_another_scans_frames(tmp_db: sqlite3.Connection) -> None:
    scan_a = _scan(tmp_db)
    scan_b = _scan(tmp_db)
    page_a = _page(tmp_db, scan_a)
    page_b = _page(tmp_db, scan_b)
    repo.replace_page_frames(tmp_db, scan_id=scan_a, page_id=page_a, frames=[_frame(1)])

    with pytest.raises(ValueError, match="does not belong"):
        repo.replace_page_frames(tmp_db, scan_id=scan_b, page_id=page_a, frames=[_frame(1)])

    assert repo.page_frames(tmp_db, scan_id=scan_b, page_id=page_a) == []
    assert repo.page_frames(tmp_db, scan_id=scan_b, page_id=page_b) == []
    assert page_inspector._saved_frames(tmp_db, scan_b, page_a) == []
    assert len(repo.page_frames(tmp_db, scan_id=scan_a, page_id=page_a)) == 1


def test_deleting_a_scan_deletes_its_rows(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    keep = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    kept_page = _page(tmp_db, keep)
    repo.replace_page_frames(tmp_db, scan_id=scan_id, page_id=page_id, frames=[_frame(1)])
    repo.replace_page_frames(tmp_db, scan_id=keep, page_id=kept_page, frames=[_frame(1)])

    with tmp_db:
        tmp_db.execute("DELETE FROM scans WHERE id = ?", (scan_id,))

    rows = tmp_db.execute("SELECT scan_id FROM page_frames").fetchall()
    assert [row["scan_id"] for row in rows] == [keep]


def test_the_inspector_gets_decoded_frames_and_drops_orphans(tmp_db: sqlite3.Connection) -> None:
    """A frame that will not decode is left out, and so is every frame inside
    it: it would have nowhere to go in the saved copy."""
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    broken = SavedFrame(frame_id=2, parent_id=0, index=1, url="", html=b"not gzip")
    frames = [_frame(1, text="kept"), broken, _frame(3, parent_id=2), _frame(4, parent_id=3)]
    repo.replace_page_frames(tmp_db, scan_id=scan_id, page_id=page_id, frames=frames)

    sent = page_inspector._saved_frames(tmp_db, scan_id, page_id)

    assert sent == [
        {
            "frame_id": 1,
            "parent_id": 0,
            "index": 0,
            "url": "https://embed.test/1",
            "html": "<p>kept</p>",
        }
    ]


def test_the_inspector_response_is_bounded(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.replace_page_frames(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        frames=[_frame(n, index=n - 1, text="y" * 10) for n in (1, 2, 3)],
    )
    # Each document is "<p>" + 10 characters + "</p>", 17 characters.
    monkeypatch.setattr(page_inspector, "MAX_INSPECT_FRAME_CHARS", 40)

    sent = page_inspector._saved_frames(tmp_db, scan_id, page_id)

    assert [frame["frame_id"] for frame in sent] == [1, 2]


def test_migration_rolls_back_and_forward_cleanly(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.replace_page_frames(tmp_db, scan_id=scan_id, page_id=page_id, frames=[_frame(1)])

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    tables = {r[0] for r in tmp_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "page_frames" not in tables
    indexes = {r[0] for r in tmp_db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_page_frames_scan" not in indexes
    # The inspector reads a database without the table as one with no frames.
    assert page_inspector._saved_frames(tmp_db, scan_id, page_id) == []

    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())
    assert tmp_db.execute("SELECT COUNT(*) FROM page_frames").fetchone()[0] == 0
    repo.replace_page_frames(tmp_db, scan_id=scan_id, page_id=page_id, frames=[_frame(1)])
    assert len(repo.page_frames(tmp_db, scan_id=scan_id, page_id=page_id)) == 1
