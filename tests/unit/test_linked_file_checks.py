"""The type rules for linked files."""

from __future__ import annotations

import pytest

from audit.linked_files import formats


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.org/files/Report.PDF", "pdf"),
        ("https://example.org/files/report.pdf?version=2", "pdf"),
        ("https://example.org/a.docx", "docx"),
        ("https://example.org/a.doc", "doc"),
        ("https://example.org/a.pptx", "pptx"),
        ("https://example.org/a.ppt", "ppt"),
        ("https://example.org/a.xlsx", "xlsx"),
        ("https://example.org/a.xls", "xls"),
        ("https://example.org/a.odt", "odt"),
        ("https://example.org/a.odp", "odp"),
        ("https://example.org/a.ods", "ods"),
        ("https://example.org/a.rtf", "rtf"),
        ("https://docs.google.com/document/d/abc/edit", "google_doc"),
        ("https://docs.google.com/a/example.edu/spreadsheets/d/abc/edit", "google_sheet"),
        ("https://docs.google.com/presentation/d/abc/edit", "google_slides"),
        ("https://drive.google.com/file/d/abc/view", "google_drive"),
        ("https://drive.google.com/open?id=abc", "google_drive"),
        ("https://docs.google.com/forms/d/abc/viewform", None),
        ("https://example.org/download.php?file=report.pdf", None),
        ("https://example.org/about", None),
        ("https://example.org/page.html", None),
        ("https://example.org/.pdf", None),
        ("mailto:someone@example.org", None),
        ("ftp://example.org/report.pdf", None),
    ],
)
def test_classify_url(url: str, expected: str | None) -> None:
    assert formats.classify_url(url) == expected


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("application/pdf", "pdf"),
        ("Application/PDF; charset=binary", "pdf"),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
        ("application/msword", "doc"),
        ("text/html; charset=utf-8", None),
        ("", None),
        (None, None),
    ],
)
def test_classify_content_type(content_type: str | None, expected: str | None) -> None:
    assert formats.classify_content_type(content_type) == expected


@pytest.mark.parametrize(
    ("file_type", "status", "reason"),
    [
        ("pdf", "pending", None),
        ("docx", "could_not_check", "type_not_checked_yet"),
        ("pptx", "could_not_check", "type_not_checked_yet"),
        ("xlsx", "could_not_check", "type_not_checked_yet"),
        ("odt", "could_not_check", "type_not_checked_yet"),
        ("odp", "could_not_check", "type_not_checked_yet"),
        ("ods", "could_not_check", "type_not_checked_yet"),
        ("rtf", "could_not_check", "type_not_checked_yet"),
        ("doc", "could_not_check", "old_format"),
        ("xls", "could_not_check", "old_format"),
        ("ppt", "could_not_check", "old_format"),
        ("google_doc", "could_not_check", "google_file"),
        ("google_sheet", "could_not_check", "google_file"),
        ("google_slides", "could_not_check", "google_file"),
        ("google_drive", "could_not_check", "google_file"),
    ],
)
def test_initial_status_by_type(
    file_type: formats.FileType, status: str, reason: str | None
) -> None:
    assert formats.initial_status(file_type) == (status, reason)
