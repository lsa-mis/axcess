"""Markdown evidence inventory.

One self-contained report per scan:

  * Front matter with scan metadata and overall severity mix.
  * A short "what to read first" section highlighting the top-N findings
    sorted by priority.
  * A full table of findings at the bottom for the completionist.

Kept pure-string so it renders cleanly in GitHub, Linear docs, Google Docs
paste, and terminals. No HTML or inline styles.
"""

from __future__ import annotations

from datetime import UTC, datetime

from audit.analyzer.alfa_evidence import evidence_notice
from audit.exports.collector import ExportA11yFinding, ExportFinding, ExportScan

TOP_N = 20
TOP_A11Y_N = 30

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


def render_markdown(scan: ExportScan, *, generated_at: datetime | None = None) -> str:
    """Render the scan as a Markdown report."""
    lines: list[str] = []
    when = generated_at or datetime.now(UTC)

    lines.append(f"# Accessibility evidence inventory — Scan #{scan.id}")
    lines.append("")
    lines.append(f"_Generated {when.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')} by Axcess._")
    lines.append("")
    lines.append(
        "> This is a raw, status-bearing evidence inventory, including review leads and "
        "informational records. Use the stakeholder audit export for the expert-reviewed "
        "remediation worklist; neither artifact certifies conformance."
    )
    lines.append("")
    lines.append("## Scan metadata")
    lines.append("")
    lines.append(f"- **Seed URL:** {scan.seed_url}")
    lines.append(f"- **Status:** {scan.status}")
    if scan.started_at:
        lines.append(f"- **Started:** {scan.started_at}")
    if scan.finished_at:
        lines.append(f"- **Finished:** {scan.finished_at}")
    lines.append(f"- **Pages crawled:** {scan.page_count}")
    lines.append(f"- **Image-analysis evidence records:** {scan.finding_count}")
    lines.append(
        f"- **axe-core failed-rule evidence:** {scan.axe_violations_total} "
        f"(scanned {scan.axe_pages_scanned} of {scan.page_count} pages)"
    )
    lines.append(
        f"- **Siteimprove Alfa outcomes:** {scan.alfa_failed_total} failed; "
        f"{scan.alfa_cant_tell_total} need expert review "
        f"(evaluated {scan.alfa_pages_scanned} of {scan.page_count} pages)"
    )
    alfa_total = scan.alfa_failed_total + scan.alfa_cant_tell_total
    alfa_evidence = sum(1 for finding in scan.a11y_findings if finding.pipeline == "alfa")
    if alfa_total > alfa_evidence:
        lines.append(
            f"- **Alfa evidence limitation:** {alfa_evidence} actionable outcome record(s) "
            f"are retained for {alfa_total} reported outcome(s); per-page evidence may be capped."
        )
    if scan.error_count:
        lines.append(f"- **Errors:** {scan.error_count}")

    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(_summary_line(scan))
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("| --- | ---: |")
    for level in ("critical", "major", "minor", "info"):
        lines.append(f"| {level} | {scan.by_severity.get(level, 0)} |")

    lines.append("")
    lines.append(f"## Top {min(TOP_N, len(scan.findings))} image-analysis records")
    lines.append("")
    if not scan.findings:
        lines.append("_No findings._")
    else:
        for finding in scan.findings[:TOP_N]:
            lines.extend(_format_finding_block(finding))
            lines.append("")

    lines.append("## All image-analysis evidence")
    lines.append("")
    if not scan.findings:
        lines.append("_No findings._")
    else:
        lines.append("| # | Status | Severity | Score | Classification | Adequacy | Image |")
        lines.append("| ---: | --- | --- | ---: | --- | --- | --- |")
        for f in scan.findings:
            lines.append(
                "| {id} | {status} | {sev} | {score:.2f} | {cls} | {adeq} | {img} |".format(
                    id=f.id,
                    status=f.status,
                    sev=f.severity,
                    score=f.priority_score,
                    cls=f.vlm_classification or "—",
                    adeq=f.alt_adequacy,
                    img=_short(f.image_url, 48),
                )
            )

    # DOM-engine section — only emitted when a selected engine ran or left
    # retained evidence. This preserves legacy reports that predate both
    # engine counters while making an Alfa-only scan reportable.
    if scan.axe_pages_scanned or scan.alfa_pages_scanned or scan.a11y_findings:
        lines.append("")
        lines.append("## WCAG DOM-engine findings")
        lines.append("")
        lines.append(_dom_engine_summary_line(scan))
        lines.append("")
        lines.append("| WCAG level | Count |")
        lines.append("| --- | ---: |")
        for level_label, key in (
            ("A", "A"),
            ("AA", "AA"),
            ("AAA", "AAA"),
            ("best-practice", "best_practice"),
        ):
            lines.append(f"| {level_label} | {scan.by_wcag_level.get(key, 0)} |")

        lines.append("")
        lines.append(
            "**Scope reminder.** Each finding records its source. axe-core and "
            "Siteimprove Alfa are complementary automated methods, not conformance "
            "verdicts. Alfa `cantTell` outcomes are explicitly expert-review leads; "
            "manual evaluation remains required."
        )

        if scan.a11y_findings:
            top = scan.a11y_findings[:TOP_A11Y_N]
            lines.append("")
            lines.append(f"### Top {len(top)} DOM-engine findings")
            lines.append("")
            for af in top:
                lines.extend(_format_axe_block(af))
                lines.append("")

            lines.append("### All DOM-engine findings")
            lines.append("")
            lines.append("| # | Source | Outcome | Impact | WCAG SC | Level | Rule | Page |")
            lines.append("| ---: | --- | --- | --- | --- | --- | --- | --- |")
            for af in scan.a11y_findings:
                lines.append(
                    (
                        "| {id} | {source} | {outcome} | {imp} | {sc} | {lvl} | `{rule}` | {pg} |"
                    ).format(
                        id=af.id,
                        source=_source_label(af),
                        outcome=_outcome_label(af),
                        imp=af.impact or "—",
                        sc=af.wcag_sc or "—",
                        lvl=af.wcag_level or "—",
                        rule=af.rule_id,
                        pg=_short(af.page_url, 48),
                    )
                )

    lines.append("")
    return "\n".join(lines)


def _dom_engine_summary_line(scan: ExportScan) -> str:
    """Describe selected rule engines without conflating their outcomes."""
    parts: list[str] = []
    if scan.axe_pages_scanned:
        parts.append(
            f"axe-core found {scan.axe_violations_total} violation(s) across "
            f"{scan.axe_pages_scanned} page(s)"
        )
    if scan.alfa_pages_scanned:
        parts.append(
            f"Siteimprove Alfa returned {scan.alfa_failed_total} failed outcome(s) and "
            f"{scan.alfa_cant_tell_total} expert-review lead(s) across "
            f"{scan.alfa_pages_scanned} page(s)"
        )
    return "; ".join(parts) + "." if parts else "No DOM engine ran for this scan."


def _format_axe_block(af: ExportA11yFinding) -> list[str]:
    """One source-attributed DOM-engine finding for the top-N section."""
    lines: list[str] = []
    sc = af.wcag_sc or "best-practice"
    lvl = f" (Level {af.wcag_level})" if af.wcag_level else ""
    impact = af.impact or "—"
    lines.append(f"### [{impact}] {af.rule_id} — SC {sc}{lvl}")
    lines.append(f"- **Source:** {_source_label(af)}")
    lines.append(f"- **Outcome:** {_outcome_label(af)}")
    if af.help:
        lines.append(f"- **Rule:** {af.help}")
    lines.append(f"- **Page:** {af.page_url}")
    lines.append(f"- **Target:** `{_short(af.target_display or af.target_selector, 100)}`")
    if af.failure_summary:
        # Failure summaries can be multi-line; collapse to one for the bullet.
        one_line = " ".join(af.failure_summary.split())
        label = "Diagnostic" if af.pipeline == "alfa" else "Why it failed"
        lines.append(f"- **{label}:** {_short(one_line, 240)}")
    if af.pipeline == "alfa" and evidence_notice(af.engine_evidence_status):
        lines.append(f"- **Evidence:** {evidence_notice(af.engine_evidence_status)}")
    if af.help_url:
        lines.append(f"- **Docs:** {af.help_url}")
    lines.append(f"- **Status:** {af.status}")
    lines.append(f"- **Review:** {af.ui_url}")
    return lines


def _source_label(af: ExportA11yFinding) -> str:
    return _SOURCE_LABELS.get(af.pipeline, af.pipeline or "Unknown detector")


def _outcome_label(af: ExportA11yFinding) -> str:
    reviewed = {
        "in_progress": "Barrier confirmed by expert — remediation planned",
        "remediated": "Barrier confirmed by expert — remediated",
        "accepted_risk": "Barrier confirmed by expert — risk accepted",
        "false_positive": "Reviewed — not a barrier",
    }
    if af.status in reviewed:
        return reviewed[af.status]
    if af.pipeline == "alfa" and af.engine_outcome == "cant_tell":
        return "Needs expert review (Alfa cantTell)"
    if af.pipeline not in {"axe", "alfa"}:
        return "Needs expert review (observed lead)"
    return "Failed automated rule outcome"


def _summary_line(scan: ExportScan) -> str:
    counts = scan.by_severity
    crit = counts.get("critical", 0)
    major = counts.get("major", 0)
    minor = counts.get("minor", 0)
    info = counts.get("info", 0)
    if scan.finding_count == 0:
        return (
            "No image-analysis evidence was retained across the crawled pages. "
            "This is not a pass or conformance conclusion."
        )
    parts: list[str] = []
    if crit:
        parts.append(f"{crit} critical")
    if major:
        parts.append(f"{major} major")
    if minor:
        parts.append(f"{minor} minor")
    if info:
        parts.append(f"{info} informational")
    return (
        "Retained "
        + ", ".join(parts)
        + " image-analysis evidence record(s) across the crawled pages. Status and expert "
        "review determine whether any record belongs in a remediation worklist."
    )


def _format_finding_block(finding: ExportFinding) -> list[str]:
    lines: list[str] = []
    lines.append(
        f"### [{finding.severity}] Finding #{finding.id} — priority {finding.priority_score:.2f}"
    )
    lines.append(f"- **Review status:** {finding.status}")
    if finding.vlm_classification:
        lines.append(f"- **Classification:** {finding.vlm_classification}")
    lines.append(f"- **Alt adequacy:** {finding.alt_adequacy}")
    lines.append(f"- **Image:** {finding.image_url}")
    if finding.ocr_text:
        lines.append(f"- **OCR text:** {finding.ocr_text!r}")
    if finding.vlm_rationale:
        lines.append(f"- **VLM rationale:** {finding.vlm_rationale}")
    if finding.remediation_hint:
        lines.append(
            f"- **Detector suggestion (verify before action):** {finding.remediation_hint}"
        )
    if finding.occurrences:
        lines.append(f"- **Occurrences:** {len(finding.occurrences)}")
        for occ in finding.occurrences[:5]:
            alt = "(missing)" if occ.alt_text is None else occ.alt_text or "(empty)"
            fold = " — above fold" if occ.above_fold else ""
            lines.append(f"  - {occ.page_url} — alt={alt!r}{fold}")
        if len(finding.occurrences) > 5:
            lines.append(f"  - …{len(finding.occurrences) - 5} more")
    lines.append(f"- **Review:** {finding.ui_url}")
    return lines


def _short(url: str, limit: int) -> str:
    if len(url) <= limit:
        return url
    return url[: limit - 1] + "…"
