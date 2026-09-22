"""Unit tests for orchestrator-internal helpers.

The rescan auto-diff hangs off ``_previous_completed_scan``, which uses
``compare_key`` so a dev-server port change between crawls doesn't hide the
previous scan from the auto-diff.
"""

from __future__ import annotations

import gzip
import json
import sqlite3

from audit.crawler import orchestrator
from audit.crawler.orchestrator import (
    _MAX_STORED_HTML_BYTES,
    CrawlConfig,
    _compress_html,
    _previous_completed_scan,
    _purge_out_of_scope_jobs,
    _signed_in_entry_url,
    config_json_for_scan,
)
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


def test_compress_html_is_deterministic_and_reversible() -> None:
    body = ("<p>repeat</p>" * 100).encode()
    first = _compress_html(body)
    second = _compress_html(body)
    assert first is not None and second is not None
    assert first == second  # mtime=0 → identical bytes for identical input
    assert gzip.decompress(first) == body


def test_compress_html_rejects_empty_and_oversized() -> None:
    assert _compress_html(b"") is None
    assert _compress_html(b"x" * (_MAX_STORED_HTML_BYTES + 1)) is None


def test_config_json_includes_rendered_storage_flag() -> None:
    default = json.loads(config_json_for_scan(CrawlConfig(seed_url="https://example.com/")))
    assert default["store_rendered_html"] is True
    opt_out = json.loads(
        config_json_for_scan(
            CrawlConfig(seed_url="https://example.com/", store_rendered_html=False)
        )
    )
    assert opt_out["store_rendered_html"] is False


def test_signed_in_entry_url_keeps_any_fragment_and_still_canonicalizes() -> None:
    """The entry point is the one URL a human chose by standing on it.

    ``normalize`` must keep guessing whether a fragment names a route, because
    it runs on every discovered link and ``#main`` has to dedupe with the page
    it sits on. Here there is nothing to guess: the auditor confirmed sign-in
    on this exact URL, so whatever follows the ``#`` is the view they were
    looking at, hash-router shape or not.
    """
    # The shape normalize already accepted.
    assert _signed_in_entry_url("https://app.test/#/projects") == "https://app.test/#/projects"
    # The shape it discarded, which collapsed scan 35's entry onto the seed.
    assert _signed_in_entry_url("https://app.test/#my-courses") == "https://app.test/#my-courses"
    # Everything else normalize does is still done.
    assert (
        _signed_in_entry_url("https://APP.Test:443/a?b=2&a=1#top")
        == "https://app.test/a?a=1&b=2#top"
    )
    assert _signed_in_entry_url("https://app.test/page") == "https://app.test/page"


def test_non_document_urls_stay_on_the_static_path() -> None:
    """Skipping the static fetch must not send downloads through Playwright.

    The frontier holds every in-scope href, not just pages. A PDF or an image
    never escalates to the browser on the two-step path, so routing it there
    would be a new behavior rather than a saved request.
    """
    for url in (
        "https://example.com/report.pdf",
        "https://example.com/logo.png",
        "https://example.com/data.json",
        "https://example.com/archive.ZIP",
        "https://example.com/bundle.js",
    ):
        assert orchestrator._is_document_url(url) is False, url


def test_document_urls_are_eligible_for_direct_render() -> None:
    """Pages, extensionless paths and server-rendered templates all qualify."""
    for url in (
        "https://example.com/",
        "https://example.com/about",
        "https://example.com/about.html",
        "https://example.com/index.php",
        "https://example.com/a.b/nested",
        "https://example.com/search?q=report.pdf",
    ):
        assert orchestrator._is_document_url(url) is True, url
