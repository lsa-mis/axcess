"""A crawl with the form error check on stores its findings like any other check's.

The fixture page (tests/fixtures/site/form-errors/) has one form that only
colours its empty fields (a WCAG 3.3.1 failure) and one that describes the
error in text. With the check on, the failing form becomes one occurrence in
``page_a11y_findings`` with ``pipeline='forms'``, its submit control as the
control that revealed it; with the check off, which is the default, nothing.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from audit.crawler.orchestrator import CrawlConfig, run_crawl

from .test_saved_copy_styles_crawl import _serve

pytestmark = pytest.mark.integration


def _config(base: str, **overrides: object) -> CrawlConfig:
    return CrawlConfig(
        js_eager=True,
        seed_url=f"{base}/form-errors/",
        max_pages=1,
        rps=100.0,
        workers=1,
        vlm_enabled=False,
        semantic_enabled=False,
        interaction_checks_enabled=False,
        **overrides,  # type: ignore[arg-type]
    )


def _form_rows(conn: sqlite3.Connection, scan_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT rule_id, wcag_sc, wcag_level, target_selector, revealed_by, failure_summary "
        "FROM page_a11y_findings WHERE scan_id = ? AND pipeline = 'forms'",
        (scan_id,),
    ).fetchall()


def test_a_failing_form_is_stored_as_an_occurrence(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base, form_error_checks_enabled=True)))

    rows = _form_rows(tmp_db, summary.scan_id)
    assert len(rows) == 1, [dict(r) for r in rows]
    row = rows[0]
    assert (row["rule_id"], row["wcag_sc"], row["wcag_level"]) == (
        "form-error-not-described",
        "3.3.1",
        "A",
    )
    assert row["target_selector"].endswith("#contact")
    assert row["revealed_by"] == "Send message"
    assert "Name" in row["failure_summary"] and "Email" in row["failure_summary"]


def test_the_check_is_off_by_default(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    assert CrawlConfig(seed_url="https://example.org/").form_error_checks_enabled is False
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base)))
    assert _form_rows(tmp_db, summary.scan_id) == []


def test_a_failing_form_keeps_its_screenshots_before_and_after_the_press(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The form, outlined, before its submit press and after it (migration 0035).

    The after picture is the finding's screenshot, as for every check; the
    before picture sits beside it. The form colours its fields on the press,
    so the two pictures differ. With screenshots off, neither is kept.
    """
    blobs = tmp_path / "blobs"
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(blobs))
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base, form_error_checks_enabled=True)))
    row = tmp_db.execute(
        "SELECT screenshot_hash, before_screenshot_hash FROM page_a11y_findings "
        "WHERE scan_id = ? AND pipeline = 'forms'",
        (summary.scan_id,),
    ).fetchone()
    after, before = row["screenshot_hash"], row["before_screenshot_hash"]
    assert after and before, dict(row)
    assert after != before, "the press changed the form, so the pictures differ"
    for content_hash in (after, before):
        png = blobs / content_hash[:2] / f"{content_hash}.png"
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", png

    with _serve() as base:
        quiet = asyncio.run(
            run_crawl(
                tmp_db, _config(base, form_error_checks_enabled=True, capture_screenshots=False)
            )
        )
    row = tmp_db.execute(
        "SELECT screenshot_hash, before_screenshot_hash FROM page_a11y_findings "
        "WHERE scan_id = ? AND pipeline = 'forms'",
        (quiet.scan_id,),
    ).fetchone()
    assert row is not None
    assert (row["screenshot_hash"], row["before_screenshot_hash"]) == (None, None)


def test_the_scan_counts_what_the_check_did(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages checked and forms pressed, skipped and not judged (migration 0036).

    The fixture page has two forms the check may press, one failing and one
    that describes its error, so both are pressed and nothing is skipped.
    """
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base, form_error_checks_enabled=True)))
    row = tmp_db.execute(
        "SELECT forms_pages_checked, forms_pressed, forms_skipped, forms_not_checked, "
        "config_json FROM scans WHERE id = ?",
        (summary.scan_id,),
    ).fetchone()
    assert (row[0], row[1], row[2], row[3]) == (1, 2, 0, 0), tuple(row)
    assert '"form_check_coverage_version": 1' in row["config_json"]

    with _serve() as base:
        off = asyncio.run(run_crawl(tmp_db, _config(base)))
    row = tmp_db.execute(
        "SELECT forms_pages_checked, forms_pressed FROM scans WHERE id = ?", (off.scan_id,)
    ).fetchone()
    assert (row[0], row[1]) == (0, 0)
