"""Storage rules for a saved copy's CSS (``saved_copy_styles``, migration 0030).

The rows say which blobs style one saved copy. They are only right while they
describe the same fetch as the copy, and only safe while one report can never
read another's, so replacement and the scan checks are what is tested here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from audit.crawler.style_snapshot import SheetRef, StoredStyles
from audit.db import repo

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0030_saved_copy_styles"


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


def _styles(*hashes: str, complete: bool = True) -> StoredStyles:
    return StoredStyles(
        sheets=tuple(SheetRef(sha256=h, media="", source_url=None) for h in hashes),
        complete=complete,
        fingerprint={"scheme": "light", "samples": [{"index": 0, "color": "rgb(0, 0, 0)"}]},
    )


def test_page_and_state_styles_round_trip(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.set_page_styles(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        styles=StoredStyles(
            sheets=(
                SheetRef("a" * 64, "", "https://x.test/a.css"),
                SheetRef("b" * 64, "print", None),
            ),
            complete=False,
            fingerprint={"scheme": "light", "samples": []},
        ),
    )
    repo.replace_state_styles(
        tmp_db, scan_id=scan_id, page_id=page_id, styles={"menu": _styles("c" * 64)}
    )

    stored = repo.saved_copy_styles(tmp_db, scan_id=scan_id, page_id=page_id)
    assert set(stored) == {"", "menu"}
    assert [s.sha256 for s in stored[""].sheets] == ["a" * 64, "b" * 64]
    assert stored[""].sheets[1].media == "print"
    assert stored[""].sheets[0].source_url == "https://x.test/a.css"
    assert stored[""].complete is False
    assert stored["menu"].fingerprint["samples"][0]["color"] == "rgb(0, 0, 0)"


def test_a_refetch_replaces_rather_than_merges(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.set_page_styles(tmp_db, scan_id=scan_id, page_id=page_id, styles=_styles("a" * 64))
    repo.replace_state_styles(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        styles={"one": _styles("b" * 64), "two": _styles("c" * 64)},
    )

    repo.replace_state_styles(
        tmp_db, scan_id=scan_id, page_id=page_id, styles={"two": _styles("d" * 64)}
    )
    stored = repo.saved_copy_styles(tmp_db, scan_id=scan_id, page_id=page_id)
    assert set(stored) == {"", "two"}, "the page's own row survives a state replace"
    assert stored["two"].sheets[0].sha256 == "d" * 64

    # A copy that was not kept takes its CSS with it.
    repo.set_page_styles(tmp_db, scan_id=scan_id, page_id=page_id, styles=None)
    assert set(repo.saved_copy_styles(tmp_db, scan_id=scan_id, page_id=page_id)) == {"two"}


def test_one_scan_cannot_write_or_read_another_scans_styles(tmp_db: sqlite3.Connection) -> None:
    scan_a = _scan(tmp_db)
    scan_b = _scan(tmp_db)
    page_a = _page(tmp_db, scan_a)
    page_b = _page(tmp_db, scan_b)
    repo.set_page_styles(tmp_db, scan_id=scan_a, page_id=page_a, styles=_styles("a" * 64))

    with pytest.raises(ValueError, match="does not belong"):
        repo.set_page_styles(tmp_db, scan_id=scan_b, page_id=page_a, styles=_styles("b" * 64))
    with pytest.raises(ValueError, match="does not belong"):
        repo.replace_state_styles(tmp_db, scan_id=scan_b, page_id=page_a, styles={})

    assert repo.saved_copy_styles(tmp_db, scan_id=scan_b, page_id=page_a) == {}
    assert repo.saved_copy_styles(tmp_db, scan_id=scan_b, page_id=page_b) == {}
    assert set(repo.saved_copy_styles(tmp_db, scan_id=scan_a, page_id=page_a)) == {""}


def test_deleting_a_scan_deletes_its_rows(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    keep = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    kept_page = _page(tmp_db, keep)
    repo.set_page_styles(tmp_db, scan_id=scan_id, page_id=page_id, styles=_styles("a" * 64))
    repo.set_page_styles(tmp_db, scan_id=keep, page_id=kept_page, styles=_styles("a" * 64))

    with tmp_db:
        tmp_db.execute("DELETE FROM scans WHERE id = ?", (scan_id,))

    rows = tmp_db.execute("SELECT scan_id FROM saved_copy_styles").fetchall()
    assert [row["scan_id"] for row in rows] == [keep]


def test_malformed_json_reads_as_no_sheets(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    tmp_db.execute(
        "INSERT INTO saved_copy_styles (scan_id, page_id, state_key, sheets_json, "
        "complete, fingerprint_json) VALUES (?, ?, '', 'nope', 1, 'nope')",
        (scan_id, page_id),
    )
    stored = repo.saved_copy_styles(tmp_db, scan_id=scan_id, page_id=page_id)
    assert stored[""].sheets == ()
    assert stored[""].fingerprint == {}


def test_migration_rolls_back_and_forward_cleanly(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.set_page_styles(tmp_db, scan_id=scan_id, page_id=page_id, styles=_styles("a" * 64))

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    tables = {r[0] for r in tmp_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "saved_copy_styles" not in tables
    indexes = {r[0] for r in tmp_db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_saved_copy_styles_scan" not in indexes

    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())
    assert tmp_db.execute("SELECT COUNT(*) FROM saved_copy_styles").fetchone()[0] == 0
    repo.set_page_styles(tmp_db, scan_id=scan_id, page_id=page_id, styles=_styles("a" * 64))
    assert set(repo.saved_copy_styles(tmp_db, scan_id=scan_id, page_id=page_id)) == {""}
