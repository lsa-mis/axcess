"""Unified Issues view — one row per "issue", across both pipelines.

This is the entry point that mirrors Siteimprove's Issues table. Until
this module landed, image-of-text findings and axe-core WCAG findings
lived in their own grouped views (``/findings/grouped`` and
``/a11y/by-rule``). The right operator workflow is *one* sortable,
filterable table that says "here is every issue your site has, in
priority order" — not two parallel tables in two URL prefixes.

The unifying abstraction is :class:`IssueRow`. An issue is a *kind* of
problem (one axe ``rule_id``, or one ``(classification, alt_adequacy)``
pair) — many findings collapse into one row. Each row carries the data
the table needs to render: title, conformance level, success criterion,
responsibility (owner), abilities affected, occurrence count, page
count, priority score, status summary, and the deep-link to the
existing per-issue detail page (we don't rebuild the detail layer; the
unified view is a façade over the existing URLs).

What this module deliberately does NOT do:

* It does not compute findings — both ``image_findings_queries`` and
  ``a11y_queries`` already do. We compose them.
* It does not invent a "Points you can gain" score. We surface the
  raw priority/severity weight we already compute and label it
  honestly as "Priority". Faking a Siteimprove-style proprietary
  score would be misleading.
* It does not deduplicate across pipelines. An image's missing alt
  shows up in *both* axe (``image-alt``) and the image-of-text
  pipeline (different cuts of the same defect, with different
  context). Keeping them separate is honest about the dual coverage.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Literal

import yaml

from audit.web import a11y_queries, image_findings_queries

# Conformance label shown in the table's badge column.
#   A   = WCAG Level A (legal floor in most jurisdictions)
#   AA  = WCAG Level AA (the practical industry bar)
#   AAA = WCAG Level AAA (aspirational)
#   BP  = best-practice (axe-coined, no SC mapping)
ConformanceLabel = str  # one of: "A" | "AA" | "AAA" | "BP"

# Owner / responsibility taxonomy (unchanged from audit_report.yaml).
ResponsibilityLabel = str

# Abilities — what user populations this issue blocks.
AbilityLabel = str  # vision | cognition | motor | hearing

# A result is not automatically an "issue" just because a detector emitted
# it.  This three-lane model is the product's quality boundary: deterministic
# rule failures may enter the remediation worklist, ambiguous/AI-assisted
# observations must be confirmed by an expert, and non-problems stay visible
# only as informational evidence.  Keeping the lane on every row prevents UI,
# MCP, and export renderers from silently turning review leads into WCAG
# failures.
ReviewLane = Literal["likely_barrier", "expert_review", "informational"]
EvidenceConfidence = Literal["high", "medium", "low"]


def _alfa_criterion_name(help_text: Any) -> str | None:
    """Extract Alfa's criterion title from its stored WCAG help label."""
    text = str(help_text or "").strip()
    match = re.match(r"^WCAG\s+[\d.]+\s*:\s*(.+)$", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match and match.group(1).strip() else None


def _alfa_diagnostics(findings: list[dict[str, Any]], *, limit: int = 2) -> list[str]:
    """Return concise, unique Alfa diagnostics already stored as summaries."""
    diagnostics: list[str] = []
    prefix = "The test target fails the following requirements:"
    for finding in findings:
        raw = " ".join(str(finding.get("failure_summary") or "").split())
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].strip()
        raw = re.sub(r"^[-•]\s*", "", raw).strip()
        raw = re.sub(r"\s+[-•]\s+", "; ", raw)
        if raw and raw not in diagnostics:
            diagnostics.append(raw)
        if len(diagnostics) >= limit:
            break
    return diagnostics


# Severity to priority weight. Used for sorting and for the "Priority"
# column. Multiplied by log(1 + page_count) to give multi-page issues
# more weight — one fix on 800 pages beats one fix on 1 page even if
# the per-page severity is identical.
_SEVERITY_WEIGHT = {
    "critical": 4.0,
    "serious": 3.0,
    "moderate": 2.0,
    "minor": 1.0,
    # Image-finding severities get the same scale (mapped through their
    # framework labels: critical/major/minor/info → critical/serious/moderate/minor).
    "major": 3.0,
    "info": 1.0,
}

# Effort tier → Difficulty label, in the Siteimprove vocabulary.
# Beginner is "any editor can do this in <15 min"; Expert is structural.
_EFFORT_TO_DIFFICULTY = {
    "under_15m": "Beginner",
    "under_2h": "Intermediate",
    "multi_sprint": "Advanced",
}

_RULES_FILE = "audit_report.yaml"
_RULES_PACKAGE = "audit.rules"


@dataclass(frozen=True)
class IssuePage:
    """One page affected by an issue, page-detail-table-ready.

    The detail view's "Pages with this issue" table needs:
    page id (for the in-app link), page URL (for the external link),
    page title (for the visible label), occurrence count, and a
    per-page status summary so the operator can see at a glance which
    pages are still untriaged.
    """

    page_id: int
    page_url: str
    page_title: str | None
    occurrence_count: int
    status_summary: dict[str, int]
    # Blob content hashes of the per-finding element screenshots captured
    # at scan time (empty when none were captured). The Excel export reads
    # these to embed visual evidence next to each issue.
    screenshot_hashes: tuple[str, ...] = ()


@dataclass(frozen=True)
class IssueDetail:
    """Everything the per-issue detail page needs in one trip.

    The detail page is the "page 2" the user pointed at in the
    Siteimprove screenshots: stat tiles at the top, a description card
    middle, and a sortable "Pages with this issue" table at the
    bottom. All three layers come from this single struct so the
    template / component doesn't have to fan out to multiple queries.
    """

    row: IssueRow
    pages: list[IssuePage]
    # YAML-sourced longform copy. All optional: an issue without a
    # template card degrades to "see source-data sample below" without
    # crashing.
    description: str | None
    why_matters: str | None
    fix_steps: list[str]
    verify_manual: str | None
    verify_automated: str | None
    acceptance: str | None
    help_url: str | None  # axe rule docs deep-link (None for image issues)


@dataclass(frozen=True)
class IssueLocation:
    """One bounded, scan-scoped location sample for the unified table."""

    page_id: int
    page_url: str
    page_title: str | None
    target: str
    context: str | None
    evidence_url: str
    # The control that had to be operated before this markup existed. None
    # means it was present when the page loaded. Without it a reader cannot
    # reproduce the finding: the URL alone does not show a defect that only
    # appears once a menu is opened.
    revealed_by: str | None = None


@dataclass(frozen=True)
class IssueRow:
    """One row in the unified Issues table.

    The schema deliberately mirrors what an operator would scan visually:
    What is wrong → How serious (Conformance) → Where it belongs (SC) →
    Who fixes it (Responsibility) → Who it blocks (Abilities) →
    How widespread (Occurrences, Pages) → How urgent (Priority) →
    What's been done (Status / Tasks).

    The trailing four fields (description, why_matters, fix_steps,
    acceptance) ride along with each row so the Issues list can
    surface the *what/why/how* inline — the operator triages without
    round-tripping through the detail page. They're optional because
    rules not in ``rules/audit_report.yaml`` produce rows with empty
    longform content; the row still renders.
    """

    pipeline: str  # "axe" | "image" | "semantic"
    issue_key: str  # e.g. `axe:<rule_id>`, `alfa:<rule_id>:<outcome>`, or `image:...`
    title: str
    conformance: ConformanceLabel
    wcag_sc: str | None
    wcag_name: str | None
    responsibility: ResponsibilityLabel
    abilities_affected: tuple[AbilityLabel, ...]
    difficulty: str  # Beginner | Intermediate | Advanced | Unknown
    occurrence_count: int
    page_count: int
    priority: float  # Same scale across both pipelines
    impact: str | None  # critical/serious/moderate/minor (or None)
    status_summary: dict[str, int]  # bucket → count, including "new"
    detail_url: str  # Where clicking the row title goes
    finding_ids: tuple[int, ...]  # Backing finding ids (for bulk-status, exports)
    review_lane: ReviewLane
    evidence_confidence: EvidenceConfidence
    evidence_summary: str
    # Occurrences that came from a deterministic failed outcome. This is
    # intentionally separate from occurrence_count, which also includes
    # Alfa cantTell and other review-only evidence.
    high_confidence_occurrence_count: int
    # Inline expansion content. Pulled from rules/audit_report.yaml so
    # the list view can answer "what/why/how" without a second request.
    description: str | None = None
    why_matters: str | None = None
    fix_steps: tuple[str, ...] = ()
    acceptance: str | None = None
    help_url: str | None = None
    # First three unique locations only. The row's occurrence_count remains
    # the authoritative total; the issue detail retains the full evidence.
    locations: tuple[IssueLocation, ...] = ()


def list_issues(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    conformance: list[str] | None = None,
    responsibility: list[str] | None = None,
    abilities: list[str] | None = None,
    status: str | None = None,
    search: str | None = None,
    review_lane: str | None = None,
    sort: str = "priority_desc",
) -> list[IssueRow]:
    """Build the unified issues list with optional filters.

    Filter semantics:
      * ``conformance`` — list like ``["A", "AA"]``. Empty/None = all.
      * ``responsibility`` — list of owner labels. Empty/None = all.
      * ``abilities`` — list of ability labels. An issue passes if it
        affects ANY of the requested abilities (OR semantics, matching
        the operator intent of "show me everything affecting Vision").
      * ``status`` — single status string; an issue is included if at
        least one of its findings is in that status. Empty/None = all.
      * ``search`` — case-insensitive substring match against title or
        WCAG SC.

    Sort options:
      * ``priority_desc`` (default) — highest impact x spread first
      * ``priority_asc``
      * ``conformance`` — A first, then AA, then AAA, then BP
      * ``occurrences_desc`` / ``pages_desc``

    Filters applied AFTER the query (the underlying grouping queries
    are scan-wide already; filtering in Python keeps the row-building
    logic in one place).
    """
    rules = _load_rules()

    rows: list[IssueRow] = []
    rows.extend(_axe_issue_rows(conn, scan_id, rules))
    rows.extend(_image_issue_rows(conn, scan_id, rules))

    if conformance:
        wanted = {c.upper() for c in conformance}
        rows = [r for r in rows if r.conformance in wanted]
    if responsibility:
        wanted_r = {r.lower() for r in responsibility}
        rows = [r for r in rows if r.responsibility.lower() in wanted_r]
    if abilities:
        wanted_a = {a.lower() for a in abilities}
        rows = [r for r in rows if any(a.lower() in wanted_a for a in r.abilities_affected)]
    if status:
        rows = [r for r in rows if r.status_summary.get(status, 0) > 0]
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in r.title.lower() or (r.wcag_sc and needle in r.wcag_sc)]
    if review_lane:
        rows = [r for r in rows if r.review_lane == review_lane]

    return _sort_rows(rows, sort)


def get_issue_detail(
    conn: sqlite3.Connection,
    scan_id: int,
    issue_key: str,
    *,
    sort: str = "occurrences_desc",
) -> IssueDetail | None:
    """Load the single-issue detail view for ``issue_key``.

    ``issue_key`` shape:
      * ``axe:<rule_id>``  — e.g. ``axe:color-contrast``
      * ``alfa:<rule_id>:<outcome>`` — explicit ``failed`` / ``cant_tell`` subgroup
      * ``image:<classification>_<adequacy>`` — e.g. ``image:essential_missing``

    Returns ``None`` if no matching IssueRow exists for this scan
    (e.g. stale URL after a rescan). Callers should 404 in that case.

    ``sort`` controls the pages-with-issue table order:
      * ``occurrences_desc`` (default) — biggest contributors first
      * ``occurrences_asc``
      * ``url``                       — alphabetical by URL
      * ``status``                    — pages with un-triaged findings first
    """
    rows = list_issues(conn, scan_id)
    row = next((r for r in rows if r.issue_key == issue_key), None)
    if row is None:
        # Compatibility for links emitted before Alfa outcome subgroups were
        # introduced. Resolve the legacy `alfa:<rule>` key only when it is
        # unambiguous. A mixed failed/cantTell rule intentionally has no
        # legacy aggregate detail: recreating it would reintroduce the unsafe
        # confidence and bulk-action boundary this split fixes.
        legacy_rule, legacy_outcome = _alfa_rule_and_outcome(issue_key)
        if issue_key.startswith("alfa:") and legacy_outcome is None:
            candidates = [
                candidate
                for candidate in rows
                if candidate.pipeline == "alfa"
                and _alfa_rule_and_outcome(candidate.issue_key)[0] == legacy_rule
            ]
            if len(candidates) == 1:
                row = candidates[0]
    if row is None:
        return None

    pages = _pages_for_issue(conn, scan_id, row)
    pages = _sort_pages(pages, sort)

    rules = _load_rules()
    meta = _rule_meta_for(row, rules)

    # Help URL preference: YAML card → the row itself (the list builder
    # already resolved the per-finding URL — dequeuniversity for axe,
    # the WCAG Understanding pages for the dynamic probes) → for axe,
    # one last look at the grouped data.
    help_url: str | None = meta.get("help_url") or row.help_url
    if row.pipeline == "axe" and not help_url:
        rule_id = row.issue_key.removeprefix("axe:")
        groups = a11y_queries.grouped_by_rule(conn, scan_id)
        match = next((g for g in groups if g["rule_id"] == rule_id), None)
        if match:
            help_url = match.get("help_url") or None

    return IssueDetail(
        row=row,
        pages=pages,
        description=meta.get("what_happening"),
        why_matters=meta.get("why_matters"),
        fix_steps=list(meta.get("fix_steps") or []),
        verify_manual=(
            meta.get("verify_manual")
            or (
                "Review the stored Alfa evidence and manually test the mapped "
                "WCAG success criterion."
                if row.pipeline == "alfa"
                else None
            )
        ),
        verify_automated=(
            meta.get("verify_automated")
            or (
                "Run the same Alfa rule in a fresh scan and compare its source-attributed outcomes."
                if row.pipeline == "alfa"
                else None
            )
        ),
        acceptance=meta.get("acceptance"),
        help_url=help_url,
    )


def _rule_meta_for(row: IssueRow, rules: dict[str, Any]) -> dict[str, Any]:
    """Pick the right YAML block for this issue's pipeline + key."""
    # The yaml-loaded dicts are typed as `Any` at this depth — coerce
    # via `dict(...)` so mypy sees a concrete dict[str, Any] return.
    if row.pipeline == "axe":
        rule_id = row.issue_key.removeprefix("axe:")
        meta = rules.get("axe_rules", {}).get(rule_id, {})
        return dict(meta) if isinstance(meta, dict) else {}
    if row.pipeline == "semantic":
        # `semantic:<sc>` → look up the SC in the semantic_criteria
        # YAML block we added in Phase 9.1.
        sc = row.issue_key.removeprefix("semantic:")
        meta = rules.get("semantic_criteria", {}).get(sc, {})
        return dict(meta) if isinstance(meta, dict) else {}
    if row.pipeline in ("keyboard", "responsive", "focus", "visual"):
        # Dynamic-probe rows are carded by SC (one YAML card covers
        # several rule_ids — e.g. all three keyboard-trap shapes).
        # Check semantic_criteria first (where 2.1.2 and the responsive
        # SCs live), then axe_rules for any author who keyed there.
        sc = row.wcag_sc or ""
        meta = rules.get("semantic_criteria", {}).get(sc, {}) or rules.get("axe_rules", {}).get(
            sc, {}
        )
        return dict(meta) if isinstance(meta, dict) else {}
    if row.pipeline == "alfa":
        # Alfa rule documentation and ACT diagnostics are the authoritative
        # remediation lead; no axe-specific YAML card should be borrowed.
        return {}
    image_key = row.issue_key.removeprefix("image:")
    meta = rules.get("image_findings", {}).get(image_key, {})
    return dict(meta) if isinstance(meta, dict) else {}


def _alfa_rule_and_outcome(issue_key: str) -> tuple[str, str | None]:
    """Parse an Alfa issue key while accepting the pre-subgroup key shape."""

    value = issue_key.removeprefix("alfa:")
    rule_id, separator, outcome = value.rpartition(":")
    if separator and rule_id and outcome in {"failed", "cant_tell"}:
        return rule_id, outcome
    return value, None


def _pages_for_issue(
    conn: sqlite3.Connection,
    scan_id: int,
    row: IssueRow,
) -> list[IssuePage]:
    """One IssuePage per page that contributes a finding to this issue.

    Axe findings are page-rooted in the DB (``page_a11y_findings``); for
    those we group directly on ``page_id``. Image findings live one
    level removed (``findings`` joins to ``images`` joins to
    ``page_images`` joins to ``pages``), so the query is heavier; the
    column shape comes out the same.
    """
    if row.pipeline in (
        "axe",
        "alfa",
        "semantic",
        "keyboard",
        "responsive",
        "focus",
        "visual",
        "protected_image",
    ):
        # All four DOM pipelines live in page_a11y_findings; the DB
        # rule_id carries the discriminator: bare rule_id for axe
        # ("color-contrast") and the dynamic probes
        # ("keyboard-trap-stuck", "responsive-reflow-overflow"),
        # ``semantic:<sc>`` for semantic. Our UI issue_key prefixes
        # axe/keyboard/responsive with "<pipeline>:" — strip that to
        # recover the DB value; semantic's issue_key already matches
        # the DB column exactly.
        if row.pipeline == "semantic":
            rule_id = row.issue_key
            outcome: str | None = None
        elif row.pipeline == "alfa":
            rule_id, outcome = _alfa_rule_and_outcome(row.issue_key)
        else:
            rule_id = row.issue_key.split(":", 1)[1]
            outcome = None
        if row.pipeline == "alfa":
            # Outcome is part of the public issue identity. Keep page counts,
            # screenshots, and status summaries confined to that same
            # evidence class; a failed row must never absorb cantTell pages.
            rows = conn.execute(
                """
                SELECT p.id AS page_id,
                       p.url_normalized AS page_url,
                       p.title AS page_title,
                       COUNT(*) AS occurrence_count,
                       GROUP_CONCAT(a.status) AS statuses,
                       GROUP_CONCAT(a.screenshot_hash) AS screenshot_hashes
                  FROM page_a11y_findings a
                  JOIN pages p ON p.id = a.page_id
                 WHERE a.scan_id = ? AND a.pipeline = 'alfa'
                   AND a.rule_id = ? AND a.engine_outcome = ?
                 GROUP BY p.id, p.url_normalized, p.title
                """,
                (scan_id, rule_id, outcome),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT p.id AS page_id,
                       p.url_normalized AS page_url,
                       p.title AS page_title,
                       COUNT(*) AS occurrence_count,
                       GROUP_CONCAT(a.status) AS statuses,
                       GROUP_CONCAT(a.screenshot_hash) AS screenshot_hashes
                  FROM page_a11y_findings a
                  JOIN pages p ON p.id = a.page_id
                 WHERE a.scan_id = ? AND a.pipeline = ? AND a.rule_id = ?
                 GROUP BY p.id, p.url_normalized, p.title
                """,
                (scan_id, row.pipeline, rule_id),
            ).fetchall()
    else:
        # image pipeline: list every page that has at least one
        # `page_image` row pointing at an image that has a finding
        # matching the (classification, adequacy) we're after. The
        # `IssueRow.finding_ids` we already collected does the matching
        # for us — query against those ids directly.
        if not row.finding_ids:
            return []
        placeholders = ",".join("?" for _ in row.finding_ids)
        rows = conn.execute(
            f"""
            SELECT p.id AS page_id,
                   p.url_normalized AS page_url,
                   p.title AS page_title,
                   COUNT(*) AS occurrence_count,
                   GROUP_CONCAT(f.status) AS statuses
              FROM findings f
              JOIN images i ON i.id = f.image_id
              JOIN page_images pi ON pi.image_id = i.id
              JOIN pages p ON p.id = pi.page_id
             WHERE f.id IN ({placeholders})
               AND p.scan_id = ?
             GROUP BY p.id, p.url_normalized, p.title
            """,  # noqa: S608 — placeholders are int-only
            (*row.finding_ids, scan_id),
        ).fetchall()

    out: list[IssuePage] = []
    for r in rows:
        statuses = (r["statuses"] or "").split(",")
        counts: dict[str, int] = {}
        for s in statuses:
            s = s.strip()
            if s:
                counts[s] = counts.get(s, 0) + 1
        # Screenshot hashes only come back on the a11y query (the image
        # query has no such column). GROUP_CONCAT renders NULLs as the
        # literal "None"/empty, so filter those out.
        # sqlite3.Row's `in` iterates values, not keys, so we must check
        # `.keys()` explicitly (the image query lacks this column).
        row_keys = r.keys()
        raw_shots = r["screenshot_hashes"] if "screenshot_hashes" in row_keys else None
        shots = tuple(h for h in (raw_shots or "").split(",") if h and h != "None")
        out.append(
            IssuePage(
                page_id=int(r["page_id"]),
                page_url=str(r["page_url"]),
                page_title=r["page_title"],
                occurrence_count=int(r["occurrence_count"]),
                status_summary=counts,
                screenshot_hashes=shots,
            )
        )
    return out


def _sort_pages(pages: list[IssuePage], sort: str) -> list[IssuePage]:
    if sort == "occurrences_asc":
        return sorted(pages, key=lambda p: p.occurrence_count)
    if sort == "url":
        return sorted(pages, key=lambda p: p.page_url.lower())
    if sort == "status":
        # "Has un-triaged" first, then by occurrence count.
        return sorted(
            pages,
            key=lambda p: (
                -(
                    p.status_summary.get("new", 0)
                    + p.status_summary.get("reviewing", 0)
                    + p.status_summary.get("in_progress", 0)
                ),
                -p.occurrence_count,
            ),
        )
    # Default: occurrences_desc.
    return sorted(pages, key=lambda p: -p.occurrence_count)


def conformance_breakdown(rows: list[IssueRow]) -> dict[str, int]:
    """Counts by conformance label — for the page-header stat tiles."""
    out = {"A": 0, "AA": 0, "AAA": 0, "BP": 0}
    for r in rows:
        out[r.conformance] = out.get(r.conformance, 0) + 1
    return out


def responsibility_breakdown(rows: list[IssueRow]) -> dict[str, int]:
    """Counts by owner — used to render filter chips with totals."""
    out: dict[str, int] = {}
    for r in rows:
        out[r.responsibility] = out.get(r.responsibility, 0) + 1
    return out


def abilities_breakdown(rows: list[IssueRow]) -> dict[str, int]:
    """Counts by abilities affected (each row contributes once per ability)."""
    out: dict[str, int] = {}
    for r in rows:
        for a in r.abilities_affected:
            out[a] = out.get(a, 0) + 1
    return out


def review_lane_breakdown(rows: list[IssueRow]) -> dict[str, int]:
    """Count evidence groups without implying every group is a barrier."""
    out = {"likely_barrier": 0, "expert_review": 0, "informational": 0}
    for row in rows:
        out[row.review_lane] = out.get(row.review_lane, 0) + 1
    return out


# --------------------------------------------------------------------------
# Per-pipeline row builders.
# --------------------------------------------------------------------------


def _axe_issue_rows(
    conn: sqlite3.Connection,
    scan_id: int,
    rules: dict[str, Any],
) -> list[IssueRow]:
    """One row per ``rule_id`` group from the page_a11y_findings table.

    ``pipeline`` is part of the group identity. This matters for a combined
    axe+Alfa run: similar rules remain separate evidence groups rather than
    becoming an unsupported claim that two engines saw one same result.
    """
    groups = a11y_queries.grouped_by_rule(conn, scan_id)
    out: list[IssueRow] = []
    axe_rules_meta = rules.get("axe_rules", {})
    semantic_meta = rules.get("semantic_criteria", {})
    for g in groups:
        raw_rule_id = str(g["rule_id"])
        pipeline = str(g.get("pipeline") or "axe")
        finding_rows = list(g.get("findings", []))
        legacy_keyboard_observation = pipeline == "keyboard" and (
            raw_rule_id in {"keyboard-trap-modal-no-escape", "keyboard-trap-iframe"}
            or (
                raw_rule_id == "keyboard-trap-stuck"
                and not any(
                    "Shift+Tab attempts" in str(finding.get("failure_summary") or "")
                    for finding in finding_rows
                )
            )
        )
        legacy_visual_motion_observation = (
            pipeline == "visual"
            and raw_rule_id == "visual-motion-no-pause"
            and not any(
                "Runtime playback measurement:" in str(finding.get("failure_summary") or "")
                for finding in finding_rows
            )
        )
        if pipeline == "semantic":
            sc = raw_rule_id.removeprefix("semantic:")
            meta = semantic_meta.get(sc, {})
        elif pipeline == "alfa":
            # Alfa/ACT metadata is source-specific. Never borrow an axe card
            # merely because a third-party rule id happens to collide.
            meta = {}
        else:
            meta = axe_rules_meta.get(raw_rule_id, {})
            if not meta:
                sc_from_db = g.get("wcag_sc")
                if sc_from_db:
                    meta = axe_rules_meta.get(sc_from_db, {}) or semantic_meta.get(sc_from_db, {})
        if legacy_keyboard_observation or legacy_visual_motion_observation:
            # Earlier probe versions inferred SC 2.1.2 from one-way focus,
            # Escape behavior, or iframe naming. Preserve that immutable scan
            # evidence, but do not present it as an actionable conformance lead.
            meta = {}
        wcag_sc = meta.get("wcag_sc") or g.get("wcag_sc")
        wcag_level = meta.get("wcag_level") or g.get("wcag_level")
        conformance = _conformance_label(wcag_level)
        impact = g.get("impact")
        if legacy_keyboard_observation:
            wcag_sc = None
            wcag_level = None
            conformance = "BP"
            impact = "minor"
        if legacy_visual_motion_observation:
            wcag_sc = None
            wcag_level = None
            conformance = "BP"
            impact = "minor"
        alfa_outcomes = dict(g.get("engine_outcomes") or {})
        alfa_failed = int(alfa_outcomes.get("failed") or 0)
        alfa_cant_tell = int(alfa_outcomes.get("cant_tell") or 0)
        alfa_description: str | None = None
        alfa_why_matters: str | None = None
        alfa_fix_steps: tuple[str, ...] = ()
        review_lane: ReviewLane = "expert_review"
        evidence_confidence: EvidenceConfidence = "medium"
        evidence_summary = "Observed evidence requires expert confirmation."
        high_confidence_occurrences = 0
        if pipeline == "semantic":
            sc = raw_rule_id.removeprefix("semantic:")
            issue_key = f"semantic:{sc}"
            default_title = f"WCAG SC {sc} (LLM-detected)"
            evidence_summary = "AI-assisted semantic lead; confirm in page context."
        elif pipeline == "protected_image":
            issue_key = f"{pipeline}:{raw_rule_id}"
            default_title = "Protected image-of-text review lead"
            alfa_description = (
                "The local companion detected embedded text while handling a protected "
                "image in memory. The image bytes and OCR text were not retained; "
                "review the page manually to determine whether the text is essential."
            )
            alfa_why_matters = (
                "This is an image-analysis lead, not a conformance verdict. Confirm "
                "the applicable text alternative and WCAG criterion manually."
            )
            alfa_fix_steps = (
                "Re-open the affected protected page in the companion browser.",
                (
                    "Determine whether the image text is essential and identify an "
                    "equivalent text alternative."
                ),
                (
                    "If confirmed, treat it as a remediation item; otherwise keep it "
                    "labeled as unconfirmed evidence."
                ),
            )
            evidence_summary = "Local image-analysis lead; no conformance decision was automated."
        elif pipeline == "keyboard":
            issue_key = f"{pipeline}:{raw_rule_id}"
            if legacy_keyboard_observation:
                default_title = "Legacy keyboard observation — not a confirmed trap"
                review_lane = "informational"
                evidence_confidence = "low"
                evidence_summary = (
                    "An older Axcess probe used a one-direction, Escape, or iframe "
                    "heuristic that does not establish WCAG 2.1.2. Retained for audit "
                    "history; do not report it as a barrier without manual evidence."
                )
                alfa_description = (
                    "This result predates the bidirectional accuracy gate. The recorded "
                    "observation may reflect ordinary focus movement, dialog behavior, "
                    "or focus moving inside an opaque embedded document."
                )
                alfa_why_matters = (
                    "Axcess preserves original scan evidence, but unsupported historical "
                    "heuristics must not inflate the remediation worklist or a WCAG report."
                )
                alfa_fix_steps = (
                    "Do not remediate from this observation alone.",
                    "Test the component manually with Tab, Shift+Tab, and any "
                    "documented exit command.",
                    "Run a new scan to collect bidirectional keyboard-exit measurements.",
                )
            else:
                default_title = "Keyboard exit blocked in both directions"
                evidence_summary = (
                    "Measured Tab and Shift+Tab exit attempts both remained on the same "
                    "observable element; manually check for another documented exit command."
                )
        elif pipeline == "responsive":
            issue_key = f"{pipeline}:{raw_rule_id}"
            default_title = f"Responsive failure: {raw_rule_id}"
            evidence_summary = "Browser geometry signal; confirm at 320 CSS px and 200% zoom."
        elif pipeline == "focus":
            issue_key = f"{pipeline}:{raw_rule_id}"
            default_title = f"Focus not visible: {raw_rule_id}"
            evidence_summary = (
                "Browser focus probe lead; confirm across the full interaction state."
            )
        elif pipeline == "visual":
            issue_key = f"{pipeline}:{raw_rule_id}"
            if legacy_visual_motion_observation:
                default_title = "Legacy autoplay markup observation — playback not verified"
                review_lane = "informational"
                evidence_confidence = "low"
                evidence_summary = (
                    "An older detector saw autoplay markup but did not establish that media "
                    "loaded, played, or met the WCAG duration threshold. Retained for audit "
                    "history; do not report it as a barrier without manual evidence."
                )
                alfa_description = (
                    "This result predates runtime playback measurement. A missing or blocked "
                    "media resource can carry an autoplay attribute while never producing "
                    "audio or motion."
                )
                alfa_why_matters = (
                    "Markup is not enough to establish SC 1.4.2 or SC 2.2.2. Unsupported "
                    "historical observations must not inflate a remediation report."
                )
                alfa_fix_steps = (
                    "Do not remediate from this observation alone.",
                    "Verify that the media actually starts and continues playing.",
                    "Run a new scan to collect a runtime playback measurement.",
                )
            elif raw_rule_id == "visual-autoplay-audio-no-control":
                default_title = "Automatically playing audio may lack a usable control"
                evidence_summary = (
                    "Runtime playback advanced while audible audio had no detected native or "
                    "explicitly associated custom control; confirm the interaction manually."
                )
            elif raw_rule_id == "visual-motion-no-pause":
                default_title = "Moving content may lack pause, stop, or hide controls"
                evidence_summary = (
                    "Runtime motion or marquee evidence requires expert confirmation of duration, "
                    "page context, and any custom controls."
                )
            else:
                default_title = f"Visual order: {raw_rule_id}"
                evidence_summary = (
                    "Visual-model lead; compare DOM and visual reading order manually."
                )
        elif pipeline == "alfa":
            outcome_group = str(g.get("outcome_group") or "failed")
            issue_key = f"alfa:{raw_rule_id}:{outcome_group}"
            criterion_name = _alfa_criterion_name(g.get("help"))
            diagnostics = _alfa_diagnostics(finding_rows)
            diagnostic_text = "; ".join(diagnostics)
            if outcome_group == "cant_tell":
                default_title = (
                    f"{criterion_name or 'Alfa ACT result'} — expert decision needed "
                    f"(Alfa {raw_rule_id})"
                )
                evidence_summary = (
                    f"Alfa returned {alfa_cant_tell} cantTell occurrence(s); this is not a "
                    f"failure. {diagnostic_text or 'Review the stored target in page context.'}"
                )
            else:
                diagnostic_title = diagnostics[0] if diagnostics else "rule requirements failed"
                default_title = (
                    f"{criterion_name or 'Alfa ACT rule'} — {diagnostic_title} (Alfa {raw_rule_id})"
                )
                review_lane = "likely_barrier"
                evidence_confidence = "high"
                high_confidence_occurrences = alfa_failed
                evidence_summary = (
                    f"Alfa produced {alfa_failed} failed ACT occurrence(s). Observed: "
                    f"{diagnostic_text or 'the stored rule requirements failed.'}"
                )
            outcome_parts: list[str] = []
            if alfa_failed:
                outcome_parts.append(f"{alfa_failed} failed ACT outcome(s)")
            if alfa_cant_tell:
                outcome_parts.append(f"{alfa_cant_tell} cantTell expert-review lead(s)")
            alfa_description = (
                f"Siteimprove Alfa returned {' and '.join(outcome_parts)} for this rule. "
                f"WCAG {g.get('wcag_sc') or 'criterion not mapped'}"
                f"{f' ({criterion_name})' if criterion_name else ''}; Alfa rule {raw_rule_id}. "
                f"Observed diagnostic: {diagnostic_text or 'review the stored target evidence.'}"
            )
            if outcome_group == "cant_tell":
                alfa_why_matters = (
                    "A cantTell outcome is not a failure. Review the target in context and "
                    "record a human decision before describing it as a barrier."
                )
            else:
                alfa_why_matters = (
                    "A failed ACT outcome is strong automated evidence, not a conformance "
                    "verdict. Confirm that the rule applies and reproduce the barrier before "
                    "presenting the row as a confirmed accessibility issue."
                )
            alfa_fix_steps = (
                "Open the linked page evidence and review the Alfa target and diagnostic.",
                "Manually test the applicable WCAG success criterion with the "
                "relevant assistive technology.",
                (
                    "Apply the correction, then rescan the same scope to verify the "
                    "ACT outcome is resolved."
                ),
            )
        else:
            issue_key = f"axe:{raw_rule_id}"
            default_title = f"axe rule: {raw_rule_id}"
            review_lane = "likely_barrier"
            evidence_confidence = "high"
            high_confidence_occurrences = int(g["violation_count"])
            evidence_summary = "Deterministic axe-core rule failure; verify after remediation."
        out.append(
            IssueRow(
                pipeline=pipeline,
                issue_key=issue_key,
                title=meta.get("title")
                or (
                    default_title
                    if pipeline in {"alfa", "protected_image", "visual"}
                    or legacy_keyboard_observation
                    or legacy_visual_motion_observation
                    else None
                )
                or (g.get("help") if pipeline != "semantic" else None)
                or default_title,
                conformance=conformance,
                wcag_sc=wcag_sc,
                wcag_name=meta.get("wcag_name")
                or (_alfa_criterion_name(g.get("help")) if pipeline == "alfa" else None),
                responsibility=(meta.get("owner") or "dev"),
                abilities_affected=tuple(meta.get("abilities_affected") or []),
                difficulty=_EFFORT_TO_DIFFICULTY.get(meta.get("effort", ""), "Unknown"),
                occurrence_count=g["violation_count"],
                page_count=g["page_count"],
                priority=_priority(impact, g["page_count"]),
                impact=impact,
                status_summary=dict(g.get("status_breakdown") or {}),
                # Deep-link to the dedicated Issue Detail view (the
                # Siteimprove "page 2" shape — stat tiles, description,
                # pages-with-issue table). The older grouped views
                # (/a11y/by-rule, /findings/grouped) remain reachable
                # for operators who want to scroll multiple issues at
                # once. For semantic findings we use the semantic: key
                # so the detail route can also distinguish them later.
                detail_url=f"/scans/{scan_id}/issues/{issue_key}",
                finding_ids=tuple(int(f["id"]) for f in g.get("findings", [])),
                review_lane=review_lane,
                evidence_confidence=evidence_confidence,
                evidence_summary=evidence_summary,
                high_confidence_occurrence_count=high_confidence_occurrences,
                # Inline expansion content. Title's already on the row;
                # the YAML's `what_happening` / `why_matters` / fix steps
                # / `acceptance` ride along so the list view can show
                # what/why/how without a second API call. `help_url`
                # falls back to the axe-supplied URL when the YAML
                # doesn't pin one.
                description=meta.get("what_happening") or alfa_description,
                why_matters=meta.get("why_matters") or alfa_why_matters,
                fix_steps=tuple(meta.get("fix_steps") or alfa_fix_steps),
                acceptance=meta.get("acceptance"),
                help_url=meta.get("help_url") or g.get("help_url") or None,
                locations=_a11y_location_samples(finding_rows, scan_id=scan_id),
            )
        )
    return out


def _image_issue_rows(
    conn: sqlite3.Connection,
    scan_id: int,
    rules: dict[str, Any],
) -> list[IssueRow]:
    """One row per ``(classification, alt_adequacy)`` group."""
    groups = image_findings_queries.grouped_by_remediation(conn, scan_id)
    out: list[IssueRow] = []
    image_meta = rules.get("image_findings", {})
    for g in groups:
        cls = g.get("classification") or "unclassified"
        adequacy = g.get("alt_adequacy") or "unknown"
        key = f"{cls}_{adequacy}"
        meta = image_meta.get(key, {})
        # An unclassified image does not support a criterion-level claim. An
        # apparently adequate alternative is evidence of a checked image, not
        # an accessibility failure. Preserve both as visible evidence without
        # assigning an invented WCAG 1.4.5 failure.
        is_informational = adequacy == "adequate"
        is_unclassified = cls == "unclassified"
        wcag_sc = meta.get("wcag_sc") if (not is_informational and not is_unclassified) else None
        wcag_level = meta.get("wcag_level") if wcag_sc else None
        conformance = _conformance_label(wcag_level)
        # Status bucket: the image-finding group already ships
        # status_breakdown; default to empty if missing.
        status_summary = dict(g.get("status_breakdown") or {})
        # Fall back to severity weight if the YAML has no metadata.
        worst_severity = g.get("worst_severity") or "minor"
        findings = list(g.get("findings", []))
        page_ids = {
            int(occurrence["page_id"])
            for finding in findings
            for occurrence in finding.get("occurrences", [])
            if occurrence.get("page_id") is not None
        }
        review_lane: ReviewLane = "informational" if is_informational else "expert_review"
        evidence_confidence: EvidenceConfidence = "low" if is_unclassified else "medium"
        if is_informational:
            evidence_summary = (
                "Alt comparison appears adequate; retained as non-actionable evidence."
            )
        elif is_unclassified:
            evidence_summary = (
                "Image analysis was inconclusive; classify manually before reporting a barrier."
            )
        else:
            evidence_summary = (
                "OCR/VLM-assisted image lead; confirm purpose and alternative in context."
            )
        out.append(
            IssueRow(
                pipeline="image",
                issue_key=f"image:{key}",
                title=meta.get("title") or _humanize_image_title(cls, adequacy),
                conformance=conformance,
                wcag_sc=wcag_sc,
                wcag_name=meta.get("wcag_name") or "Images of Text",
                responsibility=(meta.get("owner") or "editor"),
                abilities_affected=tuple(meta.get("abilities_affected") or []),
                difficulty=_EFFORT_TO_DIFFICULTY.get(meta.get("effort", ""), "Unknown"),
                occurrence_count=g.get("occurrence_count", g["finding_count"]),
                page_count=len(page_ids),
                priority=_priority(worst_severity, len(page_ids)),
                impact=worst_severity,
                status_summary=status_summary,
                # Deep-link to the dedicated Issue Detail view, same
                # shape the axe rows use (above).
                detail_url=f"/scans/{scan_id}/issues/image:{key}",
                finding_ids=tuple(int(f["id"]) for f in findings),
                review_lane=review_lane,
                evidence_confidence=evidence_confidence,
                evidence_summary=evidence_summary,
                high_confidence_occurrence_count=0,
                description=meta.get("what_happening"),
                why_matters=meta.get("why_matters"),
                fix_steps=tuple(meta.get("fix_steps") or ()),
                acceptance=meta.get("acceptance"),
                help_url=meta.get("help_url"),
                locations=_image_location_samples(findings, scan_id=scan_id),
            )
        )
    return out


# --------------------------------------------------------------------------
# Helpers.
# --------------------------------------------------------------------------


def _a11y_location_samples(
    findings: list[dict[str, Any]], *, scan_id: int, limit: int = 3
) -> tuple[IssueLocation, ...]:
    """Return unique page/selector samples without loading another query."""

    samples: list[IssueLocation] = []
    seen: set[tuple[int, str]] = set()
    for finding in findings:
        page_id = int(finding["page_id"])
        target = _humanize_location_target(finding.get("target_selector"))
        identity = (page_id, target)
        if identity in seen:
            continue
        seen.add(identity)
        context = " ".join(str(finding.get("failure_summary") or "").split())[:300]
        samples.append(
            IssueLocation(
                page_id=page_id,
                page_url=str(finding["page_url"]),
                page_title=finding.get("page_title"),
                target=target,
                context=context or None,
                evidence_url=f"/scans/{scan_id}/pages/{page_id}",
                revealed_by=(str(finding["revealed_by"]) if finding.get("revealed_by") else None),
            )
        )
        if len(samples) >= limit:
            break
    return tuple(samples)


def _humanize_location_target(raw_target: Any) -> str:
    """Turn Alfa's structured target hint into a compact element locator."""

    target = " ".join(str(raw_target or "").split())
    if not target:
        return "Page-level result"
    try:
        parsed = json.loads(target)
    except (TypeError, ValueError, json.JSONDecodeError):
        return target[:240]
    if not isinstance(parsed, dict):
        return target[:240]
    target_type = str(parsed.get("type") or "")
    if target_type == "document":
        return "Document root"
    if target_type == "attribute":
        name = str(parsed.get("name") or "attribute")
        value = str(parsed.get("value") or "")
        return f'[{name}="{value[:120]}"]'
    if target_type == "element":
        name = str(parsed.get("name") or "element")
        attributes = parsed.get("attributes")
        selectors: list[str] = []
        if isinstance(attributes, list):
            preferred = {"id", "class", "name", "role", "type", "href", "src"}
            for attribute in attributes:
                if not isinstance(attribute, dict):
                    continue
                attr_name = str(attribute.get("name") or "")
                if attr_name not in preferred:
                    continue
                value = str(attribute.get("value") or "")[:100]
                selectors.append(f'[{attr_name}="{value}"]')
                if len(selectors) >= 2:
                    break
        return f"{name}{''.join(selectors)}"[:240]
    return target[:240]


def _image_location_samples(
    findings: list[dict[str, Any]], *, scan_id: int, limit: int = 3
) -> tuple[IssueLocation, ...]:
    """Return page and image-position samples for OCR/VLM issue groups."""

    samples: list[IssueLocation] = []
    seen: set[tuple[int, int]] = set()
    for finding in findings:
        for occurrence in finding.get("occurrences", []):
            page_id = int(occurrence["page_id"])
            position = int(occurrence.get("position") or 0)
            identity = (page_id, position)
            if identity in seen:
                continue
            seen.add(identity)
            placement = "above the fold" if occurrence.get("above_fold") else "in the page"
            context_parts = []
            if occurrence.get("alt_text"):
                context_parts.append(f'Alt: "{occurrence["alt_text"]}"')
            if occurrence.get("context_snippet"):
                context_parts.append(str(occurrence["context_snippet"]))
            samples.append(
                IssueLocation(
                    page_id=page_id,
                    page_url=str(occurrence["page_url"]),
                    page_title=occurrence.get("page_title"),
                    target=f"Image occurrence {position + 1} ({placement})",
                    context=" · ".join(context_parts)[:300] or None,
                    evidence_url=f"/scans/{scan_id}/pages/{page_id}",
                )
            )
            if len(samples) >= limit:
                return tuple(samples)
    return tuple(samples)


def _conformance_label(wcag_level: str | None) -> ConformanceLabel:
    if wcag_level in {"A", "AA", "AAA"}:
        return wcag_level
    return "BP"


_CONFORMANCE_RANK = {"A": 0, "AA": 1, "AAA": 2, "BP": 3}


def _priority(impact: str | None, page_count: int) -> float:
    """Severity weight x log(1 + pages_affected). Cheap and honest.

    The weight is the same scale we use everywhere else
    (4 critical → 1 minor). Multiplying by ``log(1 + page_count)`` gives
    spread credit without letting one rule with thousands of pages
    drown out a critical-but-narrow issue.
    """
    import math

    weight = _SEVERITY_WEIGHT.get(impact or "", 1.0)
    return round(weight * math.log1p(page_count), 3)


def _humanize_image_title(classification: str, adequacy: str) -> str:
    """Fallback title for image issues without YAML metadata."""
    cls_human = {
        "essential": "Essential text in image",
        "informational": "Informational image",
        "logo": "Logo image",
        "decorative": "Decorative image",
        "no_meaningful_text": "Image (no meaningful text)",
    }.get(classification, f"Image ({classification})")
    adequacy_human = {
        "missing": "missing alt",
        "inadequate": "inadequate alt",
        "partial": "partial alt",
        "adequate": "adequate alt",
    }.get(adequacy, adequacy)
    return f"{cls_human} — {adequacy_human}"


def _sort_rows(rows: list[IssueRow], sort: str) -> list[IssueRow]:
    if sort == "priority_asc":
        return sorted(rows, key=lambda r: r.priority)
    if sort == "conformance":
        return sorted(
            rows,
            key=lambda r: (_CONFORMANCE_RANK.get(r.conformance, 9), -r.priority),
        )
    if sort == "occurrences_desc":
        return sorted(rows, key=lambda r: -r.occurrence_count)
    if sort == "pages_desc":
        return sorted(rows, key=lambda r: -r.page_count)
    # Default: priority_desc.
    return sorted(rows, key=lambda r: -r.priority)


def _load_rules() -> dict[str, Any]:
    """Load audit_report.yaml. Returns ``{}`` on parse error.

    The Issues view degrades cleanly without metadata — every row
    still gets a sensible default title and 'dev' as the owner.
    """
    try:
        text = (resources.files(_RULES_PACKAGE) / _RULES_FILE).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except (FileNotFoundError, yaml.YAMLError):
        return {}


# Re-export.
__all__ = [
    "IssueDetail",
    "IssuePage",
    "IssueRow",
    "abilities_breakdown",
    "conformance_breakdown",
    "get_issue_detail",
    "list_issues",
    "responsibility_breakdown",
]


# Field is unused by callers but referenced internally to ensure the
# dataclass stays "frozen" — silences a linter complaint about an
# unused `field` import on platforms where annotations strip it.
_ = field
