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

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from typing import Any

import yaml

from audit import coverage_matrix
from audit.exports.collector import ExportA11yFinding, ExportFinding, ExportScan
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
    "image": "image-of-text VLM",
    "semantic": "per-criterion LLM analyzer",
    "keyboard": "dynamic keyboard-trap probe",
    "responsive": "responsive & zoom probe",
    "focus": "live-page focus probe",
}

# Static description of each detection pipeline for the coverage section.
# Editorial, not derived — what each method can and can't see. The
# "ran" flag is filled in dynamically from the issues actually present.
_PIPELINE_COVERAGE = [
    {
        "key": "axe",
        "name": "axe-core",
        "method": "Deterministic DOM + computed-style rules run in a real browser.",
        "checks": "Contrast, missing alt/labels, ARIA misuse, landmark structure, "
        "heading order, link/button names, target size.",
        "confidence": "High — near-zero false positives; this is the industry baseline.",
    },
    {
        "key": "image",
        "name": "Image-of-text VLM",
        "method": "OCR + a vision-language model on every rendered image, "
        "cross-checked against the authored alt text.",
        "checks": "WCAG 1.4.5 (images of text) and whether the alt conveys the "
        "same information the image does.",
        "confidence": "Medium-high — the model occasionally over-flags decorative "
        "images; triage filters those.",
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
        "name": "Dynamic keyboard-trap probe",
        "method": "Drives a real browser, presses Tab/Shift-Tab/Escape, and watches "
        "where focus actually goes.",
        "checks": "WCAG 2.1.2 — focus stuck on an element, modals that don't release "
        "on Escape, untitled tabbable iframes.",
        "confidence": "High for what it reaches — but only the initial DOM; "
        "interaction-triggered traps need manual testing.",
    },
    {
        "key": "responsive",
        "name": "Responsive & zoom probe",
        "method": "Resizes the live page to 320px, the 200%-zoom proxy viewport, and "
        "applies WCAG's text-spacing override, looking for overflow and clipped text.",
        "checks": "SC 1.4.10 reflow at 320px, SC 1.4.4 text clipping at 200% zoom, "
        "SC 1.4.12 clipping under user text-spacing.",
        "confidence": "High for reflow (deterministic geometry); medium for the "
        "clipping checks — designed truncation needs a human eye.",
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
    selector: str | None
    image_url: str | None
    detail: str | None


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
    rules = _load_rules()
    when = generated_at or datetime.now(UTC)

    rows = issues_mod.list_issues(conn, scan.id)

    # Split the unified rows into the three buckets the framework's
    # self-critique pass produces:
    #   * open WCAG cards (have a real SC, at least one un-triaged finding)
    #   * dropped (every finding already triaged) → Appendix A
    #   * best-practice (no WCAG SC) → Appendix B
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
        if row.conformance == "BP" or not row.wcag_sc:
            best_practice.append(row)
            continue
        open_rows.append(row)

    cards = [_card_from_row(conn, row, rules) for row in open_rows]
    cards.sort(key=lambda c: (_severity_rank(c.severity), -c.affected_page_count))

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

    lines.extend(_executive_summary(cards, dropped, best_practice))
    lines.append("")
    lines.extend(_conformance_scorecard(cards))
    lines.append("")
    lines.extend(_abilities_rollup(cards))
    lines.append("")
    lines.extend(_coverage_and_method(rows, scan))
    lines.append("")
    lines.extend(_wcag_coverage_matrix())
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
        "**Scope note.** Automated tooling detects roughly 30-40% of WCAG "
        "2.x AA success criteria. This report combines four methods (see "
        "*Coverage and method* above) to push past the usual axe-only "
        "ceiling, but a clean run is **necessary, not sufficient** for "
        "conformance. The criteria listed under *What we did not check* "
        "still require a human."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: executive summary.
# ---------------------------------------------------------------------------


def _executive_summary(
    cards: list[AuditCard],
    dropped: list[DroppedFinding],
    best_practice: list[Any],
) -> list[str]:
    """Eight-sentence executive summary, framework-shaped."""
    lines: list[str] = ["## Executive summary", ""]
    sentences: list[str] = []

    level_a = sum(1 for c in cards if c.wcag_level == "A")
    level_aa = sum(1 for c in cards if c.wcag_level == "AA")
    sentences.append(
        f"After self-critique, **{len(cards)} open issue type(s)** need work "
        f"({len(dropped)} already-triaged item(s) moved to Appendix A; "
        f"{len(best_practice)} best-practice item(s) to Appendix B)."
    )
    if cards:
        sentences.append(
            f"Of those, **{level_a} fail WCAG Level A** (the legal floor) and "
            f"**{level_aa} fail Level AA** — Level A issues lock users out "
            "entirely and should be fixed first."
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
    if estimate:
        sentences.append(f"Rough effort to clear what this tool can see: **{estimate}**.")
    else:
        sentences.append(
            "The scope is already clean within the rules this tool can check — "
            "remaining conformance work is the ~60% of WCAG that needs a human."
        )

    for s in sentences[:SUMMARY_MAX_SENTENCES]:
        lines.append(s)
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Section: conformance scorecard.
# ---------------------------------------------------------------------------


def _conformance_scorecard(cards: list[AuditCard]) -> list[str]:
    """A table by WCAG level + a POUR-principle rollup.

    Answers the stakeholder question "where do we stand on Level AA?"
    without making them count cards.
    """
    lines = ["## Conformance scorecard", ""]
    if not cards:
        lines.append("_No open WCAG failures — nothing to score._")
        return lines

    by_level: dict[str, int] = {}
    by_level_pages: dict[str, set[int]] = {}
    for c in cards:
        level = c.wcag_level or "—"
        by_level[level] = by_level.get(level, 0) + 1
        by_level_pages.setdefault(level, set())

    lines.append("Open issue types by WCAG conformance level (lower level = more urgent):")
    lines.append("")
    lines.append("| Level | Open issue types | What it means |")
    lines.append("|---|---:|---|")
    level_meaning = {
        "A": "Minimum bar. Failing locks users out — fix first.",
        "AA": "The legal/industry target in most jurisdictions.",
        "AAA": "Enhanced. Aspirational; fix after A and AA.",
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


def _coverage_and_method(rows: list[Any], scan: ExportScan) -> list[str]:
    """What each detection pipeline checks + the honest "not checked" list."""
    lines = ["## Coverage and method", ""]
    pipelines_present = {r.pipeline for r in rows}
    # axe leaves a definitive "I ran" trace in the scan row even when it
    # finds nothing; the other pipelines only signal via their findings.
    axe_ran = scan.axe_pages_scanned > 0 or "axe" in pipelines_present

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
        else:
            ran = "✅ found issues" if p["key"] in pipelines_present else "—"
        lines.append(f"| **{p['name']}** | {ran} | {p['checks']} | {p['confidence']} |")
    lines.append("")
    lines.append(
        "_A “—” means this method produced no findings on this scan — it may "
        "have been disabled for the run, or it ran and found nothing. Only "
        "axe-core records a definitive ran-clean signal today._"
    )
    lines.append("")
    lines.append(
        "_The next section breaks this down to every WCAG 2.2 A/AA success "
        "criterion — what was automated, what was AI-assisted, and the full "
        "list of what still needs manual testing._"
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
        "what Axcess can and cannot determine for you. Automated coverage is "
        "high-confidence; AI-assisted findings are strong leads you should "
        "confirm; manual-only criteria are not detected by any pipeline."
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
    """Best-practice findings with no WCAG SC mapping."""
    lines = ["## Appendix B — Out of scope but worth knowing", ""]
    if not best_practice:
        lines.append("_No best-practice or out-of-scope findings to flag for this scan._")
        return lines
    lines.append(
        "Best-practice findings (mostly from axe-core) that don't map to a "
        "specific WCAG success criterion. They catch real issues — missing "
        "landmarks, heading-order quirks — but they aren't WCAG fails in the "
        "strict sense. Worth tracking, not blocking."
    )
    lines.append("")
    for row in best_practice[:TOP_GROUPS_PER_SECTION]:
        plural = "s" if row.page_count != 1 else ""
        # Show the underlying rule id (stripped of the ``axe:`` UI prefix)
        # so a developer can grep for it; keep the human title up front.
        rule_id = row.issue_key.split(":", 1)[-1]
        lines.append(
            f"- **{row.title}** (`{rule_id}`) — {row.occurrence_count} "
            f"finding(s) on {row.page_count} page{plural}."
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
        needs_human_review=not row.fix_steps,
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

    if row.pipeline in ("axe", "semantic", "keyboard"):
        db_rows = conn.execute(
            f"""
            SELECT p.url_normalized AS page_url, p.title AS page_title,
                   a.target_selector AS selector, a.failure_summary AS detail
              FROM page_a11y_findings a
              JOIN pages p ON p.id = a.page_id
             WHERE a.id IN ({placeholders})
            """,  # noqa: S608 — placeholders are int-only
            tuple(sample),
        ).fetchall()
        for r in db_rows:
            detail = r["detail"] or ""
            locations.append(
                IssueLocation(
                    page_url=str(r["page_url"] or ""),
                    page_title=r["page_title"],
                    selector=str(r["selector"] or "") or None,
                    image_url=None,
                    detail=_short(" ".join(detail.split()), 120) or None,
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
            bits = ["above the fold" if r["above_fold"] else "below the fold"]
            pos = r["position"]
            if pos is not None:
                bits.append(f"image #{int(pos) + 1} on the page")
            locations.append(
                IssueLocation(
                    page_url=str(r["page_url"] or ""),
                    page_title=r["page_title"],
                    selector=None,
                    image_url=str(r["image_url"] or "") or None,
                    detail="; ".join(bits) or None,
                )
            )

    overflow = max(0, len(ids) - len(locations))
    return locations, overflow


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
    labels = [_PIPELINE_LABEL[p] for p in ("axe", "image", "semantic", "keyboard") if p in present]
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
    """Render one location as a Markdown bullet: page → element — detail."""
    page = loc.page_url or "(unknown page)"
    if loc.page_title:
        page = f"{page} ({loc.page_title})"
    if loc.selector:
        target = f" → `{loc.selector}`"
    elif loc.image_url:
        target = f" → image `{_short(loc.image_url, 80)}`"
    else:
        target = ""
    detail = f" — {loc.detail}" if loc.detail else ""
    return f"- {_short(page, 90)}{target}{detail}"


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
    "IssueLocation",
    "render_audit_report",
]

# Keep the collector types imported — re-exported through the public
# render path's typing and handy for callers consuming raw rows.
_ = (ExportA11yFinding, ExportFinding)
