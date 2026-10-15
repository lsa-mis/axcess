"""The U-M ITS technical review: the team's own template, filled in from one scan."""

from __future__ import annotations

import io
import sqlite3
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from support.rich_scan import dom_finding, seed_rich_scan
from test_audit_report import _scan_with_real_findings  # tests/unit on sys.path
from typer.testing import CliRunner

from audit import cli
from audit.config import Settings
from audit.db import repo
from audit.exports.audit_report import issue_locations
from audit.exports.collector import collect_scan
from audit.exports.its_review import render_its_review
from audit.web import issues

_HEADERS = {
    "A": "number",
    "B": "test",
    "C": "notes",
    "D": "category",
    "E": "criterion",
    "F": "info",
    "G": "severity",
    "H": "impact",
    "I": "affects",
    "J": "vendor_ready",
    "K": "verified",
}
_SEVERITIES = {"4  Critical", "3  Major", "2  Minor", "1  Best practice"}


def _template() -> Workbook:
    source = resources.files("audit.exports").joinpath("templates", "its_technical_review.xlsx")
    return load_workbook(io.BytesIO(source.read_bytes()))


def _render(conn: sqlite3.Connection, scan_id: int) -> Workbook:
    out = render_its_review(collect_scan(conn, scan_id), conn=conn)
    return load_workbook(io.BytesIO(out))


def _issue_rows(wb: Workbook) -> list[dict[str, Any]]:
    ws = wb["Findings Issues"]
    rows = []
    for r in range(2, ws.max_row + 1):
        if ws[f"G{r}"].value is None:
            continue
        row = {key: ws[f"{col}{r}"].value for col, key in _HEADERS.items()}
        row["info_link"] = ws[f"F{r}"].hyperlink.target if ws[f"F{r}"].hyperlink else None
        rows.append(row)
    return rows


def _all_text(wb: Workbook) -> str:
    return "\n".join(
        str(cell.value)
        for ws in wb.worksheets
        for row in ws.iter_rows()
        for cell in row
        if cell.value is not None
    )


def _occurrence_count(conn: sqlite3.Connection, scan_id: int) -> int:
    """Occurrences the form should list: not "For information", not "Not a problem"."""
    return sum(
        1
        for row in issues.list_issues(conn, scan_id)
        if row.review_lane != "informational"
        for loc in issue_locations(conn, row, limit=None)[0]
        if loc.status != "false_positive"
    )


def test_keeps_the_templates_sheets_and_reference_tables(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    wb = _render(tmp_db, scan_id)
    template = _template()

    assert wb.sheetnames == template.sheetnames
    for name in ("Reference", "Reference Impact"):
        got = [[c.value for c in row] for row in wb[name].iter_rows()]
        want = [[c.value for c in row] for row in template[name].iter_rows()]
        assert got == want, f"{name} must stay exactly as the ITS team wrote it"
    # The dropdowns still read the template's named lists.
    for name in ("Severity", "GenericTestList", "TextAlternatives"):
        assert name in wb.defined_names


def test_an_issue_row_uses_the_templates_own_words(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    wb = _render(tmp_db, scan_id)
    impact = {
        str(a).split(" ")[0]: (b, c)
        for a, b, c in _template()["Reference Impact"].iter_rows(max_col=3, values_only=True)
    }

    # The template's own spelling, with an en dash.
    criterion = "1.4.3 \u2013 Contrast (Minimum)"
    contrast = [r for r in _issue_rows(wb) if r["criterion"] == criterion]
    # Four occurrences, one marked "Not a problem": three rows, side by side.
    assert len(contrast) == 3
    assert [r["number"] for r in contrast] == list(
        range(contrast[0]["number"], contrast[0]["number"] + 3)
    )
    for row in contrast:
        assert row["category"] == "Contrast"
        assert row["severity"] == "3  Major"  # axe "serious"
        assert (row["affects"], row["impact"]) == impact["1.4.3"]
        assert row["info"] == "1.4.3 Info"
        assert row["info_link"] == (
            "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html"
        )
        assert row["vendor_ready"] is False
        assert row["verified"] == "Not tested by UM A11y team"
        assert row["notes"].startswith("April 22, 2026, Axcess scan: ")
        assert "Found by: Rule check (axe)." in row["notes"]
    assert [r["test"] for r in contrast] == ["Home", "Home", "About us"]
    first, second, third = (r["notes"] for r in contrast)
    assert "(occurrence 1 of 3)" in first
    assert "Element locator (CSS selector): p > span.muted" in first
    assert "Page: Home: https://example.org/" in first
    assert "Element locator (CSS selector): footer small" in second
    assert 'To see it, first open "Show more".' in third
    assert "label.hint" not in "".join((first, second, third))  # Not a problem

    # A criterion the ITS list does not have (AAA) still gets a category.
    (enhanced,) = [r for r in _issue_rows(wb) if str(r["criterion"]).startswith("1.4.6")]
    assert enhanced["category"] == "Contrast"


def test_lists_barriers_only(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    page = repo.upsert_page(
        tmp_db,
        scan_id=scan_id,
        url_normalized="https://example.org/rejected",
        status_code=200,
        title="Rejected",
        render_mode="js",
        html_hash="9" * 64,
    )
    dom_finding(
        tmp_db,
        scan_id=scan_id,
        page_id=page,
        rule_id="only-rejected-rule",
        help_text="Only rejected occurrences",
        target="#rejected",
        impact="serious",
        wcag_sc="1.3.1",
        wcag_level="A",
        status="false_positive",
    )
    wb = _render(tmp_db, scan_id)
    rows = _issue_rows(wb)

    assert len(rows) == _occurrence_count(tmp_db, scan_id)
    assert [r["number"] for r in rows] == list(range(1, len(rows) + 1))
    assert "Only rejected occurrences" not in _all_text(wb)


def test_each_row_is_one_occurrence(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    rows = _issue_rows(_render(tmp_db, scan_id))

    for row in rows:
        notes = row["notes"]
        assert notes.count("\nPage: ") == 1, notes
        assert notes.count("Element locator (CSS selector):") + notes.count("\nImage: ") <= 1
    # Twelve links without text on one page: twelve rows, not one.
    links = [r for r in rows if "nav > a:nth-child(" in r["notes"]]
    assert len(links) == 12
    assert "(occurrence 12 of 12)" in links[-1]["notes"]


def test_severity_is_conservative(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    rows = _issue_rows(_render(tmp_db, scan_id))

    # Blocker needs a person's judgement of which tasks are core.
    assert {r["severity"] for r in rows} <= _SEVERITIES
    for row in rows:
        if row["criterion"] == "No WCAG criterion (best practice)":
            assert row["severity"] == "1  Best practice"
            assert row["category"] is None


def test_every_test_is_a_test_plan_entry(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    wb = _render(tmp_db, scan_id)
    plan = wb["Test Plan"]
    tests = [plan[f"A{r}"].value for r in range(5, plan.max_row + 1) if plan[f"A{r}"].value]
    pages = tmp_db.execute("SELECT COUNT(*) FROM pages WHERE scan_id = ?", (scan_id,)).fetchone()

    # One Test per scanned page, and every row's Test is the page it is on.
    assert tests[:2] == ["Home", "About us"]
    assert len(tests) == pages[0]
    assert len(set(tests)) == len(tests)
    assert {r["test"] for r in _issue_rows(wb)} <= set(tests)
    # The Description column is the team's to write.
    assert all(plan[f"C{r}"].value is None for r in range(5, plan.max_row + 1))
    assert wb.defined_names["GenericTestList"].attr_text == "'Test Plan'!$A$5:$A$138"


def test_scan_text_never_becomes_a_formula(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    hostile = '=HYPERLINK("https://attacker.example","Open")'
    page = repo.upsert_page(
        tmp_db,
        scan_id=scan_id,
        url_normalized="https://example.org/hostile",
        status_code=200,
        title=hostile,
        render_mode="js",
        html_hash="8" * 64,
    )
    dom_finding(
        tmp_db,
        scan_id=scan_id,
        page_id=page,
        rule_id="hostile-rule",
        help_text="Hostile page",
        target="=1+1",
        impact="minor",
        wcag_sc="1.3.1",
        wcag_level="A",
    )
    wb = _render(tmp_db, scan_id)

    cells = [
        cell
        for ws in (wb["Test Plan"], wb["Findings Issues"])
        for row in ws.iter_rows()
        for cell in row
        if isinstance(cell.value, str) and "attacker.example" in cell.value
    ]
    assert cells, "the hostile title should be listed"
    assert all(cell.data_type == "s" for cell in cells)
    # Listed in the Test Plan and as the issue's Test, both times as text.
    assert {c.value for c in cells if c.value.startswith("=")} == {hostile}


def _style(cell: Any) -> tuple[Any, ...]:
    return (
        repr(cell.font),
        repr(cell.fill),
        repr(cell.border),
        repr(cell.alignment),
        repr(cell.protection),
        cell.number_format,
    )


def test_template_structure_is_unchanged(tmp_db: sqlite3.Connection) -> None:
    """Only data cells change: formulas, lists, names and styles stay as supplied.

    The baseline is the template after one openpyxl load and save, so the
    comparison sees what this exporter changed, not openpyxl's own rewrite.
    That rewrite only normalizes defaults (``shrinkToFit=0`` is dropped) and
    leaves out parts that are empty in the template: six blank drawings and
    an empty list of people.
    """
    scan_id = seed_rich_scan(tmp_db)
    wb = _render(tmp_db, scan_id)
    buf = io.BytesIO()
    _template().save(buf)
    template = load_workbook(io.BytesIO(buf.getvalue()))

    assert {n: d.attr_text for n, d in wb.defined_names.items()} == {
        n: d.attr_text for n, d in template.defined_names.items()
    }
    for name in template.sheetnames:
        got, want = wb[name], template[name]
        assert [
            (str(v.sqref), v.type, v.formula1) for v in got.data_validations.dataValidation
        ] == [(str(v.sqref), v.type, v.formula1) for v in want.data_validations.dataValidation], (
            name
        )
        assert {str(r) for r in got.merged_cells.ranges} == {
            str(r) for r in want.merged_cells.ranges
        }, name
        assert {k: v.width for k, v in got.column_dimensions.items()} == {
            k: v.width for k, v in want.column_dimensions.items()
        }, name
        assert got.freeze_panes == want.freeze_panes, name
        for row in want.iter_rows():
            for cell in row:
                mine = got[cell.coordinate]
                assert _style(mine) == _style(cell), f"{name}!{cell.coordinate} style"
                if cell.data_type == "f":
                    assert mine.value == cell.value, f"{name}!{cell.coordinate} formula"
    # The template's example value is kept, too.
    assert wb["Coversheet"]["B5"].value == template["Coversheet"]["B5"].value


def test_summary_says_when_its_counts_miss_rows(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    count = _occurrence_count(tmp_db, scan_id)
    assert count > 48, "the fixture must outgrow the template's 48 rows"
    wb = _render(tmp_db, scan_id)
    narrative = str(wb["Summary"]["A4"].value)

    # Every occurrence is still listed, past the template's last row.
    assert len(_issue_rows(wb)) == count
    assert f"one row for each place an issue appears (an occurrence): {count} rows" in narrative
    assert "The counts below include the first 48 rows only." in narrative
    assert f"{count - 48:,} more rows are listed" in narrative
    assert "Blocker" in narrative


def test_coversheet_says_only_what_the_scan_knows(tmp_db: sqlite3.Connection) -> None:
    scan_id = seed_rich_scan(tmp_db)
    cover = _render(tmp_db, scan_id)["Coversheet"]

    assert cover["B3"].value == datetime(2026, 4, 22)
    # Tester(s) is the team's to fill, even when the evaluation names a reviewer.
    assert cover["B4"].value == _template()["Coversheet"]["B4"].value
    assert cover["B8"].value == "example.org"
    assert cover["B17"].value == "https://example.org/"
    assert cover["B17"].hyperlink.target == "https://example.org/"
    # A sign-in scan is not recorded as one, so Login info is the team's to fill.
    assert cover["B18"].value == _template()["Coversheet"]["B18"].value
    assert "Rule check (axe)" in cover["B19"].value


def test_coversheet_keeps_the_prompts_a_person_must_answer(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan_with_real_findings(tmp_db)
    cover = _render(tmp_db, scan_id)["Coversheet"]
    template = _template()["Coversheet"]

    for cell in ("B4", "B9", "B10", "B11", "B12", "B13"):
        assert cover[cell].value == template[cell].value


def test_never_reads_another_scan(tmp_db: sqlite3.Connection) -> None:
    scan_a = seed_rich_scan(tmp_db)
    scan_b = seed_rich_scan(tmp_db)
    page = repo.upsert_page(
        tmp_db,
        scan_id=scan_b,
        url_normalized="https://example.org/only-in-b",
        status_code=200,
        title="Only in scan B",
        render_mode="js",
        html_hash="7" * 64,
    )
    dom_finding(
        tmp_db,
        scan_id=scan_b,
        page_id=page,
        rule_id="only-in-b",
        help_text="Only in scan B",
        target="#b",
        impact="critical",
        wcag_sc="1.3.1",
        wcag_level="A",
    )
    wb = _render(tmp_db, scan_a)

    assert "Only in scan B" not in _all_text(wb)
    assert "only-in-b" not in _all_text(wb)
    assert len(_issue_rows(wb)) == _occurrence_count(tmp_db, scan_a)


def test_cli_writes_the_its_review(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan_id = seed_rich_scan(tmp_db)
    tmp_db.commit()
    db_path = Path(str(tmp_db.execute("PRAGMA database_list").fetchone()[2]))
    data_dir = tmp_path / "data"
    settings = Settings(
        data_dir=data_dir, db_path=db_path, blob_dir=data_dir / "blobs", log_dir=data_dir / "logs"
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    result = CliRunner().invoke(cli.app, ["export", str(scan_id), "--format", "its"])

    assert result.exit_code == 0, result.output
    written = data_dir / "exports" / f"scan_{scan_id}.its.xlsx"
    assert load_workbook(written).sheetnames == _template().sheetnames
