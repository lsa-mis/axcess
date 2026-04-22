"""Shared data collector for every export format.

One DB query pass produces a list of :class:`ExportFinding` rows with every
piece of context an export needs — severity, classification, OCR + VLM
text, remediation hint, all occurrences on the scanned site, and a deep
link back into the local review UI.

Keeping the export surface flat means CSV/JSON/Jira/Markdown each just
render the same collected structure without re-joining tables.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any

from audit.synthesizer.alt_compare import AltAdequacy, compare, worst

DEFAULT_UI_BASE = "http://127.0.0.1:8765"


@dataclass(frozen=True)
class ExportOccurrence:
    """One ``(page, image, position)`` occurrence of a finding's image."""

    page_id: int
    page_url: str
    alt_text: str | None
    above_fold: bool
    position: int


@dataclass(frozen=True)
class ExportFinding:
    """Flat per-finding record ready to render in any export format."""

    id: int
    scan_id: int
    severity: str
    status: str
    priority_score: float
    wcag_criterion: str
    vlm_classification: str | None
    vlm_rationale: str | None
    alt_adequacy: str
    ocr_text: str | None
    ocr_confidence: float | None
    remediation_hint: str | None
    image_url: str
    content_hash: str
    mime: str | None
    has_svg_text: bool
    occurrences: list[ExportOccurrence] = field(default_factory=list)
    ui_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Recursive dict form (used by JSON export)."""
        return {
            **asdict(self),
            "occurrences": [asdict(o) for o in self.occurrences],
        }


@dataclass(frozen=True)
class ExportScan:
    """Scan-level metadata paired with its findings."""

    id: int
    seed_url: str
    status: str
    started_at: str | None
    finished_at: str | None
    page_count: int
    finding_count: int
    error_count: int
    findings: list[ExportFinding]
    by_severity: dict[str, int]


def collect_scan(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    ui_base_url: str = DEFAULT_UI_BASE,
) -> ExportScan:
    """Load a scan + all of its findings into a render-ready structure."""
    scan_row = conn.execute(
        "SELECT id, seed_url, status, started_at, finished_at, page_count, "
        "finding_count, error_count FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if scan_row is None:
        raise ValueError(f"Scan {scan_id} not found")

    findings = _collect_findings(conn, scan_id, ui_base_url=ui_base_url)
    by_severity: dict[str, int] = {"critical": 0, "major": 0, "minor": 0, "info": 0}
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    return ExportScan(
        id=int(scan_row["id"]),
        seed_url=str(scan_row["seed_url"]),
        status=str(scan_row["status"]),
        started_at=_to_iso(scan_row["started_at"]),
        finished_at=_to_iso(scan_row["finished_at"]),
        page_count=int(scan_row["page_count"]),
        finding_count=int(scan_row["finding_count"]),
        error_count=int(scan_row["error_count"]),
        findings=findings,
        by_severity=by_severity,
    )


def _collect_findings(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    ui_base_url: str,
) -> list[ExportFinding]:
    rows = conn.execute(
        """
        WITH best AS (
            SELECT a.image_id,
                   a.ocr_text,
                   a.ocr_confidence,
                   a.vlm_classification,
                   a.vlm_rationale,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.image_id
                       ORDER BY
                           CASE WHEN a.vlm_classification IS NOT NULL THEN 0 ELSE 1 END,
                           a.analyzed_at DESC,
                           a.id DESC
                   ) AS rank
              FROM analyses a
        )
        SELECT f.id, f.scan_id, f.severity, f.status, f.priority_score,
               f.wcag_criterion, f.remediation_hint,
               i.id AS image_id, i.content_hash, i.mime, i.src_url_canonical,
               i.has_svg_text,
               b.ocr_text, b.ocr_confidence, b.vlm_classification, b.vlm_rationale
          FROM findings f
          JOIN images i ON i.id = f.image_id
          LEFT JOIN best b ON b.image_id = i.id AND b.rank = 1
         WHERE f.scan_id = ?
         ORDER BY f.priority_score DESC, f.id ASC
        """,
        (scan_id,),
    ).fetchall()

    findings: list[ExportFinding] = []
    for row in rows:
        occurrences = _collect_occurrences(
            conn, scan_id=scan_id, image_id=int(row["image_id"])
        )
        ocr_text = row["ocr_text"] or ""
        adequacy = worst(
            [compare(occ.alt_text, ocr_text) for occ in occurrences]
        ) if occurrences else AltAdequacy.MISSING
        findings.append(
            ExportFinding(
                id=int(row["id"]),
                scan_id=int(row["scan_id"]),
                severity=str(row["severity"]),
                status=str(row["status"]),
                priority_score=float(row["priority_score"]),
                wcag_criterion=str(row["wcag_criterion"]),
                vlm_classification=row["vlm_classification"],
                vlm_rationale=row["vlm_rationale"],
                alt_adequacy=adequacy.value,
                ocr_text=row["ocr_text"],
                ocr_confidence=(
                    float(row["ocr_confidence"])
                    if row["ocr_confidence"] is not None
                    else None
                ),
                remediation_hint=row["remediation_hint"],
                image_url=str(row["src_url_canonical"]),
                content_hash=str(row["content_hash"]),
                mime=row["mime"],
                has_svg_text=bool(row["has_svg_text"]),
                occurrences=occurrences,
                ui_url=f"{ui_base_url.rstrip('/')}/findings/{row['id']}",
            )
        )
    return findings


def _collect_occurrences(
    conn: sqlite3.Connection, *, scan_id: int, image_id: int
) -> list[ExportOccurrence]:
    rows = conn.execute(
        """
        SELECT pi.page_id, pi.alt_text, pi.above_fold, pi.position,
               p.url_normalized AS page_url
          FROM page_images pi
          JOIN pages p ON p.id = pi.page_id
         WHERE pi.image_id = ? AND p.scan_id = ?
         ORDER BY pi.position
        """,
        (image_id, scan_id),
    ).fetchall()
    return [
        ExportOccurrence(
            page_id=int(r["page_id"]),
            page_url=str(r["page_url"]),
            alt_text=r["alt_text"],
            above_fold=bool(r["above_fold"]),
            position=int(r["position"]),
        )
        for r in rows
    ]


def _to_iso(value: Any) -> str | None:
    """Coerce sqlite timestamp values to a stable ISO-8601 string."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[no-any-return]
    return str(value)
