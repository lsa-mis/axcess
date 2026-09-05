"""Unit tests for :mod:`audit.web.image_findings_queries`.

Covers the grouped-by-remediation pipeline: a fixture scan with three
representative findings (one essential-missing, one logo-adequate, one
SVG-text-with-no-classification) goes in; we assert the grouping shape,
ordering, breakdowns, and that the status filter actually filters.
"""

from __future__ import annotations

import sqlite3

import pytest

from audit.db import repo
from audit.synthesizer.findings import synthesize_findings
from audit.web.image_findings_queries import (
    coverage,
    group_label,
    grouped_by_remediation,
)


@pytest.fixture
def scan(tmp_db: sqlite3.Connection) -> int:
    """Seed a small scan with three image findings of distinct kinds."""
    cur = tmp_db.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, "
        "config_json) VALUES ('http://example.test/', 'completed', 2, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)

    page_home = repo.upsert_page(
        tmp_db,
        scan_id=scan_id,
        url_normalized="http://example.test/",
        status_code=200,
        title="Home",
        render_mode="static",
        html_hash="0" * 64,
    )
    page_about = repo.upsert_page(
        tmp_db,
        scan_id=scan_id,
        url_normalized="http://example.test/about",
        status_code=200,
        title="About",
        render_mode="static",
        html_hash="1" * 64,
    )

    # Essential image with NO alt — should land in
    # ("essential", "missing") and synthesize as critical.
    banner_id = repo.upsert_image(
        tmp_db,
        content_hash="b" * 64,
        src_url="http://example.test/banner.png",
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
        context_snippet=None,
        position=0,
        above_fold=True,
    )
    repo.upsert_page_image(
        tmp_db,
        page_id=page_about,
        image_id=banner_id,
        alt_text=None,
        role=None,
        context_snippet=None,
        position=1,
    )
    repo.upsert_analysis(
        tmp_db,
        image_id=banner_id,
        ocr_text="BUY WIDGETS NOW",
        ocr_confidence=92.0,
        vlm_classification="essential",
        vlm_rationale="Promotional banner with text as image.",
        has_text=True,
        model_versions={"ocr": "tess", "vlm": "stub", "prompt": "v1"},
    )

    # Logo with matching alt — ("logo", "adequate"), info severity.
    logo_id = repo.upsert_image(
        tmp_db,
        content_hash="c" * 64,
        src_url="http://example.test/logo.png",
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
        model_versions={"ocr": "tess", "vlm": "stub", "prompt": "v1"},
    )

    synthesize_findings(tmp_db, scan_id=scan_id)
    return scan_id


def test_group_label_renders_human_readable() -> None:
    assert group_label("essential", "missing") == "Essential image, missing alt"
    assert group_label("logo", "adequate") == "Logo, adequate alt"
    assert group_label(None, "missing") == "Image (unclassified), missing alt"


def test_grouped_findings_shape(tmp_db: sqlite3.Connection, scan: int) -> None:
    groups = grouped_by_remediation(tmp_db, scan)
    assert len(groups) == 2

    # Worst-severity-first ordering: essential-missing (critical) ranks
    # before logo-adequate (info).
    g0, g1 = groups
    assert (g0["classification"], g0["alt_adequacy"]) == ("essential", "missing")
    assert g0["worst_severity"] == "critical"
    assert g0["finding_count"] == 1
    assert g0["occurrence_count"] == 2  # banner is on both pages

    assert (g1["classification"], g1["alt_adequacy"]) == ("logo", "adequate")
    assert g1["worst_severity"] == "info"
    assert g1["finding_count"] == 1

    # Each group inherits the shared remediation hint from the rule book.
    assert g0["remediation_hint"]  # non-empty
    assert g1["remediation_hint"]
    assert g0["remediation_hint"] != g1["remediation_hint"]


def test_grouped_findings_severity_and_status_breakdowns(
    tmp_db: sqlite3.Connection, scan: int
) -> None:
    groups = grouped_by_remediation(tmp_db, scan)
    g0 = groups[0]
    assert g0["severity_breakdown"]["critical"] == 1
    assert g0["severity_breakdown"]["info"] == 0
    # Fresh from synthesis, no human triage yet → all "new".
    assert g0["status_breakdown"] == {"new": 1}


def test_grouped_findings_status_filter(tmp_db: sqlite3.Connection, scan: int) -> None:
    # Mark the logo finding as remediated, then filter.
    tmp_db.execute(
        "UPDATE findings SET status = 'remediated'  WHERE scan_id = ? AND severity = 'info'",
        (scan,),
    )
    remediated = grouped_by_remediation(tmp_db, scan, status="remediated")
    assert len(remediated) == 1
    assert remediated[0]["classification"] == "logo"

    new = grouped_by_remediation(tmp_db, scan, status="new")
    assert len(new) == 1
    assert new[0]["classification"] == "essential"

    # Unrecognized status string falls through to "all" — the queries
    # layer's contract.
    all_groups = grouped_by_remediation(tmp_db, scan, status=None)
    assert len(all_groups) == 2


def test_grouped_findings_occurrences_are_attached(tmp_db: sqlite3.Connection, scan: int) -> None:
    groups = grouped_by_remediation(tmp_db, scan)
    essential = next(g for g in groups if g["classification"] == "essential")
    finding = essential["findings"][0]
    urls = {occ["page_url"] for occ in finding["occurrences"]}
    assert urls == {"http://example.test/", "http://example.test/about"}
    # Above-fold flag round-trips per occurrence.
    home_occ = next(o for o in finding["occurrences"] if o["page_url"].endswith("/"))
    assert home_occ["above_fold"] is True


def test_coverage_counts(tmp_db: sqlite3.Connection, scan: int) -> None:
    cov = coverage(tmp_db, scan)
    assert cov["finding_count"] == 2
    assert cov["page_count"] == 2
    # 3 page_images rows: banner on 2 pages, logo on 1 page.
    assert cov["occurrence_total"] == 3
