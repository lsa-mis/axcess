"""Jira-flavored CSV export.

Produces a CSV that Jira's "External system import" screen accepts with
sensible default mappings: Summary, Description, Priority, Labels,
Issue Type. The Description field bundles the finding's metadata in
Markdown-ish bullet points plus a deep-link back into the local review UI.

Tested against Jira Cloud's "CSV file" importer; other issue trackers
(Linear, YouTrack) accept similarly flat CSV so the same file usually
works after column-name remapping.
"""

from __future__ import annotations

import csv
import io

from audit.exports.collector import ExportFinding, ExportScan

JIRA_COLUMNS = (
    "Summary",
    "Description",
    "Priority",
    "Issue Type",
    "Labels",
    "Component",
)

# Jira's default priorities: Highest, High, Medium, Low, Lowest.
# Mapping ``info`` to Lowest keeps it off default dashboards without hiding it.
_SEVERITY_TO_PRIORITY = {
    "critical": "Highest",
    "major": "High",
    "minor": "Medium",
    "info": "Lowest",
}

_ISSUE_TYPE = "Bug"
_COMPONENT = "Accessibility"


def render_jira_csv(scan: ExportScan) -> str:
    """One Jira issue per finding. Multi-page findings list every page."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(JIRA_COLUMNS)
    for finding in scan.findings:
        writer.writerow(
            [
                _summary(finding),
                _description(finding),
                _SEVERITY_TO_PRIORITY.get(finding.severity, "Low"),
                _ISSUE_TYPE,
                " ".join(_labels(finding)),
                _COMPONENT,
            ]
        )
    return buf.getvalue()


def _summary(finding: ExportFinding) -> str:
    """Short, issue-tracker-friendly title."""
    hint = (finding.ocr_text or "").strip()
    if hint:
        hint = " ".join(hint.split())
        if len(hint) > 60:
            hint = hint[:57].rstrip() + "..."
        return f"WCAG 1.4.5: image of text — {hint}"
    if finding.has_svg_text:
        return f"WCAG 1.4.5: inline SVG with visible text ({finding.severity})"
    return f"WCAG 1.4.5: text in image — {finding.severity} ({finding.image_url})"


def _description(finding: ExportFinding) -> str:
    """Multi-line Markdown-lite description.

    Jira Cloud renders bullet lists and bolding from wiki / Markdown input
    well enough for a non-curated issue; Linear and YouTrack do too.
    """
    lines: list[str] = []
    lines.append(f"**Severity:** {finding.severity}  (priority score {finding.priority_score:.2f})")
    lines.append(f"**Criterion:** WCAG {finding.wcag_criterion}")
    if finding.vlm_classification:
        lines.append(f"**Classification:** {finding.vlm_classification}")
    lines.append(f"**Alt adequacy:** {finding.alt_adequacy}")
    lines.append(f"**Image URL:** {finding.image_url}")
    if finding.ocr_text:
        lines.append(f"**OCR text:** {finding.ocr_text}")
    if finding.vlm_rationale:
        lines.append(f"**VLM rationale:** {finding.vlm_rationale}")
    if finding.remediation_hint:
        lines.append(f"**Suggested fix:** {finding.remediation_hint}")

    lines.append("")
    lines.append("**Occurrences:**")
    if not finding.occurrences:
        lines.append("  - (no occurrences recorded)")
    for occ in finding.occurrences:
        alt = "(missing)" if occ.alt_text is None else occ.alt_text or "(empty)"
        fold = " (above fold)" if occ.above_fold else ""
        lines.append(f"  - {occ.page_url} — alt={alt!r}{fold}")

    lines.append("")
    lines.append(f"Review locally: {finding.ui_url}")
    return "\n".join(lines)


def _labels(finding: ExportFinding) -> list[str]:
    labels = ["wcag-1-4-5", "accessibility", "images-of-text", f"sev-{finding.severity}"]
    if finding.vlm_classification:
        labels.append(f"class-{finding.vlm_classification.replace('_', '-')}")
    if finding.has_svg_text:
        labels.append("inline-svg")
    return labels
