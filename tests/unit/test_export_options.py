"""The Export panel's file facts: names and sizes of what a download delivers."""

from __future__ import annotations

import pytest

from audit.web.export_options import (
    PANEL_FORMATS,
    build_export_options,
    encoded_size,
)
from audit.web.export_readiness import PublicExportReadiness

_EXTENSIONS = {
    "csv": "csv",
    "json": "json",
    "jira": "jira.csv",
    "markdown": "md",
    "audit": "audit.md",
    "xlsx": "xlsx",
    "its": "its.xlsx",
    "brief": "fix-brief.md",
}


def test_text_is_measured_in_the_utf8_bytes_the_route_sends() -> None:
    # "é" and "…" are 2 and 3 bytes in UTF-8; counting characters would
    # understate every export that quotes non-ASCII page text.
    assert encoded_size("é…") == 5
    assert encoded_size(b"\x00\x01\x02") == 3


@pytest.mark.parametrize(
    ("is_draft", "suffix"),
    [(True, "_DRAFT"), (False, "")],
)
def test_each_panel_format_is_named_and_sized_as_rendered(is_draft: bool, suffix: str) -> None:
    rendered: dict[str, str | bytes] = {
        "xlsx": b"PK" + b"\x00" * 98,
        "its": b"PK" + b"\x00" * 48,
        "audit": "# Report\n",
        "brief": "# Brief\n",
        "csv": "a,b\n1,é\n",
        "json": "{}",
    }
    asked: list[str] = []

    def render(export_format: str) -> str | bytes:
        asked.append(export_format)
        return rendered[export_format]

    readiness = PublicExportReadiness(evaluation_status="in_progress", is_draft=is_draft)
    options = build_export_options(
        12, readiness, extensions=_EXTENSIONS, render=render, always_redacted={"brief"}
    )

    # Only what the panel offers is rendered: Jira CSV and plain Markdown
    # would cost a render each for a size nobody sees.
    assert asked == list(PANEL_FORMATS)
    assert options.scan_id == 12
    assert options.draft is is_draft
    assert options.evaluation_status == "in_progress"
    assert [(o.format, o.filename, o.size_bytes) for o in options.formats] == [
        ("xlsx", f"scan_12{suffix}.xlsx", 100),
        ("its", f"scan_12{suffix}.its.xlsx", 50),
        ("audit", f"scan_12{suffix}.audit.md", 9),
        # The fix brief is always the redacted copy, and named so.
        ("brief", f"scan_12{suffix}_REDACTED.fix-brief.md", 8),
        ("csv", f"scan_12{suffix}.csv", 9),
        ("json", f"scan_12{suffix}.json", 2),
    ]


def test_a_format_the_route_would_refuse_is_left_out() -> None:
    """A fix brief of a report that is not complete has no size to show."""
    readiness = PublicExportReadiness(evaluation_status="draft", is_draft=True)

    options = build_export_options(
        3,
        readiness,
        extensions=_EXTENSIONS,
        render=lambda export_format: "x",
        unavailable={"brief"},
    )

    assert [option.format for option in options.formats] == ["xlsx", "its", "audit", "csv", "json"]
