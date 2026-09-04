"""Unit tests for the CSV and JSON export formats.

We seed a deterministic DB fixture (no live OCR/VLM), run the collector,
and compare the rendered output to golden files under ``golden/``. To
refresh after an intentional schema change, set ``AUDIT_UPDATE_GOLDEN=1``.
"""

from __future__ import annotations

import csv as _csv_module  # noqa: F401  # used inside test_axe_findings_propagate_to_all_exports
import io
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
    # Header starts with `finding_kind` since v2 of the CSV — that's the
    # discriminator between image-of-text and wcag_axe rows.
    lines = actual.splitlines()
    assert lines[0].startswith("finding_kind,finding_id")
    # Fixture has no axe findings, so the row count is unchanged from v1.
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
    # v2 schema additions — the a11y section is present but empty on a
    # legacy fixture scan (no axe pages run).
    assert payload["schema_version"] == 4
    assert payload["a11y_findings"] == []
    assert payload["scan"]["axe_pages_scanned"] == 0
    assert payload["scan"]["axe_violations_total"] == 0


def _seed_axe_finding(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page_id: int,
    rule_id: str = "color-contrast",
    wcag_sc: str | None = "1.4.3",
    wcag_level: str | None = "AA",
    impact: str | None = "serious",
) -> int:
    """Insert a single axe finding for tests. Returns the row id."""
    cur = conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
             impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            page_id,
            scan_id,
            rule_id,
            wcag_sc,
            wcag_sc,
            wcag_level,
            impact,
            "Elements must have sufficient color contrast",
            f"https://dequeuniversity.com/rules/axe/4.10/{rule_id}",
            "p > span.muted",
            "Fix any of the following: foreground/background contrast is 2.1.",
            '<span class="muted">low-contrast text</span>',
            f"deadbeef-{rule_id}",
        ),
    )
    conn.execute(
        "UPDATE scans SET axe_pages_scanned = axe_pages_scanned + 1, "
        "axe_violations_total = axe_violations_total + 1 WHERE id = ?",
        (scan_id,),
    )
    return int(cur.lastrowid or 0)


def test_axe_findings_propagate_to_all_exports(
    tmp_db: sqlite3.Connection, scan_fixture: int
) -> None:
    """Seed one axe row and verify it shows up in every export format.

    Image-of-text + axe rows live in different tables; this is the
    contract test that proves the collector + renderers honor both.
    """
    from audit.exports.jira_export import render_jira_csv
    from audit.exports.markdown_report import render_markdown

    page_row = tmp_db.execute(
        "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1",
        (scan_fixture,),
    ).fetchone()
    assert page_row is not None
    _seed_axe_finding(tmp_db, scan_id=scan_fixture, page_id=int(page_row["id"]))

    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    assert scan.axe_violations_total == 1
    assert scan.axe_pages_scanned == 1
    assert len(scan.a11y_findings) == 1
    assert scan.by_wcag_level["AA"] == 1

    # CSV gains exactly one wcag_axe row; image rows unchanged.
    csv_text = render_csv(scan)
    csv_rows = csv_text.strip().splitlines()
    assert sum(1 for r in csv_rows[1:] if r.startswith("wcag_axe,")) == 1
    assert sum(1 for r in csv_rows[1:] if r.startswith("image_of_text,")) == 4

    # JSON gains the a11y_findings array.
    payload = json.loads(render_json(scan))
    assert len(payload["a11y_findings"]) == 1
    assert payload["a11y_findings"][0]["rule_id"] == "color-contrast"
    assert payload["a11y_findings"][0]["wcag_sc"] == "1.4.3"
    assert payload["scan"]["axe_violations_total"] == 1
    assert payload["scan"]["by_wcag_level"] == {
        "A": 0,
        "AA": 1,
        "AAA": 0,
        "best_practice": 0,
    }

    # Markdown report preserves the engine source in its WCAG section.
    md = render_markdown(scan)
    assert "## WCAG DOM-engine findings" in md
    assert "**Source:** axe-core" in md
    assert "color-contrast" in md
    assert "SC 1.4.3" in md

    # Jira CSV adds one extra issue row, with axe-flavored labels and a
    # priority derived from impact, not severity. The Description column
    # is intentionally multi-line, so we parse with csv.reader rather
    # than splitlines() — one bug in this test was confusing the
    # description body for separate rows.
    import csv as _csv

    jira_text = render_jira_csv(scan)
    reader = _csv.reader(io.StringIO(jira_text))
    rows = list(reader)
    header = rows[0]
    data_rows = rows[1:]
    axe_row = next(r for r in data_rows if "color-contrast" in r[0])
    labels = axe_row[header.index("Labels")]
    priority = axe_row[header.index("Priority")]
    assert "wcag-1-4-3" in labels
    assert "wcag-level-aa" in labels
    assert priority == "High"  # serious → High


def test_behavioral_and_ai_sources_are_not_mislabeled_as_axe(
    tmp_db: sqlite3.Connection, scan_fixture: int
) -> None:
    from audit.exports.jira_export import render_jira_csv
    from audit.exports.markdown_report import render_markdown

    page_id = int(
        tmp_db.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_fixture,)
        ).fetchone()["id"]
    )
    finding_id = _seed_axe_finding(
        tmp_db,
        scan_id=scan_fixture,
        page_id=page_id,
        rule_id="semantic:2.4.4",
        wcag_sc="2.4.4",
        wcag_level="A",
        impact=None,
    )
    tmp_db.execute(
        "UPDATE page_a11y_findings SET pipeline = 'semantic' WHERE id = ?", (finding_id,)
    )

    scan = collect_scan(tmp_db, scan_fixture, ui_base_url="http://127.0.0.1:8765")
    markdown = render_markdown(scan)
    jira = render_jira_csv(scan)

    assert "**Source:** Semantic analyzer" in markdown
    assert "**Source:** Semantic analyzer" in jira
    assert "Needs expert review (observed lead" in markdown
    assert "Needs expert review (observed lead" in jira
    assert "**Source:** axe-core" not in jira
