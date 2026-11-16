"""Machine checks on one PDF's bytes.

Each check reads a fact the PDF states about itself, and fails only when
that fact proves a barrier. Nothing here judges quality: a PDF can pass
every check and still have a wrong reading order, useless alternative text
or tables without headers. That is why a PDF that passes is "Not sure",
never "accessible" (see :mod:`audit.linked_files.formats`).

The checks, and the WCAG technique each one follows:

``not_tagged``
    No structure tree (``/StructTreeRoot`` in the catalog). Without tags a
    screen reader cannot tell headings, lists and tables apart. WCAG
    technique PDF9 and the others that use tags all need one. A file that
    has a structure tree but no ``/MarkInfo /Marked true`` is *not* failed:
    the tree may still be usable, so that is left to the person.
``no_text``
    No text on any page read (at most ``MAX_TEXT_PAGES``), as in a scan
    saved as pictures. Text a screen reader can read is what PDF7 (OCR on
    a scanned PDF) asks for.
``blocks_assistive_tech``
    The file opens without a password, but its permissions forbid copying
    text for accessibility: bit 10 of ``/P`` with a security handler of
    revision 3 or later, or bit 5 at revision 2 (ISO 32000-1, table 22).
    PDF 2.0 deprecated bit 10 and tells readers to ignore it, so a PDF 2.0
    file is not failed on it.
``no_title``
    No title in the document information dictionary or in the XMP
    metadata (``dc:title``). WCAG technique PDF18.
``no_language``
    No ``/Lang`` in the catalog. WCAG technique PDF16.

pypdf is pure Python, so a hostile file can make it slow; the caller runs
:func:`check_pdf` in a thread under a time limit. Every exception from
reading is "damaged": the file is untrusted input, and no fault in it may
stop a crawl.
"""

from __future__ import annotations

import contextlib
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from audit.linked_files.formats import FailedCheck

#: Pages read for text. A file whose first 50 pages are all pictures is a
#: scan in every sense that matters to a reader.
MAX_TEXT_PAGES = 50

Outcome = Literal["checked", "password", "damaged", "not_a_pdf"]

_ACCESSIBILITY_BIT = 1 << 9  # bit 10, "extract for accessibility"
_EXTRACT_BIT = 1 << 4  # bit 5, "copy or extract text"


@dataclass(frozen=True)
class PdfCheck:
    """What the checks found in one PDF."""

    outcome: Outcome
    #: Failed checks, in the order of ``ALL_CHECKS``. Empty unless ``checked``.
    failed: tuple[FailedCheck, ...] = ()
    #: True when the file has fillable form fields; None when not read.
    is_form: bool | None = None
    page_count: int | None = None
    #: Short technical note for the log only, never shown or stored.
    detail: str = field(default="", compare=False)


ALL_CHECKS: tuple[FailedCheck, ...] = (
    "not_tagged",
    "no_text",
    "blocks_assistive_tech",
    "no_title",
    "no_language",
)


def looks_like_pdf(data: bytes) -> bool:
    """A PDF starts with ``%PDF-``; readers allow some junk before it."""
    return b"%PDF-" in data[:1024]


def check_pdf(data: bytes) -> PdfCheck:
    """Run every check on ``data``. Never raises."""
    if not looks_like_pdf(data):
        return PdfCheck(outcome="not_a_pdf")
    # pypdf logs every recoverable fault in a broken file as a warning. They
    # are expected from untrusted files and say nothing a reader needs.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        return _check(data)
    except Exception as exc:  # untrusted input, RecursionError included: "damaged"
        return PdfCheck(outcome="damaged", detail=type(exc).__name__)


def _check(data: bytes) -> PdfCheck:
    from pypdf import PdfReader
    from pypdf._encryption import PasswordType

    reader = PdfReader(io.BytesIO(data), strict=False)
    failed: set[FailedCheck] = set()
    if reader.is_encrypted:
        if reader.decrypt("") == PasswordType.NOT_DECRYPTED:
            return PdfCheck(outcome="password")
        if _blocks_assistive_tech(reader):
            failed.add("blocks_assistive_tech")

    catalog = reader.root_object
    if "/StructTreeRoot" not in catalog:
        failed.add("not_tagged")
    if not _text_value(catalog.get("/Lang")):
        failed.add("no_language")
    if not _has_title(reader):
        failed.add("no_title")

    page_count = len(reader.pages)
    if page_count == 0:
        return PdfCheck(outcome="damaged", detail="no pages")
    if not _has_text(reader, page_count):
        failed.add("no_text")

    return PdfCheck(
        outcome="checked",
        failed=tuple(check for check in ALL_CHECKS if check in failed),
        is_form=_has_form_fields(catalog),
        page_count=page_count,
    )


def _blocks_assistive_tech(reader: Any) -> bool:
    encrypt = reader.trailer.get("/Encrypt")
    if encrypt is None:
        return False
    encrypt = encrypt.get_object()
    revision = int(encrypt.get("/R", 2))
    permissions = int(encrypt.get("/P", -1)) & 0xFFFFFFFF
    if revision >= 3:
        if _pdf_version(reader) >= 2.0:
            return False
        return not permissions & _ACCESSIBILITY_BIT
    return not permissions & _EXTRACT_BIT


def _pdf_version(reader: Any) -> float:
    """The header's version, or the catalog's ``/Version`` when that is later."""
    versions = []
    header = str(reader.pdf_header or "")
    if header.startswith("%PDF-"):
        versions.append(header[5:8])
    catalog_version = reader.root_object.get("/Version")
    if catalog_version is not None:
        versions.append(str(catalog_version).lstrip("/"))
    parsed = []
    for value in versions:
        try:
            parsed.append(float(value))
        except ValueError:
            continue
    return max(parsed, default=1.0)


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    with contextlib.suppress(AttributeError):
        value = value.get_object()
    return str(value).strip()


def _has_title(reader: Any) -> bool:
    try:
        info = reader.metadata
    except Exception:
        info = None
    if info is not None and _text_value(info.get("/Title")):
        return True
    try:
        xmp = reader.xmp_metadata
        titles = xmp.dc_title if xmp is not None else None
    except Exception:
        return False
    if not titles:
        return False
    return any(str(value).strip() for value in titles.values())


def _has_text(reader: Any, page_count: int) -> bool:
    for index in range(min(page_count, MAX_TEXT_PAGES)):
        text = ""
        # A page whose text cannot be read counts as a page with none.
        with contextlib.suppress(Exception):
            text = reader.pages[index].extract_text() or ""
        if text.strip():
            return True
    return False


def _has_form_fields(catalog: Any) -> bool:
    form = catalog.get("/AcroForm")
    if form is None:
        return False
    try:
        fields = form.get_object().get("/Fields")
        return bool(fields.get_object()) if fields is not None else False
    except Exception:
        return False
