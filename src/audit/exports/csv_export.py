"""CSV export — flat, one row per atomic finding.

Two finding kinds coexist in the same CSV, distinguished by the
``finding_kind`` column:

* ``image_of_text`` — one row per (finding, occurrence) for the WCAG
  1.4.5 pipeline. Original column set is preserved unchanged so
  existing Jira / Excel import scripts that ignore the new
  ``finding_kind`` column keep working.
* ``wcag_axe`` — one row per axe DOM violation. Image-pipeline columns
  (``image_url``, ``ocr_text``, etc.) are blank for these; the axe-only
  columns (``rule_id``, ``wcag_sc``, ``target_selector``…) are blank for
  the image rows.

Filtering in Excel / a CSV reader is a single equality check on
``finding_kind``. Sorting by ``severity`` works across kinds because
both pipelines emit values from a known enum.
"""

from __future__ import annotations

import csv
import io

from audit.exports.collector import ExportA11yFinding, ExportFinding, ExportScan

CSV_COLUMNS = (
    "finding_kind",
    "finding_id",
    # Shared / unified columns
    "severity",  # image: critical|major|minor|info  ·  axe: critical|serious|moderate|minor
    "status",
    "wcag_criterion",  # image: "1.4.5" · axe: SC like "1.4.3"
    "wcag_level",  # axe only: A|AA|AAA
    "page_url",
    "ui_url",
    # Image-of-text-specific
    "priority_score",
    "classification",
    "alt_adequacy",
    "alt_text",
    "above_fold",
    "image_url",
    "content_hash",
    "ocr_text",
    "ocr_confidence",
    "vlm_rationale",
    "remediation_hint",
    # WCAG axe-specific
    "rule_id",
    "target_selector",
    "failure_summary",
    "help_url",
)


def render_csv(scan: ExportScan) -> str:
    """Return the CSV body for ``scan``.

    Image-of-text findings are emitted first, then axe findings,
    matching the order a reviewer would read them in the UI (image
    findings have a curated priority score; axe rows are bulk DOM
    findings the reviewer triages second).
    """
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)

    for finding in scan.findings:
        if not finding.occurrences:
            writer.writerow(_image_row(finding, page_url="", alt_text=None, above_fold=False))
            continue
        for occ in finding.occurrences:
            writer.writerow(
                _image_row(
                    finding,
                    page_url=occ.page_url,
                    alt_text=occ.alt_text,
                    above_fold=occ.above_fold,
                )
            )

    for af in scan.a11y_findings:
        writer.writerow(_axe_row(af))

    return buf.getvalue()


def _image_row(
    finding: ExportFinding,
    *,
    page_url: str,
    alt_text: str | None,
    above_fold: bool,
) -> list[str]:
    return [
        "image_of_text",
        str(finding.id),
        finding.severity,
        finding.status,
        finding.wcag_criterion,
        "",  # wcag_level — N/A for image findings
        page_url,
        finding.ui_url,
        f"{finding.priority_score:.3f}",
        finding.vlm_classification or "",
        finding.alt_adequacy,
        "" if alt_text is None else alt_text,
        "true" if above_fold else "false",
        finding.image_url,
        finding.content_hash,
        _one_line(finding.ocr_text),
        "" if finding.ocr_confidence is None else f"{finding.ocr_confidence:.2f}",
        _one_line(finding.vlm_rationale),
        _one_line(finding.remediation_hint),
        # WCAG axe columns left blank
        "",
        "",
        "",
        "",
    ]


def _axe_row(af: ExportA11yFinding) -> list[str]:
    return [
        "wcag_axe",
        str(af.id),
        af.impact or "",
        af.status,
        # We deliberately surface axe's primary WCAG SC under
        # `wcag_criterion` (the same column that holds "1.4.5" for image
        # findings) so a developer filtering by criterion sees both
        # pipelines on the same axis.
        af.wcag_sc or "",
        af.wcag_level or "",
        af.page_url,
        af.ui_url,
        # Image-of-text columns left blank
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        # WCAG axe-specific
        af.rule_id,
        af.target_selector,
        _one_line(af.failure_summary),
        af.help_url,
    ]


def _one_line(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())
