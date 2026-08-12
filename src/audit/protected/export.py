"""Redacted, in-memory exports for authorized protected reports.

This module deliberately does *not* reuse the normal export collector.  That
collector includes page URLs, selectors, OCR and other evidence that public
reports are expected to carry.  A protected export is a narrowly scoped
operational summary built only from the non-sensitive protected issue index.

The rendered value is returned to the caller as bytes in memory.  Callers
must not write it to a server-side temporary file or store it as an artifact;
the recipient's browser download is the only copy Axcess creates.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

from audit import coverage_matrix, evaluation
from audit.protected.models import ProtectedScanRecord, ProtectedScanStatus


class ProtectedExportError(ValueError):
    """A protected report is not eligible for a redacted handoff."""


_MAX_ISSUE_GROUPS: Final = 250
_RULE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_WCAG_SC = re.compile(r"^\d\.\d\.\d$")
_PIPELINE_LABELS: Final = {
    "axe": "axe-core",
    "alfa": "Alfa",
    "keyboard": "Keyboard probe",
    "responsive": "Responsive probe",
    "focus": "Focus probe",
    "protected_image": "Protected in-memory image lead",
}
_IMPACTS: Final = frozenset({"critical", "serious", "moderate", "minor"})
_OUTCOMES: Final = frozenset({"failed", "cant_tell"})
_MANUAL_OUTCOME_LABELS: Final = {
    "not_started": "Not started",
    "pass": "Pass",
    "fail": "Fail",
    "not_tested": "Not tested",
    "needs_follow_up": "Needs follow-up",
}


def render_redacted_protected_report(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    record: ProtectedScanRecord,
    generated_at: datetime | None = None,
) -> str:
    """Render a bounded protected handoff without reading raw evidence.

    The report intentionally omits the seed URL, approved origins, page
    aliases, page titles, selectors, snippets, screenshots, OCR/VLM text,
    attachment metadata, browser state, and auditor/owner names.  Even if a
    database is manually contaminated with such data, this renderer only
    selects whitelisted aggregate fields and validates each value again before
    adding it to the Markdown.
    """

    if scan_id <= 0 or record.scan_id != scan_id:
        raise ProtectedExportError("Protected report is unavailable.")
    if record.protection_status is not ProtectedScanStatus.COMPLETED:
        raise ProtectedExportError("Protected reports can be exported only after completion.")
    if not record.is_evidence_available:
        raise ProtectedExportError(
            "Protected evidence is unavailable after its retention deadline."
        )

    scan = conn.execute(
        """
        SELECT page_count, axe_pages_scanned, axe_violations_total,
               alfa_pages_scanned, alfa_failed_total, alfa_cant_tell_total
          FROM scans
         WHERE id = ?
        """,
        (scan_id,),
    ).fetchone()
    if scan is None:
        raise ProtectedExportError("Protected report is unavailable.")

    rows = conn.execute(
        """
        SELECT pipeline, rule_id, wcag_sc, wcag_level, impact, engine_outcome,
               COUNT(*) AS occurrence_count, COUNT(DISTINCT page_id) AS page_count
          FROM page_a11y_findings
         WHERE scan_id = ?
         GROUP BY pipeline, rule_id, wcag_sc, wcag_level, impact, engine_outcome
         ORDER BY occurrence_count DESC, page_count DESC, pipeline ASC, rule_id ASC
         LIMIT ?
        """,
        (scan_id, _MAX_ISSUE_GROUPS),
    ).fetchall()
    # This is deliberately the protected, outcome-only projection.  It never
    # loads free-text rationale, page references, or manual-evidence records.
    manual_checks = evaluation.list_manual_check_outcomes(conn, scan_id)

    created = (generated_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    lines = [
        "# Axcess protected report — redacted operational summary",
        "",
        "**Handling:** Protected. This download is intentionally redacted and must be "
        "handled according to the report's approved data classification.",
        "",
        "This is not a conformance claim. Automated results are review leads; "
        "manual verification remains required.",
        "",
        "## Export boundary",
        "",
        "This in-memory download omits target URLs, approved origins, page aliases, "
        "page titles, selectors, HTML, screenshots, OCR/VLM text, attachments, browser "
        "state, credentials, session material, target-owner details, and auditor identity.",
        "Axcess does not write this generated export to server storage or a temporary file.",
        "",
        "## Report metadata",
        "",
        f"- Report ID: `{scan_id}`",
        f"- Environment: `{record.environment.value}`",
        f"- Data classification: `{record.data_classification.value}`",
        f"- Protected workflow status: `{record.protection_status.value}`",
        f"- Generated (UTC): `{created}`",
        f"- Detailed-evidence retention deadline (UTC): `{record.cleanup_at.isoformat()}`",
        "",
        "## Coverage summary",
        "",
        f"- Pages indexed: {_safe_count(scan['page_count'])}",
        f"- axe-core pages evaluated: {_safe_count(scan['axe_pages_scanned'])}",
        f"- axe-core detected occurrences: {_safe_count(scan['axe_violations_total'])}",
        f"- Alfa pages evaluated: {_safe_count(scan['alfa_pages_scanned'])}",
        f"- Alfa failed outcomes: {_safe_count(scan['alfa_failed_total'])}",
        f"- Alfa `cant_tell` outcomes: {_safe_count(scan['alfa_cant_tell_total'])}",
        "",
        "## Manually documented WCAG check outcomes",
        "",
        "These outcomes are manually documented by the authorized reviewer; they are not "
        "automated test results or conformance determinations. This redacted export contains "
        "only the criterion and outcome, with no supporting review detail.",
        "",
        "| WCAG SC | Criterion | Level | Manually documented outcome |",
        "| --- | --- | --- | --- |",
    ]

    if manual_checks:
        for check in manual_checks:
            lines.append(_manual_check_row(check))
    else:  # pragma: no cover - the validated WCAG matrix is always populated
        lines.append("| — | No WCAG manual-check matrix available | — | — |")

    lines.extend(
        [
            "",
            "## Redacted issue index",
            "",
            "The index is grouped by source and rule. It deliberately does not identify "
            "affected pages or include raw evidence.",
            "",
            "| Source layer | Rule | WCAG SC | Level | Outcome | Impact | Occurrences | "
            "Indexed pages |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: |",
        ]
    )

    if rows:
        for row in rows:
            lines.append(_issue_row(row))
    else:
        lines.append("| No retained issue index rows | — | — | — | — | — | 0 | 0 |")
    if len(rows) == _MAX_ISSUE_GROUPS:
        lines.extend(
            [
                "",
                f"Only the first {_MAX_ISSUE_GROUPS} issue groups are included in this "
                "redacted export. Review the protected report directly for the complete index.",
            ]
        )

    lines.extend(
        [
            "",
            "## Verification and sharing",
            "",
            "Verify each remediated item in the protected report with the same authorized "
            "account and approved scope. Do not attach this file, its contents, a pairing code, "
            "or browser evidence to public tickets or external chat. Downloaded copies are the "
            "recipient's responsibility; Axcess retains no server-side generated export.",
            "",
        ]
    )
    return "\n".join(lines)


def _issue_row(row: sqlite3.Row) -> str:
    """Return one markdown-safe group row, degrading corrupted fields safely."""

    pipeline = str(row["pipeline"] or "")
    source = _PIPELINE_LABELS.get(pipeline, "Protected source unavailable")
    rule_id = str(row["rule_id"] or "")
    safe_rule = rule_id if _RULE_ID.fullmatch(rule_id) else "unavailable"
    wcag_sc = str(row["wcag_sc"] or "")
    safe_sc = wcag_sc if _WCAG_SC.fullmatch(wcag_sc) else "—"
    level = str(row["wcag_level"] or "")
    safe_level = level if level in {"A", "AA", "AAA"} else "—"
    outcome = str(row["engine_outcome"] or "")
    safe_outcome = outcome if outcome in _OUTCOMES else "—"
    impact = str(row["impact"] or "")
    safe_impact = impact if impact in _IMPACTS else "—"
    return (
        f"| {source} | `{safe_rule}` | {safe_sc} | {safe_level} | {safe_outcome} | "
        f"{safe_impact} | {_safe_count(row['occurrence_count'])} | "
        f"{_safe_count(row['page_count'])} |"
    )


def _manual_check_row(check: Mapping[str, Any]) -> str:
    """Render only a static criterion label and a bounded manual outcome.

    ``list_manual_check_outcomes`` returns the coverage-matrix projection, but
    this second lookup deliberately ignores its human-readable prose fields.
    That keeps a contaminated database row or a future caller from turning a
    protected export into a carrier for reviewer notes.
    """

    raw_criterion = check.get("criterion")
    raw_sc = raw_criterion.get("sc") if isinstance(raw_criterion, Mapping) else ""
    sc = str(raw_sc or "")
    criterion = coverage_matrix.by_sc(sc) if _WCAG_SC.fullmatch(sc) else None
    outcome = _MANUAL_OUTCOME_LABELS.get(str(check.get("outcome") or ""), "—")
    if criterion is None:
        return f"| — | Unavailable | — | {outcome} |"
    return f"| {criterion.sc} | {criterion.name} | {criterion.level} | {outcome} |"


def _safe_count(value: object) -> int:
    """Keep aggregate fields bounded even if a database is manually modified."""

    try:
        if isinstance(value, (int, float, str, bytes, bytearray)):
            parsed = int(value)
        else:
            return 0
        return max(0, min(parsed, 10_000_000))
    except (TypeError, ValueError):
        return 0
