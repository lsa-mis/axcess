"""Unit tests for orchestrator-internal helpers.

The rescan auto-diff hangs off ``_previous_completed_scan``, which uses
``compare_key`` so a dev-server port change between crawls doesn't hide the
previous scan from the auto-diff.
"""

from __future__ import annotations

import sqlite3

from audit.crawler.orchestrator import _previous_completed_scan, _purge_out_of_scope_jobs
from audit.crawler.url_policy import build_scope


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


# ---------- _purge_out_of_scope_jobs -----------------------------------------


def _add_pending_job(conn: sqlite3.Connection, *, scan_id: int, url: str) -> int:
    cur = conn.execute(
        "INSERT INTO jobs (kind, payload_json, state) VALUES ('fetch', ?, 'pending')",
        (f'{{"url":"{url}","scan_id":{scan_id},"depth":0}}',),
    )
    return int(cur.lastrowid or 0)


def test_purge_drops_jobs_outside_path_prefix(tmp_db: sqlite3.Connection) -> None:
    scan_id = _insert_scan(tmp_db, "https://lsa.umich.edu/bicentennial/")
    _add_pending_job(tmp_db, scan_id=scan_id, url="https://lsa.umich.edu/bicentennial/a")
    _add_pending_job(tmp_db, scan_id=scan_id, url="https://lsa.umich.edu/lsa/news/x")
    _add_pending_job(tmp_db, scan_id=scan_id, url="https://lsa.umich.edu/bicentennial-news/y")

    scope = build_scope("https://lsa.umich.edu/bicentennial/")
    dropped = _purge_out_of_scope_jobs(tmp_db, scan_id=scan_id, scope=scope, allow_subdomains=False)
    assert dropped == 2

    remaining = tmp_db.execute(
        "SELECT json_extract(payload_json, '$.url') AS url FROM jobs WHERE state = 'pending'"
    ).fetchall()
    urls = {r["url"] for r in remaining}
    assert urls == {"https://lsa.umich.edu/bicentennial/a"}


def test_purge_leaves_other_scans_alone(tmp_db: sqlite3.Connection) -> None:
    a = _insert_scan(tmp_db, "https://a.example/docs/")
    b = _insert_scan(tmp_db, "https://b.example/docs/")
    _add_pending_job(tmp_db, scan_id=a, url="https://a.example/docs/x")
    _add_pending_job(tmp_db, scan_id=b, url="https://b.example/elsewhere/y")  # stale if scoped

    # Purge scan b only — scan a's (unrelated) job must remain.
    scope_b = build_scope("https://b.example/docs/")
    dropped = _purge_out_of_scope_jobs(tmp_db, scan_id=b, scope=scope_b, allow_subdomains=False)
    assert dropped == 1
    urls = {
        r["url"]
        for r in tmp_db.execute(
            "SELECT json_extract(payload_json, '$.url') AS url FROM jobs WHERE state = 'pending'"
        ).fetchall()
    }
    assert urls == {"https://a.example/docs/x"}


def test_purge_is_noop_when_all_in_scope(tmp_db: sqlite3.Connection) -> None:
    scan_id = _insert_scan(tmp_db, "https://example.com/")
    _add_pending_job(tmp_db, scan_id=scan_id, url="https://example.com/a")
    _add_pending_job(tmp_db, scan_id=scan_id, url="https://example.com/b")
    scope = build_scope("https://example.com/")
    assert (
        _purge_out_of_scope_jobs(tmp_db, scan_id=scan_id, scope=scope, allow_subdomains=False) == 0
    )
