"""The Word and PowerPoint checks (audit.linked_files.office_check).

Files we wrote (tests/support/office_docs.py), one problem at a time:
regression tests that keep each rule doing what it did when it was measured
on real files (tests/real_pages/test_office_real_files.py). The real-file
cut-downs at the end are the markup of real files the check first got
wrong, kept so the fix stays fixed.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest
from support.office_docs import slides, word

from audit.linked_files.office_check import (
    COUNTED,
    SLIDES_CHECKS,
    WORD_CHECKS,
    check_office,
    checks_for,
    counts,
    sniff,
)
from audit.linked_files.pdf_check import ALL_CHECKS


def _failed(data: bytes, kind: str) -> tuple[str, ...]:
    result = check_office(data, kind)
    assert result.outcome == "checked", result.detail
    return result.failed


# -- what a file is ------------------------------------------------------


def test_sniff_tells_the_formats_apart_by_their_bytes() -> None:
    assert sniff(word()) == "docx"
    assert sniff(slides()) == "pptx"
    assert sniff(b"%PDF-1.7\n...") == "pdf"
    assert sniff(b"<!doctype html><html></html>") == "unknown"
    assert sniff(b"PK\x03\x04 not really a zip") == "unknown"


def test_an_excel_file_is_office_but_not_checked() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as package:
        package.writestr(
            "[Content_Types].xml",
            '<Types><Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>',
        )
    assert sniff(out.getvalue()) == "office_other"


def test_an_encrypted_office_file_is_told_from_an_old_one() -> None:
    header = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100
    assert sniff(header + "EncryptionInfo".encode("utf-16-le")) == "encrypted"
    assert sniff(header + "WordDocument".encode("utf-16-le")) == "old_office"


@pytest.mark.parametrize(
    "data",
    [b"", b"PK\x03\x04", b"%PDF", b"\x00" * 50, b"PK\x03\x04" + b"\xff" * 500],
)
def test_untrusted_bytes_never_raise(data: bytes) -> None:
    sniff(data)
    for kind in ("docx", "pptx"):
        assert check_office(data, kind).outcome == "damaged"


def test_a_zip_that_unpacks_too_large_is_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    from audit.linked_files import office_check

    monkeypatch.setattr(office_check, "MAX_UNPACKED_BYTES", 1000)
    assert check_office(word(), "docx").outcome == "damaged"


# -- which checks apply, and which count -----------------------------------


def test_each_type_gets_its_own_checks() -> None:
    assert checks_for("pdf") == ALL_CHECKS
    assert checks_for("docx") == WORD_CHECKS
    assert checks_for("pptx") == SLIDES_CHECKS
    assert checks_for(None) == ()
    assert "slide_no_title" not in WORD_CHECKS
    assert "no_headings" not in SLIDES_CHECKS


def test_only_barriers_count_and_every_pdf_check_does() -> None:
    assert {
        "no_alt_text",
        "table_no_header",
        "slide_no_title",
        "no_headings",
        "no_language",
    } == COUNTED
    assert counts("pdf", "no_title")
    assert not counts("docx", "no_title")
    assert not counts("pptx", "unclear_link_text")
    assert counts("docx", "no_alt_text")


def test_a_possible_problem_alone_leaves_a_file_not_sure() -> None:
    result = check_office(word(title="", link_text="click here"), "docx")
    assert result.failed == ("unclear_link_text", "no_title")
    assert result.status == "not_sure"


# -- Word ----------------------------------------------------------------


def test_a_clean_word_file_fails_nothing() -> None:
    assert (
        _failed(word(image="described", table="style_option", link_text="Benefits guide"), "docx")
        == ()
    )


@pytest.mark.parametrize(
    ("image", "failed"),
    [
        ("described", ()),
        ("decorative", ()),
        ("missing", ("no_alt_text",)),
        ("file_name", ("no_alt_text",)),
    ],
)
def test_word_images_need_alt_text_or_the_decorative_mark(
    image: str, failed: tuple[str, ...]
) -> None:
    assert _failed(word(image=image), "docx") == failed  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("table", "failed"),
    [
        ("style_option", ()),
        ("repeat", ()),
        ("none", ("table_no_header",)),
        ("off", ("table_no_header",)),
    ],
)
def test_word_tables_need_a_header_row(table: str, failed: tuple[str, ...]) -> None:
    """The "Header Row" style option or "Repeat as header row"; a
    ``tblHeader`` set to "0" (as Google writes on every row) is off."""
    assert _failed(word(table=table), "docx") == failed  # type: ignore[arg-type]


def test_a_long_word_file_without_headings_fails_and_a_short_one_does_not() -> None:
    assert _failed(word(headings=(), words=600), "docx") == ("no_headings",)
    assert _failed(word(headings=(), words=100), "docx") == ()


def test_skipped_heading_levels_are_a_possible_problem() -> None:
    assert _failed(word(headings=(1, 3)), "docx") == ("skipped_heading_level",)
    assert _failed(word(headings=(2, 3, 1, 2)), "docx") == ()


@pytest.mark.parametrize(
    ("text", "unclear"),
    [
        ("click here", True),
        ("Here.", True),
        ("https://hr.umich.edu/benefits", True),
        ("hr.umich.edu/retirement-savings-plans", True),
        ("www.umich.edu", True),
        ("Retirement Savings Plan enrollment guide", False),
        ("benefits@umich.edu", False),
    ],
)
def test_word_link_text_that_does_not_say_where_it_goes(text: str, unclear: bool) -> None:
    assert ("unclear_link_text" in _failed(word(link_text=text), "docx")) is unclear


def test_word_language_and_title() -> None:
    assert _failed(word(language=False), "docx") == ("no_language",)
    assert _failed(word(title=""), "docx") == ("no_title",)


# -- Word: cut-downs of real files ------------------------------------------


def _replace_part(data: bytes, name: str, change: object) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            body = source.read(info.filename)
            if change is None and name == "docProps/core.xml":
                # A file with no core properties at all, as Google exports
                # them: no part, no relationship to it, no content type.
                if info.filename == name:
                    continue
                if info.filename in {"_rels/.rels", "[Content_Types].xml"}:
                    body = re.sub(rb"<[^<>]*core[^<>]*/>", b"", body)
            if info.filename == name and callable(change):
                body = change(body)
            target.writestr(info, body)
    return out.getvalue()


def test_a_google_export_has_no_core_properties_so_no_title() -> None:
    """Google's .docx exports have no docProps/core.xml at all; python-docx
    would make up the title "Word Document" for one (real files 2026-11-17,
    e.g. the Ross IT Google Docs)."""
    data = _replace_part(word(), "docProps/core.xml", None)
    assert "no_title" in _failed(data, "docx")


def test_a_vml_fallback_copy_is_not_checked_twice() -> None:
    """Word keeps an old VML copy of a shape in ``mc:Fallback``; its picture
    has no alt of its own (a real hr.umich.edu enrollment guide)."""
    fallback = (
        b'<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        b'<mc:Choice Requires="wps"/><mc:Fallback><w:pict>'
        b'<v:shape xmlns:v="urn:schemas-microsoft-com:vml">'
        b'<v:imagedata r:id="rId99"/></v:shape></w:pict></mc:Fallback></mc:AlternateContent>'
    )

    def add(body: bytes) -> bytes:
        return body.replace(b"</w:body>", b"<w:p><w:r>" + fallback + b"</w:r></w:p></w:body>")

    assert _failed(_replace_part(word(), "word/document.xml", add), "docx") == ()


# -- PowerPoint ------------------------------------------------------------


def test_a_clean_deck_fails_nothing_and_counts_its_slides() -> None:
    result = check_office(
        slides(image="described", table="header", link_text="Benefits guide"), "pptx"
    )
    assert (result.outcome, result.failed, result.page_count) == ("checked", (), 2)


@pytest.mark.parametrize(
    ("image", "failed"),
    [
        ("described", ()),
        ("decorative", ()),
        ("missing", ("no_alt_text",)),
        ("file_name", ("no_alt_text",)),
    ],
)
def test_slide_pictures_need_alt_text_or_the_decorative_mark(
    image: str, failed: tuple[str, ...]
) -> None:
    assert _failed(slides(image=image), "pptx") == failed  # type: ignore[arg-type]


def test_every_slide_needs_a_title() -> None:
    assert _failed(slides(slide_titles=("Welcome", "")), "pptx") == ("slide_no_title",)


def test_slide_tables_need_the_header_row_option() -> None:
    assert _failed(slides(table="header"), "pptx") == ()
    assert _failed(slides(table="none"), "pptx") == ("table_no_header",)


def test_slide_language_link_text_and_title() -> None:
    assert _failed(slides(language=False), "pptx") == ("no_language",)
    assert _failed(slides(link_text="hr.umich.edu/benefits"), "pptx") == ("unclear_link_text",)
    assert _failed(slides(title=""), "pptx") == ("no_title",)
