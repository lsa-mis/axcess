"""Small Word and PowerPoint files for the Word and PowerPoint check's tests.

Built with python-docx and python-pptx, then changed in their XML to make
exactly one problem at a time. These are files we wrote: regression tests,
not evidence that the check works on real files (tests/real_pages/ is).
"""

from __future__ import annotations

import io
import struct
import zlib
from typing import Any, Literal

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from lxml import etree
from pptx import Presentation
from pptx.util import Inches

DECORATIVE = "http://schemas.microsoft.com/office/drawing/2017/decorative"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def png() -> bytes:
    """A 1 by 1 pixel PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


def _decorate(props: Any) -> None:
    """Office's "Mark as decorative" on a ``docPr``/``cNvPr``."""
    ext_list = etree.SubElement(props, f"{{{_A}}}extLst")
    ext = etree.SubElement(ext_list, f"{{{_A}}}ext", uri="{C183D7F6-B498-43B3-948B-1728B52AA6E4}")
    etree.SubElement(ext, f"{{{DECORATIVE}}}decorative", val="1")


Alt = Literal["described", "missing", "file_name", "decorative"] | None
Header = Literal["style_option", "repeat", "none", "off"] | None


def word(
    *,
    title: str = "Annual report",
    language: bool = True,
    headings: tuple[int, ...] = (1, 2),
    words: int = 60,
    image: Alt = None,
    table: Header = None,
    table_shape: Literal["grid", "merged_row", "merged_column", "nested"] = "grid",
    link_text: str | None = None,
    alt: str | None = None,
) -> bytes:
    """A Word file with one of each thing the check reads, as asked.

    ``table_shape`` makes the table a layout one: a row merged across both
    columns, a column merged down both rows, or a table inside a cell.
    ``alt`` replaces a described image's alt text.
    """
    document = Document()
    document.core_properties.title = title
    for level in headings:
        document.add_heading(f"Part at level {level}", level=level)
    document.add_paragraph(" ".join(["word"] * words))
    if image is not None:
        document.add_picture(io.BytesIO(png()), width=Inches(1))
        props = document.element.body.findall(f".//{qn('wp:docPr')}")[-1]
        props.set(
            "descr",
            alt
            if alt is not None
            else {"described": "Bar chart of 2026 costs", "file_name": "image1.png"}.get(image, ""),
        )
        if image == "decorative":
            _decorate(props)
    if table is not None:
        grid = document.add_table(rows=2, cols=2)
        grid.cell(0, 0).text, grid.cell(0, 1).text = "Plan", "Cost"
        grid.cell(1, 0).text, grid.cell(1, 1).text = "Basic", "$10"
        if table_shape == "merged_row":
            grid.cell(1, 0).merge(grid.cell(1, 1))
        elif table_shape == "merged_column":
            grid.cell(0, 0).merge(grid.cell(1, 0))
        elif table_shape == "nested":
            grid.cell(1, 1).add_table(rows=1, cols=1)
        look = grid._tbl.tblPr.find(qn("w:tblLook"))
        look.set(qn("w:firstRow"), "1" if table == "style_option" else "0")
        look.set(qn("w:val"), "04A0" if table == "style_option" else "0400")
        if table in {"repeat", "off"}:
            row_props = grid.rows[0]._tr.get_or_add_trPr()
            marker = etree.SubElement(row_props, qn("w:tblHeader"))
            if table == "off":
                marker.set(qn("w:val"), "0")
    if link_text is not None:
        paragraph = document.add_paragraph("See ")
        rel = paragraph.part.relate_to(
            "https://example.org/benefits", RT.HYPERLINK, is_external=True
        )
        link = etree.SubElement(paragraph._p, qn("w:hyperlink"))
        link.set(qn("r:id"), rel)
        run = etree.SubElement(link, qn("w:r"))
        text = etree.SubElement(run, qn("w:t"))
        text.text = link_text
    if not language:
        for root in (document.element, document.styles.element):
            for node in list(root.iter(qn("w:lang"))):
                node.getparent().remove(node)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def slides(
    *,
    title: str = "Benefits orientation",
    language: bool = True,
    slide_titles: tuple[str, ...] = ("Welcome", "Your choices"),
    image: Alt = None,
    table: Literal["header", "none", "merged"] | None = None,
    link_text: str | None = None,
    alt: str | None = None,
) -> bytes:
    """A PowerPoint file with one slide per title ("" for a slide without one).

    ``table="merged"``: no header row, and its first row merged across both
    columns. ``alt`` replaces a described picture's alt text.
    """
    deck = Presentation()
    deck.core_properties.title = title
    for slide_title in slide_titles:
        slide = deck.slides.add_slide(deck.slide_layouts[5])  # "Title Only"
        if slide_title:
            slide.shapes.title.text = slide_title
        else:
            slide.shapes._spTree.remove(slide.shapes.title._element)
    slide = deck.slides[0]
    if image is not None:
        picture = slide.shapes.add_picture(io.BytesIO(png()), Inches(1), Inches(2))
        props = picture._element.nvPicPr.cNvPr
        props.set(
            "descr",
            alt
            if alt is not None
            else {"described": "Map of the campus", "file_name": "photo.jpg"}.get(image, ""),
        )
        if image == "decorative":
            _decorate(props)
    if table is not None:
        grid = slide.shapes.add_table(2, 2, Inches(1), Inches(4), Inches(4), Inches(1)).table
        grid.first_row = table == "header"
        grid.cell(0, 0).text, grid.cell(0, 1).text = "Plan", "Cost"
        if table == "merged":
            grid.cell(0, 0).merge(grid.cell(0, 1))
    if link_text is not None:
        box = slide.shapes.add_textbox(Inches(1), Inches(5), Inches(4), Inches(1))
        run = box.text_frame.paragraphs[0].add_run()
        run.text = link_text
        run.hyperlink.address = "https://example.org/benefits"
    if not language:
        for part in deck.part.package.iter_parts():
            element = getattr(part, "_element", None)
            if element is None:
                continue
            for node in element.iter():
                if "lang" in node.attrib:
                    del node.attrib["lang"]
    out = io.BytesIO()
    deck.save(out)
    return out.getvalue()
