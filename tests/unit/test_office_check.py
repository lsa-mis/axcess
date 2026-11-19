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


def test_no_headings_needs_lines_that_look_like_headings() -> None:
    """WCAG 1.3.1: headings a reader can see must be marked as headings. A
    long document with no heading style and no visible parts fails nothing."""
    assert _failed(word(headings=(), words=600), "docx") == ()
    looks_like = _word_lines(
        [("Benefits", "bold"), BODY, ("Costs", "bold"), BODY, ("Contacts", "bold"), BODY]
    )
    assert _failed(looks_like, "docx") == ("no_headings",)
    styled = _word_lines(
        [("Benefits", "Heading 1"), BODY, ("Costs", "bold"), BODY, ("Contacts", "bold"), BODY]
    )
    assert _failed(styled, "docx") == ()


@pytest.mark.parametrize("look", ["bold", "underline", "capitals", "large", "all caps text"])
def test_a_heading_can_stand_out_in_several_ways(look: str) -> None:
    text = "PART ONE" if look == "all caps text" else "Part one"
    lines = [(text, look), BODY, (text.replace("ONE", "TWO").replace("one", "two"), look), BODY]
    assert _failed(_word_lines(lines), "docx") == ("no_headings",)


def test_a_bold_line_with_no_text_under_it_is_not_a_heading() -> None:
    """A form's bold labels ("Name:", "Date:") each followed by a short
    field are labels, not the start of a part."""
    lines = [(label, "bold") for label in ("Name:", "Date:", "Department:", "Signature:")]
    assert _failed(_word_lines([*lines, BODY]), "docx") == ()


def test_word_tables_that_are_not_plain_grids_are_not_counted() -> None:
    """A table with merged cells or another table inside it is how Word
    lays out a form or a page; only a plain grid is read as a data table."""
    assert _failed(word(table="none", table_shape="merged_row"), "docx") == ()
    assert _failed(word(table="none", table_shape="merged_column"), "docx") == ()
    assert _failed(word(table="none", table_shape="nested"), "docx") == ()


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


#: Body text under a heading: more than the 20 words a heading needs under it.
BODY = (" ".join(["text"] * 30), "plain")


def _word_lines(lines: list[tuple[str, str]], *, title: str = "") -> bytes:
    """A Word file of paragraphs, each (text, look): "plain", "bold",
    "underline", "capitals" (the All caps font option), "large" (16 pt
    against 11 pt body text), "all caps text" (plain, typed in capitals),
    "list" (a numbered list item), or a paragraph style's name."""
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.core_properties.title = "Real file cut-down"
    if title:
        document.add_paragraph(title, style="Title")
    for text, look in lines:
        style = {"list": "List Number"}.get(look, look if look[0].isupper() else None)
        paragraph = document.add_paragraph(style=style)
        run = paragraph.add_run(text)
        run.bold = look == "bold" or None
        run.underline = look == "underline" or None
        run.font.all_caps = look == "capitals" or None
        run.font.size = Pt(16) if look == "large" else Pt(11)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def test_a_meeting_transcript_with_one_title_line_has_no_visible_parts() -> None:
    """section508.gov's IT Accessibility Community Meeting transcripts
    (2026-11-18): a Title line, a "--- BEGIN CAPTIONED TEXT ---" marker,
    then hundreds of speaker turns. Nothing to move between, so no barrier,
    whatever its length."""
    turns = [(f">> SPEAKER {n}: " + " ".join(["said"] * 40), "plain") for n in range(40)]
    lines = [("--- BEGIN CAPTIONED TEXT ---", "plain"), *turns, ("[LAUGHTER]", "plain"), BODY]
    data = _word_lines(lines, title="June 2023 IT Accessibility Community Meeting Captioned Text")
    assert _failed(data, "docx") == ()


def test_a_one_part_form_of_numbered_questions_has_no_visible_parts() -> None:
    """NIH's SBIR and STTR certification forms (grants.nih.gov, 2026-11-18):
    a Title line, then numbered statements, each with Yes and No."""
    questions = [
        ("The small business concern meets the requirements " + "of the program " * 6, "list"),
        ("Yes  No", "plain"),
    ] * 20
    data = _word_lines(questions, title="SBIR Funding Agreement Certification")
    assert _failed(data, "docx") == ()


def test_a_policy_with_underlined_section_names_fails_no_headings() -> None:
    """A finance.umich.edu tax policy (2026-11-17): its sections are
    underlined lines such as "B. Bereavement", with no heading style."""
    lines = [
        ("Policy on Taxation of Gifts, Prizes and Awards to Employees", "bold"),
        BODY,
        ("B. Bereavement", "underline"),
        BODY,
        ("D. Length of Service Award", "underline"),
        BODY,
    ]
    assert _failed(_word_lines(lines), "docx") == ("no_headings",)


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
    assert _failed(slides(table="merged"), "pptx") == ()


@pytest.mark.parametrize("alt", ['"  "', "  ", "-", "\u201c \u201d"])
def test_alt_text_of_only_spaces_and_marks_is_none(alt: str) -> None:
    """section508.gov's PowerPoint 2016 guide (2026-11-18) gives 12
    screenshots the alt text '"  "': a screen reader has nothing to say."""
    assert _failed(slides(image="described", alt=alt), "pptx") == ("no_alt_text",)
    assert _failed(word(image="described", alt=alt), "docx") == ("no_alt_text",)


def test_slide_language_link_text_and_title() -> None:
    assert _failed(slides(language=False), "pptx") == ("no_language",)
    assert _failed(slides(link_text="hr.umich.edu/benefits"), "pptx") == ("unclear_link_text",)
    assert _failed(slides(title=""), "pptx") == ("no_title",)
