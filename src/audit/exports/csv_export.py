"""CSV export — flat, one row per (finding, occurrence) pair."""

from __future__ import annotations

import csv
import io

from audit.exports.collector import ExportFinding, ExportScan

CSV_COLUMNS = (
    "finding_id",
    "severity",
    "priority_score",
    "status",
    "wcag_criterion",
    "classification",
    "alt_adequacy",
    "page_url",
    "alt_text",
    "above_fold",
    "image_url",
    "content_hash",
    "ocr_text",
    "ocr_confidence",
    "vlm_rationale",
    "remediation_hint",
    "ui_url",
)


def render_csv(scan: ExportScan) -> str:
    """Return the CSV body as a string.

    One header row plus one data row per ``(finding, occurrence)``. Findings
    with no occurrences still produce a single row so nothing is silently
    dropped on export.
    """
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)

    for finding in scan.findings:
        if not finding.occurrences:
            writer.writerow(_row(finding, page_url="", alt_text=None, above_fold=False))
            continue
        for occ in finding.occurrences:
            writer.writerow(
                _row(
                    finding,
                    page_url=occ.page_url,
                    alt_text=occ.alt_text,
                    above_fold=occ.above_fold,
                )
            )
    return buf.getvalue()


def _row(
    finding: ExportFinding,
    *,
    page_url: str,
    alt_text: str | None,
    above_fold: bool,
) -> list[str]:
    return [
        str(finding.id),
        finding.severity,
        f"{finding.priority_score:.3f}",
        finding.status,
        finding.wcag_criterion,
        finding.vlm_classification or "",
        finding.alt_adequacy,
        page_url,
        "" if alt_text is None else alt_text,
        "true" if above_fold else "false",
        finding.image_url,
        finding.content_hash,
        _one_line(finding.ocr_text),
        ""
        if finding.ocr_confidence is None
        else f"{finding.ocr_confidence:.2f}",
        _one_line(finding.vlm_rationale),
        _one_line(finding.remediation_hint),
        finding.ui_url,
    ]


def _one_line(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())
