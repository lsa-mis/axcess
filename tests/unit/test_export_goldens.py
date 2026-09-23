"""Export-equivalence goldens: every route format, as a final and as a draft.

These goldens exist so a refactor of the exporters (``audit.exports``, the
workbook renderer, ``export_readiness`` draft labeling) can be proven
output-identical rather than argued to be. Each export is rendered through
``tests/support/export_render.py``, which calls the entry points
``GET /api/scans/{id}/export/{fmt}`` calls, with the clock and base URL
pinned to the values the older goldens were recorded with.
``tests/ui/test_export_route_parity.py`` downloads the rich scan through the
route itself and checks that the two agree.

Text formats are compared byte for byte. Workbooks are compared through the
semantic fingerprint in ``tests/support/xlsx_fingerprint.py`` (values, styles,
links, layout), because an .xlsx file's bytes change on every save.

A final export is pinned in full (``rich_scan.csv``, ``rich_scan.xlsx.json``).
A draft is its final plus draft labeling, so only that difference is
committed: ``<draft golden>.diff`` (``rich_scan_DRAFT.csv.diff``) is a unified
diff from the final golden to the draft, made by
``tests/support/golden_delta.py``. A draft must equal its final golden with
that diff applied, which is exactly the draft a full copy would pin. A change
to the final output therefore fails the final golden (and the drafts built on
it); a change to draft labeling alone fails only the draft.
``patch -o - rich_scan.csv < rich_scan_DRAFT.csv.diff``, run in ``golden/``,
prints a whole draft for reading.

Two scans back the goldens:

* ``scan``, the fixture behind the existing ``scan.csv`` / ``scan.json`` /
  ``scan.jira.csv`` / ``scan.md`` goldens, imported unchanged. Its finals are
  checked against those files (read-only); its draft diffs and workbook are
  new.
* ``rich_scan``, seeded by ``tests/support/rich_scan.py``, which reaches the
  paths the small fixture does not (see that module), rendered with a blob
  store holding its evidence screenshots, as the route renders it.

``scan`` has no ``audit`` golden on purpose. The one audit-report golden
that predates this harness, ``scan_audit.md``, pins a different fixture
(``test_audit_report._scan_with_real_findings``), and a ``scan.audit.md``
beside it would read as its sibling. ``rich_scan`` pins the audit report.

Refresh the new goldens with ``AUDIT_UPDATE_GOLDEN=1`` after a deliberate
output change. Each test then writes what it rendered and fails, so an update
run never passes, and under ``CI`` it refuses to write at all. A missing
golden fails rather than being recorded, so one deleted or renamed during a
refactor cannot quietly regenerate. The pre-existing goldens are never
written from here.
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import pytest
from support.export_render import (
    EXPORT_EXTENSIONS,
    EXPORT_FORMATS,
    export_filename,
    render_export,
    render_unlabeled,
)
from support.golden_delta import DeltaError, apply_delta, make_delta
from support.rich_scan import seed_rich_scan, write_evidence_blobs
from support.xlsx_fingerprint import dumps_fingerprint, fingerprint_diff, fingerprint_xlsx
from test_exports_csv_json import scan_fixture  # noqa: F401  # fixture behind scan.csv

from audit.blob_store import BlobStore
from audit.exports import xlsx_export
from audit.web import issues

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
UPDATE_ENV = "AUDIT_UPDATE_GOLDEN"

# Formats whose final golden predates this harness. Their finals are compared
# against those files and never rewritten here.
_EXISTING_FINALS = ("csv", "json", "jira", "markdown")

# Unchanged lines a draft diff keeps around each change, so a reader can see
# where the labeling lands.
_DELTA_CONTEXT = 1
_DIFF_LINES = 60

#: Renders one export of a scan: ``render(draft)``.
Render = Callable[[bool], str | bytes]


def _updating() -> bool:
    if os.environ.get(UPDATE_ENV) != "1":
        return False
    if os.environ.get("CI"):
        pytest.fail(f"{UPDATE_ENV}=1 is set under CI; goldens are only rewritten locally.")
    return True


def _record(name: str, content: str) -> NoReturn:
    """Write a golden, then fail: an update run must never leave the suite green."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (GOLDEN_DIR / name).write_bytes(content.encode("utf-8"))
    pytest.fail(
        f"Wrote {name}. Review `git diff tests/unit/golden`, then rerun without "
        f"{UPDATE_ENV} to verify.",
        pytrace=False,
    )


def _read_golden(name: str) -> str:
    """Read bytes, not text: a bare ``\\r`` would not survive ``read_text``."""
    path = GOLDEN_DIR / name
    if not path.is_file():
        pytest.fail(
            f"Golden {name} is missing. Record it with {UPDATE_ENV}=1 only if the export "
            "is new; a golden that went missing in a refactor must be restored."
        )
    return path.read_bytes().decode("utf-8")


def _golden_text(rendered: str | bytes, export_format: str) -> str:
    """What a golden holds for an export: the text, or the workbook's fingerprint."""
    if export_format == "xlsx":
        assert isinstance(rendered, bytes)
        return dumps_fingerprint(fingerprint_xlsx(rendered))
    assert isinstance(rendered, str)
    return rendered


def _golden_name(stem: str, export_format: str, *, draft: bool) -> str:
    name = export_filename(stem, export_format, draft=draft)
    return f"{name}.json" if export_format == "xlsx" else name


def _text_diff(expected: str, actual: str, labels: tuple[str, str]) -> list[str]:
    lines = list(
        difflib.unified_diff(expected.splitlines(), actual.splitlines(), *labels, lineterm="", n=1)
    )
    if not lines:
        return [f"Same lines, different line endings ({len(expected)} vs {len(actual)} chars)."]
    if len(lines) > _DIFF_LINES:
        lines = [*lines[:_DIFF_LINES], f"... {len(lines) - _DIFF_LINES} more diff line(s)"]
    return lines


def _assert_same(
    expected: str,
    rendered: str | bytes,
    export_format: str,
    labels: tuple[str, str],
    message: str,
) -> None:
    if export_format == "xlsx":
        assert isinstance(rendered, bytes)
        # Against the fingerprint itself, not a reserialized copy, so the
        # golden's layout cannot drop anything without failing here.
        diff = fingerprint_diff(json.loads(expected), fingerprint_xlsx(rendered), labels=labels)
    else:
        assert isinstance(rendered, str)
        diff = [] if rendered == expected else _text_diff(expected, rendered, labels)
    assert not diff, f"{message} Re-run with {UPDATE_ENV}=1 if the change was deliberate.\n" + (
        "\n".join(diff)
    )


def _check_final(render: Render, stem: str, export_format: str) -> None:
    name = _golden_name(stem, export_format, draft=False)
    rendered = render(False)
    if _updating():
        _record(name, _golden_text(rendered, export_format))
    expected = _read_golden(name)
    _assert_same(expected, rendered, export_format, (name, "rendered"), f"{name} mismatch.")


def _check_draft(render: Render, stem: str, export_format: str) -> None:
    """The draft must be its final golden with the recorded draft diff applied."""
    final_name = _golden_name(stem, export_format, draft=False)
    draft_name = _golden_name(stem, export_format, draft=True)
    delta_name = f"{draft_name}.diff"
    rendered = render(True)
    if _updating():
        final = _golden_text(render(False), export_format)
        draft = _golden_text(rendered, export_format)
        delta = make_delta(
            final, draft, before_name=final_name, after_name=draft_name, context=_DELTA_CONTEXT
        )
        assert apply_delta(final, delta) == draft
        _record(delta_name, delta)
    delta = _read_golden(delta_name)
    assert not delta or delta.startswith(f"--- {final_name}\n+++ {draft_name}\n"), (
        f"{delta_name} must be a diff from {final_name} to {draft_name}."
    )
    try:
        expected = apply_delta(_read_golden(final_name), delta)
    except DeltaError as exc:
        pytest.fail(
            f"{delta_name} does not apply to {final_name}: {exc}. Record it again with "
            f"{UPDATE_ENV}=1.",
            pytrace=False,
        )
    labels = (f"{final_name} + {delta_name}", "rendered")
    message = f"{draft_name} is no longer {final_name} with {delta_name} applied."
    _assert_same(expected, rendered, export_format, labels, message)


# --------------------------------------------------------------------------
# The harness itself.
# --------------------------------------------------------------------------


def test_harness_renders_every_route_format() -> None:
    """A format added to the route must be added to the harness too."""
    from audit.web import server

    assert set(EXPORT_FORMATS) == set(server._EXPORT_RENDERERS)
    assert EXPORT_EXTENSIONS == server._EXPORT_EXTENSIONS


def test_drafts_are_pinned_only_as_diffs() -> None:
    """A full draft golden beside its diff would be read by nothing and go stale."""
    full_drafts = sorted(
        path.name for path in GOLDEN_DIR.glob("*_DRAFT.*") if path.suffix != ".diff"
    )
    assert not full_drafts, f"Draft goldens are stored as diffs; remove {full_drafts}."


# --------------------------------------------------------------------------
# The small image-pipeline scan (scan.*).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("export_format", _EXISTING_FINALS)
def test_scan_final_matches_existing_golden(
    tmp_db: sqlite3.Connection,
    scan_fixture: int,  # noqa: F811
    export_format: str,
) -> None:
    """The harness renders exactly what the older per-format goldens pin."""
    rendered = render_export(tmp_db, scan_fixture, export_format, draft=False)
    name = _golden_name("scan", export_format, draft=False)
    expected = (GOLDEN_DIR / name).read_bytes()
    assert _golden_text(rendered, export_format).encode("utf-8") == expected


@pytest.mark.parametrize(
    ("export_format", "draft"),
    [(fmt, True) for fmt in _EXISTING_FINALS] + [("xlsx", False), ("xlsx", True)],
)
def test_scan_export_matches_golden(
    tmp_db: sqlite3.Connection,
    scan_fixture: int,  # noqa: F811
    export_format: str,
    draft: bool,
) -> None:
    def render(as_draft: bool) -> str | bytes:
        return render_export(tmp_db, scan_fixture, export_format, draft=as_draft)

    check = _check_draft if draft else _check_final
    check(render, "scan", export_format)


# --------------------------------------------------------------------------
# The rich scan (rich_scan.*).
# --------------------------------------------------------------------------


@pytest.fixture
def rich_scan(tmp_db: sqlite3.Connection) -> int:
    return seed_rich_scan(tmp_db)


@pytest.fixture
def rich_blobs(tmp_path: Path) -> BlobStore:
    """The rich scan's evidence screenshots, in a blob store the route would pass."""
    return write_evidence_blobs(tmp_path / "blobs")


@pytest.mark.parametrize("draft", [False, True], ids=["final", "draft"])
@pytest.mark.parametrize("export_format", EXPORT_FORMATS)
def test_rich_scan_export_matches_golden(
    tmp_db: sqlite3.Connection,
    rich_scan: int,
    rich_blobs: BlobStore,
    export_format: str,
    draft: bool,
) -> None:
    def render(as_draft: bool) -> str | bytes:
        return render_export(
            tmp_db, rich_scan, export_format, draft=as_draft, blob_store=rich_blobs
        )

    check = _check_draft if draft else _check_final
    check(render, "rich_scan", export_format)


def test_rich_scan_reaches_the_paths_its_goldens_pin(
    tmp_db: sqlite3.Connection,
    rich_scan: int,
    rich_blobs: BlobStore,
) -> None:
    """Fail loudly if a fixture edit stops exercising a pinned path."""
    rows = issues.list_issues(tmp_db, rich_scan)
    keys = {row.issue_key for row in rows}

    # More issues than tabs: the workbook pools the rest.
    assert len(rows) > xlsx_export._MAX_ISSUE_SHEETS + 5
    rendered = render_unlabeled(tmp_db, rich_scan, "xlsx", blob_store=rich_blobs)
    assert isinstance(rendered, bytes)
    workbook = fingerprint_xlsx(rendered)
    assert "More Issues" in workbook["sheet_names"]

    # Evidence screenshots: the wide one is scaled to the evidence column,
    # the narrow one keeps its size, each row grows to fit its image, a
    # screenshot whose blob is missing leaves its tab without one, and a
    # pooled issue's screenshot is embedded nowhere. Tabs are found by the
    # rule-book titles the workbook prints.
    def issue_sheet(title: str) -> dict[str, Any]:
        return next(
            sheet
            for sheet in workbook["sheets"]
            if sheet["cells"] and str(sheet["cells"][0][1]).endswith(f" · {title}")
        )

    embedded = set()
    for title, (width, height) in {
        "Text doesn't meet the 4.5:1 contrast ratio": (240, 60),
        "The page has no top-level heading": (160, 90),
    }.items():
        sheet = issue_sheet(title)
        [image] = sheet["images"]
        assert (image["width"], image["height"]) == (width, height)
        assert sheet["rows"][image["anchor"][1:]][0] == height * 0.75
        embedded.add(image["sha256"])
    assert len(embedded) == 2
    assert issue_sheet("Links have no accessible name")["images"] == []
    pooled = next(sheet for sheet in workbook["sheets"] if sheet["title"] == "More Issues")
    assert "Keyboard users can't escape this element" in {cell[1] for cell in pooled["cells"]}
    assert sum(len(sheet["images"]) for sheet in workbook["sheets"]) == 2

    # A best-practice group, which never becomes a card, on several pages.
    heading = next(row for row in rows if row.issue_key == "axe:page-has-heading-one")
    assert heading.conformance == "BP" and heading.page_count == 3
    references = next(sheet for sheet in workbook["sheets"] if sheet["title"] == "Page References")
    heading_rows = [
        cell for cell in references["cells"] if cell[0].startswith("A") and cell[1] == heading.title
    ]
    assert len(heading_rows) == 3

    # The inline SVG is judged against its text snippet, not an empty OCR.
    assert "image:unclassified_inadequate" in keys

    # No documentation link at any level, so the issue detail's last-resort
    # help_url lookup runs. That only proves the branch executes: the list
    # row already takes help_url from the same grouped rows, so the lookup
    # cannot find anything the row lacks and no golden can observe it.
    detail = issues.get_issue_detail(tmp_db, rich_scan, "axe:fixture-empty-help")
    assert detail is not None and detail.help_url is None

    # Manual evidence with no page and no external reference prints the
    # audit report's placeholders.
    audit = render_unlabeled(tmp_db, rich_scan, "audit")
    assert isinstance(audit, str)
    assert "| 2.4.7 | n/a | n/a | Checked with the keyboard only. |" in audit

    # A bare carriage return survives in a quoted CSV field (the flat CSV
    # carries alt text verbatim), and draft labeling keeps both CSV exports
    # rectangular without splitting a record.
    for export_format in ("csv", "jira"):
        final = render_export(tmp_db, rich_scan, export_format, draft=False)
        draft = render_export(tmp_db, rich_scan, export_format, draft=True)
        assert isinstance(final, str) and isinstance(draft, str)
        final_rows = list(csv.reader(io.StringIO(final, newline="")))
        draft_rows = list(csv.reader(io.StringIO(draft, newline="")))
        if export_format == "csv":
            assert "Company\rlogo" in {field for row in final_rows for field in row}
        assert [row[:-1] for row in draft_rows] == final_rows
        assert {len(row) for row in draft_rows} == {len(final_rows[0]) + 1}
