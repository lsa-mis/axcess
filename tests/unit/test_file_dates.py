"""When a linked file says it was created and last changed (linked_files/file_dates.py).

The real files these follow (docs/internal/document-check.md, "Creation and
modified dates"): 321 of 325 Word files and 35 of 45 PowerPoint files carry
``dcterms:created``; every real PDF had a date in /Info or XMP; no Google
Docs or Slides export had any (0 of 42).
"""

from __future__ import annotations

import datetime as dt
import io
import re
import zipfile

import pytest
from support.office_docs import slides, word

from audit.linked_files.file_dates import FileDates, _iso, pdf_dates
from audit.linked_files.office_check import check_office
from audit.linked_files.pdf_check import check_pdf

NOW = dt.datetime(2026, 11, 25, tzinfo=dt.UTC)


def _replace_part(data: bytes, name: str, change: object) -> bytes:
    """``data`` with one zip part changed, or the core properties removed
    (``change=None``), as Google exports them: no part, no relationship to
    it, no content type. The same as test_office_check's helper."""
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            body = source.read(info.filename)
            if change is None and name == "docProps/core.xml":
                if info.filename == name:
                    continue
                if info.filename in {"_rels/.rels", "[Content_Types].xml"}:
                    body = re.sub(rb"<[^<>]*core[^<>]*/>", b"", body)
            if info.filename == name and callable(change):
                body = change(body)
            target.writestr(info, body)
    return out.getvalue()


def _with_dates(data: bytes, created: str, modified: str) -> bytes:
    def change(core: bytes) -> bytes:
        core = re.sub(rb"<dcterms:created[^>]*>[^<]*</dcterms:created>", b"", core)
        core = re.sub(rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>", b"", core)
        stamp = (
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{modified}</dcterms:modified>'
        ).encode()
        return core.replace(b"</cp:coreProperties>", stamp + b"</cp:coreProperties>")

    return _replace_part(data, "docProps/core.xml", change)


@pytest.mark.parametrize("make, kind", [(word, "docx"), (slides, "pptx")])
def test_a_word_or_powerpoint_file_gives_its_core_dates(make: object, kind: str) -> None:
    data = _with_dates(make(), "2018-07-17T09:30:00Z", "2025-05-23T16:17:00Z")  # type: ignore[operator]
    result = check_office(data, kind)
    assert result.dates == FileDates(
        created="2018-07-17T09:30:00+00:00", modified="2025-05-23T16:17:00+00:00"
    )


def test_a_google_export_has_no_dates_not_todays() -> None:
    """With no core properties, python-docx would make up a part dated now."""
    data = _replace_part(word(), "docProps/core.xml", None)
    assert check_office(data, "docx").dates == FileDates()


def test_a_date_from_a_broken_clock_is_dropped() -> None:
    data = _with_dates(word(), "1601-01-01T00:00:00Z", "2099-01-01T00:00:00Z")
    assert check_office(data, "docx").dates == FileDates()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (dt.datetime(2010, 11, 17, 8, 0), "2010-11-17T08:00:00"),
        (dt.datetime(1979, 12, 31), None),
        # A clock a few hours ahead is kept; a day and more is not.
        (dt.datetime(2026, 11, 25, 20, tzinfo=dt.UTC), "2026-11-25T20:00:00+00:00"),
        (dt.datetime(2026, 11, 27, tzinfo=dt.UTC), None),
        ("2010-11-17", None),
        (None, None),
    ],
)
def test_only_believable_dates_are_kept(value: object, expected: str | None) -> None:
    assert _iso(value, now=NOW) == expected


def _pdf(info: dict[str, str] | None = None, xmp: bytes | None = None) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, StreamObject

    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    if info:
        writer.add_metadata(info)
    if xmp is not None:
        stream = StreamObject()
        stream.set_data(xmp)
        stream.update(
            {
                NameObject("/Type"): NameObject("/Metadata"),
                NameObject("/Subtype"): NameObject("/XML"),
            }
        )
        writer._root_object[NameObject("/Metadata")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _reader(data: bytes) -> object:
    from pypdf import PdfReader

    return PdfReader(io.BytesIO(data))


def test_a_pdf_gives_its_document_information_dates() -> None:
    data = _pdf({"/CreationDate": "D:20250627095727+01'00'", "/ModDate": "D:20250630112538+01'00'"})
    assert pdf_dates(_reader(data), now=NOW) == FileDates(
        created="2025-06-27T09:57:27+01:00", modified="2025-06-30T11:25:38+01:00"
    )
    # The same through the whole PDF check.
    assert check_pdf(data).dates.created == "2025-06-27T09:57:27+01:00"


def test_a_pdf_without_document_information_dates_uses_xmp() -> None:
    xmp = b"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
<xmp:CreateDate>2019-03-04T10:00:00Z</xmp:CreateDate><xmp:ModifyDate>2020-01-02T03:04:05Z</xmp:ModifyDate>
</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>"""
    dates = pdf_dates(_reader(_pdf(xmp=xmp)), now=NOW)
    assert (dates.created or "").startswith("2019-03-04T10:00:00")
    assert (dates.modified or "").startswith("2020-01-02T03:04:05")


def test_a_pdf_with_no_dates_or_a_broken_one_has_none() -> None:
    assert pdf_dates(_reader(_pdf()), now=NOW).created is None
    broken = _pdf({"/CreationDate": "not a date"})
    assert pdf_dates(_reader(broken), now=NOW).created is None
