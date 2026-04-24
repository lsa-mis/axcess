"""Unit tests for orchestrator-internal helpers.

The rescan auto-diff hangs off ``_previous_completed_scan``, which uses
``compare_key`` so a dev-server port change between crawls doesn't hide the
previous scan from the auto-diff.
"""

from __future__ import annotations

import sqlite3

from audit.crawler.orchestrator import _previous_completed_scan


def _insert_scan(conn: sqlite3.Connection, seed: str, status: str = "completed") -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, ?, '{}')",
        (seed, status),
    )
    return int(cur.lastrowid or 0)


def test_previous_completed_scan_ignores_self(tmp_db: sqlite3.Connection) -> None:
    a = _insert_scan(tmp_db, "http://127.0.0.1:8000/")
    assert _previous_completed_scan(tmp_db, "http://127.0.0.1:8000/", current_scan_id=a) is None


def test_previous_completed_scan_exact_match(tmp_db: sqlite3.Connection) -> None:
    a = _insert_scan(tmp_db, "http://127.0.0.1:8000/")
    b = _insert_scan(tmp_db, "http://127.0.0.1:8000/")
    assert _previous_completed_scan(tmp_db, "http://127.0.0.1:8000/", current_scan_id=b) == a


def test_previous_completed_scan_matches_across_loopback_ports(
    tmp_db: sqlite3.Connection,
) -> None:
    a = _insert_scan(tmp_db, "http://127.0.0.1:18800/gallery.html")
    b = _insert_scan(tmp_db, "http://localhost:18801/gallery.html")
    # From scan B's perspective, scan A is the logical predecessor even though
    # the port (and host alias) differ.
    assert (
        _previous_completed_scan(tmp_db, "http://localhost:18801/gallery.html", current_scan_id=b)
        == a
    )


def test_previous_completed_scan_does_not_bridge_different_real_hosts(
    tmp_db: sqlite3.Connection,
) -> None:
    _insert_scan(tmp_db, "https://staging.example.com/gallery")
    b = _insert_scan(tmp_db, "https://prod.example.com/gallery")
    # Different hosts → no auto-match.
    assert (
        _previous_completed_scan(tmp_db, "https://prod.example.com/gallery", current_scan_id=b)
        is None
    )


def test_previous_completed_scan_skips_running_and_failed_scans(
    tmp_db: sqlite3.Connection,
) -> None:
    _insert_scan(tmp_db, "http://127.0.0.1:8000/", status="failed")
    _insert_scan(tmp_db, "http://127.0.0.1:8000/", status="running")
    completed = _insert_scan(tmp_db, "http://127.0.0.1:8000/", status="completed")
    cursor_id = _insert_scan(tmp_db, "http://127.0.0.1:8000/")
    assert (
        _previous_completed_scan(tmp_db, "http://127.0.0.1:8000/", current_scan_id=cursor_id)
        == completed
    )


def test_previous_completed_scan_picks_most_recent_match(
    tmp_db: sqlite3.Connection,
) -> None:
    _insert_scan(tmp_db, "http://127.0.0.1:8000/")
    newer = _insert_scan(tmp_db, "http://localhost:9000/")
    current = _insert_scan(tmp_db, "http://127.0.0.1:7000/")
    assert (
        _previous_completed_scan(tmp_db, "http://127.0.0.1:7000/", current_scan_id=current) == newer
    )
