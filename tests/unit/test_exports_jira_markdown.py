"""Golden-file tests for the Jira CSV and Markdown report exports."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from audit.db import repo
from audit.exports.collector import collect_scan
from audit.exports.jira_export import JIRA_COLUMNS, render_jira_csv
from audit.exports.markdown_report import render_markdown
from audit.synthesizer.findings import synthesize_findings

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
UPDATE_GOLDEN = os.environ.get("AUDIT_UPDATE_GOLDEN") == "1"


def _assert_matches_golden(actual: str, name: str) -> None:
    path = GOLDEN_DIR / name
    if UPDATE_GOLDEN or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"Golden mismatch for {name}. Re-run with AUDIT_UPDATE_GOLDEN=1 to refresh."
    )


@pytest.fixture
def scan_fixture(tmp_db: sqlite3.Connection) -> int:
    """Mirror the fixture used by the CSV/JSON tests so goldens align."""
    cur = tmp_db.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, "
        "config_json, started_at, finished_at) "
        "VALUES ('http://example.com/', 'completed', 2, 0, '{}', "
        "'2026-04-22 12:00:00', '2026-04-22 12:01:00')"
    )
    scan_id = int(cur.lastrowid or 0)

    page_home = repo.upsert_page(
        tmp_db,
        scan_id=scan_id,
        url_normalized="http://example.com/",
        status_code=200,
        title="Home",
        render_mode="static",
        html_hash="0" * 64,
    )
    page_about = repo.upsert_page(
        tmp_db,
        scan_id=scan_id,
        url_normalized="http://example.com/about",
        status_code=200,
        title="About",
        render_mode="static",
        html_hash="1" * 64,
    )

    banner_id = repo.upsert_image(
        tmp_db,
        content_hash="b" * 64,
        src_url="http://example.com/banner.png",
        mime="image/png",
        bytes_len=512,
        width=600,
        height=100,
        blob_path="bb/" + "b" * 64 + ".png",
        has_svg_text=False,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        tmp_db,
        page_id=page_home,
        image_id=banner_id,
        alt_text=None,
        role=None,
        context_snippet="Buy widgets now",
        position=0,
        above_fold=True,
    )
    repo.upsert_page_image(
        tmp_db,
        page_id=page_about,
        image_id=banner_id,
        alt_text=None,
        role=None,
        context_snippet="Buy widgets now",
        position=1,
        above_fold=False,
    )
    repo.upsert_analysis(
        tmp_db,
        image_id=banner_id,
        ocr_text="BUY WIDGETS NOW",
        ocr_confidence=92.50,
        vlm_classification="essential",
        vlm_rationale="Promotional banner with text as image.",
        has_text=True,
        model_versions={"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"},
    )

    logo_id = repo.upsert_image(
        tmp_db,
        content_hash="c" * 64,
        src_url="http://example.com/logo.png",
        mime="image/png",
        bytes_len=200,
        width=120,
        height=40,
        blob_path="cc/" + "c" * 64 + ".png",
        has_svg_text=False,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        tmp_db,
        page_id=page_home,
        image_id=logo_id,
        alt_text="Acme Corp",
        role=None,
        context_snippet=None,
        position=2,
    )
    repo.upsert_analysis(
        tmp_db,
        image_id=logo_id,
        ocr_text="Acme Corp",
        ocr_confidence=88.0,
        vlm_classification="logo",
        vlm_rationale="Brand mark.",
        has_text=True,
        model_versions={"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"},
    )

    svg_id = repo.upsert_image(
        tmp_db,
        content_hash="e" * 64,
        src_url="inline-svg://http://example.com/#0",
        mime="image/svg+xml",
        bytes_len=None,
        width=None,
        height=None,
        blob_path=None,
        has_svg_text=True,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        tmp_db,
        page_id=page_home,
        image_id=svg_id,
        alt_text=None,
        role=None,
        context_snippet="ACME",
        position=3,
    )

    synthesize_findings(tmp_db, scan_id=scan_id)
    return scan_id


def test_jira_csv_matches_golden(tmp_db: sqlite3.Connection, scan_fixture: int) -> None:
    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    actual = render_jira_csv(scan)
    _assert_matches_golden(actual, "scan.jira.csv")

    # Round-trip through the CSV parser: header + one record per finding.
    records = list(csv.reader(io.StringIO(actual)))
    assert records[0] == list(JIRA_COLUMNS)
    assert len(records) == 1 + 3


def test_jira_priority_maps_from_severity(
    tmp_db: sqlite3.Connection, scan_fixture: int
) -> None:
    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    actual = render_jira_csv(scan)
    # The essential / missing-alt banner should map to Highest.
    assert '"Highest"' in actual or ",Highest," in actual
    # The logo / adequate-alt finding should land at Lowest.
    assert ",Lowest," in actual


def test_jira_includes_labels_and_ui_url(
    tmp_db: sqlite3.Connection, scan_fixture: int
) -> None:
    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    actual = render_jira_csv(scan)
    assert "wcag-1-4-5" in actual
    assert "class-essential" in actual
    assert "inline-svg" in actual
    assert "http://127.0.0.1:8765/findings/" in actual


def test_markdown_matches_golden(tmp_db: sqlite3.Connection, scan_fixture: int) -> None:
    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    actual = render_markdown(
        scan, generated_at=datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
    )
    _assert_matches_golden(actual, "scan.md")


def test_markdown_for_empty_scan_does_not_crash(tmp_db: sqlite3.Connection) -> None:
    cur = tmp_db.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES ('http://empty/', 'completed', 0, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    scan = collect_scan(tmp_db, scan_id)
    md = render_markdown(scan, generated_at=datetime(2026, 4, 22, tzinfo=UTC))
    assert "No WCAG 1.4.5 failures detected" in md
    assert "_No findings._" in md
