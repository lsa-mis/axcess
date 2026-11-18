"""The four structure checks (pdf_structure.py), on small PDFs written here.

These are files we wrote, so they are regression tests, not evidence that
the checks are right on real files. Several cases are cut down from real
files the checks were tuned on (hr.umich.edu and www.dol.gov forms; see
docs/internal/document-check.md), and say so.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

import pytest
from support.linked_file_pdfs import _assemble, _stream

from audit.linked_files.pdf_check import BASE_CHECKS, check_pdf

# Fixed numbers: 1 catalog, 2 pages, 3 page, 4 content, 5 font,
# 6 struct tree root, 7 Document element; elements from 8, then annotations.
_BODY = b"/P << /MCID 0 >> BDC BT /F1 12 Tf 72 700 Td (Body text) Tj ET EMC"
_P = "<< /Type /StructElem /S /P /P 7 0 R /Pg 3 0 R /K 0 >>"


def _pdf(
    content: bytes = _BODY,
    elements: Sequence[str] = (_P,),
    *,
    annots: Sequence[str] = (),
    fields: Sequence[int] = (),
    tagged: bool = True,
    role_map: str = "",
    parent_tree: str = "",
    document_kids: Sequence[int] | None = None,
) -> bytes:
    first_annot = 8 + len(elements)
    catalog = "<< /Type /Catalog /Pages 2 0 R /Lang (en-US)"
    if tagged:
        catalog += " /MarkInfo << /Marked true >> /StructTreeRoot 6 0 R"
    if fields:
        catalog += " /AcroForm << /Fields [" + " ".join(f"{n} 0 R" for n in fields) + "] >>"
    catalog += " >>"
    page = (
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> /StructParents 0"
    )
    if annots:
        page += " /Annots [" + " ".join(f"{first_annot + i} 0 R" for i in range(len(annots))) + "]"
    page += " >>"
    numbers = document_kids if document_kids is not None else range(8, 8 + len(elements))
    kids = " ".join(f"{n} 0 R" for n in numbers)
    root = f"<< /Type /StructTreeRoot /K 7 0 R{role_map}{parent_tree} >>"
    objects = [
        catalog.encode(),
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        page.encode(),
        _stream(content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        root.encode(),
        f"<< /Type /StructElem /S /Document /P 6 0 R /K [{kids}] >>".encode(),
        *(e.encode() for e in elements),
        *(a.encode() for a in annots),
    ]
    # The title goes in the info dictionary, the last object.
    objects.append(b"<< /Title (Structure test) >>")
    return _assemble(objects, info=len(objects))


def _figure(alt: str = "") -> str:
    return f"<< /Type /StructElem /S /Figure /P 7 0 R /Pg 3 0 R /K 1{alt} >>"


_FIGURE_CONTENT = _BODY + b" /Figure << /MCID 1 >> BDC 0 0 1 rg 72 400 100 100 re f EMC"


def _failed(data: bytes) -> tuple[str, ...]:
    result = check_pdf(data)
    assert result.outcome == "checked"
    return result.failed


def test_a_clean_tagged_file_runs_the_text_check_and_fails_nothing() -> None:
    result = check_pdf(_pdf())
    assert result.failed == ()
    assert set(result.checks_run) == set(BASE_CHECKS) | {"untagged_text"}


# --- images ------------------------------------------------------------------


def test_a_figure_without_alt_text_fails() -> None:
    data = _pdf(_FIGURE_CONTENT, (_P, _figure()))
    assert _failed(data) == ("image_no_description",)


def test_a_figure_with_alt_text_passes() -> None:
    data = _pdf(_FIGURE_CONTENT, (_P, _figure(" /Alt (University of Michigan logo)")))
    assert _failed(data) == ()
    assert "image_no_description" in check_pdf(data).checks_run


def test_alt_text_with_a_stray_nul_still_counts() -> None:
    """Cut down from hr.umich.edu's supplemental appointment form: pypdf
    cannot decode the alt text as PDFDocEncoding (it ends in a NUL byte) and
    returns raw bytes, but a screen reader reads the words."""
    data = _pdf(
        _FIGURE_CONTENT,
        (_P, _figure(" /Alt <556E6976657273697479206F66204D6963686967616E206C6F676F00>")),
    )
    assert _failed(data) == ()


def test_a_role_mapped_figure_is_a_figure() -> None:
    element = "<< /Type /StructElem /S /Picture /P 7 0 R /Pg 3 0 R /K 1 >>"
    data = _pdf(_FIGURE_CONTENT, (_P, element), role_map=" /RoleMap << /Picture /Figure >>")
    assert _failed(data) == ("image_no_description",)


def test_a_file_with_no_figures_is_not_given_the_image_check() -> None:
    assert "image_no_description" not in check_pdf(_pdf()).checks_run


def test_a_formula_without_alt_text_fails() -> None:
    element = "<< /Type /StructElem /S /Formula /P 7 0 R /Pg 3 0 R /K 1 >>"
    data = _pdf(_FIGURE_CONTENT, (_P, element))
    assert _failed(data) == ("formula_no_description",)


def test_a_formula_with_alt_text_passes() -> None:
    element = "<< /Type /StructElem /S /Formula /P 7 0 R /Pg 3 0 R /K 1 /Alt (x squared plus 1) >>"
    data = _pdf(_FIGURE_CONTENT, (_P, element))
    assert _failed(data) == ()
    assert "formula_no_description" in check_pdf(data).checks_run


def test_a_formula_with_mathml_inside_passes() -> None:
    """As in the LaTeX Project's tagged PDFs (LaTeX News, its STEM demo):
    MathML elements inside the formula, in the MathML namespace."""
    formula = "<< /Type /StructElem /S /Formula /P 7 0 R /Pg 3 0 R /K [1 10 0 R] >>"
    math = (
        "<< /Type /StructElem /S /math /P 9 0 R "
        "/NS << /Type /Namespace /NS (http://www.w3.org/1998/Math/MathML) >> >>"
    )
    data = _pdf(_FIGURE_CONTENT, (_P, formula, math), document_kids=(8, 9))
    assert _failed(data) == ()


def _formula_with_file(subtype: str) -> tuple[str, ...]:
    return (
        _P,
        "<< /Type /StructElem /S /Formula /P 7 0 R /Pg 3 0 R /K 1 /AF [10 0 R] >>",
        "<< /Type /Filespec /F (math.xml) /UF (math.xml) /AFRelationship /Supplement "
        "/EF << /F 11 0 R >> >>",
        f"<< /Type /EmbeddedFile /Subtype /{subtype} /Length 0 >>\nstream\n\nendstream",
    )


def test_a_formula_with_a_mathml_file_passes() -> None:
    """As in TUGboat's tagged articles: MathML as an associated file."""
    data = _pdf(
        _FIGURE_CONTENT, _formula_with_file("application#2Fmathml+xml"), document_kids=(8, 9)
    )
    assert _failed(data) == ()


def test_a_formula_with_only_its_tex_source_fails() -> None:
    """As in latex-lab-math.pdf: TeX source is not something a screen reader reads."""
    data = _pdf(_FIGURE_CONTENT, _formula_with_file("application#2Fx-tex"), document_kids=(8, 9))
    assert _failed(data) == ("formula_no_description",)


def test_an_empty_replacement_text_is_no_description() -> None:
    """veraPDF's corpus passes 7.7-t01-pass-c (ActualText present, but empty);
    a screen reader reads nothing, so Axcess fails it."""
    element = "<< /Type /StructElem /S /Formula /P 7 0 R /Pg 3 0 R /K 1 /ActualText () >>"
    assert _failed(_pdf(_FIGURE_CONTENT, (_P, element))) == ("formula_no_description",)


# --- tables ------------------------------------------------------------------


def _table(rows: Sequence[Sequence[str]], first: int) -> tuple[str, ...]:
    """A Table (object ``first``), its rows, then their cells, numbered in that order.

    Each cell is "TD", "TH", or with spans, e.g. "TD c2" (ColSpan 2) or
    "TH r2" (RowSpan 2).
    """
    first_row = first + 1
    first_cell = first_row + len(rows)
    elements = [
        "<< /Type /StructElem /S /Table /P 7 0 R /K ["
        + " ".join(f"{first_row + i} 0 R" for i in range(len(rows)))
        + "] >>"
    ]
    cells: list[str] = []
    for i, row in enumerate(rows):
        numbers = [first_cell + len(cells) + j for j in range(len(row))]
        elements.append(
            f"<< /Type /StructElem /S /TR /P {first} 0 R "
            f"/K [{' '.join(f'{n} 0 R' for n in numbers)}] >>"
        )
        for cell in row:
            kind, *spans = cell.split()
            attrs = ""
            for span in spans:
                key = "/ColSpan" if span[0] == "c" else "/RowSpan"
                attrs += f" {key} {span[1:]}"
            a = f" /A << /O /Table{attrs} >>" if attrs else ""
            cells.append(f"<< /Type /StructElem /S /{kind} /P {first_row + i} 0 R{a} >>")
    return (*elements, *cells)


@pytest.mark.parametrize(
    ("rows", "failed"),
    [
        ([["TH", "TH", "TH"], ["TD", "TD", "TD"]], ()),
        # A header spanning two columns over two cells.
        ([["TH", "TH c2"], ["TD", "TD", "TD"]], ()),
        # A row header spanning two rows.
        ([["TH r2", "TD", "TD"], ["TD", "TD"]], ()),
        # Cut down from hr.umich.edu's 2027 Medicare plan profiles: the
        # Website row is a cell short, so the next cell is read under the
        # wrong plan (veraPDF 7.2-43).
        (
            [["TH", "TH", "TH", "TH"], ["TD", "TD", "TD", "TD"], ["TD", "TD", "TD"]],
            ("table_uneven_rows",),
        ),
        # A span that overshoots.
        ([["TH", "TH"], ["TD c3"]], ("table_uneven_rows",)),
    ],
)
def test_table_rows(rows: list[list[str]], failed: tuple[str, ...]) -> None:
    elements = _table(rows, first=9)
    data = _pdf(elements=(_P, *elements), document_kids=(8, 9))
    assert _failed(data) == failed
    assert "table_uneven_rows" in check_pdf(data).checks_run


def _positioned_table(rows: Sequence[Sequence[int | None]]) -> bytes:
    """A table whose cells hold text at the given x positions (None: empty).

    Table is object 9 (after the paragraph, 8), then its rows, then cells.
    Each cell with text marks it with its own MCID, from 1.
    """
    first_row = 10
    first_cell = first_row + len(rows)
    content = _BODY
    elements = [
        "<< /Type /StructElem /S /Table /P 7 0 R /K ["
        + " ".join(f"{first_row + i} 0 R" for i in range(len(rows)))
        + "] >>"
    ]
    cells: list[str] = []
    mcid = 1
    for i, row in enumerate(rows):
        numbers = [first_cell + len(cells) + j for j in range(len(row))]
        elements.append(
            f"<< /Type /StructElem /S /TR /P 9 0 R /K [{' '.join(f'{n} 0 R' for n in numbers)}] >>"
        )
        y = 600 - 20 * i
        for x in row:
            if x is None:
                cells.append(f"<< /Type /StructElem /S /TD /P {first_row + i} 0 R >>")
                continue
            content += (
                f" /TD << /MCID {mcid} >> BDC BT /F1 10 Tf {x} {y} Td (Cell) Tj ET EMC".encode()
            )
            cells.append(
                f"<< /Type /StructElem /S /TD /P {first_row + i} 0 R /Pg 3 0 R /K {mcid} >>"
            )
            mcid += 1
    return _pdf(content, (_P, *elements, *cells), document_kids=(8, 9))


def test_a_heading_tagged_in_the_wrong_column_is_misplaced() -> None:
    """Cut down from the Australian Budget's Table 3.1 and St Albans' page
    20: a group heading over the last columns is tagged as the row's first
    cell, with no ColSpan, so it is read under the first column."""
    data = _positioned_table([[350], [72, 200, 350], [72, 200, 350]])
    assert _failed(data) == ("table_cells_misplaced",)


def test_a_label_row_with_its_missing_cells_at_the_end_is_only_uneven() -> None:
    """Cut down from St Albans' page 10: a label across the table tagged as
    one cell, which starts in the first column; no cell moves."""
    data = _positioned_table([[72, 200, 350], [72], [72, 200, 350]])
    assert _failed(data) == ("table_uneven_rows",)
    assert {"table_cells_misplaced", "table_uneven_rows"} <= set(check_pdf(data).checks_run)


def test_a_label_tagged_after_an_empty_cell_is_misplaced() -> None:
    """Cut down from Pew Research's topline, page 30: the label starts in the
    first column on the page but is the row's second cell, so it is read
    under the second column's heading."""
    data = _positioned_table([[72, 200, 350], [None, 72], [72, 200, 350]])
    assert _failed(data) == ("table_cells_misplaced",)


# --- form fields -------------------------------------------------------------


def _field(extra: str) -> str:
    return (
        "<< /FT /Tx /T (undefined_5) /Type /Annot /Subtype /Widget "
        f"/Rect [72 600 300 620] /P 3 0 R{extra} >>"
    )


@pytest.mark.parametrize(
    ("extra", "failed"),
    [
        (" /TU (Telephone)", ()),
        # The tooltip on www.dol.gov's WH-384 Telephone and Fax fields.
        (" /TU (undefined)", ("field_no_name",)),
        ("", ("field_no_name",)),
        (" /TU ()", ("field_no_name",)),
    ],
)
def test_a_field_needs_a_name(extra: str, failed: tuple[str, ...]) -> None:
    data = _pdf(annots=(_field(extra),), fields=(9,))
    assert _failed(data) == failed
    assert "field_no_name" in check_pdf(data).checks_run


def test_a_hidden_field_is_not_counted() -> None:
    data = _pdf(annots=(_field(" /F 2"),), fields=(9,))
    assert "field_no_name" not in check_pdf(data).checks_run


def test_a_radio_group_is_one_field_named_on_the_group() -> None:
    """The group has the name; its buttons are widgets without one."""
    group = "<< /FT /Btn /Ff 49152 /T (gender) /TU (Gender) /Kids [10 0 R 11 0 R] >>"
    button = "<< /Type /Annot /Subtype /Widget /Parent 9 0 R /Rect [72 600 90 618] /P 3 0 R >>"
    data = _pdf(annots=(group, button, button), fields=(9,))
    assert _failed(data) == ()


def test_field_names_are_checked_in_an_untagged_file_too() -> None:
    data = _pdf(
        b"BT /F1 12 Tf 72 700 Td (Body text) Tj ET",
        (),
        annots=(_field(" /TU (undefined)"),),
        fields=(8,),
        tagged=False,
    )
    assert _failed(data) == ("not_tagged", "field_no_name")


# --- links ---------------------------------------------------------------------

_LINK_ANNOT = (
    "<< /Type /Annot /Subtype /Link /Rect [72 690 160 710] "
    "/A << /S /URI /URI (https://example.org/) >>{extra} >>"
)


def test_a_link_tag_with_text_inside_passes() -> None:
    link = "<< /Type /StructElem /S /Link /P 7 0 R /Pg 3 0 R /K [0 << /Type /OBJR /Obj 9 0 R >>] >>"
    data = _pdf(elements=(link,), annots=(_LINK_ANNOT.format(extra=""),))
    assert _failed(data) == ()
    assert "link_no_description" in check_pdf(data).checks_run


def test_a_link_tag_holding_only_the_link_fails() -> None:
    """Cut down from hr.umich.edu's supplemental appointment form: the Link
    tag holds only the annotation; the visible words sit in the paragraph."""
    link = "<< /Type /StructElem /S /Link /P 7 0 R /Pg 3 0 R /K << /Type /OBJR /Obj 10 0 R >> >>"
    data = _pdf(elements=(_P, link), annots=(_LINK_ANNOT.format(extra=""),))
    assert _failed(data) == ("link_no_description",)


def test_an_untagged_link_fails() -> None:
    data = _pdf(annots=(_LINK_ANNOT.format(extra=""),))
    assert _failed(data) == ("link_no_description",)


def test_a_link_with_contents_passes() -> None:
    data = _pdf(annots=(_LINK_ANNOT.format(extra=" /Contents (Example site)"),))
    assert _failed(data) == ()


# --- untagged text -----------------------------------------------------------


@pytest.mark.parametrize(
    ("extra", "failed"),
    [
        # Mid-page, outside every tag: skipped by a screen reader.
        (b" BT /F1 12 Tf 72 400 Td (priorityhealth.com) Tj ET", ("untagged_text",)),
        # A footer 20 points up, like hr.umich.edu's untagged revision notes.
        (b" BT /F1 8 Tf 72 20 Td (Revised 06/2026) Tj ET", ()),
        # Marked as decoration.
        (b" /Artifact BMC BT /F1 12 Tf 72 400 Td (Decoration) Tj ET EMC", ()),
        # Invisible (render mode 3), as an OCR layer can be.
        (b" BT 3 Tr /F1 12 Tf 72 400 Td (Invisible) Tj ET", ()),
        # Punctuation only.
        (b" BT /F1 12 Tf 72 400 Td (\\() Tj ET", ()),
        # Marked with an MCID no tag refers to, like the heading on WH-385.
        (b" /P << /MCID 7 >> BDC BT /F1 12 Tf 72 400 Td (PART A) Tj ET EMC", ("untagged_text",)),
    ],
)
def test_untagged_text(extra: bytes, failed: tuple[str, ...]) -> None:
    assert _failed(_pdf(_BODY + extra)) == failed


def test_an_mcid_the_parent_tree_calls_an_artifact_is_decoration() -> None:
    """Cut down from hr.umich.edu's supplemental appointment form: the
    repeated title on page 3 is marked with an MCID whose only parent is an
    "/Artifact" element that the tag tree never reaches."""
    content = _BODY + b" /P << /MCID 1 >> BDC BT /F1 12 Tf 72 400 Td (Form title) Tj ET EMC"
    artifact = "<< /Type /StructElem /S /Artifact /K 1 >>"
    # The artifact element is object 9, reached only through the parent tree.
    data = _pdf(
        content,
        (_P, artifact),
        parent_tree=" /ParentTree << /Nums [0 [8 0 R 9 0 R]] >>",
        document_kids=(8,),
    )
    assert _failed(data) == ()


# --- untrusted input ---------------------------------------------------------


def test_a_file_over_the_time_budget_skips_only_the_structure_checks() -> None:
    from pypdf import PdfReader

    from audit.linked_files.pdf_structure import read_structure

    reader = PdfReader(io.BytesIO(_pdf()))
    assert read_structure(reader, max_pages=50, budget_s=-1) is None


def test_a_broken_structure_tree_leaves_the_base_checks() -> None:
    """A fault in the tags must not make the whole file "damaged"."""
    data = _pdf(elements=("<< /Type /StructElem /S /P /P 7 0 R /K [1 2 3 << /Type /MCR >>] >>",))
    result = check_pdf(data)
    assert result.outcome == "checked"
    assert set(BASE_CHECKS) <= set(result.checks_run)
