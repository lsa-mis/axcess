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
    # The checks that count come first in the report.
    for order in (WORD_CHECKS, SLIDES_CHECKS):
        tiers = [check in COUNTED for check in order]
        assert tiers == sorted(tiers, reverse=True)


def test_only_barriers_count_and_every_pdf_check_does() -> None:
    """The two tiers (the developer's decision, 2026-11-20): only the checks
    with no false alarm on the fresh real files count."""
    assert {"no_alt_text", "slide_no_title", "no_language"} == COUNTED
    assert not counts("docx", "table_no_header")
    assert not counts("docx", "no_headings")
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


def test_no_headings_lists_a_bold_line_when_no_heading_style_is_used() -> None:
    """The developer's rule (2026-11-20): no heading style, and a bold line
    that is its own paragraph of at most one sentence, is listed as a
    possible problem. A long document with no bold line is not."""
    assert _failed(word(headings=(), words=600), "docx") == ()
    assert _failed(_word_lines([("Benefits", "bold"), BODY]), "docx") == ("no_headings",)
    styled = _word_lines([("Benefits", "Heading 1"), BODY, ("Costs", "bold"), BODY])
    assert _failed(styled, "docx") == ()


@pytest.mark.parametrize(
    ("look", "failed"),
    [
        ("bold", ("no_headings",)),
        ("underline", ()),
        ("large", ()),
        ("capitals", ()),
        ("all caps text", ()),
    ],
)
def test_only_bold_makes_a_line_look_like_a_heading(look: str, failed: tuple[str, ...]) -> None:
    lines = [line for name in ("Part one", "Part two") for line in ((name, look), BODY)]
    assert _failed(_word_lines(lines), "docx") == failed


def test_no_headings_and_tables_are_possible_problems_only() -> None:
    """Since 2026-11-20 neither makes a file "Mostly sure"."""
    for data in (_word_lines([("Benefits", "bold"), BODY]), word(table="none")):
        result = check_office(data, "docx")
        assert result.failed in {("no_headings",), ("table_no_header",)}
        assert result.status == "not_sure"


def test_a_bold_title_style_line_is_not_listed() -> None:
    """Word's Title and Subtitle styles name the document; they are not
    headings a screen reader user would move between."""
    assert _failed(_word_lines([("Annual report", "bold Title"), BODY]), "docx") == ()
    assert _failed(_word_lines([("Fiscal year 2026", "bold Subtitle"), BODY]), "docx") == ()


def test_a_bold_line_in_a_text_box_is_not_listed() -> None:
    """A text box is a sidebar or callout, read apart from the body."""
    box = (
        b'<w:p><w:r><w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml"><v:textbox>'
        b"<w:txbxContent><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Did you know?</w:t></w:r></w:p>"
        b"</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
    )

    def add(body: bytes) -> bytes:
        return body.replace(b"<w:sectPr", box + b"<w:sectPr", 1)

    data = _replace_part(_word_lines([BODY]), "word/document.xml", add)
    assert _failed(data, "docx") == ()


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


#: A paragraph of body text.
BODY = (" ".join(["text"] * 45), "plain")


def _word_lines(lines: list[tuple[str, str]], *, title: str = "") -> bytes:
    """A Word file of paragraphs, each (text, look): "plain", "bold",
    "underline", "capitals" (the All caps font option), "large" (16 pt
    against 11 pt body text), "all caps text" (plain, typed in capitals),
    "list" (a numbered list item), "run-in" (the words before the first
    "|" bold, the rest plain, in one paragraph), "bold cell" (a bold line
    in the first cell of a one-row, two-column table), "bold " and a
    paragraph style's name (bold text in that style), or a paragraph
    style's name."""
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.core_properties.title = "Real file cut-down"
    if title:
        document.add_paragraph(title, style="Title")
    for text, look in lines:
        if look == "bold cell":
            document.add_table(rows=1, cols=2).cell(0, 0).paragraphs[0].add_run(text).bold = True
            continue
        bold = look == "bold" or look.startswith("bold ")
        look = look.removeprefix("bold ")
        style = {"list": "List Number"}.get(look, look if look[0].isupper() else None)
        paragraph = document.add_paragraph(style=style)
        if look == "run-in":
            lead, rest = text.split("|", 1)
            paragraph.add_run(lead).bold = True
            paragraph.add_run(rest)
            continue
        run = paragraph.add_run(text)
        run.bold = bold or None
        run.underline = look == "underline" or None
        run.font.all_caps = look == "capitals" or None
        run.font.size = Pt(16) if look == "large" else Pt(11)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _words(n: int, word: str = "text") -> str:
    return " ".join([word] * n)


def test_a_meeting_transcript_with_one_title_line_has_no_visible_parts() -> None:
    """section508.gov's IT Accessibility Community Meeting transcripts
    (2026-11-18): a Title line, a "--- BEGIN CAPTIONED TEXT ---" marker,
    then hundreds of speaker turns, none bold. Nothing to list."""
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


def test_a_checklist_with_bold_part_names_lists_no_headings() -> None:
    """deq.nc.gov's CDBG-I inspection checklist (fresh2, labelled a
    barrier): no heading style; "Construction Site", "Construction Records",
    "Schedule" and "Additional Observation Notes" are bold paragraphs of
    their own over the checklist items. Its bold field labels ("Owner:",
    "Grant No.:") are in a table and are not what lists it."""
    lines = [
        ("Owner:", "bold cell"),
        ("Grant No.:", "bold cell"),
        ("Construction Site", "bold"),
        *[(_words(9), "list")] * 4,
        ("Construction Records", "bold"),
        *[(_words(7), "list")] * 3,
        ("Schedule", "bold"),
        (_words(12), "list"),
        ("Additional Observation Notes", "bold"),
    ]
    assert _failed(_word_lines(lines), "docx") == ("no_headings",)
    in_cells_only = _word_lines([*lines[:2], (_words(30), "plain")])
    assert _failed(in_cells_only, "docx") == ()


def test_bold_words_that_start_a_paragraph_are_not_a_line_of_their_own() -> None:
    """hyannislonghorns.org's policy 5054 Student Bullying (first fresh
    set, disputed): each section name is bold words at the start of a
    paragraph of plain text ("Bullying Prohibited.  Students are
    prohibited..."). Bold inside a paragraph is not a line of its own. (The
    real file is listed for its bold "5054" and "Student Bullying" lines.)"""
    lines = [
        ("Bullying Prohibited.|  Students are prohibited from " + _words(30, "bullying"), "run-in"),
        ("Disciplinary Consequences.|  The disciplinary " + _words(30, "consequence"), "run-in"),
        ("Policy Review.|  The school district shall review this policy annually.", "run-in"),
    ]
    assert _failed(_word_lines(lines), "docx") == ()


def test_a_bold_instruction_of_two_sentences_is_not_listed() -> None:
    """hr.umich.edu's professional development application (development
    set): bold instructions such as "Please describe your proposed
    professional development activity. The proposal should specify ..." are
    two sentences, an instruction rather than a part's name. (The real file
    is listed for its one-sentence bold line "Program/Department
    Verification ...".)"""
    lines = [
        (
            "Please describe your proposed professional development activity. "
            "The proposal should specify the goals of the activity.",
            "bold",
        ),
        (_words(40), "plain"),
        (
            "Please provide an itemized budget in the space below. "
            "Please see https://www.gsa.gov/ for travel rates.",
            "bold",
        ),
        (_words(10), "plain"),
    ]
    assert _failed(_word_lines(lines), "docx") == ()
    one_sentence = [("Program/Department Verification (to be completed by the Chair)", "bold")]
    assert _failed(_word_lines([*one_sentence, *lines]), "docx") == ("no_headings",)


def test_bold_course_names_in_table_cells_are_not_listed() -> None:
    """A math course list, a Google Doc linked from a U-M site (development
    set, labelled a barrier): each course is a table whose first cell holds its
    bold name ("Math 500. Responsible Conduct of Research and Scholarship
    in Math"). Lines in tables are not read, so this is a known miss: 4 of
    the development set's barrier files and 3 fresh ones show their part
    names only in table cells (docs/internal/office-check-research.md, "Two
    tiers")."""
    names = (
        "Math 500. Responsible Conduct of Research and Scholarship in Math",
        "Math 501. AIM Student Seminar",
        "Math 506. Stochastic Analysis for Finance",
    )
    lines = [line for name in names for line in ((name, "bold cell"), (_words(30), "plain"))]
    assert _failed(_word_lines(lines), "docx") == ()


def test_a_file_with_heading_styles_is_not_listed_for_its_bold_lines() -> None:
    """section508.gov's Accessibility in Procurement Guide (development
    set, no barrier): Heading 1 to 3 for its parts, and bold lines of
    its own above them: a date line and a list of parts with page numbers
    ("Purpose1", "Compliance2"). A document that
    uses heading styles is not listed, whatever else is bold."""
    lines = [
        ("iteration 2 (November 2, 2023)", "bold"),
        ("Purpose 1", "bold"),
        ("Compliance 2", "bold"),
        ("Accessibility in Procurement Guide", "Heading 1"),
        ("Purpose", "Heading 2"),
        BODY,
        ("Compliance", "Heading 2"),
        BODY,
    ]
    assert _failed(_word_lines(lines), "docx") == ()


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
