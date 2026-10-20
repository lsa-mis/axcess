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
