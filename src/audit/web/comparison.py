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
from typing import Any, Literal

from pydantic import BaseModel, Field

from audit.analyzer.alfa_evidence import parse_evidence
from audit.crawler import url_policy
from audit.web import image_findings_queries, issues

Category = Literal["new", "still_detected", "changed", "no_longer_detected", "cannot_compare"]
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
    occurrences: int
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


class ComparisonResponse(BaseModel):
    current: ReportIdentity
    baseline: ReportIdentity | None
    counts: dict[str, int]
    pipeline_counts: dict[str, int]
    coverage: list[CoveragePair] = Field(default_factory=list)
    limitations: list[str]
    rows: list[ComparisonRow] = Field(max_length=50)
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


def _scope(seed_url: str) -> str:
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
    scope = _scope(str(scan["seed_url"]))
    for row in rows:
        if not _protected(conn, int(row["id"])) and _scope(str(row["seed_url"])) == scope:
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


@dataclass
class _Group:
    pipeline: Pipeline
    title: str
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
            pages=len(self.pages),
            statuses=dict(self.statuses),
            outcomes=dict(self.outcomes),
            issues=self.issue_links[:4],
            evidence=self.evidence,
        )


def _groups(conn: sqlite3.Connection, scan_id: int) -> dict[str, _Group]:
    grouped: dict[str, _Group] = {}
    ids: dict[tuple[str, int], str] = {}
    for row in issues.list_issues(conn, scan_id):
        if row.pipeline not in PIPELINES:
            continue
        key = row.issue_key
        if row.pipeline == "alfa" and key.rsplit(":", 1)[-1] in {"failed", "cant_tell"}:
            key = key.rsplit(":", 1)[0]
        group = grouped.setdefault(key, _Group(pipeline=row.pipeline, title=row.title))
        if row.pipeline == "alfa":
            group.title = f"{row.wcag_name or 'ACT rule'} (Alfa {key.removeprefix('alfa:')})"
        group.issue_links.append(EvidenceLink(label=row.title, url=row.detail_url))
        for finding_id in row.finding_ids:
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


def _coverage(
    conn: sqlite3.Connection, scan: dict[str, Any], groups: dict[str, _Group]
) -> tuple[set[str], dict[str, list[str]], list[str]]:
    scan_id = int(scan["id"])
    cfg = _config(scan)
    rows = conn.execute(
        "SELECT url_normalized, status_code, render_mode, final_url FROM pages WHERE scan_id = ?",
        (scan_id,),
    ).fetchall()
    pages = {url_policy.normalize(str(row["url_normalized"])) for row in rows}
    common: list[str] = []
    if not rows or any(
        not row["status_code"] or not 200 <= row["status_code"] < 300 for row in rows
    ):
        common.append(f"Report #{scan_id} contains missing or unsuccessful page responses.")
    if int(scan.get("error_count") or 0):
        common.append(f"Report #{scan_id} recorded crawl or analysis errors.")
    if int(scan.get("page_count") or 0) != len(rows):
        common.append(f"Report #{scan_id} page coverage counts are inconsistent.")
    if any(row["final_url"] for row in rows):
        common.append(
            f"Report #{scan_id} includes redirects; confirm the same content was checked."
        )
    if cfg.get("search"):
        search = conn.execute(
            "SELECT status FROM scan_search_runs WHERE scan_id = ?", (scan_id,)
        ).fetchall()
        if not search or any(row["status"] != "completed" for row in search):
            common.append(
                f"Report #{scan_id} has incomplete or unrecorded configured-search coverage."
            )
    by_pipeline: dict[str, list[str]] = {}
    for pipeline in PIPELINES:
        limitations: list[str] = []
        flag = _FLAGS.get(pipeline)
        if flag and cfg.get(flag) is False:
            limitations.append(f"Report #{scan_id}: {pipeline} was disabled.")
        elif pipeline in {"focus", "visual"}:
            limitations.append(
                f"Report #{scan_id}: completed {pipeline} coverage was not recorded."
            )
        elif pipeline == "image":
            # A shared cached analysis alone cannot prove it was evaluated in
            # this report. Historical schema has no per-report analysis ledger.
            limitations.append(
                f"Report #{scan_id}: per-report image-analysis coverage was not recorded."
            )
        else:
            checked = int(scan.get(_COUNTERS[pipeline]) or 0)
            if pipeline in {"semantic", "keyboard", "responsive"} and not cfg.get(
                "method_coverage_version"
            ):
                limitations.append(f"Report #{scan_id}: historical {pipeline} coverage is unknown.")
            elif not rows or checked < len(rows):
                limitations.append(
                    f"Report #{scan_id}: {pipeline} checked {checked} of {len(rows)} pages."
                )
        if pipeline in {"keyboard", "responsive"} and not (flag and cfg.get(flag) is False):
            limitations.append(
                f"Report #{scan_id}: {pipeline} counters record page attempts; "
                "per-check errors and probe limits were not recorded."
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
                    f"Report #{scan_id}: Alfa findings were capped or evidence is missing "
                    f"({stored} of {emitted} stored)."
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
                    f"Report #{scan_id}: interaction states were skipped, bounded, or not recorded."
                )
        by_pipeline[pipeline] = limitations
    return pages, by_pipeline, common


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
    if page < 1 or not 1 <= page_size <= 50:
        raise ComparisonError("Page must be positive and page_size must be between 1 and 50.", 422)
    if category is not None and category not in CATEGORIES:
        raise ComparisonError("Unknown comparison category.", 422)
    if pipeline is not None and pipeline not in PIPELINES:
        raise ComparisonError("Unknown pipeline.", 422)
    current = _load_scan(conn, scan_id)
    if current["status"] != "completed":
        raise ComparisonError("Only completed reports can be compared.", 409)
    baseline_id = compare_to if compare_to is not None else previous_scan_id(conn, current)
    counts: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    if baseline_id is None:
        return ComparisonResponse(
            current=_identity(current),
            baseline=None,
            counts=counts,
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
    if _scope(str(current["seed_url"])) != _scope(str(baseline["seed_url"])):
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
    old_pages, old_methods, old_common = _coverage(conn, baseline, before)
    new_pages, new_methods, new_common = _coverage(conn, current, after)
    common = list(dict.fromkeys([*old_common, *new_common]))
    if old_pages != new_pages:
        common.append(
            f"Page coverage changed: {len(old_pages - new_pages)} earlier pages missing; "
            f"{len(new_pages - old_pages)} additional pages."
        )
    old_cfg, new_cfg = _config(baseline), _config(current)
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
        limitations=all_limitations,
        rows=selected[(page - 1) * page_size : page * page_size],
        total=len(selected),
        page=page,
        page_size=page_size,
    )
