"""Excel (.xlsx) audit report — the whole report, every section a table.

A multi-sheet workbook that turns the Markdown audit report into something
you can sort, filter, and track in a spreadsheet:

* **Summary** — the at-a-glance dashboard: scan metadata plus every headline
  rollup (counts, severity, WCAG level, POUR principle, coverage).
* **Issues Overview** — the remediation-guide table (one row per issue) in
  the University of Michigan Digital Accessibility Services format: a
  metadata header block + Issues · Conformance Level · Remediation Ownership ·
  Status · What to Fix · Page Links / Locations · Action · Helpful Resources ·
  Notes · Evidence (a highlighted screenshot of the issue's element, embedded
  when a ``blob_store`` is supplied and the finding has one).
* **Owner Worklist** — the same open issues sliced by who fixes them.
* **Page Hotspots** — pages ranked by a severity-weighted load.
* **Who's Affected** — open issues by the user ability each one blocks.
* **Coverage & Method** — per-criterion automated-vs-manual coverage.
* **Test Tracking** — the manual Pass / Fail checklist, one row per WCAG 2.2
  A/AA criterion.

Every issue-derived sheet is built from :func:`audit_report.build_audit_cards`
— the exact card model the Markdown audit report renders — so the two
deliverables can't drift. The coverage/checklist sheets come from
``coverage_matrix``. All of it is pinned by tests.
"""

from __future__ import annotations

import io
import sqlite3
from datetime import datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from audit import coverage_matrix, evaluation
from audit.blob_store import BlobStore
from audit.exports.audit_report import (
    MAX_HOTSPOTS,
    AuditCard,
    DroppedFinding,
    _owner_key,
    _principle_for,
    _severity_rank,
    build_audit_cards,
)
from audit.exports.collector import ExportScan
from audit.logging import get_logger
from audit.web import issues

log = get_logger(__name__)

# Embedded-evidence sizing: scale screenshots down to this pixel width so a
# wide element capture doesn't blow out the Evidence column; the height is
# scaled proportionally and the row grown to fit.
_EVIDENCE_MAX_WIDTH = 240

# --- palette (matches the source template) --------------------------------
_HEADER_FILL = PatternFill("solid", fgColor="FF356854")  # dark teal-green
_HEADER_FONT = Font(bold=True, color="FFFFFFFF", size=11)
_META_FILL = PatternFill("solid", fgColor="FFFFF2CC")  # light yellow
_META_LABEL_FONT = Font(bold=True, size=11)
_BAND_FILL = PatternFill("solid", fgColor="FFF6F8F9")  # zebra stripe
_TITLE_FONT = Font(bold=True, size=14, color="FF356854")
_WRAP_TOP = Alignment(wrap_text=True, vertical="top")
_WRAP_TOP_CENTER = Alignment(wrap_text=True, vertical="top", horizontal="center")
_THIN = Side(style="thin", color="FFD0D7DE")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

# --- value mappings -------------------------------------------------------
# The template grades conformance A / AA / S, where "S" = a best-practice
# recommendation beyond the WCAG success criteria. Axcess labels those "BP".
_CONFORMANCE_DISPLAY = {"A": "A", "AA": "AA", "AAA": "AAA", "BP": "S"}
_STATUS_DISPLAY = {
    "new": "Not Started",
    "reviewing": "Reviewing",
    "in_progress": "In Progress",
    "remediated": "Resolved",
    "accepted_risk": "Accepted Risk",
    "false_positive": "Not an Issue",
}
_STATUS_CHOICES = [
    "Not Started",
    "Reviewing",
    "In Progress",
    "Resolved",
    "Accepted Risk",
    "Not an Issue",
]
_OWNER_DISPLAY = {
    "dev": "Developer",
    "editor": "Editor",
    "designer": "Designer",
    "content": "Content author",
}

_GUIDANCE = (
    "Prioritization Guidance — Fix issues in conformance-level order. "
    "Level A flags the most significant barriers that block people with "
    "disabilities outright; remediate these first. Level AA issues are "
    "required for WCAG 2.2 AA conformance (the standard most policies and "
    "laws reference) and should follow. Items marked S are best-practice "
    "recommendations that go beyond the success criteria — address them "
    "once the A and AA issues are resolved. Within a level, work top-down: "
    "the table is sorted by Axcess's priority score (occurrence count, "
    "impact, and reach)."
)

_ISSUE_HEADERS = (
    "Issues",
    "Conformance Level",
    "Remediation Ownership",
    "Status",
    "What to Fix",
    "Page Links / Locations",
    "Action",
    "Helpful Resources",
    "Notes",
    "Evidence",
)
_ISSUE_WIDTHS = (34.75, 17.5, 19.13, 15.38, 40.0, 41.25, 48.88, 30.5, 24.0, 22.0)

_TRACK_HEADERS = ("Focus", "What to check", "Pass / Fail")
_TRACK_WIDTHS = (28.0, 70.0, 14.0)
_PASS_FAIL_CHOICES = ["Pass", "Fail", "Needs follow-up", "N/A", "Not tested"]

_LOCATION_CAP = 6  # page links listed before collapsing to "+N more"

# Most-urgent-first ordering for the severity rollups.
_SEVERITY_ORDER = ("Critical", "Serious", "Moderate", "Minor")
# Page-hotspot weighting — mirrors audit_report._page_hotspots so the Excel
# "Page Hotspots" sheet ranks pages identically to the Markdown report.
_SEVERITY_WEIGHT = {"Critical": 4.0, "Serious": 3.0, "Moderate": 2.0, "Minor": 1.0}
# Owner key → singular display label for the per-row Owner Worklist column.
_OWNER_ROW_LABEL = {
    "dev": "Developer",
    "editor": "Content editor",
    "designer": "Designer",
    "content": "Content team",
}
_OWNER_ROW_ORDER = ("dev", "editor", "designer", "content")
# User-group labels — mirrors audit_report._abilities_rollup.
_ABILITY_LABEL = {
    "vision": "Vision (blind / low-vision / color-blind)",
    "motor": "Motor (keyboard-only / switch / tremor)",
    "cognition": "Cognition (memory / attention / language)",
    "hearing": "Hearing (deaf / hard-of-hearing)",
}


def _fmt_date(raw: str | None) -> str:
    """ISO timestamp → 'June 24, 2026'; falls back to the raw string."""
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%B %-d, %Y")
    except (ValueError, TypeError):
        return raw


def _dominant_status(summary: dict[str, int]) -> str:
    """The status bucket with the most occurrences → its display label."""
    if not summary:
        return _STATUS_DISPLAY["new"]
    bucket = max(summary, key=lambda k: summary.get(k, 0))
    return _STATUS_DISPLAY.get(bucket, "Not Started")


def _bullets(steps: tuple[str, ...] | list[str]) -> str:
    """Render fix steps as a newline-bulleted block for one cell."""
    items = [s.strip() for s in steps if s and s.strip()]
    return "\n".join(f"• {s}" for s in items)


def _locations(pages: list[issues.IssuePage], total_pages: int) -> str:
    """Affected-page URLs for the 'Page Links / Locations' cell."""
    urls = [p.page_url for p in pages if p.page_url]
    if not urls:
        return ""
    # Site-wide problem (every crawled page) reads better as a phrase.
    if total_pages > 1 and len(set(urls)) >= total_pages:
        return "All pages."
    shown = urls[:_LOCATION_CAP]
    out = "\n".join(shown)
    if len(urls) > _LOCATION_CAP:
        out += f"\n…and {len(urls) - _LOCATION_CAP} more"
    return out


def _style_header_row(ws: Worksheet, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _WRAP_TOP
        cell.border = _BORDER


def _embed_evidence(
    ws: Worksheet,
    *,
    row: int,
    col: int,
    detail: issues.IssueDetail | None,
    blob_store: BlobStore,
) -> None:
    """Embed the first available finding screenshot into the row's Evidence cell.

    Pulls the first screenshot hash across ``detail.pages``, resolves it to a
    PNG in the blob store, scales it to fit the column, and anchors it to the
    Evidence cell — growing the row to fit. A missing or corrupt file never
    breaks the export (the whole body is defensive); the cell stays blank.
    """
    if detail is None:
        return
    hash_ = next(
        (h for p in detail.pages for h in p.screenshot_hashes if h),
        None,
    )
    if not hash_:
        return
    try:
        path = blob_store.path_for(BlobStore._rel_path(hash_, "png"))
        if not path.exists():
            return
        img = XLImage(str(path))
        if img.width and img.width > _EVIDENCE_MAX_WIDTH:
            img.height = int(img.height * _EVIDENCE_MAX_WIDTH / img.width)
            img.width = _EVIDENCE_MAX_WIDTH
        col_letter = get_column_letter(col)
        img.anchor = f"{col_letter}{row}"
        ws.add_image(img)
        existing = ws.row_dimensions[row].height or 0
        ws.row_dimensions[row].height = max(existing, img.height * 0.75)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("xlsx.evidence_embed_failed", hash=hash_, error=str(exc))


def _build_issues_sheet(
    ws: Worksheet,
    scan: ExportScan,
    conn: sqlite3.Connection,
    *,
    auditor: str,
    audit_date: str,
    blob_store: BlobStore | None = None,
) -> None:
    ncols = len(_ISSUE_HEADERS)
    for i, w in enumerate(_ISSUE_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # --- metadata header block (rows 1-5, merged across the table width) ---
    meta = [
        ("Page", scan.seed_url or "—"),
        ("Compliance Standard", f"WCAG 2.2 Level {scan.axe_level}"),
        ("Audit Date", audit_date),
        ("Auditor", auditor),
        ("Prioritization Guidance", _GUIDANCE),
    ]
    for r, (label, value) in enumerate(meta, start=1):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        cell = ws.cell(row=r, column=1, value=f"{label}: {value}")
        cell.fill = _META_FILL
        cell.alignment = _WRAP_TOP
        cell.font = _META_LABEL_FONT if label != "Prioritization Guidance" else Font(size=10)
    ws.row_dimensions[5].height = 96  # the guidance paragraph needs room

    # --- the issues table (header on row 8, data from row 9) --------------
    header_row = 8
    for c, name in enumerate(_ISSUE_HEADERS, start=1):
        ws.cell(row=header_row, column=c, value=name)
    _style_header_row(ws, header_row, ncols)

    rows = issues.list_issues(conn, scan.id)
    r = header_row
    for idx, row in enumerate(rows):
        r += 1
        detail = issues.get_issue_detail(conn, scan.id, row.issue_key)
        what = (detail.why_matters if detail else None) or row.description or row.title
        fix = (detail.fix_steps if detail else None) or list(row.fix_steps)
        help_url = (detail.help_url if detail else None) or row.help_url or ""
        locations = _locations(detail.pages, scan.page_count) if detail else ""
        values = (
            row.title,
            _CONFORMANCE_DISPLAY.get(row.conformance, row.conformance),
            _OWNER_DISPLAY.get(row.responsibility, row.responsibility.title()),
            _dominant_status(row.status_summary),
            what,
            locations,
            _bullets(fix),
            help_url,
            "",  # Notes — left blank for the auditor
            "",  # Evidence — image is anchored here below (when available)
        )
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment = _WRAP_TOP_CENTER if c in (2, 3, 4) else _WRAP_TOP
            cell.border = _BORDER
            if idx % 2 == 1:
                cell.fill = _BAND_FILL
        # Embed a highlighted element screenshot in the Evidence column
        # (last column) when a blob store is supplied and the finding has one.
        if blob_store is not None:
            _embed_evidence(ws, row=r, col=ncols, detail=detail, blob_store=blob_store)

    last_row = max(r, header_row + 1)
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(ncols)}{last_row}"
    ws.freeze_panes = f"A{header_row + 1}"

    # Status dropdown so a reviewer can update it in Excel.
    dv = DataValidation(type="list", formula1=f'"{",".join(_STATUS_CHOICES)}"', allow_blank=True)
    ws.add_data_validation(dv)
    if r > header_row:
        dv.add(f"D{header_row + 1}:D{last_row}")


def _build_tracking_sheet(ws: Worksheet, *, manual_outcomes: dict[str, str] | None = None) -> None:
    for i, w in enumerate(_TRACK_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.merge_cells("A1:C1")
    title = ws.cell(row=1, column=1, value="Manual Test Tracking")
    title.font = _TITLE_FONT
    ws.merge_cells("A2:C2")
    sub = ws.cell(
        row=2,
        column=1,
        value=(
            "Automated checks can't decide every criterion. For each WCAG 2.2 "
            "A/AA success criterion below, confirm by hand what the tool flags "
            "as needing a human, then record Pass / Fail."
        ),
    )
    sub.alignment = _WRAP_TOP
    sub.font = Font(size=10)
    ws.row_dimensions[2].height = 42

    header_row = 4
    for c, name in enumerate(_TRACK_HEADERS, start=1):
        ws.cell(row=header_row, column=c, value=name)
    _style_header_row(ws, header_row, len(_TRACK_HEADERS))

    crit = sorted(
        coverage_matrix.load_matrix(),
        key=lambda c: [int(p) for p in c.sc.split(".")],
    )
    r = header_row
    for idx, cr in enumerate(crit):
        r += 1
        values = (
            f"{cr.sc} {cr.name} (Level {cr.level})",
            cr.manual_check,
            (manual_outcomes or {}).get(cr.sc, ""),
        )
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=v)
            cell.alignment = _WRAP_TOP_CENTER if col == 3 else _WRAP_TOP
            cell.border = _BORDER
            if idx % 2 == 1:
                cell.fill = _BAND_FILL

    last_row = max(r, header_row + 1)
    ws.auto_filter.ref = f"A{header_row}:C{last_row}"
    ws.freeze_panes = f"A{header_row + 1}"

    dv = DataValidation(type="list", formula1=f'"{",".join(_PASS_FAIL_CHOICES)}"', allow_blank=True)
    ws.add_data_validation(dv)
    if r > header_row:
        dv.add(f"C{header_row + 1}:C{last_row}")


# --- generic data-sheet layout (used by every rollup sheet) ---------------


def _styled_table(
    ws: Worksheet,
    *,
    title: str,
    subtitle: str,
    headers: tuple[str, ...],
    rows: list[tuple[Any, ...]],
    widths: tuple[float, ...],
    center_cols: tuple[int, ...] = (),
    empty_note: str = "Nothing to report for this scan.",
) -> None:
    """Lay out one self-contained data sheet.

    Title (row 1) · subtitle (row 2) · a dark-green header (row 4) · banded,
    bordered data rows from row 5, with a frozen header and an auto-filter.
    Keeps every rollup sheet visually consistent.
    """
    ncols = len(headers)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    last_col = get_column_letter(ncols)

    ws.merge_cells(f"A1:{last_col}1")
    tcell = ws.cell(row=1, column=1, value=title)
    tcell.font = _TITLE_FONT
    ws.merge_cells(f"A2:{last_col}2")
    scell = ws.cell(row=2, column=1, value=subtitle)
    scell.alignment = _WRAP_TOP
    scell.font = Font(size=10)
    ws.row_dimensions[2].height = 42

    header_row = 4
    for c, name in enumerate(headers, start=1):
        ws.cell(row=header_row, column=c, value=name)
    _style_header_row(ws, header_row, ncols)

    center = set(center_cols)
    r = header_row
    if not rows:
        ws.merge_cells(
            start_row=header_row + 1, start_column=1, end_row=header_row + 1, end_column=ncols
        )
        note = ws.cell(row=header_row + 1, column=1, value=empty_note)
        note.alignment = _WRAP_TOP
        note.font = Font(italic=True, size=10)
    else:
        for idx, row in enumerate(rows):
            r += 1
            for col, v in enumerate(row, start=1):
                cell = ws.cell(row=r, column=col, value=v)
                cell.alignment = _WRAP_TOP_CENTER if col in center else _WRAP_TOP
                cell.border = _BORDER
                if idx % 2 == 1:
                    cell.fill = _BAND_FILL
    last_row = max(r, header_row + 1)
    ws.auto_filter.ref = f"A{header_row}:{last_col}{last_row}"
    ws.freeze_panes = f"A{header_row + 1}"


# --- summary dashboard ----------------------------------------------------


def _build_summary_sheet(
    ws: Worksheet,
    scan: ExportScan,
    cards: list[AuditCard],
    dropped: list[DroppedFinding],
    best_practice: list[Any],
    *,
    audit_date: str,
) -> None:
    """A one-screen dashboard: scan metadata + every headline rollup."""
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 58

    ws.merge_cells("A1:B1")
    title = ws.cell(row=1, column=1, value=f"Accessibility audit — Scan #{scan.id}")
    title.font = _TITLE_FONT
    ws.merge_cells("A2:B2")
    sub = ws.cell(
        row=2,
        column=1,
        value=(
            "At-a-glance summary of this scan. Each rollup below has its own "
            "sheet with the detail; this is the dashboard for tracking progress."
        ),
    )
    sub.alignment = _WRAP_TOP
    sub.font = Font(size=10)
    ws.row_dimensions[2].height = 36

    r = 4

    def section(label: str) -> None:
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        cell = ws.cell(row=r, column=1, value=label)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _WRAP_TOP
        r += 1

    def metric(label: str, value: Any) -> None:
        nonlocal r
        lc = ws.cell(row=r, column=1, value=label)
        lc.font = Font(bold=True, size=11)
        lc.alignment = _WRAP_TOP
        lc.border = _BORDER
        vc = ws.cell(row=r, column=2, value=value)
        vc.alignment = _WRAP_TOP
        vc.border = _BORDER
        r += 1

    section("Scan")
    metric("Seed URL", scan.seed_url or "—")
    metric("Audited against", f"WCAG 2.2 Level {scan.axe_level}")
    metric("Pages crawled", scan.page_count)
    metric("Audit date", audit_date)
    r += 1

    open_occurrences = sum(c.affected_finding_count for c in cards)
    section("Issue counts")
    metric("Open issue types", len(cards))
    metric("Open findings (occurrences)", open_occurrences)
    metric("Best-practice items (beyond WCAG)", len(best_practice))
    metric("Already-triaged issue types", len(dropped))
    r += 1

    by_sev: dict[str, int] = {}
    for c in cards:
        by_sev[c.severity] = by_sev.get(c.severity, 0) + 1
    section("Open issues by severity")
    for sev in _SEVERITY_ORDER:
        metric(sev, by_sev.get(sev, 0))
    r += 1

    by_level: dict[str, int] = {}
    for c in cards:
        by_level[c.wcag_level or "—"] = by_level.get(c.wcag_level or "—", 0) + 1
    section("Open issues by WCAG level")
    for lvl in ("A", "AA", "AAA"):
        if by_level.get(lvl):
            metric(f"Level {lvl}", by_level[lvl])
    r += 1

    by_principle: dict[str, int] = {}
    for c in cards:
        p = _principle_for(c.wcag_sc)
        by_principle[p] = by_principle.get(p, 0) + 1
    section("Open issues by WCAG principle (POUR)")
    for principle in ("Perceivable", "Operable", "Understandable", "Robust"):
        if by_principle.get(principle):
            metric(principle, by_principle[principle])
    r += 1

    cov = coverage_matrix.summary()
    section("WCAG 2.2 A/AA coverage (all 55 criteria)")
    for m in coverage_matrix.METHODS:
        metric(coverage_matrix.METHOD_LABELS[m], cov.by_method.get(m, 0))


# --- rollup sheets (Owner / Hotspots / Affected / Coverage) ---------------


def _build_worklist_sheet(ws: Worksheet, cards: list[AuditCard]) -> None:
    """One row per open issue, grouped by who fixes it — filter by Owner."""
    ordered = sorted(
        cards,
        key=lambda c: (
            _OWNER_ROW_ORDER.index(_owner_key(c.owner))
            if _owner_key(c.owner) in _OWNER_ROW_ORDER
            else len(_OWNER_ROW_ORDER),
            _severity_rank(c.severity),
            -c.affected_page_count,
        ),
    )
    rows: list[tuple[Any, ...]] = []
    for c in ordered:
        key = _owner_key(c.owner)
        sc = f"{c.wcag_sc} {c.wcag_name}".strip() if c.wcag_sc else "Best practice"
        rows.append(
            (
                _OWNER_ROW_LABEL.get(key, key.capitalize()),
                c.title,
                c.severity,
                c.effort,
                c.affected_page_count,
                sc,
            )
        )
    _styled_table(
        ws,
        title="Remediation worklist by owner",
        subtitle=(
            "The same open issues, re-sliced by the team that fixes them. "
            "Filter the Owner column to hand each team their pack."
        ),
        headers=("Owner", "Issue", "Severity", "Effort", "Pages", "WCAG"),
        rows=rows,
        widths=(18.0, 46.0, 13.0, 20.0, 9.0, 30.0),
        center_cols=(3, 5),
        empty_note="No open issues to assign.",
    )


def _build_hotspots_sheet(ws: Worksheet, cards: list[AuditCard]) -> None:
    """Pages ranked by a severity-weighted count of the open findings on them."""
    score: dict[str, float] = {}
    count: dict[str, int] = {}
    title_for: dict[str, str | None] = {}
    for card in cards:
        w = _SEVERITY_WEIGHT.get(card.severity, 1.0)
        for loc in card.locations:
            url = loc.page_url or "(unknown)"
            score[url] = score.get(url, 0.0) + w
            count[url] = count.get(url, 0) + 1
            title_for.setdefault(url, loc.page_title)
    ranked = sorted(score.items(), key=lambda kv: -kv[1])[:MAX_HOTSPOTS]
    rows: list[tuple[Any, ...]] = [
        (url, title_for.get(url) or "", round(s), count[url]) for url, s in ranked
    ]
    _styled_table(
        ws,
        title="Page hotspots",
        subtitle=(
            "Pages carrying the most (and most severe) open findings — fix shared "
            "templates here to clear issues across the site. Weighted load = sum of "
            "severity weights (Critical 4 · Serious 3 · Moderate 2 · Minor 1)."
        ),
        headers=("Page", "Title", "Weighted load", "Findings shown"),
        rows=rows,
        widths=(60.0, 30.0, 16.0, 16.0),
        center_cols=(3, 4),
        empty_note="No open findings pinned to specific pages.",
    )


def _build_affected_sheet(ws: Worksheet, cards: list[AuditCard]) -> None:
    """Open issues rolled up by the user ability each one blocks."""
    by_ability: dict[str, int] = {}
    by_ability_pages: dict[str, int] = {}
    for c in cards:
        for ability in c.abilities:
            by_ability[ability] = by_ability.get(ability, 0) + 1
            by_ability_pages[ability] = by_ability_pages.get(ability, 0) + c.affected_page_count
    rows: list[tuple[Any, ...]] = [
        (_ABILITY_LABEL.get(a, a.capitalize()), n, by_ability_pages[a])
        for a, n in sorted(by_ability.items(), key=lambda kv: -kv[1])
    ]
    _styled_table(
        ws,
        title="Who is affected",
        subtitle=(
            "Each issue is tagged with the user groups it blocks. One issue can "
            "affect several groups, so these counts overlap."
        ),
        headers=("User group", "Issue types affecting them", "Across (page-instances)"),
        rows=rows,
        widths=(44.0, 30.0, 24.0),
        center_cols=(2, 3),
        empty_note="No ability metadata on the open issues.",
    )


def _build_coverage_sheet(ws: Worksheet) -> None:
    """Per-criterion coverage for all 55 WCAG 2.2 A/AA SCs (filter by Coverage)."""
    crit = sorted(
        coverage_matrix.load_matrix(),
        key=lambda c: [int(p) for p in c.sc.split(".")],
    )
    rows: list[tuple[Any, ...]] = [
        (
            c.sc,
            c.name,
            c.level,
            coverage_matrix.METHOD_LABELS[c.method],
            c.automated_check or "—",
            c.manual_check,
        )
        for c in crit
    ]
    _styled_table(
        ws,
        title="Coverage & method — what's automated vs. manual",
        subtitle=(
            "For every WCAG 2.2 A/AA success criterion: how Axcess covers it and "
            "what a human must still confirm. Filter Coverage = 'Manual only' to see "
            "exactly what no pipeline detects."
        ),
        headers=(
            "SC",
            "Criterion",
            "Level",
            "Coverage",
            "What Axcess does",
            "Still verify by hand",
        ),
        rows=rows,
        widths=(9.0, 34.0, 8.0, 17.0, 44.0, 44.0),
        center_cols=(1, 3),
    )


def render_xlsx(
    scan: ExportScan,
    *,
    conn: sqlite3.Connection,
    auditor: str = "Axcess",
    audit_date: str | None = None,
    blob_store: BlobStore | None = None,
) -> bytes:
    """Render the full Excel audit workbook and return the .xlsx bytes.

    Seven sheets, every report section as a filterable table:

    1. **Summary** — the at-a-glance dashboard (counts, severity, level,
       principle, coverage headline).
    2. **Issues Overview** — the remediation table (one row per issue).
    3. **Owner Worklist** — the same issues sliced by who fixes them.
    4. **Page Hotspots** — pages ranked by severity-weighted load.
    5. **Who's Affected** — open issues by the ability each blocks.
    6. **Coverage & Method** — per-criterion automated-vs-manual coverage.
    7. **Test Tracking** — the manual Pass / Fail checklist.

    ``conn`` is required: the issue tables are built live from the same
    ``issues.list_issues()`` / audit-report card model the Markdown report
    uses, so the two deliverables can't drift. ``audit_date`` defaults to the
    scan's finish time formatted as a human date.

    ``blob_store`` is optional: when supplied, the Issues Overview sheet
    embeds the highlighted element screenshot captured for each finding at
    scan time into a trailing "Evidence" column. When ``None`` (the default)
    the behaviour is unchanged — no images, just the textual table.
    """
    date_str = audit_date or _fmt_date(scan.finished_at or scan.started_at)
    cards, dropped, best_practice = build_audit_cards(conn, scan)

    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    _build_summary_sheet(summary, scan, cards, dropped, best_practice, audit_date=date_str)

    _build_issues_sheet(
        wb.create_sheet("Issues Overview"),
        scan,
        conn,
        auditor=auditor,
        audit_date=date_str,
        blob_store=blob_store,
    )
    _build_worklist_sheet(wb.create_sheet("Owner Worklist"), cards)
    _build_hotspots_sheet(wb.create_sheet("Page Hotspots"), cards)
    _build_affected_sheet(wb.create_sheet("Who's Affected"), cards)
    _build_coverage_sheet(wb.create_sheet("Coverage & Method"))
    manual_outcomes = {
        check["criterion"]["sc"]: {
            "pass": "Pass",
            "fail": "Fail",
            "not_tested": "Not tested",
            "needs_follow_up": "Needs follow-up",
        }.get(check["outcome"], "")
        for check in evaluation.list_manual_checks(conn, scan.id)
    }
    _build_tracking_sheet(wb.create_sheet("Test Tracking"), manual_outcomes=manual_outcomes)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
