"""Read-only, scan-scoped comparisons of the canonical issue projection.

Finding identities and counters are compared in full; only display links are
sampled. An absent result is meaningful only when the stored coverage supports
it. Historical unknown coverage is never treated as a clean check.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from audit.analyzer.alfa_evidence import parse_evidence
from audit.crawler import url_policy
from audit.labels import CLICK_THROUGH_STATES
from audit.wcag_version import stored_wcag_version
from audit.web import image_findings_queries, issues

Category = Literal["new", "still_detected", "changed", "no_longer_detected", "cannot_compare"]
# The plain presence of a group in each report, for the Compare scans page:
# only in the later report, only in the earlier one, or in both. ``Category``
# keeps the stricter reading of the same row (whether coverage supports it).
Change = Literal["new", "resolved", "remaining"]
Pipeline = Literal["axe", "alfa", "keyboard", "responsive", "focus", "visual", "semantic", "image"]
CATEGORIES: tuple[Category, ...] = (
    "new",
    "still_detected",
    "changed",
    "no_longer_detected",
    "cannot_compare",
)
PIPELINES: tuple[Pipeline, ...] = (
    "axe",
    "alfa",
    "keyboard",
    "responsive",
    "focus",
    "visual",
    "semantic",
    "image",
)
CHANGES: tuple[Change, ...] = ("new", "resolved", "remaining")
# Every issue group of two reports fits: a group is one rule or image
# classification, so the count is bounded by the rule catalogue, not the site.
MAX_PAGE_SIZE = 500
# Completed reports of one site drawn in the trend, most recent last.
HISTORY_LIMIT = 20


class ComparisonError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ReportIdentity(BaseModel):
    id: int
    seed_url: str
    started_at: str


class EvidenceLink(BaseModel):
    label: str
    url: str


class Snapshot(BaseModel):
    # Every stored finding, cross-page repeats included: what the location
    # matching compares.
    occurrences: int
    # The same group as the Issues table counts it, each element once. What
    # the Compare scans page shows, so its numbers match the report's.
    issue_occurrences: int
    pages: int
    statuses: dict[str, int]
    outcomes: dict[str, int]
    issues: list[EvidenceLink] = Field(max_length=4)
    evidence: list[EvidenceLink] = Field(max_length=10)


class ComparisonRow(BaseModel):
    key: str
    pipeline: Pipeline
    title: str
    category: Category
    change: Change
    wcag_sc: str | None
    wcag_name: str | None
    conformance: str
    before: Snapshot | None
    after: Snapshot | None
    limitations: list[str]


class MethodCoverage(BaseModel):
    state: Literal["complete", "incomplete", "unknown", "disabled"]
    checked: int | None
    total: int


class CoveragePair(BaseModel):
    pipeline: Pipeline
    before: MethodCoverage
    after: MethodCoverage


class CoverageNote(BaseModel):
    """One coverage note, said once for whichever of the two scans it is true of.

    ``limitations`` repeats a note per report; this is the same evidence for a
    reader, without the notes the method coverage table already states.
    """

    text: str
    # The scans it is true of, earlier first; empty when it is about the pair,
    # such as the pages only one of them checked.
    scans: list[int]
    # True of one scan or of the pair, so it can make a group look new or
    # resolved. A limit both scans share cannot, though it can hide issues.
    differs: bool


class GroupTotals(BaseModel):
    """A report's issue groups and occurrences, counted as the Issues table does."""

    groups: int
    occurrences: int


class ComparisonResponse(BaseModel):
    current: ReportIdentity
    baseline: ReportIdentity | None
    counts: dict[str, int]
    # Rows by ``Change``, over every row, whatever the filters.
    changes: dict[str, int]
    before_totals: GroupTotals | None
    after_totals: GroupTotals
    pipeline_counts: dict[str, int]
    coverage: list[CoveragePair] = Field(default_factory=list)
    # Names, never values, of the detection settings that differ.
    settings_changed: list[str] = Field(default_factory=list)
    limitations: list[str]
    notes: list[CoverageNote] = Field(default_factory=list)
    rows: list[ComparisonRow] = Field(max_length=MAX_PAGE_SIZE)
    total: int
    page: int
    page_size: int


def _protected(conn: sqlite3.Connection, scan_id: int) -> bool:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='protected_scans'"
    ).fetchone():
        return False
    return (
        conn.execute("SELECT 1 FROM protected_scans WHERE scan_id = ?", (scan_id,)).fetchone()
        is not None
    )


def site_scope(seed_url: str) -> str:
    """Normalized seed scope: the key that makes two reports the same site."""
    return url_policy.normalize(url_policy.normalize_seed_url(seed_url))


def _load_scan(conn: sqlite3.Connection, scan_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if row is None:
        raise ComparisonError("Report not found.", 404)
    if _protected(conn, scan_id):
        raise ComparisonError("Protected scans cannot be compared with another report.", 403)
    return dict(row)


def previous_scan_id(conn: sqlite3.Connection, scan: dict[str, Any]) -> int | None:
    """Latest strictly earlier public report in the same normalized seed scope."""
    if _protected(conn, int(scan["id"])):
        return None
    rows = conn.execute(
        "SELECT id, seed_url FROM scans WHERE status = 'completed' "
        "AND (julianday(started_at) < julianday(?) OR "
        "(julianday(started_at) = julianday(?) AND id < ?)) "
        "ORDER BY julianday(started_at) DESC, id DESC",
        (str(scan["started_at"]), str(scan["started_at"]), int(scan["id"])),
    )
    scope = site_scope(str(scan["seed_url"]))
    for row in rows:
        if not _protected(conn, int(row["id"])) and site_scope(str(row["seed_url"])) == scope:
            return int(row["id"])
    return None


def _identity(scan: dict[str, Any]) -> ReportIdentity:
    return ReportIdentity(
        id=int(scan["id"]), seed_url=str(scan["seed_url"]), started_at=str(scan["started_at"])
    )


def _config(scan: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(scan.get("config_json") or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


class HistoryPoint(BaseModel):
    id: int
    started_at: str
    finished_at: str | None
    groups: int
    occurrences: int


class SiteHistory(BaseModel):
    """Completed public reports of one site, oldest first, for the trend."""

    site_url: str
    # Every completed public report of the site; ``scans`` keeps the latest.
    total: int
    scans: list[HistoryPoint] = Field(max_length=HISTORY_LIMIT)


@dataclass
class _Group:
    pipeline: Pipeline
    title: str
    wcag_sc: str | None = None
    wcag_name: str | None = None
    conformance: str = "BP"
    issue_occurrences: int = 0
    issue_links: list[EvidenceLink] = field(default_factory=list)
    evidence: list[EvidenceLink] = field(default_factory=list)
    signatures: Counter[tuple[str, ...]] = field(default_factory=Counter)
    locations: Counter[tuple[str, ...]] = field(default_factory=Counter)
    pages: set[str] = field(default_factory=set)
    statuses: Counter[str] = field(default_factory=Counter)
    outcomes: Counter[str] = field(default_factory=Counter)
    limitations: set[str] = field(default_factory=set)

    def add(self, location: tuple[str, ...], status: str, outcome: str, link: EvidenceLink) -> None:
        self.locations[location] += 1
        self.signatures[(*location, status, outcome)] += 1
        self.pages.add(location[0])
        self.statuses[status] += 1
        if outcome:
            self.outcomes[outcome] += 1
        if len(self.evidence) < 10 and link not in self.evidence:
            self.evidence.append(link)

    def snapshot(self) -> Snapshot:
        return Snapshot(
            occurrences=sum(self.signatures.values()),
            issue_occurrences=self.issue_occurrences,
            pages=len(self.pages),
            statuses=dict(self.statuses),
            outcomes=dict(self.outcomes),
            issues=self.issue_links[:4],
            evidence=self.evidence,
        )


def _group_key(row: issues.IssueRow) -> str:
    """One Alfa rule is one group whichever outcome it had, so a finding that
    moves between failed and cannot-tell is a change, not a new issue."""
    key = row.issue_key
    if row.pipeline == "alfa" and key.rsplit(":", 1)[-1] in {"failed", "cant_tell"}:
        key = key.rsplit(":", 1)[0]
    return key


def _compared_rows(conn: sqlite3.Connection, scan_id: int) -> list[issues.IssueRow]:
    return [row for row in issues.list_issues(conn, scan_id) if row.pipeline in PIPELINES]


def _groups(conn: sqlite3.Connection, scan_id: int) -> dict[str, _Group]:
    grouped: dict[str, _Group] = {}
    ids: dict[tuple[str, int], str] = {}
    for row in _compared_rows(conn, scan_id):
        key = _group_key(row)
        group = grouped.setdefault(
            key,
            _Group(
                # ``_compared_rows`` keeps only these pipelines.
                pipeline=cast(Pipeline, row.pipeline),
                title=row.title,
                wcag_sc=row.wcag_sc,
                wcag_name=row.wcag_name,
                conformance=row.conformance,
            ),
        )
        if row.pipeline == "alfa":
            group.title = f"{row.wcag_name or 'ACT rule'} (Alfa {key.removeprefix('alfa:')})"
        group.issue_occurrences += row.occurrence_count
        group.issue_links.append(EvidenceLink(label=row.title, url=row.detail_url))
        # A comparison matches locations page by page, so it needs the
        # cross-page repeats the report itself lists only once.
        for finding_id in (*row.finding_ids, *row.repeat_finding_ids):
            ids[(row.pipeline, finding_id)] = key

    # The canonical projection's location samples are intentionally only three
    # items. Read every underlying finding instead, joining both scan columns.
    for row in conn.execute(
        "SELECT a.id, a.pipeline, a.target_selector, a.status, a.engine_outcome, "
        "a.engine_evidence_json, a.revealed_by, a.page_id, p.url_normalized "
        "FROM page_a11y_findings a JOIN pages p ON p.id = a.page_id AND p.scan_id = a.scan_id "
        "WHERE a.scan_id = ? ORDER BY a.id",
        (scan_id,),
    ):
        finding_key = ids.get((str(row["pipeline"]), int(row["id"])))
        if finding_key is None:
            continue
        group = grouped[finding_key]
        target = str(row["target_selector"])
        evidence = row["engine_evidence_json"]
        if group.pipeline == "alfa":
            parsed, evidence_status = parse_evidence(evidence)
            if evidence_status == "unavailable":
                group.limitations.add("Stored Alfa evidence is incomplete or unavailable.")
            elif evidence_status in {"truncated", "recovered"}:
                group.limitations.add("Stored Alfa evidence was truncated.")
            try:
                target_value = json.loads(target)
            except (TypeError, ValueError):
                target_value = None
            if parsed.get("target_identity"):
                target = str(parsed["target_identity"])
            elif isinstance(target_value, dict) and target_value.get("path"):
                target = str(target_value["path"])
            elif isinstance(target_value, dict):
                target = json.dumps(target_value, sort_keys=True, separators=(",", ":"))
                if target_value.get("type") != "document":
                    group.limitations.add(
                        "Legacy Alfa targets have no DOM location; repeated content may be merged."
                    )
        page_url = url_policy.normalize(str(row["url_normalized"]))
        group.add(
            (page_url, target, str(row["revealed_by"] or "")),
            str(row["status"]),
            str(row["engine_outcome"] or ""),
            EvidenceLink(
                label=f"Finding {row['id']} on {page_url}"[:300],
                url=f"/scans/{scan_id}/pages/{row['page_id']}#finding-{row['id']}",
            ),
        )

    for entry in image_findings_queries.grouped_by_remediation(conn, scan_id):
        for finding in entry["findings"]:
            finding_key = ids.get(("image", int(finding["id"])))
            if finding_key is None:
                continue
            group = grouped[finding_key]
            for occurrence in finding["occurrences"]:
                group.add(
                    (
                        url_policy.normalize(occurrence["page_url"]),
                        finding["content_hash"],
                        str(occurrence["position"]),
                        str(occurrence["alt_text"] or ""),
                    ),
                    str(finding["status"]),
                    "",
                    EvidenceLink(
                        label=f"Image finding {finding['id']}", url=f"/findings/{finding['id']}"
                    ),
                )
    return grouped


_COUNTERS = {
    "axe": "axe_pages_scanned",
    "alfa": "alfa_pages_scanned",
    "semantic": "semantic_pages_analyzed",
    "keyboard": "keyboard_pages_probed",
    "responsive": "responsive_pages_probed",
}
_FLAGS = {
    "axe": "axe_enabled",
    "alfa": "alfa_enabled",
    "semantic": "semantic_enabled",
    "keyboard": "keyboard_probe_enabled",
    "responsive": "responsive_checks_enabled",
    "focus": "focus_checks_enabled",
    "visual": "visual_checks_enabled",
}


@dataclass(frozen=True)
class _Note:
    """A coverage limit of one report, worded to stand without its number."""

    scan_id: int
    text: str
    # The method coverage table already says it: a check that was off, ran
    # on part of the site, or has no page count.
    in_table: bool = False

    def __str__(self) -> str:
        return f"Report #{self.scan_id}: {self.text}"


def _coverage(
    conn: sqlite3.Connection, scan: dict[str, Any], groups: dict[str, _Group]
) -> tuple[set[str], dict[str, list[str]], list[str], list[_Note]]:
    scan_id = int(scan["id"])
    cfg = _config(scan)
    rows = conn.execute(
        "SELECT url_normalized, status_code, render_mode, final_url FROM pages WHERE scan_id = ?",
        (scan_id,),
    ).fetchall()
    pages = {url_policy.normalize(str(row["url_normalized"])) for row in rows}
    notes: list[_Note] = []

    def note(text: str, *, in_table: bool = False) -> str:
        notes.append(_Note(scan_id, text, in_table))
        return str(notes[-1])

    common: list[str] = []
    if not rows or any(
        not row["status_code"] or not 200 <= row["status_code"] < 300 for row in rows
    ):
        common.append(note("Some pages were missing or did not load successfully."))
    if int(scan.get("error_count") or 0):
        common.append(note("Errors were recorded while crawling or checking pages."))
    if int(scan.get("page_count") or 0) != len(rows):
        common.append(note("The page count recorded does not match the pages stored."))
    if any(row["final_url"] for row in rows):
        common.append(note("Some pages redirected; confirm the same content was checked."))
    if cfg.get("search"):
        search = conn.execute(
            "SELECT status FROM scan_search_runs WHERE scan_id = ?", (scan_id,)
        ).fetchall()
        if not search or any(row["status"] != "completed" for row in search):
            common.append(
                note("The site search set up for the scan did not finish or was not recorded.")
            )
    by_pipeline: dict[str, list[str]] = {}
    for pipeline in PIPELINES:
        limitations: list[str] = []
        flag = _FLAGS.get(pipeline)
        if flag and cfg.get(flag) is False:
            limitations.append(note(f"{pipeline} was disabled.", in_table=True))
        elif pipeline in {"focus", "visual"}:
            limitations.append(
                note(f"completed {pipeline} coverage was not recorded.", in_table=True)
            )
        elif pipeline == "image":
            # A shared cached analysis alone cannot prove it was evaluated in
            # this report. Historical schema has no per-report analysis ledger.
            limitations.append(
                note("per-report image-analysis coverage was not recorded.", in_table=True)
            )
        else:
            checked = int(scan.get(_COUNTERS[pipeline]) or 0)
            if pipeline in {"semantic", "keyboard", "responsive"} and not cfg.get(
                "method_coverage_version"
            ):
                limitations.append(
                    note(f"historical {pipeline} coverage is unknown.", in_table=True)
                )
            elif not rows or checked < len(rows):
                limitations.append(
                    note(f"{pipeline} checked {checked} of {len(rows)} pages.", in_table=True)
                )
        if pipeline in {"keyboard", "responsive"} and not (flag and cfg.get(flag) is False):
            # The table marks these counts "tried" and explains the word.
            limitations.append(
                note(
                    f"{pipeline} counters record page attempts; "
                    "per-check errors and probe limits were not recorded.",
                    in_table=True,
                )
            )
        if pipeline == "alfa":
            stored = sum(
                sum(g.signatures.values()) for g in groups.values() if g.pipeline == pipeline
            )
            emitted = int(scan.get("alfa_failed_total") or 0) + int(
                scan.get("alfa_cant_tell_total") or 0
            )
            if emitted > stored:
                limitations.append(
                    note(
                        "Some Siteimprove Alfa results were capped or lost their evidence: "
                        f"{stored} of {emitted} were stored."
                    )
                )
        if pipeline == "axe" and cfg.get("interaction_checks_enabled"):
            has_ledger = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scan_interaction_runs'"
            ).fetchone()
            ledger = (
                conn.execute(
                    "SELECT limits, blocked_controls, dialogs_stuck, "
                    "controls_found, controls_operated "
                    "FROM scan_interaction_runs "
                    "WHERE scan_id = ?",
                    (scan_id,),
                ).fetchall()
                if has_ledger
                else []
            )
            if (
                not has_ledger
                or len(ledger) < len(rows)
                or any(
                    row["limits"]
                    or row["blocked_controls"]
                    or row["dialogs_stuck"]
                    or row["controls_operated"] < row["controls_found"]
                    for row in ledger
                )
            ):
                limitations.append(
                    note(f"Some {CLICK_THROUGH_STATES} were skipped, cut short, or not recorded.")
                )
        by_pipeline[pipeline] = limitations
    return pages, by_pipeline, common, notes


def _pages(n: int) -> str:
    return f"{n} page" if n == 1 else f"{n} pages"


def _coverage_notes(
    baseline_id: int, current_id: int, notes: list[_Note], pair: list[str]
) -> list[CoverageNote]:
    """Each note once, with the scans it is true of; differences first."""
    scans: dict[str, set[int]] = {}
    for item in notes:
        if not item.in_table:
            scans.setdefault(item.text, set()).add(item.scan_id)
    result = [CoverageNote(text=text, scans=[], differs=True) for text in pair]
    for text, ids in scans.items():
        both = [scan_id for scan_id in (baseline_id, current_id) if scan_id in ids]
        result.append(CoverageNote(text=text, scans=both, differs=len(both) == 1))
    return sorted(result, key=lambda item: not item.differs)


def _method_coverage(
    scan: dict[str, Any], pipeline: Pipeline, total: int, limitations: list[str]
) -> MethodCoverage:
    cfg = _config(scan)
    flag = _FLAGS.get(pipeline)
    if flag and cfg.get(flag) is False:
        state: Literal["complete", "incomplete", "unknown", "disabled"] = "disabled"
    elif (
        pipeline not in _COUNTERS
        or pipeline in {"keyboard", "responsive"}
        or (pipeline == "semantic" and not cfg.get("method_coverage_version"))
    ):
        state = "unknown"
    else:
        state = "incomplete" if limitations else "complete"
    return MethodCoverage(
        state=state,
        checked=int(scan.get(_COUNTERS[pipeline]) or 0) if pipeline in _COUNTERS else None,
        total=total,
    )


def compare_reports(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    compare_to: int | None = None,
    page: int = 1,
    page_size: int = 50,
    category: Category | None = None,
    pipeline: Pipeline | None = None,
) -> ComparisonResponse:
    """Compare exactly two completed public reports without changing evidence."""
    if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ComparisonError(
            f"Page must be positive and page_size must be between 1 and {MAX_PAGE_SIZE}.", 422
        )
    if category is not None and category not in CATEGORIES:
        raise ComparisonError("Unknown comparison category.", 422)
    if pipeline is not None and pipeline not in PIPELINES:
        raise ComparisonError("Unknown pipeline.", 422)
    current = _load_scan(conn, scan_id)
    if current["status"] != "completed":
        raise ComparisonError("Only completed reports can be compared.", 409)
    baseline_id = compare_to if compare_to is not None else previous_scan_id(conn, current)
    counts: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    changes: dict[str, int] = dict.fromkeys(CHANGES, 0)
    if baseline_id is None:
        return ComparisonResponse(
            current=_identity(current),
            baseline=None,
            counts=counts,
            changes=changes,
            before_totals=None,
            after_totals=_totals(conn, scan_id),
            pipeline_counts={},
            limitations=["Scan the same site again to compare with an earlier completed report."],
            rows=[],
            total=0,
            page=page,
            page_size=page_size,
        )
    baseline = _load_scan(conn, baseline_id)
    if baseline_id == scan_id:
        raise ComparisonError("Choose two different reports.")
    if baseline["status"] != "completed":
        raise ComparisonError("Only completed reports can be compared.", 409)
    if site_scope(str(current["seed_url"])) != site_scope(str(baseline["seed_url"])):
        raise ComparisonError("Reports must have the same normalized seed URL.")
    earlier = conn.execute(
        "SELECT julianday(?) < julianday(?) OR (julianday(?) = julianday(?) AND ? < ?)",
        (
            str(baseline["started_at"]),
            str(current["started_at"]),
            str(baseline["started_at"]),
            str(current["started_at"]),
            baseline_id,
            scan_id,
        ),
    ).fetchone()[0]
    if not earlier:
        raise ComparisonError("The baseline must be an earlier report.")

    before = _groups(conn, baseline_id)
    after = _groups(conn, scan_id)
    old_pages, old_methods, old_common, old_notes = _coverage(conn, baseline, before)
    new_pages, new_methods, new_common, new_notes = _coverage(conn, current, after)
    common = list(dict.fromkeys([*old_common, *new_common]))
    pair_notes: list[str] = []
    if old_pages != new_pages:
        common.append(
            f"Page coverage changed: {len(old_pages - new_pages)} earlier pages missing; "
            f"{len(new_pages - old_pages)} additional pages."
        )
        pair_notes.append(
            f"The scans checked different pages: {_pages(len(old_pages - new_pages))} "
            f"only in scan {baseline_id}, {_pages(len(new_pages - old_pages))} "
            f"only in scan {scan_id}."
        )
    old_cfg, new_cfg = _config(baseline), _config(current)
    # A report stored before the version setting has no key but ran WCAG
    # 2.2; compare what each scan actually ran, not whether the key exists.
    for cfg in (old_cfg, new_cfg):
        cfg["wcag_version"] = stored_wcag_version(cfg)
    # Do not echo configuration values: search inputs and provider fields can
    # contain private data. Only report names of changed detection settings.
    changed = sorted(
        k
        for k in old_cfg.keys() | new_cfg.keys()
        if old_cfg.get(k) != new_cfg.get(k)
        and not k.endswith("coverage_version")
        and k not in {"seed_url", "db_path", "blob_dir", "workers"}
    )
    if changed:
        common.append("Scan settings changed: " + ", ".join(changed[:12]) + ".")
    result_rows: list[ComparisonRow] = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        group = new or old
        if group is None:  # keys come from the union above
            continue
        limitations = list(
            dict.fromkeys(
                [
                    *common,
                    *old_methods[group.pipeline],
                    *new_methods[group.pipeline],
                    *sorted(old.limitations if old else []),
                    *sorted(new.limitations if new else []),
                ]
            )
        )
        change: Change = "new" if old is None else "resolved" if new is None else "remaining"
        changes[change] += 1
        if old is None:
            result: Category = "cannot_compare" if limitations else "new"
        elif new is None:
            result = "cannot_compare" if limitations else "no_longer_detected"
        elif old.signatures == new.signatures:
            result = "still_detected"
        elif (old.locations - new.locations or new.locations - old.locations) and limitations:
            result = "cannot_compare"
        else:
            result = "changed"
        counts[result] += 1
        result_rows.append(
            ComparisonRow(
                key=key,
                pipeline=group.pipeline,
                title=group.title,
                category=result,
                change=change,
                wcag_sc=group.wcag_sc,
                wcag_name=group.wcag_name,
                conformance=group.conformance,
                before=old.snapshot() if old else None,
                after=new.snapshot() if new else None,
                limitations=limitations,
            )
        )
    pipeline_counts: dict[str, int] = dict(Counter(row.pipeline for row in result_rows))
    selected = [
        row
        for row in result_rows
        if (category is None or row.category == category)
        and (pipeline is None or row.pipeline == pipeline)
    ]
    all_limitations = list(
        dict.fromkeys(
            [
                *common,
                *(item for p in PIPELINES for item in [*old_methods[p], *new_methods[p]]),
                *(item for row in result_rows for item in row.limitations),
                "No longer detected still needs confirmation on the page "
                "before marking it remediated.",
            ]
        )
    )
    return ComparisonResponse(
        current=_identity(current),
        baseline=_identity(baseline),
        counts=counts,
        changes=changes,
        before_totals=_group_totals(before),
        after_totals=_group_totals(after),
        pipeline_counts=pipeline_counts,
        coverage=[
            CoveragePair(
                pipeline=p,
                before=_method_coverage(
                    baseline, p, len(old_pages), [*old_common, *old_methods[p]]
                ),
                after=_method_coverage(current, p, len(new_pages), [*new_common, *new_methods[p]]),
            )
            for p in PIPELINES
        ],
        settings_changed=changed[:50],
        limitations=all_limitations,
        notes=_coverage_notes(
            baseline_id,
            scan_id,
            [
                *old_notes,
                *new_notes,
                # A group's own evidence limits, from the scan that stored it.
                *(_Note(baseline_id, t) for g in before.values() for t in sorted(g.limitations)),
                *(_Note(scan_id, t) for g in after.values() for t in sorted(g.limitations)),
            ],
            pair_notes,
        ),
        rows=selected[(page - 1) * page_size : page * page_size],
        total=len(selected),
        page=page,
        page_size=page_size,
    )


def _group_totals(groups: dict[str, _Group]) -> GroupTotals:
    return GroupTotals(
        groups=len(groups), occurrences=sum(g.issue_occurrences for g in groups.values())
    )


def _totals(conn: sqlite3.Connection, scan_id: int) -> GroupTotals:
    """``_group_totals`` without reading every finding: the trend needs only counts."""
    rows = _compared_rows(conn, scan_id)
    return GroupTotals(
        groups=len({_group_key(row) for row in rows}),
        occurrences=sum(row.occurrence_count for row in rows),
    )


def site_history(
    conn: sqlite3.Connection, scan_id: int, *, limit: int = HISTORY_LIMIT
) -> SiteHistory:
    """The completed public reports of ``scan_id``'s site, oldest first.

    Ordered the way ``previous_scan_id`` picks a baseline (start time, then
    id), so the point before a report in the trend is the report it is
    compared with by default. Totals are the comparison's, so a point and the
    Before or After of a comparison never disagree.
    """
    scan = _load_scan(conn, scan_id)
    scope = site_scope(str(scan["seed_url"]))
    same_site = [
        row
        for row in conn.execute(
            "SELECT id, seed_url, started_at, finished_at FROM scans "
            "WHERE status = 'completed' ORDER BY julianday(started_at), id"
        )
        if site_scope(str(row["seed_url"])) == scope and not _protected(conn, int(row["id"]))
    ]
    return SiteHistory(
        site_url=scope,
        total=len(same_site),
        scans=[
            HistoryPoint(
                id=int(row["id"]),
                started_at=str(row["started_at"]),
                finished_at=str(row["finished_at"]) if row["finished_at"] else None,
                **_totals(conn, int(row["id"])).model_dump(),
            )
            for row in same_site[-limit:]
        ],
    )
