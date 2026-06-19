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

import sqlite3
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

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
    issue_key: str  # `axe:<rule_id>` or `image:<classification>_<adequacy>`
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
    # Inline expansion content. Pulled from rules/audit_report.yaml so
    # the list view can answer "what/why/how" without a second request.
    description: str | None = None
    why_matters: str | None = None
    fix_steps: tuple[str, ...] = ()
    acceptance: str | None = None
    help_url: str | None = None


def list_issues(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    conformance: list[str] | None = None,
    responsibility: list[str] | None = None,
    abilities: list[str] | None = None,
    status: str | None = None,
    search: str | None = None,
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
        rows = [
            r
            for r in rows
            if any(a.lower() in wanted_a for a in r.abilities_affected)
        ]
    if status:
        rows = [r for r in rows if r.status_summary.get(status, 0) > 0]
    if search:
        needle = search.lower()
        rows = [
            r
            for r in rows
            if needle in r.title.lower()
            or (r.wcag_sc and needle in r.wcag_sc)
        ]

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
        verify_manual=meta.get("verify_manual"),
        verify_automated=meta.get("verify_automated"),
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
    if row.pipeline in ("keyboard", "responsive"):
        # Dynamic-probe rows are carded by SC (one YAML card covers
        # several rule_ids — e.g. all three keyboard-trap shapes).
        # Check semantic_criteria first (where 2.1.2 and the responsive
        # SCs live), then axe_rules for any author who keyed there.
        sc = row.wcag_sc or ""
        meta = rules.get("semantic_criteria", {}).get(sc, {}) or rules.get(
            "axe_rules", {}
        ).get(sc, {})
        return dict(meta) if isinstance(meta, dict) else {}
    image_key = row.issue_key.removeprefix("image:")
    meta = rules.get("image_findings", {}).get(image_key, {})
    return dict(meta) if isinstance(meta, dict) else {}


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
    if row.pipeline in ("axe", "semantic", "keyboard", "responsive"):
        # All four DOM pipelines live in page_a11y_findings; the DB
        # rule_id carries the discriminator: bare rule_id for axe
        # ("color-contrast") and the dynamic probes
        # ("keyboard-trap-stuck", "responsive-reflow-overflow"),
        # ``semantic:<sc>`` for semantic. Our UI issue_key prefixes
        # axe/keyboard/responsive with "<pipeline>:" — strip that to
        # recover the DB value; semantic's issue_key already matches
        # the DB column exactly.
        rule_id = (
            row.issue_key
            if row.pipeline == "semantic"
            else row.issue_key.split(":", 1)[1]
        )
        rows = conn.execute(
            """
            SELECT p.id AS page_id,
                   p.url_normalized AS page_url,
                   p.title AS page_title,
                   COUNT(*) AS occurrence_count,
                   GROUP_CONCAT(a.status) AS statuses
              FROM page_a11y_findings a
              JOIN pages p ON p.id = a.page_id
             WHERE a.scan_id = ? AND a.rule_id = ?
             GROUP BY p.id, p.url_normalized, p.title
            """,
            (scan_id, rule_id),
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
        out.append(
            IssuePage(
                page_id=int(r["page_id"]),
                page_url=str(r["page_url"]),
                page_title=r["page_title"],
                occurrence_count=int(r["occurrence_count"]),
                status_summary=counts,
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
                -(p.status_summary.get("new", 0)
                  + p.status_summary.get("reviewing", 0)
                  + p.status_summary.get("in_progress", 0)),
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


# --------------------------------------------------------------------------
# Per-pipeline row builders.
# --------------------------------------------------------------------------


def _axe_issue_rows(
    conn: sqlite3.Connection,
    scan_id: int,
    rules: dict[str, Any],
) -> list[IssueRow]:
    """One row per ``rule_id`` group from the page_a11y_findings table.

    The table stores both axe and semantic rows (distinguished by the
    ``pipeline`` column added in migration 0003). Semantic rows have
    a synthetic ``rule_id`` of the form ``semantic:<sc>``; we look
    up the SC in the YAML's ``semantic_criteria`` block and tag the
    IssueRow with ``pipeline='semantic'`` so the UI can distinguish
    LLM-detected findings from deterministic axe findings.
    """
    groups = a11y_queries.grouped_by_rule(conn, scan_id)
    out: list[IssueRow] = []
    axe_rules_meta = rules.get("axe_rules", {})
    semantic_meta = rules.get("semantic_criteria", {})
    for g in groups:
        raw_rule_id: str = g["rule_id"]
        is_semantic = raw_rule_id.startswith("semantic:")
        # For semantic rows, look up the SC card; for axe rows, the
        # axe-rule card. Both share the same YAML field shape.
        # Keyboard probe (SC 2.1.2) writes rows with rule_id values
        # like "keyboard-trap-stuck" that aren't axe rules and aren't
        # tagged "semantic:". Detect them up front so the lookup
        # routes correctly and the IssueRow's pipeline label is
        # accurate (not silently "axe").
        is_keyboard = raw_rule_id.startswith("keyboard-trap-")
        # Responsive/zoom probe rows ("responsive-reflow-overflow",
        # "responsive-text-clipped", …) follow the keyboard pattern:
        # non-axe rule_ids resolved by SC through the YAML fallback.
        is_responsive = raw_rule_id.startswith("responsive-")
        if is_semantic:
            sc = raw_rule_id.removeprefix("semantic:")
            meta = semantic_meta.get(sc, {})
        else:
            meta = axe_rules_meta.get(raw_rule_id, {})
            # Fallback: for non-axe rules (keyboard probe today,
            # other dynamic checks later), look up by WCAG SC. Lets a
            # single YAML card key on "2.1.2" cover all three
            # keyboard rule_ids without duplication. We check both
            # the axe_rules block AND the semantic_criteria block —
            # whichever the YAML author chose to put the card in.
            if not meta:
                sc_from_db = g.get("wcag_sc")
                if sc_from_db:
                    meta = (
                        axe_rules_meta.get(sc_from_db, {})
                        or semantic_meta.get(sc_from_db, {})
                    )
        wcag_sc = meta.get("wcag_sc") or g.get("wcag_sc")
        wcag_level = meta.get("wcag_level") or g.get("wcag_level")
        conformance = _conformance_label(wcag_level)
        impact = g.get("impact")
        # Semantic rows: title comes from the YAML's curated text, not
        # the LLM's per-finding rationale (which lands in `help` of
        # each individual finding row, surfaced inside the detail view).
        if is_semantic:
            sc = raw_rule_id.removeprefix("semantic:")
            issue_key = f"semantic:{sc}"
            default_title = f"WCAG SC {sc} (LLM-detected)"
        elif is_keyboard:
            issue_key = f"keyboard:{raw_rule_id}"
            default_title = f"Keyboard trap: {raw_rule_id}"
        elif is_responsive:
            issue_key = f"responsive:{raw_rule_id}"
            default_title = f"Responsive failure: {raw_rule_id}"
        else:
            issue_key = f"axe:{raw_rule_id}"
            default_title = f"axe rule: {raw_rule_id}"
        out.append(
            IssueRow(
                pipeline=(
                    "semantic"
                    if is_semantic
                    else "keyboard"
                    if is_keyboard
                    else "responsive"
                    if is_responsive
                    else "axe"
                ),
                issue_key=issue_key,
                title=meta.get("title")
                or (g.get("help") if not is_semantic else None)
                or default_title,
                conformance=conformance,
                wcag_sc=wcag_sc,
                wcag_name=meta.get("wcag_name"),
                responsibility=(meta.get("owner") or "dev"),
                abilities_affected=tuple(meta.get("abilities_affected") or []),
                difficulty=_EFFORT_TO_DIFFICULTY.get(
                    meta.get("effort", ""), "Unknown"
                ),
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
                # Inline expansion content. Title's already on the row;
                # the YAML's `what_happening` / `why_matters` / fix steps
                # / `acceptance` ride along so the list view can show
                # what/why/how without a second API call. `help_url`
                # falls back to the axe-supplied URL when the YAML
                # doesn't pin one.
                description=meta.get("what_happening"),
                why_matters=meta.get("why_matters"),
                fix_steps=tuple(meta.get("fix_steps") or ()),
                acceptance=meta.get("acceptance"),
                help_url=meta.get("help_url") or g.get("help_url") or None,
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
        wcag_sc = meta.get("wcag_sc") or "1.4.5"
        wcag_level = meta.get("wcag_level") or "AA"
        conformance = _conformance_label(wcag_level)
        # Status bucket: the image-finding group already ships
        # status_breakdown; default to empty if missing.
        status_summary = dict(g.get("status_breakdown") or {})
        # Fall back to severity weight if the YAML has no metadata.
        worst_severity = g.get("worst_severity") or "minor"
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
                difficulty=_EFFORT_TO_DIFFICULTY.get(
                    meta.get("effort", ""), "Unknown"
                ),
                occurrence_count=g.get("occurrence_count", g["finding_count"]),
                page_count=g.get("page_count", 0),
                priority=_priority(worst_severity, g.get("page_count", 0)),
                impact=worst_severity,
                status_summary=status_summary,
                # Deep-link to the dedicated Issue Detail view, same
                # shape the axe rows use (above).
                detail_url=f"/scans/{scan_id}/issues/image:{key}",
                finding_ids=tuple(int(f["id"]) for f in g.get("findings", [])),
                description=meta.get("what_happening"),
                why_matters=meta.get("why_matters"),
                fix_steps=tuple(meta.get("fix_steps") or ()),
                acceptance=meta.get("acceptance"),
                help_url=meta.get("help_url"),
            )
        )
    return out


# --------------------------------------------------------------------------
# Helpers.
# --------------------------------------------------------------------------


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
        text = (resources.files(_RULES_PACKAGE) / _RULES_FILE).read_text(
            encoding="utf-8"
        )
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
