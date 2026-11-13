"""The PDF checks and the type rules, against the seeded fixture files.

Each fixture PDF (tests/support/linked_file_pdfs.py) differs from the clean
control in one way, so each must fail exactly one check, and the control
none. These are files we wrote, so they are regression tests for the checks,
not evidence that the checks are right on real files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from support.linked_file_pdfs import build

from audit.linked_files import formats
from audit.linked_files.pdf_check import check_pdf

FILES = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "documents" / "files"


@pytest.mark.parametrize(
    ("name", "failed"),
    [
        ("clean.pdf", ()),
        ("revealed.pdf", ()),
        ("form.pdf", ()),
        ("untagged.pdf", ("not_tagged",)),
        ("offsite.pdf", ("not_tagged",)),
        ("scanned.pdf", ("no_text",)),
        ("no-title.pdf", ("no_title",)),
        ("no-language.pdf", ("no_language",)),
        ("encrypted.pdf", ("blocks_assistive_tech",)),
    ],
)
def test_each_seeded_pdf_fails_exactly_its_check(name: str, failed: tuple[str, ...]) -> None:
    result = check_pdf((FILES / name).read_bytes())
    assert result.outcome == "checked"
    assert result.failed == failed
    assert result.page_count == 1


def test_a_password_protected_pdf_is_not_checked() -> None:
    result = check_pdf((FILES / "password.pdf").read_bytes())
    assert (result.outcome, result.failed) == ("password", ())


def test_form_fields_are_detected() -> None:
    assert check_pdf((FILES / "form.pdf").read_bytes()).is_form is True
    assert check_pdf((FILES / "clean.pdf").read_bytes()).is_form is False


def test_the_committed_files_match_the_generator() -> None:
    """The hand-written files are rebuilt byte for byte (encrypted ones aside)."""
    assert (FILES / "clean.pdf").read_bytes() == build()
    assert (FILES / "untagged.pdf").read_bytes() == build(tagged=False)
    assert (FILES / "scanned.pdf").read_bytes() == build(text=False)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<html><body>Not found</body></html>",
        b"%PDF-1.7\n" + b"\x00" * 200,
        b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\ntrailer << /Root 1 0 R >>",
    ],
)
def test_untrusted_bytes_never_raise(data: bytes) -> None:
    result = check_pdf(data)
    assert result.outcome in {"not_a_pdf", "damaged"}
    assert result.failed == ()


def test_html_is_not_a_pdf() -> None:
    assert check_pdf(b"<!doctype html><title>Sign in</title>").outcome == "not_a_pdf"


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
