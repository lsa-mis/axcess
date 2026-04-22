"""Unit tests for the CSV and JSON export formats.

We seed a deterministic DB fixture (no live OCR/VLM), run the collector,
and compare the rendered output to golden files under ``golden/``. To
refresh after an intentional schema change, set ``AUDIT_UPDATE_GOLDEN=1``.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from audit.db import repo
from audit.exports.collector import collect_scan
from audit.exports.csv_export import render_csv
from audit.exports.json_export import render_json
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
        f"Golden mismatch for {name}. "
        "Re-run tests with AUDIT_UPDATE_GOLDEN=1 to refresh after "
        "a deliberate change."
    )


@pytest.fixture
def scan_fixture(tmp_db: sqlite3.Connection) -> int:
    """Build a scan with three representative findings."""
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

    # 1) Essential banner with missing alt — will become critical.
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

    # 2) Logo with adequate alt — info severity.
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

    # 3) Inline SVG with text — minor severity, no VLM, no blob.
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


def test_collect_scan_shape(tmp_db: sqlite3.Connection, scan_fixture: int) -> None:
    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    assert scan.id == scan_fixture
    assert scan.seed_url == "http://example.com/"
    assert scan.finding_count == len(scan.findings) == 3
    # Ordered by priority_score desc.
    severities = [f.severity for f in scan.findings]
    assert severities[0] in ("critical", "major")
    assert severities[-1] in ("info", "minor")
    # Banner finding should have two occurrences.
    banner = next(f for f in scan.findings if f.image_url.endswith("/banner.png"))
    assert len(banner.occurrences) == 2
    assert any(o.above_fold for o in banner.occurrences)
    # UI URL uses the custom base.
    assert banner.ui_url.startswith("http://127.0.0.1:8765/findings/")


def test_csv_matches_golden(tmp_db: sqlite3.Connection, scan_fixture: int) -> None:
    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    actual = render_csv(scan)
    _assert_matches_golden(actual, "scan.csv")
    # Sanity: header + one row per occurrence (+ one for the orphan inline-svg).
    lines = actual.splitlines()
    assert lines[0].startswith("finding_id,severity")
    assert len(lines) == 1 + 2 + 1 + 1  # header + banner(2) + logo(1) + svg(1)


def test_json_matches_golden(tmp_db: sqlite3.Connection, scan_fixture: int) -> None:
    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    actual = render_json(scan)
    _assert_matches_golden(actual, "scan.json")
    # Sanity: round-trips to dict and preserves counts.
    payload = json.loads(actual)
    assert payload["scan"]["id"] == scan_fixture
    assert len(payload["findings"]) == 3
    assert payload["scan"]["by_severity"]["critical"] + payload["scan"]["by_severity"]["major"] >= 1
