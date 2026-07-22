"""Expert-review records layered on top of immutable scan evidence.

The crawler owns its scan tables. This module owns the deliberate human
judgement needed to turn a scan into a defensible accessibility evaluation.
It is intentionally database-first so the web UI, exports, and future
read-only MCP tools use the same scope and manual-test record.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from audit import coverage_matrix

OUTCOMES = frozenset({"not_started", "pass", "fail", "not_tested", "needs_follow_up"})
EVALUATION_STATUSES = frozenset({"draft", "in_progress", "completed"})

_DEFAULT_EVALUATION: dict[str, str] = {
    "target_standard": "WCAG 2.2",
    "target_level": "AA",
    "purpose": "",
    "scope_included": "",
    "scope_excluded": "",
    "sample_description": "",
    "reviewer": "",
    "methods_note": "",
    "limitations": "",
    "status": "draft",
}


def get_evaluation(conn: sqlite3.Connection, scan_id: int) -> dict[str, Any]:
    """Return the persisted evaluation or a non-persisted WCAG 2.2 AA draft."""
    row = conn.execute(
        "SELECT id, scan_id, target_standard, target_level, purpose, scope_included, "
        "scope_excluded, sample_description, reviewer, methods_note, limitations, "
        "status, created_at, updated_at FROM evaluation_reports WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    if row is not None:
        return {**dict(row), "exists": True}
    return {
        "id": None,
        "scan_id": scan_id,
        **_DEFAULT_EVALUATION,
        "created_at": None,
        "updated_at": None,
        "exists": False,
    }


def upsert_evaluation(
    conn: sqlite3.Connection,
    scan_id: int,
    values: dict[str, str],
) -> dict[str, Any]:
    """Create or update the evaluation metadata for one scan."""
    merged = {**_DEFAULT_EVALUATION, **values}
    if merged["target_level"] not in {"A", "AA", "AAA"}:
        raise ValueError("target_level must be A, AA, or AAA")
    if merged["status"] not in EVALUATION_STATUSES:
        raise ValueError("invalid evaluation status")
    conn.execute(
        """
        INSERT INTO evaluation_reports (
            scan_id, target_standard, target_level, purpose, scope_included,
            scope_excluded, sample_description, reviewer, methods_note,
            limitations, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scan_id) DO UPDATE SET
            target_standard = excluded.target_standard,
            target_level = excluded.target_level,
            purpose = excluded.purpose,
            scope_included = excluded.scope_included,
            scope_excluded = excluded.scope_excluded,
            sample_description = excluded.sample_description,
            reviewer = excluded.reviewer,
            methods_note = excluded.methods_note,
            limitations = excluded.limitations,
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            scan_id,
            merged["target_standard"],
            merged["target_level"],
            merged["purpose"],
            merged["scope_included"],
            merged["scope_excluded"],
            merged["sample_description"],
            merged["reviewer"],
            merged["methods_note"],
            merged["limitations"],
            merged["status"],
        ),
    )
    return get_evaluation(conn, scan_id)


def _ensure_evaluation_id(conn: sqlite3.Connection, scan_id: int) -> int:
    evaluation = get_evaluation(conn, scan_id)
    if evaluation["id"] is None:
        evaluation = upsert_evaluation(conn, scan_id, {})
    return int(evaluation["id"])


def list_manual_checks(conn: sqlite3.Connection, scan_id: int) -> list[dict[str, Any]]:
    """Return the complete WCAG A/AA matrix with persisted expert outcomes."""
    evaluation = get_evaluation(conn, scan_id)
    result_rows: list[sqlite3.Row] = []
    evidence_by_result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if evaluation["id"] is not None:
        result_rows = conn.execute(
            "SELECT id, criterion_sc, outcome, rationale, tested_at, updated_at "
            "FROM manual_check_results WHERE evaluation_report_id = ?",
            (evaluation["id"],),
        ).fetchall()
        evidence_rows = conn.execute(
            """
            SELECT e.id, e.manual_check_result_id, e.page_id, e.evidence_url,
                   e.note, e.created_at, p.url_normalized AS page_url
              FROM manual_check_evidence e
              LEFT JOIN pages p ON p.id = e.page_id
             WHERE e.manual_check_result_id IN (
                 SELECT id FROM manual_check_results WHERE evaluation_report_id = ?
             )
             ORDER BY e.id
            """,
            (evaluation["id"],),
        ).fetchall()
        for row in evidence_rows:
            evidence_by_result[int(row["manual_check_result_id"])].append(dict(row))
    by_sc = {str(row["criterion_sc"]): row for row in result_rows}
    checks: list[dict[str, Any]] = []
    for criterion in coverage_matrix.load_matrix():
        result = by_sc.get(criterion.sc)
        result_id = int(result["id"]) if result is not None else None
        checks.append(
            {
                "criterion": {
                    "sc": criterion.sc,
                    "name": criterion.name,
                    "level": criterion.level,
                    "method": criterion.method,
                    "confidence": criterion.confidence,
                    "automated_check": criterion.automated_check,
                    "manual_check": criterion.manual_check,
                },
                "result_id": result_id,
                "outcome": str(result["outcome"]) if result is not None else "not_started",
                "rationale": str(result["rationale"]) if result is not None else "",
                "tested_at": result["tested_at"] if result is not None else None,
                "updated_at": result["updated_at"] if result is not None else None,
                "evidence": evidence_by_result.get(result_id, []) if result_id is not None else [],
            }
        )
    return checks


def update_manual_check(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    criterion_sc: str,
    outcome: str,
    rationale: str,
) -> dict[str, Any]:
    """Persist an expert outcome after validating it against the coverage matrix."""
    if coverage_matrix.by_sc(criterion_sc) is None:
        raise ValueError("Unknown WCAG criterion")
    if outcome not in OUTCOMES:
        raise ValueError("Unknown manual-check outcome")
    evaluation_id = _ensure_evaluation_id(conn, scan_id)
    conn.execute(
        """
        INSERT INTO manual_check_results (
            evaluation_report_id, criterion_sc, outcome, rationale, tested_at
        )
        VALUES (?, ?, ?, ?, CASE WHEN ? = 'not_started' THEN NULL ELSE CURRENT_TIMESTAMP END)
        ON CONFLICT(evaluation_report_id, criterion_sc) DO UPDATE SET
            outcome = excluded.outcome,
            rationale = excluded.rationale,
            tested_at = CASE
                WHEN excluded.outcome = 'not_started' THEN NULL
                ELSE CURRENT_TIMESTAMP
            END,
            updated_at = CURRENT_TIMESTAMP
        """,
        (evaluation_id, criterion_sc, outcome, rationale, outcome),
    )
    return next(
        check
        for check in list_manual_checks(conn, scan_id)
        if check["criterion"]["sc"] == criterion_sc
    )


def add_manual_evidence(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    criterion_sc: str,
    note: str,
    page_id: int | None,
    evidence_url: str,
) -> dict[str, Any]:
    """Attach a bounded expert note to one manual criterion.

    If a page is referenced, it must belong to the report's scan. This is the
    same scope guard used by the page-evidence endpoint.
    """
    if coverage_matrix.by_sc(criterion_sc) is None:
        raise ValueError("Unknown WCAG criterion")
    if page_id is not None:
        row = conn.execute(
            "SELECT 1 FROM pages WHERE id = ? AND scan_id = ?", (page_id, scan_id)
        ).fetchone()
        if row is None:
            raise ValueError("Page is not part of this report")
    evaluation_id = _ensure_evaluation_id(conn, scan_id)
    conn.execute(
        "INSERT INTO manual_check_results (evaluation_report_id, criterion_sc) VALUES (?, ?) "
        "ON CONFLICT(evaluation_report_id, criterion_sc) DO NOTHING",
        (evaluation_id, criterion_sc),
    )
    result = conn.execute(
        "SELECT id FROM manual_check_results WHERE evaluation_report_id = ? AND criterion_sc = ?",
        (evaluation_id, criterion_sc),
    ).fetchone()
    if result is None:  # pragma: no cover - protected by INSERT above
        raise RuntimeError("Could not create manual check record")
    cur = conn.execute(
        "INSERT INTO manual_check_evidence (manual_check_result_id, page_id, evidence_url, note) "
        "VALUES (?, ?, ?, ?)",
        (int(result["id"]), page_id, evidence_url, note),
    )
    evidence = conn.execute(
        "SELECT id, manual_check_result_id, page_id, evidence_url, note, created_at "
        "FROM manual_check_evidence WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    if evidence is None:  # pragma: no cover - protected by INSERT above
        raise RuntimeError("Could not create manual evidence record")
    return dict(evidence)


def get_page_evidence(
    conn: sqlite3.Connection, *, scan_id: int, page_id: int
) -> dict[str, Any] | None:
    """Return scan-scoped page metadata and its machine evidence."""
    page = conn.execute(
        "SELECT id, scan_id, url_normalized, title, status_code, render_mode, fetched_at "
        "FROM pages WHERE id = ? AND scan_id = ?",
        (page_id, scan_id),
    ).fetchone()
    if page is None:
        return None
    findings = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, pipeline, rule_id, criterion_sc, wcag_sc, wcag_level,
                   impact, help, target_selector, failure_summary, html_snippet,
                   status, screenshot_hash
              FROM page_a11y_findings
             WHERE page_id = ? AND scan_id = ?
             ORDER BY CASE impact WHEN 'critical' THEN 0 WHEN 'serious' THEN 1
                                  WHEN 'moderate' THEN 2 WHEN 'minor' THEN 3 ELSE 4 END,
                      id
            """,
            (page_id, scan_id),
        ).fetchall()
    ]
    images = [
        dict(row)
        for row in conn.execute(
            """
            SELECT pi.id AS occurrence_id, pi.alt_text, pi.context_snippet, pi.position,
                   pi.above_fold, i.content_hash, i.src_url_canonical, i.mime,
                   a.ocr_text, a.vlm_classification, a.vlm_rationale
              FROM page_images pi
              JOIN images i ON i.id = pi.image_id
              LEFT JOIN analyses a ON a.image_id = i.id
             WHERE pi.page_id = ?
             ORDER BY pi.position, a.analyzed_at DESC
            """,
            (page_id,),
        ).fetchall()
    ]
    return {"page": dict(page), "a11y_findings": findings, "image_occurrences": images}
