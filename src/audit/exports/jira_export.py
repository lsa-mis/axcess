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

from audit.exports.collector import ExportA11yFinding, ExportFinding, ExportScan
from audit.exports.interaction_coverage import reproduction_step

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

# Axe's impact scale to the same Jira priority axis. The mapping is
# the same shape as the SPA's impact-to-severity chip mapping, so a
# triager who sees `serious` in the UI sees `High` in Jira — no
# off-by-one surprise.
_IMPACT_TO_PRIORITY = {
    "critical": "Highest",
    "serious": "High",
    "moderate": "Medium",
    "minor": "Low",
}

_ISSUE_TYPE = "Bug"
_COMPONENT = "Accessibility"

_SOURCE_LABELS = {
    "axe": "axe-core",
    "alfa": "Siteimprove Alfa",
    "semantic": "Semantic analyzer",
    "keyboard": "Keyboard probe",
    "responsive": "Reflow and zoom probe",
    "focus": "Focus visibility probe",
    "visual": "Visual analysis",
    "protected_image": "Protected image analysis",
}

# Statuses that mean "we're not opening a ticket for this." Jira import
# would silently create issues for accepted_risk / false_positive rows
# otherwise — Sam would have to delete them manually. Filter out here.
_TRIAGE_SKIP = frozenset({"remediated", "accepted_risk", "false_positive"})


def render_jira_csv(scan: ExportScan) -> str:
    """One Jira issue per finding. Multi-page findings list every page.

    DOM-engine findings join image findings in the same CSV — each row carries
    the same column shape, just different ``Labels`` and ``Description``
    content. Findings already triaged as remediated / accepted_risk /
    false_positive are skipped so re-running an export against a
    partially-triaged scan doesn't re-open old tickets.
    """
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(JIRA_COLUMNS)
    for finding in scan.findings:
        if finding.status in _TRIAGE_SKIP:
            continue
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
    for af in scan.a11y_findings:
        if af.status in _TRIAGE_SKIP:
            continue
        writer.writerow(
            [
                _a11y_summary(af),
                _a11y_description(af),
                _IMPACT_TO_PRIORITY.get(af.impact or "", "Low"),
                _ISSUE_TYPE,
                " ".join(_a11y_labels(af)),
                _COMPONENT,
            ]
        )
    return buf.getvalue()


def _a11y_summary(af: ExportA11yFinding) -> str:
    sc = f" — SC {af.wcag_sc}" if af.wcag_sc else " — best-practice"
    return f"WCAG {af.rule_id}{sc}: {af.page_url}"


def _a11y_description(af: ExportA11yFinding) -> str:
    lines: list[str] = []
    lines.append(f"**Source:** {_a11y_source_label(af)}")
    if af.status == "in_progress":
        lines.append("**Outcome:** Barrier confirmed by expert; remediation planned")
    elif af.pipeline == "alfa" and af.engine_outcome == "cant_tell":
        lines.append("**Outcome:** Needs expert review (Alfa cantTell; not a conformance failure)")
    elif af.pipeline not in {"axe", "alfa"}:
        lines.append("**Outcome:** Needs expert review (observed lead; not a conformance failure)")
    else:
        lines.append("**Outcome:** Failed automated rule outcome")
    lines.append(f"**Rule:** {af.rule_id}")
    if af.impact:
        lines.append(f"**Impact:** {af.impact}")
    if af.wcag_sc:
        lines.append(
            f"**WCAG SC:** {af.wcag_sc}" + (f" (Level {af.wcag_level})" if af.wcag_level else "")
        )
    else:
        lines.append("**WCAG SC:** _best-practice — no SC mapping_")
    if af.help:
        lines.append(f"**Description:** {af.help}")
    lines.append(f"**Page:** {af.page_url}")
    # A click-revealed barrier is invisible on load. Without this step the
    # assignee looks at the page, sees nothing, and closes the ticket as
    # "cannot reproduce" — so it sits directly above the selector.
    lines.append(f"**To reproduce:** {reproduction_step(af.revealed_by)}")
    lines.append(f"**Target selector:** `{af.target_display or af.target_selector}`")
    if af.failure_summary:
        label = "Diagnostic" if af.pipeline == "alfa" else "Why it failed"
        lines.append(f"**{label}:** {af.failure_summary}")
    if af.html_snippet:
        # Triple-backtick fence so Jira's wiki renderer treats it as
        # a code block instead of trying to parse the HTML.
        lines.append("**Failing HTML:**")
        lines.append("```")
        lines.append(af.html_snippet)
        lines.append("```")
    if af.help_url:
        lines.append(f"**Rule docs:** {af.help_url}")
    lines.append("")
    lines.append(f"Review locally: {af.ui_url}")
    return "\n".join(lines)


def _a11y_labels(af: ExportA11yFinding) -> list[str]:
    labels = ["accessibility", f"{af.pipeline or 'axe'}-{af.rule_id}"]
    if af.impact:
        labels.append(f"impact-{af.impact}")
    if af.wcag_sc:
        # Encode "1.4.3" → "wcag-1-4-3" so the label is valid Jira syntax
        # (dots are reserved as label separators in some Jira configs).
        labels.append("wcag-" + af.wcag_sc.replace(".", "-"))
    if af.wcag_level:
        labels.append(f"wcag-level-{af.wcag_level.lower()}")
    else:
        labels.append(f"{af.pipeline or 'axe'}-best-practice")
    return labels


def _a11y_source_label(af: ExportA11yFinding) -> str:
    return _SOURCE_LABELS.get(af.pipeline, af.pipeline or "Unknown detector")


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
