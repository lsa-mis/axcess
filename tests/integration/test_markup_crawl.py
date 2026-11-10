"""A crawl stores the page code check's findings like any other check's.

The known issues page (tests/fixtures/site/known_issues/) has one pattern for
each page code rule. A crawl with the check on, the default, stores one
occurrence per rule with ``pipeline='markup'``, counts the page in
``scans.markup_pages_checked`` (migration 0037), and records the setting in
the scan's config; the issue list shows each rule as its own issue type.
With ``--skip-markup`` it stores nothing and counts nothing.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from audit.crawler.orchestrator import CrawlConfig, run_crawl
from audit.web import issues

from .test_saved_copy_styles_crawl import _serve

pytestmark = pytest.mark.integration


def _config(base: str, **overrides: object) -> CrawlConfig:
    return CrawlConfig(
        js_eager=True,
        seed_url=f"{base}/known_issues/",
        max_pages=1,
        rps=100.0,
        workers=1,
        vlm_enabled=False,
        semantic_enabled=False,
        interaction_checks_enabled=False,
        **overrides,  # type: ignore[arg-type]
    )


def _markup_rules(conn: sqlite3.Connection, scan_id: int) -> list[str]:
    return sorted(
        r[0]
        for r in conn.execute(
            "SELECT rule_id FROM page_a11y_findings WHERE scan_id = ? AND pipeline = 'markup'",
            (scan_id,),
        )
    )


def test_each_rule_is_stored_counted_and_listed(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    assert CrawlConfig(seed_url="https://example.org/").markup_checks_enabled is True
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base)))

    assert _markup_rules(tmp_db, summary.scan_id) == [
        "markup-label-for-missing",
        "markup-placeholder-only",
        "markup-styled-as-heading",
        "markup-title-repeats-text",
    ]
    scan = tmp_db.execute(
        "SELECT markup_pages_checked, config_json FROM scans WHERE id = ?", (summary.scan_id,)
    ).fetchone()
    assert scan["markup_pages_checked"] == 1
    assert json.loads(scan["config_json"])["markup_checks_enabled"] is True
    keys = {r.issue_key for r in issues.list_issues(tmp_db, summary.scan_id)}
    assert {
        "markup:markup-label-for-missing",
        "markup:markup-placeholder-only",
        "markup:markup-styled-as-heading",
        "markup:markup-title-repeats-text",
    } <= keys


def test_skipping_the_check_stores_and_counts_nothing(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    with _serve() as base:
        summary = asyncio.run(run_crawl(tmp_db, _config(base, markup_checks_enabled=False)))

    assert _markup_rules(tmp_db, summary.scan_id) == []
    scan = tmp_db.execute(
        "SELECT markup_pages_checked FROM scans WHERE id = ?", (summary.scan_id,)
    ).fetchone()
    assert scan["markup_pages_checked"] == 0
