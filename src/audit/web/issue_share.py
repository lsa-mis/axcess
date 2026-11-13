"""Running issue share: what Axcess finds, by detection layer, across completed scans.

Three figures for the Product roadmap (Tracking) page, all computed on request
from the local SQLite store, so they change as soon as a scan completes and no
scan data leaves the machine:

1. **Found occurrences by detection layer (exact).** Of every occurrence
   Axcess found, the share each layer produced. Counted from the canonical
   issue projection (:func:`audit.web.issues.list_issues`), so the numbers
   match the Issues page: repeats of one element on later pages are counted
   once, as there.
2. **Estimated share of all issues (an estimate).** A scan counts only what
   Axcess found, never what it missed. For each WCAG criterion, the issues
   axe-core missed are estimated from axe-core's catch rate in Deque's
   "Automated Accessibility Coverage Report" (table 1). Shown only when the
   sample is large enough. It is never a statement about conformance.
3. **Criteria that failed manual review.** Of the criteria a person marked
   *fail* in an expert evaluation, the share where Axcess had found at least
   one occurrence for that criterion in the same scan. Criterion-level only.

What is counted, and why:

* Occurrences marked "Not a problem" (``false_positive``) are left out: that
  status says the check was wrong, so counting it would inflate what Axcess
  found. Fixed, Accepted risk and the review statuses stay in: each was a real
  occurrence that a layer found.
* Rows the Issues page files as *informational* (an image whose alt text
  already matches, older probe records kept for history) and the rule check
  (Alfa)'s "cannot tell" results are not found issues and are left out too.
  axe-core's own "incomplete" results are never stored (``analyzer/axe.py``).

Bounds: at most :data:`MAX_SCANS` of the most recent completed scans are read,
and every list in the response is sized by the Deque table, the layer list or
that scan bound, never by a site's size.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from audit.web import image_findings_queries, issues
from audit.web.coverage_checks import STUDY, axe_catalog

Layer = Literal[
    "axe_loaded",
    "axe_click_through",
    "alfa",
    "probes",
    "image",
    "semantic",
]
#: Display order: the order a scan runs them, cheapest and surest first.
LAYERS: tuple[Layer, ...] = (
    "axe_loaded",
    "axe_click_through",
    "alfa",
    "probes",
    "image",
    "semantic",
)
_PIPELINE_LAYER: dict[str, Layer] = {
    "axe": "axe_loaded",  # split into click-through below, by ``revealed_by``
    "alfa": "alfa",
    "keyboard": "probes",
    "responsive": "probes",
    "focus": "probes",
    "visual": "probes",
    "image": "image",
    "protected_image": "image",
    "semantic": "semantic",
}

#: Statuses that say the occurrence was not a real problem.
EXCLUDED_STATUSES: frozenset[str] = frozenset({"false_positive"})

#: Most recent completed scans read for the all-scans view and the picker.
MAX_SCANS = 25
#: axe-core occurrences (page as loaded) needed on the anchor criteria
#: before the estimate is shown at all.
MIN_ESTIMATE_SAMPLE = 50
#: Below this catch rate, dividing by it explodes noise (2.49% turns one
#: occurrence into forty), so the criterion's estimate comes from its share of
#: all issues instead.
RATE_FLOOR = 0.10

SOURCE_TITLE = "Deque, Automated Accessibility Coverage Report, table 1"
SOURCE_URL = "https://www.deque.com/automated-accessibility-coverage-report/"
_OTHER = "other"


@dataclass(frozen=True)
class DequeRow:
    sc: str  # WCAG number, or "other" for the remainder row
    share: float  # share of all issues, 0-1
    axe_rate: float  # share axe-core found, 0-1


#: Deque's table 1, less 4.1.1 Parsing: the same figures the "What Axcess
#: checks" page shows (:data:`audit.web.coverage_checks.STUDY`), so the two
#: pages cannot disagree about the study.
DEQUE_TABLE: tuple[DequeRow, ...] = tuple(
    DequeRow(row.sc, row.share / 100, row.axe_rate / 100) for row in STUDY
)
_EXCLUDED_CRITERIA = frozenset({"4.1.1"})
_TABLE_SHARE_TOTAL = sum(row.share for row in DEQUE_TABLE)
_LISTED = frozenset(row.sc for row in DEQUE_TABLE) - {_OTHER}
_SC_RE = re.compile(r"\b\d+\.\d+\.\d+\b")


# --- Response models ---------------------------------------------------


class ScanOption(BaseModel):
    id: int
    seed_url: str
    finished_at: str | None


class LayerCount(BaseModel):
    layer: Layer
    count: int
    share: float | None  # 0-1; None when nothing was found


class LayerShare(BaseModel):
    total: int
    layers: list[LayerCount]
    excluded_not_a_problem: int
    excluded_records: int


class CriterionEstimate(BaseModel):
    sc: str  # WCAG number, or "other"
    deque_share: float
    axe_rate: float
    axe_found: int
    found: int
    estimated_total: float
    method: Literal["axe_rate", "issue_share"]


class EstimateShare(BaseModel):
    available: bool
    axe_sample: int
    min_sample: int
    found: int
    estimated_total: float | None
    share: float | None
    criteria: list[CriterionEstimate]
    source_title: str
    source_url: str


class ManualReviewScan(BaseModel):
    scan_id: int
    seed_url: str
    failed: int
    found: int


class RuleCount(BaseModel):
    """One axe-core rule's counted occurrences, split by page state."""

    rule_id: str
    help: str
    category: str  # axe-core's own kind of problem ("color", "forms", ...)
    criteria: list[str]
    loaded: int
    click_through: int


class CriterionCount(BaseModel):
    sc: str
    count: int


class ManualReviewShare(BaseModel):
    evaluations: int
    failed: int
    found: int
    share: float | None
    scans: list[ManualReviewScan]


class IssueShareResponse(BaseModel):
    scan_id: int | None
    scans: list[ScanOption]
    scans_included: int
    scans_completed: int
    layers: LayerShare
    axe_rules: list[RuleCount]
    found_by_criterion: list[CriterionCount]
    estimate: EstimateShare
    manual_review: ManualReviewShare


class IssueShareError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# --- Counting ----------------------------------------------------------


@dataclass
class _ScanCounts:
    """One scan's counted occurrences."""

    by_layer: Counter[Layer] = field(default_factory=Counter)
    # Criterion -> counted occurrences, every layer / axe on the loaded page.
    by_criterion: Counter[str] = field(default_factory=Counter)
    axe_by_criterion: Counter[str] = field(default_factory=Counter)
    # Every layer, each occurrence once under its first criterion (estimate).
    first_criterion: Counter[str] = field(default_factory=Counter)
    # (axe-core rule id, found after Click-Through) -> counted occurrences.
    axe_rules: Counter[tuple[str, bool]] = field(default_factory=Counter)
    excluded_not_a_problem: int = 0
    excluded_records: int = 0


def criteria_of(raw: str | None) -> list[str]:
    """The WCAG numbers in a stored ``wcag_sc`` ("1.4.3", "1.3.1, 4.1.2")."""
    return _SC_RE.findall(raw or "")


def _bucket(sc: str) -> str | None:
    """The Deque row a criterion falls in, or None for one left out (4.1.1)."""
    if sc in _EXCLUDED_CRITERIA:
        return None
    return sc if sc in _LISTED else _OTHER


def _is_record(row: issues.IssueRow) -> bool:
    return row.review_lane == "informational" or (
        row.pipeline == "alfa" and row.issue_key.endswith(":cant_tell")
    )


def count_scan(conn: sqlite3.Connection, scan_id: int) -> _ScanCounts:
    """Count one scan's found occurrences, by layer and by criterion."""
    out = _ScanCounts()
    rows = issues.list_issues(conn, scan_id)
    dom = {
        int(r["id"]): (str(r["status"]), bool(r["revealed_by"]))
        for r in conn.execute(
            "SELECT id, status, revealed_by FROM page_a11y_findings WHERE scan_id = ?",
            (scan_id,),
        )
    }
    image_findings: dict[str, list[tuple[str, int]]] = {}
    for group in image_findings_queries.grouped_by_remediation(conn, scan_id):
        key = image_findings_queries.image_issue_key(
            group.get("classification"), group.get("alt_adequacy")
        )
        image_findings[key] = [
            (str(f["status"]), len(f.get("occurrences") or [])) for f in group.get("findings", [])
        ]

    for row in rows:
        # Each counted occurrence: (status, revealed in a click-through state).
        occurrences: Iterable[tuple[str, bool]]
        if row.pipeline == "image":
            occurrences = (
                (status, False)
                for status, n in image_findings.get(row.issue_key, [])
                for _ in range(n)
            )
        else:
            occurrences = (dom[i] for i in row.finding_ids if i in dom)
        layer = _PIPELINE_LAYER.get(row.pipeline)
        criteria = criteria_of(row.wcag_sc)
        record = _is_record(row)
        for status, revealed in occurrences:
            if status in EXCLUDED_STATUSES:
                out.excluded_not_a_problem += 1
                continue
            if record or layer is None:
                out.excluded_records += 1
                continue
            this_layer: Layer = "axe_click_through" if layer == "axe_loaded" and revealed else layer
            out.by_layer[this_layer] += 1
            if row.pipeline == "axe":
                out.axe_rules[(row.issue_key.removeprefix("axe:"), revealed)] += 1
            # One occurrence counts once in the estimate, under its first
            # criterion; the manual-review match uses every criterion.
            for sc in criteria:
                out.by_criterion[sc] += 1
            if criteria:
                out.first_criterion[criteria[0]] += 1
                if this_layer == "axe_loaded":
                    out.axe_by_criterion[criteria[0]] += 1
    return out


def _share(part: float, whole: float) -> float | None:
    return part / whole if whole else None


def _layer_share(counts: list[_ScanCounts]) -> LayerShare:
    totals: Counter[Layer] = Counter()
    for c in counts:
        totals.update(c.by_layer)
    total = sum(totals.values())
    return LayerShare(
        total=total,
        layers=[
            LayerCount(layer=layer, count=totals[layer], share=_share(totals[layer], total))
            for layer in LAYERS
        ],
        excluded_not_a_problem=sum(c.excluded_not_a_problem for c in counts),
        excluded_records=sum(c.excluded_records for c in counts),
    )


def estimate_share(axe_found: Counter[str], found: Counter[str]) -> EstimateShare:
    """Estimate all issues from axe-core's catch rates, and Axcess's share of them.

    ``axe_found`` and ``found`` map a WCAG number to counted occurrences: axe-core
    on the page as loaded, and every layer. Criteria with a catch rate at or
    above :data:`RATE_FLOOR` are *anchors*: their total is axe_found ÷ rate.
    The anchors' combined share of all issues then scales to an estimated
    total, which gives every other row its total from its share. Axcess's
    found occurrences count up to each row's estimate, never past it, so the
    share cannot pass 100%.
    """
    axe_bucket: Counter[str] = Counter()
    found_bucket: Counter[str] = Counter()
    for sc, n in axe_found.items():
        if (b := _bucket(sc)) is not None:
            axe_bucket[b] += n
    for sc, n in found.items():
        if (b := _bucket(sc)) is not None:
            found_bucket[b] += n

    anchors = [row for row in DEQUE_TABLE if row.axe_rate >= RATE_FLOOR]
    sample = sum(axe_bucket[row.sc] for row in anchors)
    anchor_total = sum(axe_bucket[row.sc] / row.axe_rate for row in anchors)
    anchor_share = sum(row.share for row in anchors) / _TABLE_SHARE_TOTAL
    total = anchor_total / anchor_share if anchor_total else 0.0

    criteria: list[CriterionEstimate] = []
    counted = 0.0
    for row in DEQUE_TABLE:
        is_anchor = row.axe_rate >= RATE_FLOOR
        estimated = (
            axe_bucket[row.sc] / row.axe_rate
            if is_anchor
            else total * row.share / _TABLE_SHARE_TOTAL
        )
        counted += min(found_bucket[row.sc], estimated)
        criteria.append(
            CriterionEstimate(
                sc=row.sc,
                deque_share=row.share,
                axe_rate=row.axe_rate,
                axe_found=axe_bucket[row.sc],
                found=found_bucket[row.sc],
                estimated_total=estimated,
                method="axe_rate" if is_anchor else "issue_share",
            )
        )
    available = sample >= MIN_ESTIMATE_SAMPLE and total > 0
    return EstimateShare(
        available=available,
        axe_sample=sample,
        min_sample=MIN_ESTIMATE_SAMPLE,
        found=sum(found_bucket.values()),
        estimated_total=total if available else None,
        share=_share(counted, total) if available else None,
        criteria=criteria if available else [],
        source_title=SOURCE_TITLE,
        source_url=SOURCE_URL,
    )


def _manual_review(
    conn: sqlite3.Connection, scan_ids: list[int], counts: dict[int, _ScanCounts]
) -> ManualReviewShare:
    if not scan_ids:
        return ManualReviewShare(evaluations=0, failed=0, found=0, share=None, scans=[])
    marks = ",".join("?" * len(scan_ids))
    evaluations = conn.execute(
        f"SELECT COUNT(*) FROM evaluation_reports WHERE scan_id IN ({marks})",  # noqa: S608
        scan_ids,
    ).fetchone()[0]
    seed_urls = {
        int(r[0]): str(r[1])
        for r in conn.execute(
            f"SELECT id, seed_url FROM scans WHERE id IN ({marks})",  # noqa: S608
            scan_ids,
        )
    }
    failed_by_scan: dict[int, set[str]] = {}
    for scan_id, sc in conn.execute(
        f"""
        SELECT e.scan_id, m.criterion_sc
          FROM manual_check_results m
          JOIN evaluation_reports e ON e.id = m.evaluation_report_id
         WHERE m.outcome = 'fail' AND e.scan_id IN ({marks})
        """,  # noqa: S608
        scan_ids,
    ):
        failed_by_scan.setdefault(int(scan_id), set()).add(str(sc).strip())
    scans: list[ManualReviewScan] = []
    for scan_id in scan_ids:
        failed = failed_by_scan.get(scan_id)
        if not failed:
            continue
        found_here = counts[scan_id].by_criterion
        scans.append(
            ManualReviewScan(
                scan_id=scan_id,
                seed_url=seed_urls.get(scan_id, ""),
                failed=len(failed),
                found=sum(1 for sc in failed if found_here[sc] > 0),
            )
        )
    failed_total = sum(s.failed for s in scans)
    found_total = sum(s.found for s in scans)
    return ManualReviewShare(
        evaluations=int(evaluations),
        failed=failed_total,
        found=found_total,
        share=_share(found_total, failed_total),
        scans=scans,
    )


def _rule_counts(counts: list[_ScanCounts]) -> list[RuleCount]:
    """axe-core occurrences by rule, most first. Bounded by the rule catalogue."""
    meta = axe_catalog().by_id()
    totals: Counter[tuple[str, bool]] = Counter()
    for c in counts:
        totals.update(c.axe_rules)
    out: list[RuleCount] = []
    for rule_id in sorted({key[0] for key in totals}):
        info = meta.get(rule_id)
        out.append(
            RuleCount(
                rule_id=rule_id,
                help=info.help if info else rule_id,
                category=info.category if info else "other",
                criteria=list(info.criteria) if info else [],
                loaded=totals[(rule_id, False)],
                click_through=totals[(rule_id, True)],
            )
        )
    out.sort(key=lambda r: (-(r.loaded + r.click_through), r.rule_id))
    return out


def _sc_key(sc: str) -> tuple[int, ...]:
    return tuple(int(part) for part in sc.split("."))


def _public_only(conn: sqlite3.Connection) -> str:
    """SQL that leaves out sign-in (protected) scans, whose evidence stays in their own workflow."""
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'protected_scans'"
    ).fetchone()
    return " AND id NOT IN (SELECT scan_id FROM protected_scans)" if has_table else ""


def completed_scans(conn: sqlite3.Connection) -> tuple[list[ScanOption], int]:
    """The newest completed public scans (at most :data:`MAX_SCANS`), and how many exist."""
    public = _public_only(conn)
    total = conn.execute(
        f"SELECT COUNT(*) FROM scans WHERE status = 'completed'{public}"  # noqa: S608
    ).fetchone()[0]
    options = [
        ScanOption(
            id=int(r[0]),
            seed_url=str(r[1]),
            finished_at=str(r[2]) if r[2] is not None else None,
        )
        for r in conn.execute(
            f"""
            SELECT id, seed_url, finished_at FROM scans
             WHERE status = 'completed'{public}
             ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
             LIMIT ?
            """,  # noqa: S608
            (MAX_SCANS,),
        )
    ]
    return options, int(total)


def issue_share(conn: sqlite3.Connection, scan_id: int | None = None) -> IssueShareResponse:
    """The three figures, across recent completed scans or for one of them.

    A ``scan_id`` must name a completed scan; anything else is refused rather
    than counted, so a running or failed scan never enters the figures.
    """
    options, completed = completed_scans(conn)
    if scan_id is None:
        scan_ids = [o.id for o in options]
    else:
        row = conn.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if row is None:
            raise IssueShareError("Report not found", status_code=404)
        if row[0] != "completed":
            raise IssueShareError("This report is not complete yet", status_code=409)
        if (
            _public_only(conn)
            and conn.execute(
                "SELECT 1 FROM protected_scans WHERE scan_id = ?", (scan_id,)
            ).fetchone()
        ):
            raise IssueShareError(
                "Coverage leaves out sign-in scans; open the report instead", status_code=409
            )
        scan_ids = [scan_id]

    counts = {sid: count_scan(conn, sid) for sid in scan_ids}
    axe_found: Counter[str] = Counter()
    found: Counter[str] = Counter()
    for c in counts.values():
        axe_found.update(c.axe_by_criterion)
        # Each occurrence once, under its first criterion, so a
        # two-criterion group does not count twice in the estimate.
        found.update(c.first_criterion)
    return IssueShareResponse(
        scan_id=scan_id,
        scans=options,
        scans_included=len(scan_ids),
        scans_completed=completed,
        layers=_layer_share(list(counts.values())),
        axe_rules=_rule_counts(list(counts.values())),
        found_by_criterion=[
            CriterionCount(sc=sc, count=n)
            for sc, n in sorted(
                sum((c.by_criterion for c in counts.values()), Counter()).items(),
                key=lambda item: _sc_key(item[0]),
            )
        ],
        estimate=estimate_share(axe_found, found),
        manual_review=_manual_review(conn, scan_ids, counts),
    )
