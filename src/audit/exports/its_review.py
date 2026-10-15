"""The U-M ITS Accessibility Team's "Technical Review" workbook, filled in.

The University of Michigan ITS Accessibility Team records each evaluation in
one spreadsheet template (``templates/its_technical_review.xlsx``, kept
byte-for-byte as the team supplied it). This module opens that template and
fills it from one completed scan, so the team receives its own format rather
than a second workbook to transcribe.

The template stays exactly as the team supplied it: its formulas, dropdowns,
named ranges, styles, example values and reference tables are not changed,
even where they have known faults. Only data cells are written. This is the
team's decision for now (October 2026). Two consequences follow, and the
tests pin both:

* The Summary formulas count rows 2-49 only, so they miss any row past the
  48th. Their ``DIVIDE()`` is a Google Sheets function, so Excel shows
  ``#NAME?`` for the percentages.
* Rows past the template's own (Findings Issues row 49, Test Plan row 138)
  are written as plain cells, with no dropdown or styling. Every reported
  element is still listed rather than dropped.

Only what a person confirmed is listed. In the page inspector, the auditor
reviews each flagged element and chooses "Checked: a problem to report",
"Checked: a repeat of one already reported", or leaves it "Not checked yet"
(``audit.occurrence_reviews``). The workbook lists the first kind only:
the barriers the team hands to the vendor, each element once. Elements not
checked yet, and repeats of a problem already reported, are left out.

What each sheet receives:

* **Coversheet**: the scan date, the site's host as the IT name, its start
  URL, the tools the scan used, and, when an expert evaluation records it,
  the purpose as Background. Tester(s) is left for the team, as the team
  asked: Axcess has no user accounts to name a tester from. Fields only a
  person knows (U-M contact, vendor contact, VPAT, description, login info)
  keep the template's own prompt so they read as unfilled, not as blank
  facts, and IT provenance and IT type keep the template's values.
* **Test Plan**: each place a reported element is: a page, or a page state
  reached by clicking (the click chain the inspector shows), one row each,
  with its Test name, and its URL with the clicks to reach it. The
  Description column is left for the team. Column A feeds the Test dropdown
  on Findings Issues through the template's ``GenericTestList`` name.
* **Summary**: a short factual narrative in the Narrative Summary cell.
* **Findings Issues**: one row per reported element, as the ITS team asked:
  the team tracks, fixes and verifies each barrier on its own row. Issue
  notes are the notes the auditor saved in Axcess, as written; a reported
  element saved without notes gets the issue's plain-language title, so no
  row is blank. An element carrying several occurrences of one issue (the
  inspector saves one review for all of them) is one row. An issue's rows
  sit together, in the app's priority order, and each row's Test is the
  page or page state it is in. Category, Criterion, Impact and "Most
  affects" use the template's own Reference and Reference Impact wording
  wherever the criterion is listed there, so the team's dropdowns and
  Summary counts match.
* **Reference**, **Reference Impact**: unchanged.

Severity is a first estimate. The template's scale judges access to core
and secondary tasks, which a crawl cannot know, so the automated impact
rating is mapped onto it conservatively and nothing is ever marked Blocker.
The Summary narrative says so.

Every value written from the scan (page titles, URLs, element locators) is
stored as text, never as a formula: a page titled ``=HYPERLINK(...)`` must
not become a live formula in the team's spreadsheet.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from typing import Any
from urllib.parse import urlsplit

from openpyxl import load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from audit import coverage_matrix, evaluation
from audit.exports.audit_report import plain_text
from audit.exports.collector import ExportScan
from audit.logging import get_logger
from audit.web import issues

log = get_logger(__name__)

_TEMPLATE_PACKAGE = "audit.exports"
_TEMPLATE_PATH = ("templates", "its_technical_review.xlsx")

# The template's sheet names, as the ITS team wrote them.
_COVER = "Coversheet"
_PLAN = "Test Plan"
_SUMMARY = "Summary"
_FINDINGS = "Findings Issues"
_REFERENCE = "Reference"
_IMPACT = "Reference Impact"

# Findings Issues: the template ships 48 numbered blank rows (2-49), and its
# Summary formulas and dropdowns cover only those. The export keeps at least
# that many, so the team can still add issues by hand.
_FIRST_ISSUE_ROW = 2
_TEMPLATE_LAST_ISSUE_ROW = 49
# Test Plan: rows 5-138 carry the template's styles and its named range.
# Rows past either are written without the template's dropdowns or styles,
# because the template is kept unchanged (see the module docstring).
_FIRST_PLAN_ROW = 5
_TEMPLATE_LAST_PLAN_ROW = 138


# The template's severity scale, exactly as Reference!A19:A23 spells it
# (two spaces after the digit). The Summary counts match on this text.
_SEV_CRITICAL = "4  Critical"
_SEV_MAJOR = "3  Major"
_SEV_MINOR = "2  Minor"
_SEV_BEST_PRACTICE = "1  Best practice"
# Automated impact -> the template's scale. Conservative on purpose: the
# template's levels judge access to core and secondary tasks, which a scan
# cannot know, so no impact maps to "5  Blocker" and a person raises it.
_SEVERITY_FROM_IMPACT = {
    "critical": _SEV_CRITICAL,
    "serious": _SEV_MAJOR,
    "major": _SEV_MAJOR,
    "moderate": _SEV_MINOR,
    "minor": _SEV_MINOR,
    "info": _SEV_MINOR,
}

# The template's starting value for Verified by a11y team (column K).
_NOT_TESTED_BY_TEAM = "Not tested by UM A11y team"

# Criteria the ITS Reference sheet does not list (it predates WCAG 2.2 and
# covers A/AA only), placed in the category of the listed criterion they
# sit beside, so the Category dropdown and the Summary counts still apply.
_EXTRA_CATEGORY = {
    # WCAG 2.2 A/AA additions.
    "2.4.11": "Keyboard and other Input",
    "2.5.7": "Keyboard and other Input",
    "2.5.8": "Keyboard and other Input",
    "3.2.6": "Navigation and Consistency",
    "3.3.7": "Instructions",
    "3.3.8": "Instructions",
    # AAA, for scans checked at Level AAA.
    "1.2.6": "Text Alternatives",
    "1.2.7": "Text Alternatives",
    "1.2.8": "Text Alternatives",
    "1.2.9": "Text Alternatives",
    "1.3.6": "Semantics and Structure",
    "1.4.6": "Contrast",
    "1.4.7": "Media Control",
    "1.4.8": "Adaptability",
    "1.4.9": "Text Alternatives",
    "2.1.3": "Keyboard and other Input",
    "2.2.3": "User Controls",
    "2.2.4": "User Controls",
    "2.2.5": "User Controls",
    "2.2.6": "User Controls",
    "2.3.2": "Media Control",
    "2.3.3": "Media Control",
    "2.4.8": "Navigation and Consistency",
    "2.4.9": "Semantics and Structure",
    "2.4.10": "Semantics and Structure",
    "2.4.12": "Keyboard and other Input",
    "2.4.13": "Keyboard and other Input",
    "2.5.5": "Keyboard and other Input",
    "2.5.6": "Keyboard and other Input",
    "3.1.3": "Language",
    "3.1.4": "Language",
    "3.1.5": "Language",
    "3.1.6": "Language",
    "3.2.5": "User Controls",
    "3.3.5": "Instructions",
    "3.3.6": "Instructions",
    "3.3.9": "Instructions",
}

# The user groups in the template's own words (Reference Impact column B),
# for criteria that sheet does not list.
_ABILITY_GROUPS = {
    "vision": "Blind, Low vision",
    "hearing": "Deaf, Hard of hearing",
    "motor": "Mobility disability",
    "cognition": "Neurodivergent",
}

# Each check by its interface name. Mirrors CHECK_LABEL in
# web/frontend/src/lib/terms.ts so the workbook names a check as the app does.
_CHECK_LABEL = {
    "axe": "Rule check (axe)",
    "alfa": "Rule check (Alfa)",
    "keyboard": "Keyboard check",
    "responsive": "Zoom and layout check",
    "focus": "Focus check",
    "visual": "Motion and reading-order check",
    "semantic": "AI review",
    "image": "Image text check",
}

# The template writes each criterion as "<number> <en dash> <name>".
_EN_DASH = "\u2013"
_SC_PREFIX = re.compile(r"^\s*(\d+\.\d+\.\d+)")
_UNDERSTANDING_URL = "https://www.w3.org/WAI/WCAG22/Understanding/{slug}.html"


@dataclass(frozen=True)
class _Reference:
    """What the template's own reference sheets say about each criterion."""

    #: SC number -> the criterion as the template writes it ("1.4.3", an en dash,
    #: "Contrast (Minimum)").
    criterion: dict[str, str]
    #: SC number -> the template's category for it.
    category: dict[str, str]
    #: SC number -> the template's "Most affects people who are/have" text.
    affects: dict[str, str]
    #: SC number -> the template's Impact sentence.
    impact: dict[str, str]


@dataclass(frozen=True)
class _Place:
    """Where a reported element is: a page, or a page state reached by clicking."""

    page_id: int
    url: str
    title: str | None
    #: The page state's key; None for the page as it loaded.
    state_key: str | None
    #: The controls clicked to reach it, "“Menu” → “Help”"; None at page load.
    click_chain: str | None


@dataclass(frozen=True)
class _Row:
    """One Findings Issues row: one element a person reported."""

    issue: issues.IssueRow
    place: _Place
    notes: str


def _sc_of(text: Any) -> str | None:
    match = _SC_PREFIX.match(str(text or ""))
    return match.group(1) if match else None


def _clean(value: str) -> str:
    """Drop the control characters a worksheet cell cannot hold."""
    return str(ILLEGAL_CHARACTERS_RE.sub("", value))


def _put_text(ws: Worksheet, coordinate: str, value: str | None) -> None:
    """Write ``value`` as plain text, never as a formula.

    openpyxl turns any string that starts with ``=`` into a formula. Scan
    text (a page title, a URL, an element locator) comes from the crawled
    site, so it is forced back to text.
    """
    cell = ws[coordinate]
    cell.value = _clean(value) if value is not None else None
    if cell.data_type == "f":
        cell.data_type = "s"


def _put_link(ws: Worksheet, coordinate: str, text: str, url: str) -> None:
    """Write ``text`` linked to ``url``, in the cell's own template style."""
    _put_text(ws, coordinate, text)
    ws[coordinate].hyperlink = url


def _scan_date(scan: ExportScan) -> datetime | None:
    raw = scan.finished_at or scan.started_at
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return datetime(parsed.year, parsed.month, parsed.day)


def _human_date(when: datetime | None) -> str:
    return when.strftime("%B %-d, %Y") if when else "an unknown date"


def _plural(count: int, one: str, many: str) -> str:
    return f"{count:,} {one if count == 1 else many}"


def _read_reference(wb: Workbook) -> _Reference:
    """Index the template's Reference and Reference Impact sheets by SC number."""
    criterion: dict[str, str] = {}
    category: dict[str, str] = {}
    ref = wb[_REFERENCE]
    # Row 4 names each category (B4:K4); the criteria sit below it.
    for col in range(2, 12):
        name = ref.cell(row=4, column=col).value
        if not name:
            continue
        for row in range(5, 17):
            text = ref.cell(row=row, column=col).value
            sc = _sc_of(text)
            if sc:
                criterion[sc] = str(text).strip()
                category[sc] = str(name).strip()
    affects: dict[str, str] = {}
    impact: dict[str, str] = {}
    for text, who, why in wb[_IMPACT].iter_rows(min_col=1, max_col=3, values_only=True):
        sc = _sc_of(text)
        if not sc:
            continue
        criterion.setdefault(sc, str(text).strip())
        if who:
            affects[sc] = str(who).strip()
        if why:
            impact[sc] = str(why).strip()
    return _Reference(criterion=criterion, category=category, affects=affects, impact=impact)


def _short_name(name: str, limit: int = 40) -> str:
    """A control's name cut at a word near ``limit``, as the inspector cuts it."""
    text = " ".join(name.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit / 2 else cut).rstrip(" ·,.;:\u2013-") + "…"


def _click_chain(path_labels: str | None, revealed_by: str | None) -> str:
    """The controls clicked to reach a page state, as the inspector says it."""
    try:
        labels = json.loads(path_labels or "[]")
    except json.JSONDecodeError:
        labels = []
    names = [str(label) for label in labels if label] or [str(revealed_by or "")]
    return " → ".join(f"“{_short_name(name)}”" for name in names)


def _reported_reviews(
    conn: sqlite3.Connection, scan_id: int
) -> list[tuple[int | None, int | None, str]]:
    """``(a11y_finding_id, page_image_id, notes)`` of every occurrence a person reported.

    A database whose review table is missing or out of date (migrations not
    yet applied) has no reviews to list, and the workbook still renders.
    """
    try:
        rows = conn.execute(
            "SELECT a11y_finding_id, page_image_id, notes FROM occurrence_reviews "
            "WHERE scan_id = ? AND decision = 'report' ORDER BY id",
            (scan_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        log.warning("its_review.reviews_unreadable", error=str(exc))
        return []
    return [(r[0], r[1], str(r[2] or "")) for r in rows]


def _in_batches(ids: list[int], size: int = 500) -> list[list[int]]:
    return [ids[start : start + size] for start in range(0, len(ids), size)]


def _collect_rows(conn: sqlite3.Connection, scan_id: int) -> list[_Row]:
    """One row per element a person reported, in the app's priority order.

    Occurrences are grouped into elements the way the inspector outlines
    them: one issue, one page state, one element locator and markup (or one
    image placed on the page). The inspector saves one review for every
    occurrence on an element, so the group shares its notes.
    """
    reviews = _reported_reviews(conn, scan_id)
    if not reviews:
        return []
    issue_rows = issues.list_issues(conn, scan_id)
    order = {row.issue_key: index for index, row in enumerate(issue_rows)}
    # Which issue each occurrence belongs to. A repeat (the same element on a
    # later page, reported once by the Issues table) is still reviewable in
    # the inspector, so it counts for its issue too.
    by_a11y: dict[int, issues.IssueRow] = {}
    by_image_finding: dict[int, issues.IssueRow] = {}
    for row in issue_rows:
        target = by_image_finding if row.pipeline == "image" else by_a11y
        for finding_id in (*row.finding_ids, *row.repeat_finding_ids):
            target[int(finding_id)] = row

    pages = {
        int(r[0]): (str(r[1]), r[2])
        for r in conn.execute(
            "SELECT id, url_normalized, title FROM pages WHERE scan_id = ?", (scan_id,)
        )
    }
    states: dict[tuple[int, str], str] = {}
    try:
        for r in conn.execute(
            "SELECT page_id, state_key, path_labels, revealed_by FROM page_dom_states "
            "WHERE scan_id = ?",
            (scan_id,),
        ):
            states[(int(r[0]), str(r[1]))] = _click_chain(r[2], r[3])
    except sqlite3.OperationalError:
        pass  # A report from before page states were saved.

    def place(page_id: int, state_key: str | None) -> _Place | None:
        if page_id not in pages:
            return None
        url, title = pages[page_id]
        chain = states.get((page_id, state_key)) if state_key else None
        return _Place(page_id, url, title, state_key if chain else None, chain)

    notes_by_a11y = {int(a): notes for a, _, notes in reviews if a is not None}
    notes_by_image = {int(i): notes for _, i, notes in reviews if i is not None}
    # element key -> (issue, place, notes, sort key)
    elements: dict[tuple[Any, ...], tuple[issues.IssueRow, _Place, str, tuple[Any, ...]]] = {}

    for batch in _in_batches(sorted(notes_by_a11y)):
        marks = ",".join("?" for _ in batch)
        for r in conn.execute(
            f"SELECT id, page_id, revealed_state_key, target_selector, html_snippet "  # noqa: S608
            f"FROM page_a11y_findings WHERE scan_id = ? AND id IN ({marks})",
            (scan_id, *batch),
        ):
            a11y_issue = by_a11y.get(int(r[0]))
            a11y_place = place(int(r[1]), r[2])
            if a11y_issue is None or a11y_place is None:
                continue
            snippet = " ".join(str(r[4] or "").split())
            selector = str(r[3] or "")
            a11y_key: tuple[Any, ...] = (
                a11y_issue.issue_key,
                a11y_place.page_id,
                a11y_place.state_key or "",
                selector,
                snippet,
            )
            notes = notes_by_a11y[int(r[0])]
            # One element, several occurrences: keep the notes if any has them.
            if a11y_key in elements and (elements[a11y_key][2] or not notes):
                continue
            # In the order the scan recorded them, which follows the page.
            sort = (
                order[a11y_issue.issue_key],
                a11y_place.page_id,
                a11y_place.state_key or "",
                int(r[0]),
            )
            elements[a11y_key] = (a11y_issue, a11y_place, notes, sort)

    for batch in _in_batches(sorted(notes_by_image)):
        marks = ",".join("?" for _ in batch)
        for r in conn.execute(
            f"SELECT pi.id, pi.page_id, f.id FROM page_images pi "  # noqa: S608
            f"JOIN findings f ON f.image_id = pi.image_id AND f.scan_id = ? "
            f"WHERE pi.id IN ({marks})",
            (scan_id, *batch),
        ):
            image_issue = by_image_finding.get(int(r[2]))
            image_place = place(int(r[1]), None)
            if image_issue is None or image_place is None:
                continue
            image_key: tuple[Any, ...] = (
                image_issue.issue_key,
                image_place.page_id,
                "",
                "image",
                int(r[0]),
            )
            sort = (order[image_issue.issue_key], image_place.page_id, "", int(r[0]))
            elements[image_key] = (image_issue, image_place, notes_by_image[int(r[0])], sort)

    ordered = sorted(elements.values(), key=lambda item: item[3])
    return [_Row(issue=row, place=where, notes=notes) for row, where, notes, _ in ordered]


def _test_names(places: list[_Place]) -> dict[tuple[int, str | None], str]:
    """A unique Test name per place: the page's title, then the clicks to the state."""
    taken: set[str] = set()
    names: dict[tuple[int, str | None], str] = {}
    for where in places:
        path = urlsplit(where.url).path or "/"
        base = " ".join(str(where.title or "").split()) or path
        if where.click_chain:
            base = f"{base}, after clicking {where.click_chain}"
        name = base
        if name in taken:
            name = f"{base} ({path})"
        suffix = 2
        while name in taken:
            name = f"{base} ({path}) {suffix}"
            suffix += 1
        taken.add(name)
        names[(where.page_id, where.state_key)] = name
    return names


def _criterion_text(row: issues.IssueRow, ref: _Reference) -> str:
    if not row.wcag_sc:
        return "No WCAG criterion (best practice)"
    if row.wcag_sc in ref.criterion:
        return ref.criterion[row.wcag_sc]
    if row.wcag_name:
        return f"{row.wcag_sc} {_EN_DASH} {row.wcag_name}"
    return row.wcag_sc


def _info_link(row: issues.IssueRow, criterion_names: dict[str, str]) -> tuple[str, str] | None:
    """The template's Info column: W3C's page on the criterion, else the rule's page.

    W3C names each Understanding page after the criterion's official name, so
    the link is built only from the coverage matrix's official names.
    """
    if row.wcag_sc and row.wcag_sc in criterion_names:
        slug = re.sub(r"[^a-z0-9]+", "-", criterion_names[row.wcag_sc].lower()).strip("-")
        return f"{row.wcag_sc} Info", _UNDERSTANDING_URL.format(slug=slug)
    if row.help_url:
        return "Rule info", row.help_url
    return None


def _severity(row: issues.IssueRow) -> str:
    if row.conformance == "BP" or not row.wcag_sc:
        return _SEV_BEST_PRACTICE
    return _SEVERITY_FROM_IMPACT.get((row.impact or "").lower(), _SEV_MINOR)


def _fill_coversheet(
    ws: Worksheet,
    scan: ExportScan,
    scan_day: datetime | None,
    evaluation_record: dict[str, Any],
    rows: list[_Row],
) -> None:
    if scan_day is not None:
        ws["B3"].value = scan_day
    _put_text(ws, "B8", urlsplit(scan.seed_url).hostname or scan.seed_url)
    purpose = str(evaluation_record.get("purpose") or "").strip()
    if evaluation_record.get("exists") and purpose:
        _put_text(ws, "B13", purpose)
    _put_link(ws, "B17", scan.seed_url, scan.seed_url)
    # Login info (B18) is left for the team. A sign-in scan is an ordinary
    # report with no record that it signed in, so the scan cannot say.

    checks: list[str] = []
    if scan.axe_pages_scanned:
        checks.append(_CHECK_LABEL["axe"])
    if scan.alfa_pages_scanned:
        checks.append(_CHECK_LABEL["alfa"])
    for item in rows:
        label = _CHECK_LABEL.get(item.issue.pipeline)
        if label and label not in checks:
            checks.append(label)
    tools = (
        f"Axcess automated scan, WCAG {scan.wcag_version} Level {scan.axe_level}, "
        "in a Chromium browser."
    )
    if checks:
        tools += " Checks with results: " + ", ".join(checks) + "."
    tools += "\nAdd the screen readers, browsers and tools the team used for manual testing."
    _put_text(ws, "B19", tools)


def _places(rows: list[_Row]) -> list[_Place]:
    """Each place a reported element is, once, in page order, page load first."""
    seen: dict[tuple[int, str | None], _Place] = {}
    for item in rows:
        seen.setdefault((item.place.page_id, item.place.state_key), item.place)
    return sorted(seen.values(), key=lambda where: (where.page_id, where.state_key or ""))


def _fill_test_plan(
    ws: Worksheet,
    places: list[_Place],
    names: dict[tuple[int, str | None], str],
) -> None:
    """One row per place: its Test name, and its URL with the clicks to reach it.

    For a page state, "URL or location" says the clicks first and the URL
    under them, the way the team writes a location reached by clicking. The
    cell links to the page. The Description column is left for the team.
    """
    for row in range(_FIRST_PLAN_ROW, _TEMPLATE_LAST_PLAN_ROW + 1):
        for col in "ABCD":
            ws[f"{col}{row}"].value = None
    for offset, where in enumerate(places):
        row = _FIRST_PLAN_ROW + offset
        _put_text(ws, f"A{row}", names[(where.page_id, where.state_key)])
        text = (
            f"After clicking {where.click_chain}\n{where.url}" if where.click_chain else where.url
        )
        _put_link(ws, f"B{row}", text, where.url)


def _fill_findings(
    ws: Worksheet,
    rows: list[_Row],
    ref: _Reference,
    names: dict[tuple[int, str | None], str],
) -> None:
    """Write one row per reported element, starting at row 2."""
    last = max(_TEMPLATE_LAST_ISSUE_ROW, _FIRST_ISSUE_ROW + len(rows) - 1)
    criterion_names = {c.sc: c.name for c in coverage_matrix.load_matrix()}
    for row_number in range(_FIRST_ISSUE_ROW, last + 1):
        for col in "BCDEFGHI":
            ws[f"{col}{row_number}"].value = None
            ws[f"{col}{row_number}"].hyperlink = None
        ws[f"A{row_number}"].value = row_number - _FIRST_ISSUE_ROW + 1
        ws[f"J{row_number}"].value = False
        ws[f"K{row_number}"].value = _NOT_TESTED_BY_TEAM

    for r, item in enumerate(rows, start=_FIRST_ISSUE_ROW):
        row = item.issue
        sc = row.wcag_sc or ""
        _put_text(ws, f"B{r}", names[(item.place.page_id, item.place.state_key)])
        # The auditor's own notes, as saved; with none, what the problem is.
        _put_text(ws, f"C{r}", item.notes.strip() or plain_text(row.title))
        _put_text(ws, f"D{r}", ref.category.get(sc) or _EXTRA_CATEGORY.get(sc))
        _put_text(ws, f"E{r}", _criterion_text(row, ref))
        info = _info_link(row, criterion_names)
        if info:
            _put_link(ws, f"F{r}", *info)
        ws[f"G{r}"].value = _severity(row)
        why = ref.impact.get(sc) or (plain_text(row.why_matters) if row.why_matters else None)
        _put_text(ws, f"H{r}", why)
        who = ref.affects.get(sc) or ", ".join(
            _ABILITY_GROUPS[a] for a in row.abilities_affected if a in _ABILITY_GROUPS
        )
        _put_text(ws, f"I{r}", who or None)


def _fill_summary(
    ws: Worksheet,
    scan: ExportScan,
    rows: list[_Row],
    scan_date: str,
) -> None:
    """Write the Narrative Summary cell. The template's formulas are left as they are."""
    scanned = (
        f"Axcess scanned {_plural(scan.page_count, 'page', 'pages')} of {scan.seed_url} "
        f"on {scan_date}. "
    )
    if not rows:
        _put_text(
            ws,
            "A4",
            scanned + "No element has been checked and reported yet, so Findings Issues "
            "is empty. In Axcess, open an issue's pages in the inspector, and choose "
            "Checked: a problem to report for each element that is a real problem.",
        )
        return
    issue_count = len({item.issue.issue_key for item in rows})
    template_rows = _TEMPLATE_LAST_ISSUE_ROW - _FIRST_ISSUE_ROW + 1
    beyond = len(rows) - template_rows
    # The template's counts stop at its last row; say so rather than let a
    # reader trust a total that leaves rows out.
    counted = (
        f"\nThe counts below include the first {template_rows} rows only. "
        f"{_plural(beyond, 'more row is', 'more rows are')} listed on Findings Issues "
        f"after row {_TEMPLATE_LAST_ISSUE_ROW}."
        if beyond > 0
        else ""
    )
    _put_text(
        ws,
        "A4",
        scanned + "A person checked its results and reported "
        f"{_plural(len(rows), 'element', 'elements')} with "
        f"{_plural(issue_count, 'problem', 'problems')}. Findings Issues has one row for "
        "each, with the person's issue notes. Results not checked yet, and repeats of a "
        "problem already reported, are left out. Automated checks find only some "
        "accessibility problems, so test by hand as well.\n"
        "Severity is a first estimate from the automated impact rating. No issue is marked "
        "Blocker, because that depends on which tasks are core to the site, which a person "
        "must judge. Confirm each severity before you share this report." + counted,
    )


def render_its_review(scan: ExportScan, *, conn: sqlite3.Connection) -> bytes:
    """Fill the U-M ITS Technical Review template from ``scan``; return .xlsx bytes.

    ``conn`` is required: the rows are the elements a person reported in the
    page inspector, matched to the issues of the same ``issues.list_issues()``
    projection the app's Issues table shows.
    """
    source = resources.files(_TEMPLATE_PACKAGE).joinpath(*_TEMPLATE_PATH)
    wb = load_workbook(io.BytesIO(source.read_bytes()))
    ref = _read_reference(wb)

    scan_day = _scan_date(scan)
    scan_date = _human_date(scan_day)
    rows = _collect_rows(conn, scan.id)
    places = _places(rows)
    names = _test_names(places)

    _fill_coversheet(wb[_COVER], scan, scan_day, evaluation.get_evaluation(conn, scan.id), rows)
    _fill_test_plan(wb[_PLAN], places, names)
    _fill_findings(wb[_FINDINGS], rows, ref, names)
    _fill_summary(wb[_SUMMARY], scan, rows, scan_date)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
