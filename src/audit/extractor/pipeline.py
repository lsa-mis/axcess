"""Per-page image extraction pipeline.

For a single page we:

1. Parse the HTML for ``<img>`` / ``<picture><source>`` refs.
2. Download each referenced image (dedupe hits the blob store).
3. Persist an ``images`` row (keyed on content hash) and a ``page_images``
   row (keyed on ``(page_id, image_id, position)``).
4. Detect inline ``<svg>`` elements with visible ``<text>`` and record them
   as content-addressed "images" with ``has_svg_text=1`` and no blob.

Download failures are logged and swallowed — we still want the page row and
all the other images. The caller tracks the count of image errors via the
returned :class:`PageExtractionResult`.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from audit.db import repo
from audit.extractor.downloader import ImageDownloader, ImageDownloadError
from audit.extractor.html_images import extract_image_refs
from audit.extractor.svg_text import find_inline_svg_text
from audit.logging import get_logger

log = get_logger(__name__)


@dataclass
class PageExtractionResult:
    images_persisted: int = 0
    svg_text_hits: int = 0
    errors: int = 0


async def process_page(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    page_url: str,
    body: bytes,
    downloader: ImageDownloader,
) -> PageExtractionResult:
    """Extract, download, and persist every image referenced by ``body``."""
    result = PageExtractionResult()

    for ref in extract_image_refs(body, page_url):
        try:
            downloaded = await downloader.download(ref.url)
        except ImageDownloadError as exc:
            log.warning("extractor.download_failed", url=ref.url, error=str(exc))
            result.errors += 1
            continue

        image_id = repo.upsert_image(
            conn,
            content_hash=downloaded.content_hash,
            src_url=ref.url,
            mime=downloaded.mime,
            bytes_len=downloaded.bytes_len,
            width=downloaded.width,
            height=downloaded.height,
            blob_path=downloaded.blob_path,
            has_svg_text=False,
            scan_id=scan_id,
        )
        repo.upsert_page_image(
            conn,
            page_id=page_id,
            image_id=image_id,
            alt_text=ref.alt,
            role=ref.role,
            context_snippet=ref.context_snippet or ref.figcaption,
            position=ref.position,
        )
        result.images_persisted += 1

    # Inline SVG text hits get positions after any downloaded images so their
    # page_images rows don't collide with the regular ones.
    position_offset = (
        max(
            (ref.position for ref in extract_image_refs(body, page_url)),
            default=-1,
        )
        + 1
    )
    for hit in find_inline_svg_text(body):
        content_hash = _svg_text_hash(hit.visible_text)
        image_id = repo.upsert_image(
            conn,
            content_hash=content_hash,
            src_url=f"inline-svg://{page_url}#{hit.position}",
            mime="image/svg+xml",
            bytes_len=None,
            width=None,
            height=None,
            blob_path=None,
            has_svg_text=True,
            scan_id=scan_id,
        )
        repo.upsert_page_image(
            conn,
            page_id=page_id,
            image_id=image_id,
            alt_text=hit.alt_context,
            role=None,
            context_snippet=hit.visible_text,
            position=position_offset + hit.position,
        )
        result.svg_text_hits += 1

    return result


def _svg_text_hash(visible_text: str) -> str:
    """Content hash for inline SVG text — same text anywhere hashes the same."""
    return hashlib.sha256(b"inline-svg:" + visible_text.encode("utf-8")).hexdigest()
