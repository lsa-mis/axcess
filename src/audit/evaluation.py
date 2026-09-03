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

_COMPLETION_CONTEXT_FIELDS: tuple[tuple[str, str], ...] = (
    ("reviewer", "reviewer"),
    ("purpose", "purpose"),
    ("scope_included", "included scope"),
    ("methods_note", "methods used"),
    ("limitations", "limitations"),
)

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


class EvaluationCompletionError(ValueError):
    """An evaluation cannot enter or remain in an invalid completed state."""

    def __init__(self, blockers: list[str]) -> None:
        self.blockers = tuple(blockers)
        super().__init__("Evaluation cannot be completed. " + " ".join(blockers))


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
    if merged["status"] == "completed":
        blockers = evaluation_completion_blockers(conn, scan_id, merged)
        if blockers:
            raise EvaluationCompletionError(blockers)
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


def evaluation_completion_blockers(
    conn: sqlite3.Connection,
    scan_id: int,
    record: dict[str, Any],
) -> list[str]:
    """Explain every bounded condition preventing a final evaluation.

    A final state is a claim about review completeness, not merely a display
    preference. Required context must be explicit, every WCAG matrix row must
    have a terminal expert decision, and each decision must explain its basis.
    A ``not_tested`` rationale is the criterion-level documentation of that
    evaluation limitation; the report-level limitations field is required too.
    """

    blockers: list[str] = []
    missing_context = [
        label
        for field, label in _COMPLETION_CONTEXT_FIELDS
        if not str(record.get(field) or "").strip()
    ]
    if missing_context:
        blockers.append("Required context is missing: " + ", ".join(missing_context) + ".")

    checks = list_manual_checks(conn, scan_id)
    not_started = [
        check["criterion"]["sc"] for check in checks if check["outcome"] == "not_started"
    ]
    needs_follow_up = [
        check["criterion"]["sc"] for check in checks if check["outcome"] == "needs_follow_up"
    ]
    missing_rationale = [
        check["criterion"]["sc"]
        for check in checks
        if check["outcome"] != "not_started" and not str(check["rationale"] or "").strip()
    ]
    if not_started:
        blockers.append(_criterion_blocker(not_started, "not started"))
    if needs_follow_up:
        blockers.append(_criterion_blocker(needs_follow_up, "still need follow-up"))
    if missing_rationale:
        blockers.append(
            _criterion_blocker(
                missing_rationale,
                "have no rationale; Pass, Fail, Not tested, and Needs follow-up decisions "
                "require one",
            )
        )
    return blockers


def _criterion_blocker(criteria: list[str], description: str) -> str:
    """Return a bounded completion message with useful example criterion IDs."""

    preview = ", ".join(criteria[:5])
    suffix = f", and {len(criteria) - 5} more" if len(criteria) > 5 else ""
    noun = "criterion" if len(criteria) == 1 else "criteria"
    return f"{len(criteria)} manual {noun} {description}: {preview}{suffix}."


def list_manual_check_outcomes(conn: sqlite3.Connection, scan_id: int) -> list[dict[str, Any]]:
    """Return the WCAG matrix without loading any free-text review evidence.

    This projection is for constrained workflows such as protected reports,
    where an outcome is safe to retain but an evaluator's rationale, page
    reference, or evidence note must not be read from the public-report
    tables. It intentionally does *not* call :func:`list_manual_checks`.
    """

    # Do not use ``get_evaluation`` here. It intentionally selects the
    # public-report scope, reviewer, methods, and limitation prose, which a
    # protected outcome-only view must neither return *nor load at all*.
    evaluation_row = conn.execute(
        "SELECT id FROM evaluation_reports WHERE scan_id = ?", (scan_id,)
    ).fetchone()
    result_rows: list[sqlite3.Row] = []
    if evaluation_row is not None:
        result_rows = conn.execute(
            "SELECT criterion_sc, outcome, tested_at, updated_at "
            "FROM manual_check_results WHERE evaluation_report_id = ?",
            (int(evaluation_row["id"]),),
        ).fetchall()
    by_sc = {str(row["criterion_sc"]): row for row in result_rows}
    checks: list[dict[str, Any]] = []
    for criterion in coverage_matrix.load_matrix():
        result = by_sc.get(criterion.sc)
        checks.append(
            {
                "criterion": {
                    "sc": criterion.sc,
                    "name": criterion.name,
                    "level": criterion.level,
                    "method": criterion.method,
                    "manual_check": criterion.manual_check,
                },
                "outcome": str(result["outcome"]) if result is not None else "not_started",
                "tested_at": result["tested_at"] if result is not None else None,
                "updated_at": result["updated_at"] if result is not None else None,
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
    rationale = rationale.strip()
    if outcome != "not_started" and not rationale:
        raise ValueError(
            "A rationale is required for Pass, Fail, Not tested, and Needs follow-up decisions."
        )
    current_evaluation = get_evaluation(conn, scan_id)
    if current_evaluation["status"] == "completed" and outcome in {
        "not_started",
        "needs_follow_up",
    }:
        raise EvaluationCompletionError(
            [
                "Reopen the evaluation before setting a manual criterion to "
                f"{outcome.replace('_', ' ')}."
            ]
        )
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


def update_manual_check_outcome_only(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    criterion_sc: str,
    outcome: str,
) -> dict[str, Any]:
    """Persist a bounded manual result without accepting or loading prose.

    Existing public-report free text is overwritten with an empty rationale on
    this specific result. The function neither selects nor returns evidence
    rows, so callers can safely use it at a protected-report boundary.
    """

    if coverage_matrix.by_sc(criterion_sc) is None:
        raise ValueError("Unknown WCAG criterion")
    if outcome not in OUTCOMES:
        raise ValueError("Unknown manual-check outcome")
    # This dedicated helper avoids reading or copying an existing public
    # evaluation record's free-text fields into a protected workflow.
    evaluation_id = _ensure_evaluation_id_outcome_only(conn, scan_id)
    conn.execute(
        """
        INSERT INTO manual_check_results (
            evaluation_report_id, criterion_sc, outcome, rationale, tested_at
        )
        VALUES (?, ?, ?, '', CASE WHEN ? = 'not_started' THEN NULL ELSE CURRENT_TIMESTAMP END)
        ON CONFLICT(evaluation_report_id, criterion_sc) DO UPDATE SET
            outcome = excluded.outcome,
            rationale = '',
            tested_at = CASE
                WHEN excluded.outcome = 'not_started' THEN NULL
                ELSE CURRENT_TIMESTAMP
            END,
            updated_at = CURRENT_TIMESTAMP
        """,
        (evaluation_id, criterion_sc, outcome, outcome),
    )
    return next(
        check
        for check in list_manual_check_outcomes(conn, scan_id)
        if check["criterion"]["sc"] == criterion_sc
    )


def _ensure_evaluation_id_outcome_only(conn: sqlite3.Connection, scan_id: int) -> int:
    """Return/create an evaluation row without selecting its prose fields."""

    row = conn.execute("SELECT id FROM evaluation_reports WHERE scan_id = ?", (scan_id,)).fetchone()
    if row is not None:
        return int(row["id"])
    cur = conn.execute("INSERT INTO evaluation_reports (scan_id) VALUES (?)", (scan_id,))
    if cur.lastrowid is None:  # pragma: no cover - SQLite insert invariant
        raise RuntimeError("manual outcome evaluation record was not created")
    return int(cur.lastrowid)


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
                   status, screenshot_hash, engine_outcome, engine_evidence_json,
                   -- The control operated before this markup existed. Without
                   -- it the evidence page lists a dialog that does not exist
                   -- until something is clicked, alongside findings that are
                   -- present on load, with nothing to tell them apart.
                   revealed_by
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
