"""Markdown stakeholder report.

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

from audit.exports.collector import ExportFinding, ExportScan

TOP_N = 20


def render_markdown(scan: ExportScan, *, generated_at: datetime | None = None) -> str:
    """Render the scan as a Markdown report."""
    lines: list[str] = []
    when = generated_at or datetime.now(UTC)

    lines.append(f"# Accessibility audit — Scan #{scan.id}")
    lines.append("")
    lines.append(
        f"_Generated {when.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')} "
        "by AccessibleAccessibility._"
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
    lines.append(f"- **Findings:** {scan.finding_count}")
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
    lines.append(f"## Top {min(TOP_N, len(scan.findings))} findings")
    lines.append("")
    if not scan.findings:
        lines.append("_No findings._")
    else:
        for finding in scan.findings[:TOP_N]:
            lines.extend(_format_finding_block(finding))
            lines.append("")

    lines.append("## All findings")
    lines.append("")
    if not scan.findings:
        lines.append("_No findings._")
    else:
        lines.append("| # | Severity | Score | Classification | Adequacy | Image |")
        lines.append("| ---: | --- | ---: | --- | --- | --- |")
        for f in scan.findings:
            lines.append(
                "| {id} | {sev} | {score:.2f} | {cls} | {adeq} | {img} |".format(
                    id=f.id,
                    sev=f.severity,
                    score=f.priority_score,
                    cls=f.vlm_classification or "—",
                    adeq=f.alt_adequacy,
                    img=_short(f.image_url, 48),
                )
            )

    lines.append("")
    return "\n".join(lines)


def _summary_line(scan: ExportScan) -> str:
    counts = scan.by_severity
    crit = counts.get("critical", 0)
    major = counts.get("major", 0)
    minor = counts.get("minor", 0)
    info = counts.get("info", 0)
    if scan.finding_count == 0:
        return "No WCAG 1.4.5 failures detected across the crawled pages."
    parts: list[str] = []
    if crit:
        parts.append(f"{crit} critical")
    if major:
        parts.append(f"{major} major")
    if minor:
        parts.append(f"{minor} minor")
    if info:
        parts.append(f"{info} informational")
    return "Detected " + ", ".join(parts) + " finding(s) across the crawled pages."


def _format_finding_block(finding: ExportFinding) -> list[str]:
    lines: list[str] = []
    lines.append(
        f"### [{finding.severity}] Finding #{finding.id} — priority {finding.priority_score:.2f}"
    )
    if finding.vlm_classification:
        lines.append(f"- **Classification:** {finding.vlm_classification}")
    lines.append(f"- **Alt adequacy:** {finding.alt_adequacy}")
    lines.append(f"- **Image:** {finding.image_url}")
    if finding.ocr_text:
        lines.append(f"- **OCR text:** {finding.ocr_text!r}")
    if finding.vlm_rationale:
        lines.append(f"- **VLM rationale:** {finding.vlm_rationale}")
    if finding.remediation_hint:
        lines.append(f"- **Suggested fix:** {finding.remediation_hint}")
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
