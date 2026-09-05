"""Synthesize per-image findings for a completed scan.

For every image that has either inline SVG text or an OCR text-candidate
analysis, collect its occurrences across pages, derive the visible text,
compare against each occurrence's alt, compute a priority score and
severity, and upsert a single findings row keyed on ``(image_id, scan_id)``.

Runs once at end of crawl (or via ``audit synthesize``). Idempotent: repeat
runs with the same inputs produce the same rows.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from audit.analyzer.vlm.base import VlmLabel
from audit.db import repo
from audit.logging import get_logger
from audit.synthesizer.alt_compare import compare, worst
from audit.synthesizer.diff import materialize_history
from audit.synthesizer.priority import compute_priority_score, severity_for
from audit.synthesizer.rules import RemediationRules

log = get_logger(__name__)


def _zero_severity_counts() -> dict[str, int]:
    return {"critical": 0, "major": 0, "minor": 0, "info": 0}


@dataclass
class SynthesizeResult:
    """Summary returned to the CLI / orchestrator."""

    findings_written: int = 0
    by_severity: dict[str, int] = field(default_factory=_zero_severity_counts)
    first_seen: int = 0
    resolved: int = 0


def synthesize_findings(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    rules: RemediationRules | None = None,
    compare_to: int | None = None,
) -> SynthesizeResult:
    """Compute findings for every image-with-text in ``scan_id``.

    When ``compare_to`` is another scan id, first-seen / resolved rows are
    written to ``finding_history`` so the UI's diff view has a durable
    record of appearances and disappearances across rescans.
    """
    rules = rules or RemediationRules.load()
    result = SynthesizeResult()

    for image_row in _images_with_text(conn, scan_id):
        image_id = int(image_row["id"])
        has_svg_text = bool(image_row["has_svg_text"])
        ocr_text = image_row["ocr_text"] or ""
        classification = _to_label(image_row["vlm_classification"])

        occurrences = _page_image_rows(conn, scan_id=scan_id, image_id=image_id)
        if not occurrences:
            continue

        # Visible text for alt comparison: prefer OCR, fall back to the
        # snippet captured for the SVG-text case.
        svg_snippet = occurrences[0]["context_snippet"] or "" if has_svg_text else ""
        visible_text = ocr_text or svg_snippet

        adequacy = worst([compare(row["alt_text"], visible_text) for row in occurrences])
        above_fold = any(bool(row["above_fold"]) for row in occurrences)
        occurrence_count = len({int(row["page_id"]) for row in occurrences})

        priority = compute_priority_score(
            classification=classification,
            adequacy=adequacy,
            occurrence_count=occurrence_count,
            above_fold=above_fold,
        )
        severity = severity_for(priority)
        hint = rules.lookup(classification.value if classification else None, adequacy)

        repo.upsert_finding(
            conn,
            image_id=image_id,
            scan_id=scan_id,
            severity=severity.value,
            priority_score=priority,
            remediation_hint=hint,
        )

        result.findings_written += 1
        result.by_severity[severity.value] = result.by_severity.get(severity.value, 0) + 1

    _refresh_scan_finding_count(conn, scan_id)

    if compare_to is not None and compare_to != scan_id:
        history_counts = materialize_history(
            conn,
            current_scan_id=scan_id,
            compare_to_scan_id=compare_to,
        )
        result.first_seen = history_counts.get("first_seen", 0)
        result.resolved = history_counts.get("resolved", 0)

    return result


def _images_with_text(conn: sqlite3.Connection, scan_id: int) -> list[sqlite3.Row]:
    """Images in this scan that are SVG-text or have an OCR text candidate.

    Picks the most-recent analysis row per image, prefer a row that has a
    VLM classification over an OCR-only one.
    """
    rows = conn.execute(
        """
        WITH best AS (
            SELECT a.image_id,
                   a.ocr_text,
                   a.vlm_classification,
                   a.has_text,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.image_id
                       ORDER BY
                           CASE WHEN a.vlm_classification IS NOT NULL THEN 0 ELSE 1 END,
                           a.analyzed_at DESC,
                           a.id DESC
                   ) AS rank
              FROM analyses a
        )
        SELECT i.id,
               i.has_svg_text,
               b.ocr_text,
               b.vlm_classification,
               b.has_text
          FROM images i
          LEFT JOIN best b ON b.image_id = i.id AND b.rank = 1
         WHERE i.id IN (
               SELECT pi.image_id FROM page_images pi
               JOIN pages p ON p.id = pi.page_id
               WHERE p.scan_id = ?
         )
         AND (
               i.has_svg_text = 1
            OR b.has_text = 1
         )
        """,
        (scan_id,),
    ).fetchall()
    return list(rows)


def _page_image_rows(conn: sqlite3.Connection, *, scan_id: int, image_id: int) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT pi.page_id, pi.alt_text, pi.above_fold, pi.context_snippet
          FROM page_images pi
          JOIN pages p ON p.id = pi.page_id
         WHERE p.scan_id = ? AND pi.image_id = ?
        """,
        (scan_id, image_id),
    ).fetchall()
    return list(rows)


def _refresh_scan_finding_count(conn: sqlite3.Connection, scan_id: int) -> None:
    conn.execute(
        """
        UPDATE scans
           SET finding_count = (SELECT COUNT(*) FROM findings WHERE scan_id = ?)
         WHERE id = ?
        """,
        (scan_id, scan_id),
    )


def _to_label(raw: str | None) -> VlmLabel | None:
    if not raw:
        return None
    try:
        return VlmLabel(raw)
    except ValueError:
        log.warning("synthesize.unknown_vlm_label", label=raw)
        return None
