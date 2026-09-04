"""Audit-engineer-style Markdown report — the holistic deliverable.

Distinct from the data-dense ``markdown_report.py``: this is the report
you hand to a stakeholder or a remediation team. It answers, in order:

  1. **Where do we stand?** — executive summary + a conformance
     scorecard (WCAG level + POUR principle rollup).
  2. **Who is blocked?** — an abilities-affected rollup.
  3. **What did we actually check, and what couldn't we?** — a coverage
     and method section that is honest about the ~60% of WCAG that needs
     human review.
  4. **Where is it worst?** — a page-hotspots table.
  5. **Who fixes what?** — a remediation worklist split by owner
     (dev / editor / designer / content).
  6. **Exactly what's wrong and how do I fix it?** — detailed issue
     cards with element-level locations, fix steps, and a verification
     plan.
  7. **What did we set aside, and why?** — Appendix A (already-triaged)
     and Appendix B (best-practice, no WCAG SC).

The report sources every issue from :func:`audit.web.issues.list_issues`,
the one place that unifies all four detection pipelines — axe-core DOM
rules, the image-of-text VLM, the per-criterion semantic LLM analyzers,
and the dynamic keyboard-trap probe. That is why keyboard (SC 2.1.2) and
semantic (SC 2.4.4) findings now carry their real labels and remediation
content instead of being mislabeled as axe rules.

Remediation copy comes from ``rules/audit_report.yaml``. Rules without a
card still appear, flagged "human review needed" — we never invent a fix
the tool can't state concretely.

Plain-English voice throughout. If a sentence reads like a compliance
policy, rewrite it as something a teammate would Slack you.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib import resources
from typing import Any

import yaml

from audit import coverage_matrix, evaluation
from audit.analyzer.alfa_evidence import (
    STRUCTURED_TARGET_LABEL,
    bounded_summary,
    normalize_finding,
)
from audit.exports import interaction_coverage
from audit.exports.collector import ExportA11yFinding, ExportFinding, ExportScan
from audit.exports.interaction_coverage import InteractionCoverage
from audit.web import issues as issues_mod

# The framework caps the executive summary at 8 sentences. The renderer
# enforces this as a soft contract — it just doesn't emit more.
SUMMARY_MAX_SENTENCES = 8

# Top-N caps per section — the report should be useful at a glance, not
# a 200-page document dump. The full data is still in the CSV / JSON.
TOP_GROUPS_PER_SECTION = 12

# How many concrete "here's exactly where" locations to list per card.
# Enough to act on without scrolling; the rest are summarized as "+N more".
MAX_LOCATIONS_PER_CARD = 10

# How many worst pages to list in the hotspots table.
MAX_HOTSPOTS = 10

_RULES_FILE = "audit_report.yaml"
_RULES_PACKAGE = "audit.rules"

# Owner-type taxonomy used in the YAML. The renderer doesn't validate
# beyond this — anything else from the YAML passes through verbatim so
# editors can tune labels.
_KNOWN_OWNERS = ("dev", "editor", "designer", "content")
_OWNER_LABELS = {
    "dev": "Developers",
    "editor": "Content editors",
    "designer": "Designers",
    "content": "Content team",
}

# Status buckets that mean "already handled" — these issues drop out of
# the live worklist and into Appendix A.
_TRIAGED_STATUSES = frozenset({"remediated", "accepted_risk", "false_positive"})
_OPEN_STATUSES = frozenset({"new", "reviewing", "in_progress"})
_CONFIRMED_REVIEW_STATUSES = frozenset({"in_progress"})
_UNCONFIRMED_REVIEW_STATUSES = frozenset({"new", "reviewing"})

# axe / keyboard impact → framework severity word. The pipelines already
# emit critical/serious/moderate/minor, so this is mostly identity; image
# findings come in on the major/minor/info scale and get mapped too.
_IMPACT_SEVERITY = {
    "critical": "Critical",
    "serious": "Serious",
    "moderate": "Moderate",
    "minor": "Minor",
    "major": "Serious",
    "info": "Minor",
}
_SEVERITY_RANK = {"Critical": 0, "Serious": 1, "Moderate": 2, "Minor": 3}

# WCAG principle by SC first digit (the "POUR" model). Best-practice and
# unmapped findings fall through to "Other / best-practice".
_PRINCIPLE = {
    "1": "Perceivable",
    "2": "Operable",
    "3": "Understandable",
    "4": "Robust",
}

# Human-readable label for the pipeline that produced an issue. Drives the
# coverage section and the per-card method note.
_PIPELINE_LABEL = {
    "axe": "axe-core (deterministic DOM rules)",
    "alfa": "Siteimprove Alfa (ACT rules)",
    "image": "image-of-text VLM",
    "semantic": "per-criterion LLM analyzer",
    "keyboard": "dynamic keyboard-trap probe",
    "responsive": "responsive & zoom probe",
    "focus": "live-page focus probe",
    "visual": "visual order and media playback probe",
}

# Static description of each detection pipeline for the coverage section.
# Editorial, not derived — what each method can and can't see. The
# "ran" flag is filled in dynamically from the issues actually present.
# Pages listed individually before the report defers to the workbook. A
# stakeholder document should name the gaps, not reproduce a full ledger.
_MAX_LIMITED_PAGES = 15

_PIPELINE_COVERAGE = [
    {
        "key": "axe",
        "name": "axe-core",
        "method": "Deterministic DOM + computed-style rules run in a real browser.",
        "checks": "Contrast, missing alt/labels, ARIA misuse, landmark structure, "
        "heading order, link/button names, target size.",
        "confidence": "High-confidence deterministic evidence, but rule applicability and "
        "remediation still need expert verification; no fixed real-world false-positive "
        "rate is claimed.",
    },
    {
        "key": "alfa",
        "name": "Siteimprove Alfa",
        "method": "Independent ACT-rule evaluation on a separate local-browser capture.",
        "checks": "ACT rules mapped to WCAG 2.2 at the selected level; unresolved "
        "`cantTell` outcomes are review leads.",
        "confidence": "High for failed outcomes; `cantTell` is explicitly not a "
        "conformance failure.",
    },
    {
        "key": "image",
        "name": "Image-of-text VLM",
        "method": "OCR + a vision-language model on every rendered image, "
        "cross-checked against the authored alt text.",
        "checks": "WCAG 1.4.5 (images of text) and whether the alt conveys the "
        "same information the image does.",
        "confidence": "Medium — OCR/model classification can misread decorative or "
        "context-dependent images; every result remains an expert-review lead.",
    },
    {
        "key": "semantic",
        "name": "Per-criterion LLM analyzer",
        "method": "A focused language model reviews one criterion at a time with "
        "surrounding page context.",
        "checks": "Judgment calls automated tools miss — e.g. SC 2.4.4, whether a "
        "link's text actually describes where it goes.",
        "confidence": "Medium — semantic judgments are inherently fuzzier; treat as "
        "strong leads, confirm before mass edits.",
    },
    {
        "key": "keyboard",
        "name": "Bidirectional keyboard-exit probe",
        "method": "Drives a real browser and watches focus while attempting repeated "
        "Tab and Shift+Tab exits from the same observable element.",
        "checks": "WCAG 2.1.2 review leads — both directions must remain blocked. "
        "Normal wrapping, two-control cycles, modal containment, and opaque embedded "
        "contexts are not counted as traps.",
        "confidence": "Medium — repeatable browser-observed evidence with exact attempt "
        "counts. Manually check for documented or state-specific exit commands before "
        "recording a failure.",
    },
    {
        "key": "responsive",
        "name": "Responsive & zoom probe",
        "method": "Resizes the live page to 320px, the 200%-zoom proxy viewport, and "
        "applies WCAG's text-spacing override, looking for overflow and clipped text.",
        "checks": "SC 1.4.10 reflow at 320px, SC 1.4.4 text clipping at 200% zoom, "
        "SC 1.4.12 clipping under user text-spacing.",
        "confidence": "Medium — deterministic geometry is useful evidence, but designed "
        "truncation and state-specific clipping need an expert decision.",
    },
    {
        "key": "focus",
        "name": "Live-page focus probe",
        "method": "Focuses each interactive element in the live page and checks "
        "whether a position:fixed/sticky overlay covers its centre.",
        "checks": "SC 2.4.11 — focus hidden behind sticky headers / cookie banners / overlays.",
        "confidence": "Medium — catches elements whose centre is covered; "
        "partial-overlap and post-click overlays still need a human.",
    },
    {
        "key": "interaction",
        "name": "Click-through DOM states",
        "method": "Operates the page's own menus, tabs, dialogs, and disclosure "
        "controls, then re-runs the rule engine on each state a click reveals.",
        "checks": "Barriers that a page load never shows because the content only "
        "exists after a control is operated. Links are never clicked, and controls "
        "labelled sign out, delete, remove, or unsubscribe are refused.",
        "confidence": "Same deterministic rule evidence as a load-state pass, on states "
        "a load-state pass cannot reach. Coverage is bounded per page, so absence of a "
        "finding is not evidence that a state is clean.",
    },
    {
        "key": "visual",
        "name": "Visual (VLM) probe",
        "method": "Screenshots the page and asks a local vision model whether the "
        "visual reading order matches the DOM/source order.",
        "checks": "SC 1.3.2 — content visually reordered by CSS so screen readers "
        "get a different, confusing sequence.",
        "confidence": "Medium — a vision-model judgement; treat as a lead and "
        "confirm. Only runs when a local vision model is available.",
    },
]

# The honest "what still needs manual testing" list is no longer hardcoded
# here — it is derived per-criterion from the WCAG coverage matrix
# (rules/wcag_coverage.yaml), rendered by ``_wcag_coverage_matrix`` below.


@dataclass(frozen=True)
class IssueLocation:
    """One concrete "here's exactly where the issue is" pointer.

    Pairs a page with the specific element on it so the reader doesn't
    have to guess which of a page's hundred elements is the offender.
    For DOM findings ``selector`` is the CSS path; for image findings
    ``image_url`` is the offending asset. ``detail`` is a short
    human-readable note (the failure summary, fold position, etc.).
    """

    page_url: str
    page_title: str | None
    description: str
    selector: str | None
    image_url: str | None
    detail: str | None
    # The control that had to be operated before this markup existed. None
    # means it was on the page at load. This is the difference between an
    # instance a reader can reproduce and one they cannot: "open the Account
    # menu, then look at the field" versus "load the page".
    revealed_by: str | None = None


@dataclass(frozen=True)
class FixOption:
    """One authored way to fix an issue, with the trade-off it carries.

    Deliberately not derived from scan data. Which approaches exist, and
    what each one costs, is editorial judgment about a codebase — a scan
    records that a heading is missing, never that promoting a component's
    ``tag`` prop is preferable to hand-written HTML. So options live in
    ``rules/audit_report.yaml`` and are simply absent for rules nobody has
    written them for; an export renders what exists rather than inventing a
    second option to fill out a table.
    """

    label: str
    approach: str
    watch_out: str = ""


@dataclass(frozen=True)
class AuditCard:
    """One issue card, the framework's atomic unit."""

    pipeline: str  # "image" | "axe" | "semantic" | "keyboard"
    title: str
    wcag_sc: str | None
    wcag_name: str | None
    wcag_level: str | None
    severity: str
    severity_reason: str
    effort: str
    owner: str
    abilities: tuple[str, ...]
    affected_page_count: int
    affected_finding_count: int
    triaged_count: int
    locations: list[IssueLocation]
    location_overflow: int
    what_happening: str
    why_matters: str
    fix_steps: list[str]
    verify_manual: str | None
    verify_automated: str | None
    acceptance: str | None
    confidence: str
    needs_human_review: bool
    note: str | None
    finding_ids: list[int]


@dataclass(frozen=True)
class DroppedFinding:
    """One row in Appendix A — an issue the tool set aside (already triaged)."""

    pipeline: str
    location: str
    wcag_sc: str | None
    reason: str


def _bucket_rows_into_cards(
    conn: sqlite3.Connection,
    rows: list[Any],
) -> tuple[list[AuditCard], list[DroppedFinding], list[Any]]:
    """Split unified issue rows into the framework's three buckets.

    Returns ``(cards, dropped, best_practice)``:

    * **cards** — open WCAG issues (a real SC, at least one un-triaged
      finding), built into :class:`AuditCard`s and sorted by severity then
      reach. This is the substantive content both the Markdown report and
      the Excel workbook render, so they share this one builder and can't
      drift apart.
    * **dropped** — every finding already triaged → Appendix A.
    * **best_practice** — expert-review leads, informational evidence, or
      results without a WCAG SC → Appendix B. These are never promoted to
      stakeholder-facing failures without an expert decision.
    """
    rules = _load_rules()
    open_rows: list[Any] = []
    dropped: list[DroppedFinding] = []
    best_practice: list[Any] = []
    for row in rows:
        if _is_fully_triaged(row):
            dropped.append(
                DroppedFinding(
                    pipeline=row.pipeline,
                    location=row.title,
                    wcag_sc=row.wcag_sc,
                    reason="Already triaged: " + _status_phrase(row.status_summary),
                )
            )
            continue

        terminal_summary = {
            status: count
            for status, count in dict(row.status_summary or {}).items()
            if status in _TRIAGED_STATUSES and count
        }
        if terminal_summary:
            dropped.append(
                DroppedFinding(
                    pipeline=row.pipeline,
                    location=row.title,
                    wcag_sc=row.wcag_sc,
                    reason="Triaged subset: " + _status_phrase(terminal_summary),
                )
            )

        if row.review_lane == "expert_review":
            # ``in_progress`` is the current persisted decision that the expert
            # confirmed a barrier and remediation is still open. It belongs in
            # the substantive worklist; ``new`` and ``reviewing`` remain review
            # leads. Project each subset independently so a mixed group cannot
            # promote its unreviewed occurrences or hide its confirmed ones.
            confirmed = _project_row_for_statuses(conn, row, _CONFIRMED_REVIEW_STATUSES)
            if confirmed is not None:
                open_rows.append(confirmed)
            unconfirmed = _project_row_for_statuses(conn, row, _UNCONFIRMED_REVIEW_STATUSES)
            if unconfirmed is not None:
                best_practice.append(unconfirmed)
            continue

        # Terminal occurrences in a partly triaged group must not remain in an
        # open card's affected counts, pages, locations, or finding ids. The
        # Appendix-A receipt above retains their disposition.
        open_row = _project_row_for_statuses(conn, row, _OPEN_STATUSES)
        if open_row is None:
            continue
        if row.review_lane != "likely_barrier" or row.conformance == "BP" or not row.wcag_sc:
            best_practice.append(open_row)
            continue
        open_rows.append(open_row)

    cards = [_card_from_row(conn, row, rules) for row in open_rows]
    cards.sort(key=lambda c: (_severity_rank(c.severity), -c.affected_page_count))
    return cards, dropped, best_practice


def _project_row_for_statuses(
    conn: sqlite3.Connection,
    row: Any,
    statuses: frozenset[str],
) -> Any | None:
    """Return an issue-row projection containing only selected statuses.

    Issue rows are intentionally grouped for review, but stakeholder report
    counts and locations must describe only the backing records in the report
    bucket being rendered. Querying the immutable finding ids here avoids
    inferring a per-record status from aggregate ``status_summary`` counts.
    """

    finding_ids = list(row.finding_ids)
    if not finding_ids:
        return None
    table = "findings" if row.pipeline == "image" else "page_a11y_findings"
    finding_ids_json = json.dumps(finding_ids)
    status_rows = conn.execute(
        f"""
        SELECT id, status FROM {table}
         WHERE id IN (SELECT value FROM json_each(?))
        """,  # noqa: S608 — table is selected from two fixed identifiers
        (finding_ids_json,),
    ).fetchall()
    status_by_id = {int(item["id"]): str(item["status"]) for item in status_rows}
    selected_ids = tuple(
        finding_id for finding_id in finding_ids if status_by_id.get(finding_id) in statuses
    )
    if not selected_ids:
        return None

    selected_summary: dict[str, int] = {}
    for finding_id in selected_ids:
        status = status_by_id[finding_id]
        selected_summary[status] = selected_summary.get(status, 0) + 1
    occurrence_count, page_count = _projected_scope_counts(conn, row.pipeline, selected_ids)
    high_confidence_occurrences = min(int(row.high_confidence_occurrence_count), occurrence_count)
    return replace(
        row,
        finding_ids=selected_ids,
        status_summary=selected_summary,
        occurrence_count=occurrence_count,
        page_count=page_count,
        high_confidence_occurrence_count=high_confidence_occurrences,
    )


def _projected_scope_counts(
    conn: sqlite3.Connection,
    pipeline: str,
    finding_ids: tuple[int, ...],
) -> tuple[int, int]:
    """Return occurrence/page counts for one status-filtered finding subset."""

    finding_ids_json = json.dumps(finding_ids)
    if pipeline == "image":
        result = conn.execute(
            """
            SELECT COUNT(*) AS occurrence_count,
                   COUNT(DISTINCT p.id) AS page_count
              FROM findings f
              JOIN page_images pi ON pi.image_id = f.image_id
              JOIN pages p ON p.id = pi.page_id AND p.scan_id = f.scan_id
             WHERE f.id IN (SELECT value FROM json_each(?))
            """,
            (finding_ids_json,),
        ).fetchone()
    else:
        result = conn.execute(
            """
            SELECT COUNT(*) AS occurrence_count,
                   COUNT(DISTINCT page_id) AS page_count
              FROM page_a11y_findings
             WHERE id IN (SELECT value FROM json_each(?))
            """,
            (finding_ids_json,),
        ).fetchone()
    if result is None:  # pragma: no cover - aggregate SELECT always returns one row
        return (0, 0)
    return (int(result["occurrence_count"] or 0), int(result["page_count"] or 0))


def build_audit_cards(
    conn: sqlite3.Connection,
    scan: ExportScan,
) -> tuple[list[AuditCard], list[DroppedFinding], list[Any]]:
    """Public entry point: the audit model for ``scan`` as structured data.

    Wraps :func:`audit.web.issues.list_issues` + :func:`_bucket_rows_into_cards`
    so other renderers (the Excel workbook) can build their own tables from
    exactly the cards the Markdown report uses.
    """
    rows = issues_mod.list_issues(conn, scan.id)
    return _bucket_rows_into_cards(conn, rows)


def render_audit_report(
    scan: ExportScan,
    *,
    conn: sqlite3.Connection,
    generated_at: datetime | None = None,
) -> str:
    """Build the holistic Markdown audit report for ``scan``.

    Takes a live ``conn`` because the renderer reuses the unified
    :func:`audit.web.issues.list_issues` (which fans out to every
    detection pipeline) and then pulls element-level locations on
    demand.
    """
    when = generated_at or datetime.now(UTC)

    rows = issues_mod.list_issues(conn, scan.id)
    cards, dropped, best_practice = _bucket_rows_into_cards(conn, rows)
    blocked_seed = _blocked_seed_details(conn, scan)

    lines: list[str] = []
    lines.append(f"# Accessibility audit — Scan #{scan.id}")
    lines.append("")
    lines.append(f"_Generated {when.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')} by Axcess._")
    lines.append("")
    lines.append(f"**Seed URL:** {scan.seed_url}")
    lines.append(f"**Audited against:** WCAG 2.2 Level {scan.axe_level}")
    lines.append(f"**Pages crawled:** {scan.page_count}")
    lines.append(f"**Detection methods used:** {_methods_line(rows)}")
    lines.append("")
    if blocked_seed is not None:
        lines.extend(_blocked_seed_warning(blocked_seed))
        lines.append("")

    lines.extend(_executive_summary(cards, dropped, best_practice, blocked_seed=blocked_seed))
    lines.append("")
    lines.extend(_conformance_scorecard(cards, blocked_seed=blocked_seed))
    lines.append("")
    lines.extend(_abilities_rollup(cards))
    lines.append("")
    lines.extend(_coverage_and_method(rows, scan, interaction_coverage.load(conn, scan.id)))
    lines.append("")
    lines.extend(_wcag_coverage_matrix())
    lines.append("")
    expert_record = evaluation.get_evaluation(conn, scan.id)
    if expert_record["exists"]:
        lines.extend(_expert_evaluation_record(conn, scan.id, expert_record))
        lines.append("")
    lines.extend(_page_hotspots(conn, scan, cards))
    lines.append("")
    lines.extend(_worklist_by_owner(cards))
    lines.append("")

    lines.append("## Issue cards")
    lines.append("")
    if not cards:
        lines.append(
            "_No open WCAG findings after self-critique. See the appendices "
            "for already-triaged items and out-of-scope notes._"
        )
    else:
        for i, card in enumerate(cards, start=1):
            lines.extend(_render_card(i, card))
            lines.append("")

    lines.extend(_appendix_a(dropped))
    lines.append("")
    lines.extend(_appendix_b(best_practice))
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "**Scope note.** Automated tooling evaluates only defined conditions within a "
        "subset of WCAG success criteria and reached page states. This report combines "
        "multiple methods, but a clean run is **necessary, not sufficient** for "
        "conformance. The manual matrix and recorded limitations remain part of the "
        "evaluation."
    )
    lines.append("")
    return "\n".join(lines)


def _expert_evaluation_record(
    conn: sqlite3.Connection, scan_id: int, record: dict[str, Any]
) -> list[str]:
    """Render persisted expert context only when the reviewer has created it.

    Existing machine-only exports remain byte-stable; the additional section
    appears once an expert intentionally records an evaluation.
    """
    lines = ["## Expert evaluation record", ""]
    lines.append(f"**Target:** {record['target_standard']} Level {record['target_level']}")
    lines.append(f"**Review status:** {str(record['status']).replace('_', ' ')}")
    if record["reviewer"]:
        lines.append(f"**Reviewer:** {record['reviewer']}")
    for label, key in (
        ("Purpose", "purpose"),
        ("Included scope", "scope_included"),
        ("Excluded scope", "scope_excluded"),
        ("Sample", "sample_description"),
        ("Methods", "methods_note"),
        ("Limitations", "limitations"),
    ):
        if record[key]:
            lines.extend(["", f"**{label}:** {record[key]}"])

    checks = evaluation.list_manual_checks(conn, scan_id)
    completed = [check for check in checks if check["outcome"] != "not_started"]
    if completed:
        lines.extend(
            ["", "### Manual-check decisions", "", "| SC | Outcome | Rationale |", "|---|---|---|"]
        )
        for check in completed:
            lines.append(
                f"| {check['criterion']['sc']} | {str(check['outcome']).replace('_', ' ')} | "
                f"{_clean(check['rationale']) or '—'} |"
            )
    not_tested = [check for check in checks if check["outcome"] == "not_tested"]
    if not_tested:
        lines.extend(
            [
                "",
                "### Not-tested criteria — documented evaluation limitations",
                "",
                "These criteria were not tested. Their expert rationales are part of the "
                "evaluation's documented limitations.",
                "",
                "| SC | Criterion | Limitation rationale |",
                "|---|---|---|",
            ]
        )
        for check in not_tested:
            lines.append(
                f"| {check['criterion']['sc']} | {_clean(check['criterion']['name'])} | "
                f"{_clean(check['rationale'])} |"
            )
    evidence_references = [
        (check["criterion"]["sc"], item) for check in checks for item in check["evidence"]
    ]
    if evidence_references:
        lines.extend(
            [
                "",
                "### Evidence references",
                "",
                "| SC | Page | External reference | Expert note |",
                "|---|---|---|---|",
            ]
        )
        for criterion_sc, item in evidence_references:
            page = _clean(str(item.get("page_url") or "—"))
            reference = _clean(str(item.get("evidence_url") or "—"))
            note = _clean(str(item.get("note") or "—"))
            lines.append(f"| {criterion_sc} | {page} | {reference} | {note} |")
    return lines


def _blocked_seed_details(
    conn: sqlite3.Connection, scan: ExportScan
) -> tuple[int | None, str | None] | None:
    """Return a coverage limitation when the seed was not successfully read.

    A report with no open findings after a 403, login wall, or fetch failure is
    incomplete evidence—not a clean accessibility result.
    """
    row = conn.execute(
        "SELECT status_code, title FROM pages WHERE scan_id = ? AND url_normalized = ? LIMIT 1",
        (scan.id, scan.seed_url),
    ).fetchone()
    if row is None:
        if scan.page_count == 0 and scan.error_count:
            return (None, None)
        return None
    status_code = row["status_code"]
    if status_code is None or 200 <= int(status_code) < 300:
        return None
    return (int(status_code), str(row["title"] or "") or None)


def _blocked_seed_warning(blocked_seed: tuple[int | None, str | None]) -> list[str]:
    """State the evidence gap prominently before any summary prose."""
    status_code, title = blocked_seed
    if status_code is None:
        return [
            "> **Coverage warning:** The crawler recorded errors before it could retrieve "
            "the seed page. No findings should be interpreted as a pass; retry with "
            "authorized access before relying on this report."
        ]
    title_note = f" ({_clean(title)})" if title else ""
    return [
        "> **Coverage warning:** The seed page returned HTTP "
        f"{status_code}{title_note}. Axcess did not obtain the audited page; "
        "no findings should be interpreted as a pass. Request authorized access "
        "or scan an approved test environment."
    ]


# ---------------------------------------------------------------------------
# Section: executive summary.
# ---------------------------------------------------------------------------


def _executive_summary(
    cards: list[AuditCard],
    dropped: list[DroppedFinding],
    best_practice: list[Any],
    *,
    blocked_seed: tuple[int | None, str | None] | None = None,
) -> list[str]:
    """Eight-sentence executive summary, framework-shaped."""
    lines: list[str] = ["## Executive summary", ""]
    sentences: list[str] = []

    level_a = sum(1 for c in cards if c.wcag_level == "A")
    level_aa = sum(1 for c in cards if c.wcag_level == "AA")
    sentences.append(
        f"After self-critique, **{len(cards)} open issue type(s)** need work "
        f"({len(dropped)} already-triaged item(s) moved to Appendix A; "
        f"{len(best_practice)} review-only or informational item(s) to Appendix B)."
    )
    if cards:
        sentences.append(
            f"Of those, **{level_a} map to WCAG Level A** and "
            f"**{level_aa} map to Level AA**. These are likely barriers, not a "
            "standalone conformance determination; Level A items should be triaged first."
        )

    themes = sorted(cards, key=lambda c: -c.affected_page_count)[:3]
    if themes:
        theme_phrases = []
        for c in themes:
            plural = "s" if c.affected_page_count != 1 else ""
            theme_phrases.append(f"*{c.title}* (on {c.affected_page_count} page{plural})")
        sentences.append("The biggest themes by reach are: " + "; ".join(theme_phrases) + ".")

    quick_win = _quick_win(cards)
    if quick_win:
        sentences.append(
            f"**Highest-impact fix this team could ship this week:** "
            f"*{quick_win.title}* — {quick_win.severity}, {quick_win.effort}, "
            f"{quick_win.affected_page_count} page(s)."
        )

    estimate = _conformance_estimate(cards)
    if blocked_seed is not None:
        sentences.append(
            "This scan could not establish usable seed-page coverage. The absence of "
            "findings is not a passing result; obtain authorized access and rescan."
        )
    elif estimate:
        sentences.append(f"Rough effort to clear what this tool can see: **{estimate}**.")
    else:
        sentences.append(
            "No likely automated barriers remain in this evidence set. Review Appendix B "
            "and complete the manual matrix before drawing any conformance conclusion."
        )

    for s in sentences[:SUMMARY_MAX_SENTENCES]:
        lines.append(s)
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Section: conformance scorecard.
# ---------------------------------------------------------------------------


def _conformance_scorecard(
    cards: list[AuditCard], *, blocked_seed: tuple[int | None, str | None] | None = None
) -> list[str]:
    """A table by WCAG level + a POUR-principle rollup.

    Answers the stakeholder question "where do we stand on Level AA?"
    without making them count cards.
    """
    lines = ["## Open barrier summary", ""]
    if not cards:
        if blocked_seed is not None:
            lines.append(
                "_No open barrier evidence was collected because coverage was not established; "
                "this is not a passing result._"
            )
        else:
            lines.append(
                "_No confirmed open barriers in this evidence set. Review the appendices and "
                "manual matrix before drawing a conformance conclusion._"
            )
        return lines

    by_level: dict[str, int] = {}
    by_level_pages: dict[str, set[int]] = {}
    for c in cards:
        level = c.wcag_level or "—"
        by_level[level] = by_level.get(level, 0) + 1
        by_level_pages.setdefault(level, set())

    lines.append(
        "Confirmed open issue groups by mapped WCAG level; prioritize user impact and "
        "foundational dependencies:"
    )
    lines.append("")
    lines.append("| Level | Open issue types | What it means |")
    lines.append("|---|---:|---|")
    level_meaning = {
        "A": "Foundational requirements; triage promptly alongside actual user impact.",
        "AA": "Selected report target; confirm the applicable U-M and legal context.",
        "AAA": "Beyond the selected AA target; prioritize where it materially helps users.",
    }
    for level in ("A", "AA", "AAA"):
        if by_level.get(level):
            lines.append(f"| **{level}** | {by_level[level]} | {level_meaning[level]} |")
    lines.append("")

    # POUR principle rollup — which of the four WCAG principles is weakest.
    by_principle: dict[str, int] = {}
    for c in cards:
        principle = _principle_for(c.wcag_sc)
        by_principle[principle] = by_principle.get(principle, 0) + 1
    if by_principle:
        lines.append('By WCAG principle (the "POUR" model):')
        lines.append("")
        lines.append("| Principle | Open issue types |")
        lines.append("|---|---:|")
        for principle in ("Perceivable", "Operable", "Understandable", "Robust"):
            if by_principle.get(principle):
                lines.append(f"| {principle} | {by_principle[principle]} |")
    return lines


# ---------------------------------------------------------------------------
# Section: who is affected (abilities rollup).
# ---------------------------------------------------------------------------


def _abilities_rollup(cards: list[AuditCard]) -> list[str]:
    """Counts of open issues by the user ability each one blocks."""
    lines = ["## Who is affected", ""]
    by_ability: dict[str, int] = {}
    by_ability_pages: dict[str, int] = {}
    for c in cards:
        for ability in c.abilities:
            by_ability[ability] = by_ability.get(ability, 0) + 1
            by_ability_pages[ability] = by_ability_pages.get(ability, 0) + c.affected_page_count
    if not by_ability:
        lines.append(
            "_No ability metadata on the open issues. Add `abilities_affected` "
            "to the rule cards in `rules/audit_report.yaml` to populate this._"
        )
        return lines

    lines.append(
        "Each issue is tagged with the user groups it blocks. One issue can "
        "affect several groups, so these counts overlap."
    )
    lines.append("")
    lines.append("| User group | Issue types affecting them | Across (page-instances) |")
    lines.append("|---|---:|---:|")
    ability_label = {
        "vision": "Vision (blind / low-vision / color-blind)",
        "motor": "Motor (keyboard-only / switch / tremor)",
        "cognition": "Cognition (memory / attention / language)",
        "hearing": "Hearing (deaf / hard-of-hearing)",
    }
    for ability, count in sorted(by_ability.items(), key=lambda kv: -kv[1]):
        label = ability_label.get(ability, ability.capitalize())
        lines.append(f"| {label} | {count} | {by_ability_pages[ability]} |")
    return lines


# ---------------------------------------------------------------------------
# Section: coverage and method.
# ---------------------------------------------------------------------------


def _coverage_and_method(
    rows: list[Any], scan: ExportScan, interaction: InteractionCoverage
) -> list[str]:
    """What each detection pipeline checks + the honest "not checked" list."""
    lines = ["## Coverage and method", ""]
    pipelines_present = {r.pipeline for r in rows}
    # axe leaves a definitive "I ran" trace in the scan row even when it
    # finds nothing; the other pipelines only signal via their findings.
    axe_ran = scan.axe_pages_scanned > 0 or "axe" in pipelines_present
    alfa_ran = scan.alfa_pages_scanned > 0 or "alfa" in pipelines_present

    lines.append(
        "This audit used multiple detection methods. Each sees different "
        "things; together they reach further than any one tool, but none "
        "of them replace a human reviewer."
    )
    lines.append("")
    lines.append("| Method | Findings here? | What it checks | Confidence |")
    lines.append("|---|---|---|---|")
    for p in _PIPELINE_COVERAGE:
        if p["key"] == "axe":
            ran = (
                "✅ found issues"
                if "axe" in pipelines_present
                else ("ran, clean" if axe_ran else "—")
            )
        elif p["key"] == "alfa":
            ran = (
                "✅ found outcomes"
                if "alfa" in pipelines_present
                else ("ran, clean" if alfa_ran else "—")
            )
        elif p["key"] == "interaction":
            if not interaction.enabled:
                ran = "turned off"
            elif interaction.findings_revealed:
                ran = "✅ found issues"
            elif interaction.states_total:
                ran = "ran, clean"
            else:
                ran = "—"
        else:
            ran = "✅ found issues" if p["key"] in pipelines_present else "—"
        lines.append(f"| **{p['name']}** | {ran} | {p['checks']} | {p['confidence']} |")
    lines.append("")
    lines.append(
        "_A “—” means this method produced no findings on this scan — it may "
        "have been disabled for the run, or it ran and found nothing. axe-core "
        "and Alfa record definitive ran-clean signals when selected._"
    )
    if alfa_ran and scan.alfa_pages_scanned < scan.page_count:
        lines.append(
            f"_Alfa completed on {scan.alfa_pages_scanned} of {scan.page_count} crawled page(s); "
            "its evidence is partial for this report._"
        )
        lines.append("")
    alfa_total = scan.alfa_failed_total + scan.alfa_cant_tell_total
    retained_alfa = sum(1 for finding in scan.a11y_findings if finding.pipeline == "alfa")
    if alfa_total > retained_alfa:
        lines.append(
            f"_Alfa reported {alfa_total} actionable outcome(s), while {retained_alfa} "
            "page-level evidence record(s) are retained. Per-page evidence may have been capped; "
            "use the totals as coverage context, not as a complete evidence inventory._"
        )
        lines.append("")
    lines.append("")
    lines.extend(_dom_state_coverage(interaction))
    lines.append("")
    lines.append(
        "_The next section breaks this down to every WCAG 2.2 A/AA success "
        "criterion — what was automated, what was AI-assisted, and the full "
        "list of what still needs manual testing._"
    )
    return lines


def _dom_state_coverage(interaction: InteractionCoverage) -> list[str]:
    """What the click-through probe reached, and what it could not.

    A page count alone understates an application whose content appears after
    a click, so states are reported beside pages rather than folded into them.
    The pages where a bound stopped the sweep are named individually: "we
    tested less here" is the half of a coverage claim a reader cannot infer
    from a total, and it is the half that decides where manual testing goes.
    """
    lines = ["### States behind a click", ""]
    lines.append(interaction.status_line)
    lines.append("")
    if not interaction.enabled:
        return lines

    if interaction.ledger_recorded and interaction.controls_found:
        ratio = interaction.coverage_ratio
        pct = f"{ratio * 100:.0f}%" if ratio is not None else "n/a"
        lines.append("| Measure | Value |")
        lines.append("|---|---|")
        lines.append(f"| Pages probed | {interaction.pages_probed} |")
        lines.append(f"| Controls found | {interaction.controls_found} |")
        lines.append(f"| Controls operated | {interaction.controls_operated} ({pct}) |")
        lines.append(f"| Additional DOM states reached | {interaction.states_total} |")
        lines.append(f"| Findings visible only after a click | {interaction.findings_revealed} |")
        lines.append(f"| Controls refused as destructive | {interaction.blocked_controls} |")
        lines.append("")

    for caveat in interaction.caveats:
        lines.append(f"- {caveat}")
    lines.append("")

    limited = interaction.limited_pages
    if limited:
        lines.append("**Pages where the sweep stopped early**")
        lines.append("")
        lines.append("| Page | Controls operated | States | Why it stopped |")
        lines.append("|---|---|---|---|")
        for page in limited[:_MAX_LIMITED_PAGES]:
            lines.append(
                f"| {page.page_url} | {page.controls_operated} of {page.controls_found} "
                f"| {page.states} | {page.limit_text} |"
            )
        if len(limited) > _MAX_LIMITED_PAGES:
            lines.append(
                f"| _…and {len(limited) - _MAX_LIMITED_PAGES} more page(s)_ | | | "
                "_see the workbook's DOM States sheet_ |"
            )
        lines.append("")
        lines.append(
            "_These pages were tested, but not exhaustively: content behind the "
            "controls that were not reached has neither passed nor failed._"
        )
    return lines


# ---------------------------------------------------------------------------
# Section: WCAG 2.2 A/AA conformance coverage (from the coverage matrix).
# ---------------------------------------------------------------------------


def _wcag_coverage_matrix() -> list[str]:
    """Per-criterion coverage: automated / AI-assisted / manual, from the
    single source of truth in ``rules/wcag_coverage.yaml``.

    This is the honest conformance picture — it does not depend on what this
    particular scan found. It tells the reader, for all 55 Level A/AA
    criteria, exactly which ones a tool can speak to and which ones a human
    must test. That last list IS the manual-testing checklist.
    """
    crit = coverage_matrix.load_matrix()
    s = coverage_matrix.summary()
    lbl = coverage_matrix.METHOD_LABELS

    lines = ["## WCAG 2.2 A/AA coverage — what's automated vs. manual", ""]
    lines.append(
        f"Across all **{s.total}** Level A/AA success criteria, here is exactly "
        "what Axcess can and cannot test. Automated results are bounded evidence, "
        "AI-assisted findings are review leads, and manual-only criteria are not "
        "detected by any pipeline. Every final decision remains part of expert review."
    )
    lines.append("")
    lines.append("| Coverage | Criteria | What it means |")
    lines.append("|---|---:|---|")
    for m in coverage_matrix.METHODS:
        lines.append(
            f"| **{lbl[m]}** | {s.by_method.get(m, 0)} | {coverage_matrix.METHOD_BLURB[m]} |"
        )
    lines.append("")

    covered = [c for c in crit if c.method != "manual"]
    manual = [c for c in crit if c.method == "manual"]

    lines.append(f"### Automated &amp; AI-assisted ({len(covered)} criteria)")
    lines.append("")
    lines.append("| SC | Criterion | Lvl | Coverage | What Axcess does | Still verify by hand |")
    lines.append("|---|---|---|---|---|---|")
    for c in covered:
        lines.append(
            f"| {c.sc} | {c.name} | {c.level} | {lbl[c.method]} "
            f"| {_clean(c.automated_check)} | {_clean(c.manual_check)} |"
        )
    lines.append("")

    lines.append(f"### Needs manual testing ({len(manual)} criteria)")
    lines.append("")
    lines.append(
        "No Axcess pipeline detects these — they require a human. Treat this "
        "as your manual-test checklist for full Level A/AA conformance."
    )
    lines.append("")
    lines.append("| SC | Criterion | Lvl | What to test |")
    lines.append("|---|---|---|---|")
    for c in manual:
        lines.append(f"| {c.sc} | {c.name} | {c.level} | {_clean(c.manual_check)} |")
    return lines


def _clean(text: str) -> str:
    """Collapse whitespace + escape pipes so prose survives a Markdown cell."""
    return " ".join(text.split()).replace("|", "\\|")


# ---------------------------------------------------------------------------
# Section: page hotspots.
# ---------------------------------------------------------------------------


def _page_hotspots(
    conn: sqlite3.Connection,
    scan: ExportScan,
    cards: list[AuditCard],
) -> list[str]:
    """Top pages ranked by a severity-weighted count of open findings.

    Lets a team that can only touch a few pages this sprint pick the
    ones where a fix clears the most (and the most severe) issues.
    """
    lines = ["## Page hotspots", ""]
    if not cards:
        lines.append("_No open findings to locate._")
        return lines

    # Weight by severity so one critical outranks several minors.
    weight = {"Critical": 4.0, "Serious": 3.0, "Moderate": 2.0, "Minor": 1.0}
    page_score: dict[str, float] = {}
    page_issue_count: dict[str, int] = {}
    page_title_for: dict[str, str | None] = {}
    for card in cards:
        w = weight.get(card.severity, 1.0)
        for loc in card.locations:
            url = loc.page_url or "(unknown)"
            page_score[url] = page_score.get(url, 0.0) + w
            page_issue_count[url] = page_issue_count.get(url, 0) + 1
            if url not in page_title_for:
                page_title_for[url] = loc.page_title

    if not page_score:
        lines.append(
            "_Open issues are present but not pinned to specific pages — "
            "see the issue cards for details._"
        )
        return lines

    lines.append(
        "Pages carrying the most (and most severe) open findings. Fixing "
        "shared templates here clears issues across the rest of the site too."
    )
    lines.append("")
    lines.append("| Page | Weighted load | Findings shown |")
    lines.append("|---|---:|---:|")
    ranked = sorted(page_score.items(), key=lambda kv: -kv[1])[:MAX_HOTSPOTS]
    for url, score in ranked:
        title = page_title_for.get(url)
        label = f"{url} ({title})" if title else url
        lines.append(f"| {_md_escape(_short(label, 90))} | {score:.0f} | {page_issue_count[url]} |")
    lines.append("")
    lines.append(
        "_Weighted load = sum of severity weights (Critical 4 · Serious 3 · "
        "Moderate 2 · Minor 1) for the sample locations shown per card._"
    )
    return lines


# ---------------------------------------------------------------------------
# Section: remediation worklist by owner.
# ---------------------------------------------------------------------------


def _worklist_by_owner(cards: list[AuditCard]) -> list[str]:
    """Split the open work into per-role checklists.

    A developer shouldn't have to read the editor's items and vice versa.
    Each pack is a compact, severity-ordered checklist of issue titles
    with effort + reach.
    """
    lines = ["## Remediation worklist by owner", ""]
    if not cards:
        lines.append("_Nothing open to assign._")
        return lines

    by_owner: dict[str, list[AuditCard]] = {}
    for card in cards:
        owner = _owner_key(card.owner)
        by_owner.setdefault(owner, []).append(card)

    lines.append("The same findings, re-sliced by who fixes them. Hand each team their pack.")
    lines.append("")
    # Known owners first, in a sensible order, then any custom labels.
    ordered = [o for o in _KNOWN_OWNERS if o in by_owner]
    ordered += [o for o in by_owner if o not in _KNOWN_OWNERS]
    for owner in ordered:
        owner_cards = sorted(
            by_owner[owner], key=lambda c: (_severity_rank(c.severity), -c.affected_page_count)
        )
        label = _OWNER_LABELS.get(owner, owner.capitalize())
        lines.append(f"### {label} ({len(owner_cards)} item(s))")
        lines.append("")
        for card in owner_cards:
            plural = "s" if card.affected_page_count != 1 else ""
            lines.append(
                f"- [ ] **{card.title}** — {card.severity}, {card.effort}, "
                f"{card.affected_page_count} page{plural}."
            )
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Section: issue cards.
# ---------------------------------------------------------------------------


def _render_card(idx: int, card: AuditCard) -> list[str]:
    """One issue card, framework shape."""
    lines: list[str] = []
    lines.append(f"### {idx}. {card.title}")
    if card.needs_human_review:
        lines.append("")
        if card.pipeline == "alfa":
            lines.append(
                "> ⚠ **Human review needed** — Alfa ACT evidence is a review lead, "
                "not a conformance verdict. Confirm any `cantTell` outcome manually "
                "before reporting it as a barrier."
            )
        else:
            lines.append(
                "> ⚠ **Human review needed** — this finding doesn't have a "
                "templated fix in our rule book yet. The data is real; the "
                "prescriptive guidance below is light."
            )
    lines.append("")

    if card.wcag_sc:
        lines.append(
            f"**WCAG:** SC {card.wcag_sc}"
            + (f" {card.wcag_name}" if card.wcag_name else "")
            + (f" — Level {card.wcag_level}" if card.wcag_level else "")
        )
    else:
        lines.append("**WCAG:** Best-practice — no specific SC mapping.")
    lines.append("")
    lines.append(f"**Detected by:** {_PIPELINE_LABEL.get(card.pipeline, card.pipeline)}.")
    lines.append("")

    where = (
        f"**Where:** {card.affected_finding_count} finding(s) on "
        f"**{card.affected_page_count}** page(s)."
    )
    if card.triaged_count:
        where += f" ({card.triaged_count} already triaged.)"
    lines.append(where)
    if card.locations:
        lines.append("")
        lines.append("Specific locations:")
        for loc in card.locations:
            lines.append(_format_location(loc))
        if card.location_overflow > 0:
            lines.append(f"- _…and {card.location_overflow} more location(s)._")
    lines.append("")

    lines.append("**What is happening:**")
    lines.append("")
    lines.append(card.what_happening.strip())
    lines.append("")

    lines.append("**Why it matters:**")
    lines.append("")
    lines.append(card.why_matters.strip())
    lines.append("")

    if card.abilities:
        pretty = ", ".join(a.capitalize() for a in card.abilities)
        lines.append(f"**Affects:** {pretty}.")
        lines.append("")

    lines.append(f"**Severity:** {card.severity} — {card.severity_reason}")
    lines.append("")
    lines.append(f"**Effort:** {card.effort}")
    lines.append("")
    lines.append(f"**Owner:** {card.owner}")
    lines.append("")

    lines.append("**Fix (do this):**")
    lines.append("")
    for i, step in enumerate(card.fix_steps, start=1):
        lines.append(f"{i}. {_strip_html(step).strip()}")
    lines.append("")

    if card.verify_manual or card.verify_automated or card.acceptance:
        lines.append("**Verify it is fixed:**")
        lines.append("")
        if card.verify_manual:
            lines.append(f"- **Manual:** {_strip_html(card.verify_manual).strip()}")
        if card.verify_automated:
            lines.append(f"- **Automated:** {_strip_html(card.verify_automated).strip()}")
        if card.acceptance:
            lines.append(f"- **Acceptance:** {_strip_html(card.acceptance).strip()}")
        lines.append("")

    lines.append(f"**My confidence:** {card.confidence}.")
    if card.note:
        lines.append("")
        lines.append(f"_Rule docs: {card.note}_")
    return lines


# ---------------------------------------------------------------------------
# Section: appendices.
# ---------------------------------------------------------------------------


def _appendix_a(dropped: list[DroppedFinding]) -> list[str]:
    """Already-triaged issues — the receipt that self-critique ran."""
    lines = ["## Appendix A — Findings dropped during self-critique", ""]
    if not dropped:
        lines.append(
            "_No findings were dropped. Either no triage has happened yet "
            "(every finding is still `new`), or no synthesis ran._"
        )
        return lines
    if any(item.reason.startswith("Triaged subset:") for item in dropped):
        lines.append(
            "These detected findings or finding subsets were set aside after triage "
            "(remediated, accepted as a risk, or marked a false positive). Listed "
            "here so the reader can confirm the self-critique didn't quietly hide "
            "a real bug."
        )
    else:
        lines.append(
            "These issue types *were* detected but every finding in them has "
            "already been triaged (remediated, accepted as a risk, or marked a "
            "false positive). Listed here so the reader can confirm the "
            "self-critique didn't quietly hide a real bug."
        )
    lines.append("")
    lines.append("| Method | Issue | WCAG | Reason set aside |")
    lines.append("|---|---|---|---|")
    for d in dropped[:200]:
        lines.append(
            f"| {d.pipeline} | {_md_escape(d.location)} | "
            f"{d.wcag_sc or '—'} | {_md_escape(d.reason)} |"
        )
    if len(dropped) > 200:
        lines.append(f"| _…+{len(dropped) - 200} more rows omitted._ | | | |")
    return lines


def _appendix_b(best_practice: list[Any]) -> list[str]:
    """Evidence that must not be represented as an automated WCAG failure."""
    lines = ["## Appendix B — Review leads and informational evidence", ""]
    if not best_practice:
        lines.append("_No best-practice or out-of-scope findings to flag for this scan._")
        return lines
    lines.append(
        "These results are preserved for transparency but are not included in "
        "the remediation scorecard. They are AI-assisted or ambiguous review "
        "leads, informational/pass evidence, or best-practice observations with "
        "no criterion mapping. An expert decision is required before a review "
        "lead can be described as a barrier."
    )
    lines.append("")
    if any(row.pipeline == "alfa" for row in best_practice):
        lines.append(
            "**Alfa note:** Alfa ACT evidence is a review lead when the engine "
            "returns `cantTell`; it is not a conformance failure until an expert "
            "reviews the stored evidence."
        )
        lines.append("")
    for row in best_practice[:TOP_GROUPS_PER_SECTION]:
        plural = "s" if row.page_count != 1 else ""
        # Show the underlying rule id (stripped of the ``axe:`` UI prefix)
        # so a developer can grep for it; keep the human title up front.
        rule_id = row.issue_key.split(":", 1)[-1]
        lines.append(
            f"- **{row.title}** (`{rule_id}`) — {row.occurrence_count} "
            f"finding(s) on {row.page_count} page{plural}; "
            f"**{row.review_lane.replace('_', ' ')} / {row.evidence_confidence} confidence**. "
            f"{row.evidence_summary}"
        )
    if len(best_practice) > TOP_GROUPS_PER_SECTION:
        lines.append(f"- _…+{len(best_practice) - TOP_GROUPS_PER_SECTION} more._")
    return lines


# ---------------------------------------------------------------------------
# Card construction (from an IssueRow).
# ---------------------------------------------------------------------------


def _card_from_row(
    conn: sqlite3.Connection,
    row: Any,
    rules: dict[str, Any],
) -> AuditCard:
    """Turn one unified IssueRow into a fully-rendered AuditCard.

    The row already carries pipeline, conformance, abilities, difficulty,
    owner, and the YAML what/why/how (resolved by ``list_issues``). We
    add the bits the row doesn't carry: element-level locations, the
    verify/confidence fields (re-looked-up from the YAML), a severity
    reason, and the human-review flag.
    """
    meta = _meta_for_row(row, rules)
    severity = _IMPACT_SEVERITY.get(row.impact or "", "Moderate")
    locations, overflow = _locations_for_row(conn, row)
    triaged = sum(v for k, v in row.status_summary.items() if k in _TRIAGED_STATUSES)
    fix_steps = list(row.fix_steps) or [
        f"Human review needed — no templated fix for `{row.issue_key}` in "
        "`rules/audit_report.yaml` yet."
        + (f" See the rule docs: {row.help_url}" if row.help_url else "")
    ]
    # IssueRow carries `conformance` (A/AA/AAA/BP), not a raw level; the
    # three real levels map straight through, BP has no level.
    wcag_level = row.conformance if row.conformance in ("A", "AA", "AAA") else None
    return AuditCard(
        pipeline=row.pipeline,
        title=row.title,
        wcag_sc=row.wcag_sc,
        wcag_name=row.wcag_name,
        wcag_level=wcag_level,
        severity=severity,
        severity_reason=_severity_reason(row, severity),
        effort=_effort_from_difficulty(row.difficulty),
        owner=_owner_label(row.responsibility),
        abilities=tuple(row.abilities_affected),
        affected_page_count=row.page_count,
        affected_finding_count=row.occurrence_count,
        triaged_count=triaged,
        locations=locations,
        location_overflow=overflow,
        what_happening=row.description
        or f"{row.occurrence_count} finding(s) for {row.title} across {row.page_count} page(s).",
        why_matters=row.why_matters or "Users relying on assistive technology hit a barrier here.",
        fix_steps=fix_steps,
        verify_manual=meta.get("verify_manual"),
        verify_automated=meta.get("verify_automated"),
        acceptance=row.acceptance,
        confidence=(meta.get("confidence_default") or "medium").title(),
        needs_human_review=(row.pipeline == "alfa") or not row.fix_steps,
        note=row.help_url,
        finding_ids=list(row.finding_ids),
    )


def _locations_for_row(
    conn: sqlite3.Connection,
    row: Any,
) -> tuple[list[IssueLocation], int]:
    """Pull element-level "exactly where" pointers for a row's findings.

    DOM pipelines (axe/semantic/keyboard) live in ``page_a11y_findings``;
    image findings live in ``findings`` joined out to their pages. Capped
    at ``MAX_LOCATIONS_PER_CARD`` with the remainder reported as overflow.
    """
    ids = list(row.finding_ids)
    if not ids:
        return [], 0
    sample = ids[:MAX_LOCATIONS_PER_CARD]
    placeholders = ",".join("?" for _ in sample)
    locations: list[IssueLocation] = []

    if row.pipeline in ("axe", "alfa", "semantic", "keyboard", "responsive", "focus", "visual"):
        db_rows = conn.execute(
            f"""
            SELECT p.url_normalized AS page_url, p.title AS page_title,
                   a.target_selector, a.html_snippet, a.failure_summary, a.revealed_by,
                   a.pipeline, a.engine_outcome, a.engine_evidence_json
              FROM page_a11y_findings a
              JOIN pages p ON p.id = a.page_id
             WHERE a.id IN ({placeholders})
            """,  # noqa: S608 — placeholders are int-only
            tuple(sample),
        ).fetchall()
        for raw in db_rows:
            r = normalize_finding(dict(raw))
            detail = r["failure_summary"] or ""
            target = str(r.get("target_display") or r["target_selector"] or "")
            locations.append(
                IssueLocation(
                    page_url=str(r["page_url"] or ""),
                    page_title=r["page_title"],
                    description=(
                        target
                        if r["pipeline"] == "alfa"
                        else _describe_dom_location(target, str(r["html_snippet"] or ""))
                    ),
                    selector=(
                        str(r["target_selector"]) if target == STRUCTURED_TARGET_LABEL else target
                    )
                    or None,
                    image_url=None,
                    detail=(
                        bounded_summary(detail, r.get("engine_evidence_status"), maximum=240)
                        if r["pipeline"] == "alfa"
                        else _short(" ".join(detail.split()), 120)
                    )
                    or None,
                    revealed_by=str(r["revealed_by"] or "") or None,
                )
            )
    else:  # image pipeline
        db_rows = conn.execute(
            f"""
            SELECT p.url_normalized AS page_url, p.title AS page_title,
                   i.src_url_canonical AS image_url,
                   pi.above_fold AS above_fold, pi.position AS position
              FROM findings f
              JOIN images i ON i.id = f.image_id
              JOIN page_images pi ON pi.image_id = i.id
              JOIN pages p ON p.id = pi.page_id
             WHERE f.id IN ({placeholders})
             GROUP BY f.id, p.id
            """,  # noqa: S608 — placeholders are int-only
            tuple(sample),
        ).fetchall()
        for r in db_rows:
            pos = r["position"]
            locations.append(
                IssueLocation(
                    page_url=str(r["page_url"] or ""),
                    page_title=r["page_title"],
                    description=_describe_image_location(
                        above_fold=bool(r["above_fold"]),
                        position=int(pos) if pos is not None else None,
                    ),
                    selector=None,
                    image_url=str(r["image_url"] or "") or None,
                    detail=None,
                )
            )

    overflow = max(0, len(ids) - len(locations))
    return locations, overflow


def issue_locations(conn: sqlite3.Connection, row: Any) -> tuple[list[IssueLocation], int]:
    """Expose retained locations for review-only rows that have no issue card."""
    return _locations_for_row(conn, row)


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------


def _is_fully_triaged(row: Any) -> bool:
    """True when every finding in the row sits in a triaged status."""
    summary: dict[str, int] = dict(row.status_summary or {})
    total = sum(summary.values())
    if total == 0:
        return False
    open_count = sum(v for k, v in summary.items() if k in _OPEN_STATUSES)
    return bool(open_count == 0)


def _status_phrase(summary: dict[str, int]) -> str:
    """e.g. ``accepted_risk (1)`` — used in Appendix A's reason column."""
    parts = [f"{k} ({v})" for k, v in summary.items() if v and k in _TRIAGED_STATUSES]
    return ", ".join(parts) or "resolved"


def _methods_line(rows: list[Any]) -> str:
    """Comma-joined human labels for the pipelines that produced findings."""
    present = {r.pipeline for r in rows}
    labels = [
        _PIPELINE_LABEL[p]
        for p in ("axe", "alfa", "image", "semantic", "keyboard", "responsive", "focus", "visual")
        if p in present
    ]
    return ", ".join(labels) if labels else "none (no findings produced)"


def _principle_for(wcag_sc: str | None) -> str:
    if not wcag_sc:
        return "Other / best-practice"
    return _PRINCIPLE.get(wcag_sc.split(".", 1)[0], "Other / best-practice")


def _severity_rank(label: str) -> int:
    return _SEVERITY_RANK.get(label, 4)


def _severity_reason(row: Any, severity: str) -> str:
    """One-line justification tying severity to user impact, not rule wording."""
    if row.page_count > 50:
        return (
            f"Single issue across **{row.page_count} page(s)** "
            f"({row.occurrence_count} finding(s)) — almost certainly one "
            "shared template/component, so one fix has big payoff."
        )
    if severity == "Critical":
        return (
            "Completely blocks an assistive-technology user from the "
            "affected content — no workaround."
        )
    if severity == "Serious":
        return "A real barrier for affected users, even if a workaround sometimes exists."
    return f"{row.occurrence_count} finding(s) on {row.page_count} page(s)."


def _format_location(loc: IssueLocation) -> str:
    """Render a plain-language location with technical evidence retained."""
    if loc.page_url.startswith(("https://", "http://")):
        page_label = loc.page_title or _short(loc.page_url, 80)
        page_label = _md_escape(page_label).replace("[", "\\[").replace("]", "\\]")
        page = f"[{page_label}](<{loc.page_url}>)"
    else:
        page = loc.page_title or loc.page_url or "(unknown page)"
    if loc.selector:
        target = f" **Technical target:** `{loc.selector}`."
    elif loc.image_url:
        target = f" **Image asset:** `{_short(loc.image_url, 80)}`."
    else:
        target = ""
    detail = f" **Observed evidence:** {loc.detail}" if loc.detail else ""
    # Without this, a click-revealed instance reads as if it were on the page
    # at load, and whoever checks it reports "not reproducible".
    seen = (
        f' **Seen after:** activating "{_md_escape(loc.revealed_by)}" on this page.'
        if loc.revealed_by
        else ""
    )
    return f"- **Page:** {page}. **Location on page:** {loc.description}.{target}{seen}{detail}"


def _describe_dom_location(selector: str, html_snippet: str) -> str:
    """Describe an observed DOM target without guessing visual coordinates."""
    import html
    import json
    import re

    if selector.lstrip().startswith(("{", "[")):
        try:
            target = json.loads(selector)
        except (TypeError, ValueError):
            return "Document or element recorded in Alfa's structured target evidence"
        if isinstance(target, list) and target:
            target = target[0]
        if isinstance(target, dict):
            node_type = str(target.get("type") or "")
            if node_type == "document":
                return "Document root (the page as a whole)"
            if node_type == "attribute":
                name = str(target.get("name") or "attribute")
                value = target.get("value")
                suffix = f" with value “{_short(str(value), 60)}”" if value else ""
                return f"The {name} attribute{suffix}"
            if node_type == "text":
                data = " ".join(str(target.get("data") or "").split())
                return (
                    f"Text node containing “{_short(data, 60)}”" if data else "An empty text node"
                )
            if node_type == "element":
                tag = str(target.get("name") or "element").lower()
                structured_attrs = {
                    str(item.get("name") or "").lower(): str(item.get("value") or "")
                    for item in target.get("attributes") or []
                    if isinstance(item, dict) and item.get("name")
                }
                text_parts = [
                    str(child.get("data") or "")
                    for child in target.get("children") or []
                    if isinstance(child, dict) and child.get("type") == "text"
                ]
                text_value = _short(" ".join(" ".join(text_parts).split()), 60)
                kind = {
                    "a": "link",
                    "button": "button",
                    "img": "image",
                    "input": f"{structured_attrs.get('type', 'text')} input",
                    "iframe": "embedded frame",
                    "meta": "metadata element",
                }.get(tag, f"{tag} element")
                label = (
                    structured_attrs.get("aria-label")
                    or structured_attrs.get("alt")
                    or structured_attrs.get("title")
                )
                if label:
                    return f"{kind.capitalize()} labeled “{_short(label, 60)}”"
                if text_value:
                    return f"{kind.capitalize()} containing “{text_value}”"
                for attr in ("href", "src", "name", "placeholder", "type", "id"):
                    if structured_attrs.get(attr):
                        return (
                            f"{kind.capitalize()} with {attr} "
                            f"“{_short(structured_attrs[attr], 60)}”"
                        )
                return f"Empty {kind}"
        return "Element recorded in Alfa's structured target evidence"

    snippet = " ".join(html_snippet.split())
    tag_match = re.search(r"<\s*([a-zA-Z][\w:-]*)\b", snippet)
    tag = tag_match.group(1).lower() if tag_match else ""
    attrs: dict[str, str] = {}
    if tag_match:
        opening_end = snippet.find(">", tag_match.end())
        opening = snippet[tag_match.end() : opening_end if opening_end >= 0 else len(snippet)]
        for name, _quote, value in re.findall(
            r"([\w:-]+)\s*=\s*(['\"])(.*?)\2",
            opening,
        ):
            attrs[name.lower()] = html.unescape(value.strip())

    kind = {
        "a": "link",
        "button": "button",
        "img": "image",
        "input": f"{attrs.get('type', 'text')} input",
        "select": "selection control",
        "textarea": "text area",
        "label": "form label",
        "h1": "level 1 heading",
        "h2": "level 2 heading",
        "h3": "level 3 heading",
        "h4": "level 4 heading",
        "nav": "navigation region",
        "main": "main content region",
        "aside": "complementary region",
        "table": "table",
        "li": "list item",
        "p": "paragraph",
        "span": "text element",
        "div": "content container",
    }.get(tag, f"{tag} element" if tag else "affected element")

    accessible_label = attrs.get("aria-label") or attrs.get("alt") or attrs.get("title")
    visible_text = html.unescape(re.sub(r"<[^>]+>", " ", snippet))
    visible_text = _short(" ".join(visible_text.split()), 60)
    if accessible_label:
        description = f"{kind} labeled “{_short(accessible_label, 60)}”"
    elif visible_text and tag not in {"input", "img"}:
        description = f"{kind} containing “{visible_text}”"
    elif attrs.get("name"):
        description = f"{kind} named “{_short(attrs['name'], 60)}”"
    elif attrs.get("placeholder"):
        description = f"{kind} with placeholder “{_short(attrs['placeholder'], 60)}”"
    else:
        description = kind.capitalize()

    if attrs.get("id"):
        description += f" with ID “{_short(attrs['id'], 50)}”"
    elif attrs.get("class"):
        classes = " ".join(attrs["class"].split()[:3])
        description += f" with class “{_short(classes, 60)}”"
    elif selector:
        description += " identified by the recorded page selector"
    return description


def _describe_image_location(*, above_fold: bool, position: int | None) -> str:
    """Turn stored image order/fold evidence into reader-friendly language."""
    order = f"Image {position + 1}" if position is not None else "Image"
    viewport = "near the top of the page" if above_fold else "farther down the page"
    return f"{order}, {viewport}"


def _owner_key(label: str) -> str:
    """Reverse the display label back to a YAML owner key for grouping."""
    low = label.lower()
    for key in _KNOWN_OWNERS:
        if low.startswith(key):
            return key
    return low.split()[0] if low else "dev"


def _owner_label(owner: str | None) -> str:
    if not owner:
        return "Dev (default)"
    return owner.capitalize() if owner in _KNOWN_OWNERS else owner


# Difficulty (Beginner/Intermediate/Advanced) is the IssueRow's vocabulary;
# the report speaks in effort tiers. Map between them.
_DIFFICULTY_EFFORT = {
    "Beginner": "Under 15 minutes",
    "Intermediate": "Under 2 hours",
    "Advanced": "Multi-sprint",
}


def _effort_from_difficulty(difficulty: str) -> str:
    return _DIFFICULTY_EFFORT.get(difficulty, "Effort: see fix steps")


def _quick_win(cards: list[AuditCard]) -> AuditCard | None:
    """Most-impactful + lowest-effort card — the "ship today" pick."""
    effort_rank = {"Under 15 minutes": 0, "Under 2 hours": 1, "Multi-sprint": 2}
    if not cards:
        return None
    return min(
        cards,
        key=lambda c: (
            _severity_rank(c.severity),
            effort_rank.get(c.effort, 3),
            -c.affected_page_count,
        ),
    )


def _conformance_estimate(cards: list[AuditCard]) -> str | None:
    """Rough estimate combining card effort tiers."""
    if not cards:
        return None
    quick = sum(1 for c in cards if c.effort == "Under 15 minutes")
    short = sum(1 for c in cards if c.effort == "Under 2 hours")
    long_ = sum(1 for c in cards if c.effort == "Multi-sprint")
    parts: list[str] = []
    if quick:
        parts.append(f"{quick} quick win(s) (< 15 min each)")
    if short:
        parts.append(f"{short} medium item(s) (< 2 hr each)")
    if long_:
        parts.append(f"{long_} multi-sprint item(s)")
    return " · ".join(parts) if parts else None


def _fix_options(meta: dict[str, Any]) -> tuple[FixOption, ...]:
    """Read authored fix approaches, skipping anything malformed.

    A half-written option is worse than none: an export that prints an
    empty "Watch out for" cell reads as "nothing to watch out for".
    """
    raw = meta.get("fix_options")
    if not isinstance(raw, list):
        return ()
    options: list[FixOption] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        approach = str(item.get("approach") or "").strip()
        if not label or not approach:
            continue
        options.append(
            FixOption(
                label=label,
                approach=approach,
                watch_out=str(item.get("watch_out") or "").strip(),
            )
        )
    return tuple(options)


def _meta_for_row(row: Any, rules: dict[str, Any]) -> dict[str, Any]:
    """Re-resolve the YAML card for a row (for verify/confidence fields).

    ``list_issues`` already pulled description/why/fix/acceptance onto the
    row, but not the verify_* / confidence_default fields — look them up
    here by the same key scheme ``issues._rule_meta_for`` uses.
    """
    key = row.issue_key
    if key.startswith("axe:"):
        meta = rules.get("axe_rules", {}).get(key.removeprefix("axe:"), {})
    elif key.startswith("semantic:"):
        meta = rules.get("semantic_criteria", {}).get(key.removeprefix("semantic:"), {})
    elif key.startswith("keyboard:"):
        # Keyboard cards are keyed by SC in the YAML (semantic_criteria
        # block today). Fall back to the row's SC.
        meta = rules.get("semantic_criteria", {}).get(row.wcag_sc or "", {}) or rules.get(
            "axe_rules", {}
        ).get(row.wcag_sc or "", {})
    else:  # image:
        meta = rules.get("image_findings", {}).get(key.removeprefix("image:"), {})
    return dict(meta) if isinstance(meta, dict) else {}


def _strip_html(text: str) -> str:
    """Drop the inline <code>/<strong> tags the YAML uses for HTML rendering.

    The audit report is Markdown/plain-text; the YAML's HTML markup would
    render literally. Backtick the <code> spans, drop the rest.
    """
    import re

    text = re.sub(r"</?code>", "`", text)
    return re.sub(r"</?(strong|em|b|i)>", "", text)


def _md_escape(text: str) -> str:
    """Minimal Markdown table-cell escaping (pipe + newline → spaces)."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _short(text: str, limit: int) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def fix_options_for(row: Any, rules: dict[str, Any]) -> tuple[FixOption, ...]:
    """Authored fix approaches for one issue row; empty when none are written.

    Shares ``_meta_for_row``'s key scheme so every export resolves an
    issue to the same YAML entry. ``rules`` is passed in rather than loaded
    here: a caller rendering hundreds of issues reads the file once.
    """
    return _fix_options(_meta_for_row(row, rules))


def load_report_rules() -> dict[str, Any]:
    """Read the authored rule copy once, for callers outside this module."""
    return _load_rules()


def _load_rules() -> dict[str, Any]:
    """Read ``rules/audit_report.yaml`` once. Returns ``{}`` on parse error."""
    try:
        text = (resources.files(_RULES_PACKAGE) / _RULES_FILE).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


__all__ = [
    "AuditCard",
    "DroppedFinding",
    "FixOption",
    "IssueLocation",
    "fix_options_for",
    "load_report_rules",
    "render_audit_report",
]

# Keep the collector types imported — re-exported through the public
# render path's typing and handy for callers consuming raw rows.
_ = (ExportA11yFinding, ExportFinding)
