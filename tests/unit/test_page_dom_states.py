"""Storage rules for the DOM states a click revealed.

The captures exist so the inspector can show an element that is not in the
page's load-state HTML. That only holds while the two describe the same fetch,
which is what makes replacement, rather than merging, the correct write.
"""

from __future__ import annotations

import gzip
import json
import sqlite3

import pytest

from audit.analyzer.interaction.base import StateCapture
from audit.db import repo


def _capture(key: str, label: str = "Open dialog", body: str = "<p>revealed</p>") -> StateCapture:
    return StateCapture(
        state_key=key,
        revealed_by=label,
        path_labels=("Menu", label),
        html=gzip.compress(f"<!doctype html><html>{body}</html>".encode(), 1, mtime=0),
    )


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


def _scan(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES ('https://x.test/', 'completed', 1, 0, '{}')"
    )
    return int(cur.lastrowid or 0)


def test_states_round_trip_with_their_reproduction_path(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)

    written = repo.replace_page_dom_states(
        tmp_db, scan_id=scan_id, page_id=page_id, states=[_capture("s|#a|Open dialog")]
    )

    assert written == 1
    row = tmp_db.execute("SELECT * FROM page_dom_states").fetchone()
    assert row["state_key"] == "s|#a|Open dialog"
    assert row["encoding"] == "gzip"
    assert gzip.decompress(row["dom"]).endswith(b"</html>")
    # The chain is the reproduction recipe, and it ends with this state's own
    # control so the label beside it is always the last step.
    assert json.loads(row["path_labels"]) == ["Menu", "Open dialog"]


def test_refetching_a_page_discards_states_from_the_previous_document(
    tmp_db: sqlite3.Connection,
) -> None:
    """``upsert_page`` overwrites ``rendered_html``, so old states are stale.

    A capture only means anything against the load state it was taken beside.
    Merging would leave a reviewer looking at a dialog from a document the
    report no longer holds.
    """
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.replace_page_dom_states(
        tmp_db, scan_id=scan_id, page_id=page_id, states=[_capture("s|#old|Gone")]
    )

    # Same natural key, so this is the same row re-fetched.
    assert _page(tmp_db, scan_id) == page_id
    repo.replace_page_dom_states(
        tmp_db, scan_id=scan_id, page_id=page_id, states=[_capture("s|#new|Here")]
    )

    keys = [r["state_key"] for r in tmp_db.execute("SELECT state_key FROM page_dom_states")]
    assert keys == ["s|#new|Here"]


def test_a_pass_that_captured_nothing_clears_the_previous_states(
    tmp_db: sqlite3.Connection,
) -> None:
    """Empty is a statement, not a no-op: this page now has no captures."""
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.replace_page_dom_states(
        tmp_db, scan_id=scan_id, page_id=page_id, states=[_capture("s|#a|Open")]
    )

    repo.replace_page_dom_states(tmp_db, scan_id=scan_id, page_id=page_id, states=[])

    assert tmp_db.execute("SELECT COUNT(*) c FROM page_dom_states").fetchone()["c"] == 0


def test_two_controls_sharing_a_name_keep_separate_states(
    tmp_db: sqlite3.Connection,
) -> None:
    """The reason the key is not ``revealed_by``.

    An unlabelled control falls back to its tag name, so a page can hold
    several controls answering to the same string. Collapsing them would hand a
    finding the wrong markup.
    """
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)

    repo.replace_page_dom_states(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        states=[
            _capture("s|#first|<button>", "<button>", "<p>first</p>"),
            _capture("s|#second|<button>", "<button>", "<p>second</p>"),
        ],
    )

    bodies = {gzip.decompress(r["dom"]) for r in tmp_db.execute("SELECT dom FROM page_dom_states")}
    assert len(bodies) == 2


def test_states_cannot_be_written_against_another_scans_page(
    tmp_db: sqlite3.Connection,
) -> None:
    """One report's markup must not surface inside another."""
    first = _scan(tmp_db)
    second = _scan(tmp_db)
    page_id = _page(tmp_db, first)

    with pytest.raises(ValueError, match="does not belong"):
        repo.replace_page_dom_states(
            tmp_db, scan_id=second, page_id=page_id, states=[_capture("s|#a|Open")]
        )


def test_deleting_a_scan_takes_its_states_with_it(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan(tmp_db)
    page_id = _page(tmp_db, scan_id)
    repo.replace_page_dom_states(
        tmp_db, scan_id=scan_id, page_id=page_id, states=[_capture("s|#a|Open")]
    )

    tmp_db.execute("DELETE FROM scans WHERE id = ?", (scan_id,))

    assert tmp_db.execute("SELECT COUNT(*) c FROM page_dom_states").fetchone()["c"] == 0
