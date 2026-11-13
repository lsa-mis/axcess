"""Build the seeded PDFs the Documents tab's tests are scored against.

Each PDF is written by hand, object by object, so what it contains is
exactly what this file says and nothing a PDF library adds of its own. Each
one differs from the clean control in one way, so it can fail exactly one
check:

========================  ============================================
File                      What the checks must find
========================  ============================================
``clean.pdf``             Nothing. Tagged, titled, a language, real
                          text. It must come out "Not sure", never
                          "Mostly sure": a person still has to check
                          it.
``untagged.pdf``          ``not_tagged``: no structure tree (tags).
``scanned.pdf``           ``no_text``: tagged, titled, a language, but
                          its only page is a picture, as a scan is.
``no-title.pdf``          ``no_title``: no title in the document's
                          information or its XMP metadata.
``no-language.pdf``       ``no_language``: no ``/Lang`` in the catalog.
``encrypted.pdf``         ``blocks_assistive_tech``: opens without a
                          password, but its permissions (revision 3,
                          bit 10 cleared) forbid copying text for
                          accessibility.
``password.pdf``          Cannot be checked: needs a password to open.
``form.pdf``              Nothing, like the clean control, but it has a
                          fillable form field.
========================  ============================================

``revealed.pdf`` and ``offsite.pdf`` are copies of ``clean.pdf`` and
``untagged.pdf`` under other names, so the fixture page can reach the same
kind of file by a click and from another host.

The two encrypted files are made with pypdf's writer, the only part not
written by hand: encryption is not something to hand-roll. Its output has a
random file ID, so running this again changes their bytes but not what they
contain. Run from the repository root::

    uv run python tests/support/linked_file_pdfs.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "documents" / "files"

_TEXT = b"BT /F1 24 Tf 72 720 Td (Annual report 2026) Tj ET"


def _stream(data: bytes, extra: str = "") -> bytes:
    return f"<< /Length {len(data)}{extra} >>\nstream\n".encode() + data + b"\nendstream"


def _assemble(objects: list[bytes], *, info: int | None) -> bytes:
    """Number the objects from 1, write the cross-reference table and trailer."""
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    trailer = f"<< /Size {len(objects) + 1} /Root 1 0 R"
    if info is not None:
        trailer += f" /Info {info} 0 R"
    out += f"trailer\n{trailer} >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def build(
    *,
    tagged: bool = True,
    title: bool = True,
    language: bool = True,
    text: bool = True,
    form: bool = False,
) -> bytes:
    """One single-page PDF; each switch removes one accessibility feature."""
    # Fixed numbers: 1 catalog, 2 pages, 3 page, 4 content, 5 font,
    # 6 image, 7 struct tree root, 8 Document element, 9 content element,
    # 10 parent tree, 11 info, 12 form field.
    tag = b"/P" if text else b"/Figure"
    body = _TEXT if text else b"q 200 0 0 200 72 500 cm /Im1 Do Q"
    content = tag + b" << /MCID 0 >> BDC " + body + b" EMC" if tagged else body

    catalog = "<< /Type /Catalog /Pages 2 0 R"
    if tagged:
        catalog += " /MarkInfo << /Marked true >> /StructTreeRoot 7 0 R"
    if language:
        catalog += " /Lang (en-US)"
    if title:
        catalog += " /ViewerPreferences << /DisplayDocTitle true >>"
    if form:
        catalog += " /AcroForm << /Fields [12 0 R] >>"
    catalog += " >>"

    page = (
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> /XObject << /Im1 6 0 R >> >>"
    )
    if tagged:
        page += " /StructParents 0"
    if form:
        page += " /Annots [12 0 R]"
    page += " >>"

    alt = "" if text else " /Alt (A photo of the annual report cover)"
    objects = [
        catalog.encode(),
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        page.encode(),
        _stream(content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        _stream(
            b"\x00\xff\xff\x00",
            " /Type /XObject /Subtype /Image /Width 2 /Height 2 "
            "/ColorSpace /DeviceGray /BitsPerComponent 8",
        ),
        b"<< /Type /StructTreeRoot /K 8 0 R /ParentTree 10 0 R >>",
        b"<< /Type /StructElem /S /Document /P 7 0 R /K [9 0 R] >>",
        f"<< /Type /StructElem /S {tag.decode()} /P 8 0 R /Pg 3 0 R /K 0{alt} >>".encode(),
        b"<< /Nums [0 [9 0 R]] >>",
        b"<< /Title (Annual report 2026) /Producer (Axcess test fixture) >>"
        if title
        else b"<< /Producer (Axcess test fixture) >>",
        b"<< /FT /Tx /T (name) /TU (Your name) /Type /Annot /Subtype /Widget "
        b"/Rect [72 600 300 620] /P 3 0 R >>",
    ]
    return _assemble(objects, info=11)


def _encrypt(source: bytes, *, user_password: str, permissions: int) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(source)))
    writer.encrypt(
        user_password=user_password,
        owner_password="axcess-fixture-owner",
        permissions_flag=permissions,
        algorithm="RC4-128",
    )
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# Every permission except bit 5 (copy text, 16) and bit 10 (copy text for
# accessibility, 512): -1 with those two cleared, as a signed 32-bit value.
_NO_ACCESSIBILITY = -1 & ~(16 | 512)


def build_all() -> dict[str, bytes]:
    clean = build()
    untagged = build(tagged=False)
    return {
        "clean.pdf": clean,
        "untagged.pdf": untagged,
        "scanned.pdf": build(text=False),
        "no-title.pdf": build(title=False),
        "no-language.pdf": build(language=False),
        "form.pdf": build(form=True),
        "revealed.pdf": clean,
        "offsite.pdf": untagged,
        "encrypted.pdf": _encrypt(clean, user_password="", permissions=_NO_ACCESSIBILITY),
        "password.pdf": _encrypt(clean, user_password="open-sesame", permissions=-1),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in build_all().items():
        (OUT_DIR / name).write_bytes(data)
        print(f"{name}: {len(data)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
