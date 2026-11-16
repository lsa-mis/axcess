"""Pictures of a PDF's first page, for the report's Documents tab.

Drawn with PDFium (``pypdfium2``, the PDF engine in Chrome), because pypdf,
which does the checks, reads a PDF's structure but cannot draw it. Only a
PDF that the check could read is drawn (``tracker._check_fetched``), and
only its first page, scaled to ``WIDTH_PX`` wide and cut at ``MAX_HEIGHT_PX``
so a very tall page cannot make a large image. JPEG, because a page is
mostly text and photos at this size, and a JPEG of one is a few tens of
kilobytes where a PNG is several times that.

Two sizes from one drawing: ``large`` for the document's own page and
``small`` for the Documents table's 72 by 48 box (``SMALL_BOX_PX``, twice
that for a high-density screen). A table page of 100 rows then loads a few
hundred kilobytes, not several megabytes of pictures shown at a sixth of
their size.

Never raises: a PDF PDFium cannot open (a password, damage it does not
forgive) or draw simply has no picture, and the Documents tab shows its type
instead.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from audit.logging import get_logger

log = get_logger(__name__)

# 480px wide: twice the largest size the app shows it (240 CSS pixels on a
# document's own page), so it stays sharp on a high-density screen.
WIDTH_PX = 480
MAX_HEIGHT_PX = 960
JPEG_QUALITY = 80
SMALL_BOX_PX = (144, 96)


@dataclass(frozen=True)
class FirstPage:
    large: bytes
    small: bytes


def _jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def first_page_jpegs(body: bytes) -> FirstPage | None:
    """JPEGs of the first page of the PDF in ``body``, in two sizes, or None."""
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]

        pdf = pdfium.PdfDocument(body)
        try:
            if len(pdf) == 0:
                return None
            page = pdf[0]
            try:
                width_pt, height_pt = page.get_size()
                if width_pt <= 0 or height_pt <= 0:
                    return None
                scale = min(WIDTH_PX / width_pt, MAX_HEIGHT_PX / height_pt)
                image = page.render(scale=scale).to_pil().convert("RGB")
            finally:
                page.close()
        finally:
            pdf.close()
        small = image.copy()
        small.thumbnail(SMALL_BOX_PX, Image.Resampling.LANCZOS)
        return FirstPage(large=_jpeg(image), small=_jpeg(small))
    except Exception as exc:  # PDFium raises its own errors on bad files
        log.info("linked_files.thumbnail_failed", error_type=type(exc).__name__)
        return None
