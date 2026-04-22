"""Unit tests for findings.synthesize_findings against a seeded tmp DB.

Goes end-to-end through the synthesizer using the real schema and the real
rules file — skips only the crawler front-end.
"""

from __future__ import annotations

import sqlite3

from audit.db import repo
from audit.synthesizer.findings import synthesize_findings


def _make_scan(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES ('http://x', 'running', '{}')"
    )
    return int(cur.lastrowid or 0)


def _make_page(conn: sqlite3.Connection, scan_id: int, url: str) -> int:
    return repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized=url,
        status_code=200,
        title="page",
        render_mode="static",
        html_hash="0" * 64,
    )


def _seed_image_and_occurrence(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page_id: int,
    content_hash: str,
    alt_text: str | None,
    mime: str = "image/png",
    has_svg_text: bool = False,
    above_fold: bool = False,
    position: int = 0,
) -> int:
    image_id = repo.upsert_image(
        conn,
        content_hash=content_hash,
        src_url=f"http://x/{content_hash}.png",
        mime=mime,
        bytes_len=100,
        width=10,
        height=10,
        blob_path=f"aa/{content_hash}.png",
        has_svg_text=has_svg_text,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        conn,
        page_id=page_id,
        image_id=image_id,
        alt_text=alt_text,
        role=None,
        context_snippet=None,
        position=position,
        above_fold=above_fold,
    )
    return image_id


def _seed_analysis(
    conn: sqlite3.Connection,
    *,
    image_id: int,
    ocr_text: str,
    vlm_label: str | None = None,
) -> None:
    model_versions = {"ocr": "tesseract-test"}
    if vlm_label is not None:
        model_versions["vlm"] = "stub:1"
        model_versions["prompt"] = "v1-stub"
    repo.upsert_analysis(
        conn,
        image_id=image_id,
        ocr_text=ocr_text,
        ocr_confidence=90.0,
        vlm_classification=vlm_label,
        vlm_rationale="stub" if vlm_label else None,
        has_text=True,
        model_versions=model_versions,
    )


def test_no_findings_when_no_text_images(tmp_db: sqlite3.Connection) -> None:
    scan_id = _make_scan(tmp_db)
    page_id = _make_page(tmp_db, scan_id, "http://x/")
    _seed_image_and_occurrence(
        tmp_db, scan_id=scan_id, page_id=page_id, content_hash="a" * 64, alt_text="cat"
    )
    # No analysis with has_text → no finding.
    result = synthesize_findings(tmp_db, scan_id=scan_id)
    assert result.findings_written == 0


def test_essential_missing_alt_is_critical_or_major(tmp_db: sqlite3.Connection) -> None:
    scan_id = _make_scan(tmp_db)
    p1 = _make_page(tmp_db, scan_id, "http://x/a")
    p2 = _make_page(tmp_db, scan_id, "http://x/b")
    image_id = _seed_image_and_occurrence(
        tmp_db,
        scan_id=scan_id,
        page_id=p1,
        content_hash="b" * 64,
        alt_text=None,
        above_fold=True,
    )
    # Same image on a second page, also missing alt.
    repo.upsert_page_image(
        tmp_db,
        page_id=p2,
        image_id=image_id,
        alt_text=None,
        role=None,
        context_snippet=None,
        position=0,
        above_fold=False,
    )
    _seed_analysis(tmp_db, image_id=image_id, ocr_text="BUY NOW TODAY", vlm_label="essential")

    result = synthesize_findings(tmp_db, scan_id=scan_id)
    assert result.findings_written == 1
    assert result.by_severity is not None
    assert result.by_severity["major"] + result.by_severity["critical"] == 1

    row = tmp_db.execute(
        "SELECT severity, priority_score, remediation_hint FROM findings WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    # essential(4) + missing(3) + log1p(2) + above_fold(1) = ~9.1 → critical
    assert row["severity"] == "critical"
    assert row["priority_score"] >= 8.0
    assert row["remediation_hint"] and "alt" in row["remediation_hint"].lower()


def test_decorative_with_empty_alt_is_minor(tmp_db: sqlite3.Connection) -> None:
    scan_id = _make_scan(tmp_db)
    page_id = _make_page(tmp_db, scan_id, "http://x/")
    image_id = _seed_image_and_occurrence(
        tmp_db, scan_id=scan_id, page_id=page_id, content_hash="c" * 64, alt_text=""
    )
    _seed_analysis(
        tmp_db, image_id=image_id, ocr_text="some stylistic text", vlm_label="decorative"
    )

    result = synthesize_findings(tmp_db, scan_id=scan_id)
    assert result.findings_written == 1
    row = tmp_db.execute("SELECT severity FROM findings WHERE scan_id = ?", (scan_id,)).fetchone()
    # decorative(1) + inadequate(2) + log1p(1) = ~3.7 → minor
    assert row["severity"] == "minor"


def test_adequate_alt_produces_info_finding(tmp_db: sqlite3.Connection) -> None:
    scan_id = _make_scan(tmp_db)
    page_id = _make_page(tmp_db, scan_id, "http://x/")
    image_id = _seed_image_and_occurrence(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        content_hash="d" * 64,
        alt_text="Acme Corp",
    )
    _seed_analysis(tmp_db, image_id=image_id, ocr_text="Acme Corp", vlm_label="logo")

    result = synthesize_findings(tmp_db, scan_id=scan_id)
    assert result.findings_written == 1
    # logo(1) + adequate(0) + log1p(1) = ~1.7 → info
    row = tmp_db.execute(
        "SELECT severity, remediation_hint FROM findings WHERE scan_id = ?", (scan_id,)
    ).fetchone()
    assert row["severity"] == "info"
    assert row["remediation_hint"]


def test_svg_text_without_vlm_still_creates_finding(tmp_db: sqlite3.Connection) -> None:
    scan_id = _make_scan(tmp_db)
    page_id = _make_page(tmp_db, scan_id, "http://x/")
    _seed_image_and_occurrence(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        content_hash="e" * 64,
        alt_text=None,
        mime="image/svg+xml",
        has_svg_text=True,
    )
    result = synthesize_findings(tmp_db, scan_id=scan_id)
    assert result.findings_written == 1
    row = tmp_db.execute(
        "SELECT severity, remediation_hint FROM findings WHERE scan_id = ?", (scan_id,)
    ).fetchone()
    # no classification(0) + missing(3) + log1p(1)=0.69 = ~3.7 → minor
    assert row["severity"] == "minor"
    assert row["remediation_hint"]


def test_synthesize_is_idempotent(tmp_db: sqlite3.Connection) -> None:
    scan_id = _make_scan(tmp_db)
    page_id = _make_page(tmp_db, scan_id, "http://x/")
    image_id = _seed_image_and_occurrence(
        tmp_db, scan_id=scan_id, page_id=page_id, content_hash="f" * 64, alt_text="something"
    )
    _seed_analysis(tmp_db, image_id=image_id, ocr_text="BUY NOW", vlm_label="essential")

    a = synthesize_findings(tmp_db, scan_id=scan_id)
    b = synthesize_findings(tmp_db, scan_id=scan_id)
    assert a.findings_written == b.findings_written == 1
    count = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM findings WHERE scan_id = ?", (scan_id,)
    ).fetchone()["n"]
    assert count == 1


def test_preserves_human_status_on_rerun(tmp_db: sqlite3.Connection) -> None:
    scan_id = _make_scan(tmp_db)
    page_id = _make_page(tmp_db, scan_id, "http://x/")
    image_id = _seed_image_and_occurrence(
        tmp_db, scan_id=scan_id, page_id=page_id, content_hash="a1" + "0" * 62, alt_text=None
    )
    _seed_analysis(tmp_db, image_id=image_id, ocr_text="BUY", vlm_label="essential")

    synthesize_findings(tmp_db, scan_id=scan_id)
    # Simulate a reviewer marking the finding as reviewing.
    tmp_db.execute("UPDATE findings SET status = 'reviewing' WHERE scan_id = ?", (scan_id,))
    synthesize_findings(tmp_db, scan_id=scan_id)
    row = tmp_db.execute("SELECT status FROM findings WHERE scan_id = ?", (scan_id,)).fetchone()
    assert row["status"] == "reviewing"


def test_scan_finding_count_denormalized(tmp_db: sqlite3.Connection) -> None:
    scan_id = _make_scan(tmp_db)
    page_id = _make_page(tmp_db, scan_id, "http://x/")
    for i, h in enumerate(("A", "B", "C")):
        image_id = _seed_image_and_occurrence(
            tmp_db,
            scan_id=scan_id,
            page_id=page_id,
            content_hash=h * 64,
            alt_text=None,
            position=i,
        )
        _seed_analysis(tmp_db, image_id=image_id, ocr_text="TEXT", vlm_label="essential")

    synthesize_findings(tmp_db, scan_id=scan_id)
    row = tmp_db.execute("SELECT finding_count FROM scans WHERE id = ?", (scan_id,)).fetchone()
    assert row["finding_count"] == 3
