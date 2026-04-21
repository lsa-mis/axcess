"""Per-page image extraction pipeline.

For a single page we:

1. Parse the HTML for ``<img>`` / ``<picture><source>`` refs.
2. Download each referenced image (dedupe hits the blob store).
3. Persist an ``images`` row (keyed on content hash) and a ``page_images``
   row (keyed on ``(page_id, image_id, position)``).
4. Optionally OCR each raster image via the :class:`OcrPool` and persist the
   result to ``analyses``. The text-candidate flag is applied against the
   configured confidence and word-count thresholds.
5. Detect inline ``<svg>`` elements with visible ``<text>`` and record them
   as content-addressed "images" with ``has_svg_text=1`` and no blob.

Download and OCR failures are logged and swallowed — we still want the page
row and all the other images. Counts are surfaced via :class:`PageExtractionResult`.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from dataclasses import dataclass

from audit.analyzer.ocr.pool import OcrPool
from audit.blob_store import BlobStore
from audit.db import repo
from audit.extractor.downloader import DownloadedImage, ImageDownloader, ImageDownloadError
from audit.extractor.html_images import extract_image_refs
from audit.extractor.svg_text import find_inline_svg_text
from audit.logging import get_logger

log = get_logger(__name__)

_OCR_SKIP_MIMES = frozenset({"image/svg+xml", "image/x-icon", "image/vnd.microsoft.icon"})


@dataclass
class OcrConfig:
    """Wiring needed to OCR downloaded images as part of the pipeline."""

    pool: OcrPool
    blob_store: BlobStore
    min_confidence: float
    min_word_count: int


@dataclass
class PageExtractionResult:
    images_persisted: int = 0
    svg_text_hits: int = 0
    ocr_analyzed: int = 0
    ocr_text_candidates: int = 0
    errors: int = 0


async def process_page(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    page_url: str,
    body: bytes,
    downloader: ImageDownloader,
    ocr: OcrConfig | None = None,
) -> PageExtractionResult:
    """Extract, download, OCR, and persist every image referenced by ``body``."""
    result = PageExtractionResult()
    ocr_tasks: list[asyncio.Task[_OcrOutcome]] = []

    refs = extract_image_refs(body, page_url)
    for ref in refs:
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

        if ocr is not None and _should_ocr(downloaded):
            ocr_tasks.append(asyncio.create_task(_ocr_image(ocr, image_id, downloaded)))

    # Inline SVG text hits get positions after any downloaded images so their
    # page_images rows don't collide with the regular ones.
    position_offset = max((ref.position for ref in refs), default=-1) + 1
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

    if ocr_tasks:
        for outcome in await asyncio.gather(*ocr_tasks, return_exceptions=False):
            if outcome.succeeded:
                result.ocr_analyzed += 1
                if outcome.has_text:
                    result.ocr_text_candidates += 1
                repo.upsert_analysis(
                    conn,
                    image_id=outcome.image_id,
                    ocr_text=outcome.text or None,
                    ocr_confidence=outcome.confidence,
                    has_text=outcome.has_text,
                    model_versions={"ocr": outcome.engine_version},
                )
            else:
                result.errors += 1

    return result


def _should_ocr(image: DownloadedImage) -> bool:
    return image.mime not in _OCR_SKIP_MIMES


@dataclass(frozen=True)
class _OcrOutcome:
    image_id: int
    succeeded: bool
    text: str = ""
    confidence: float = 0.0
    has_text: bool = False
    engine_version: str = ""


async def _ocr_image(cfg: OcrConfig, image_id: int, downloaded: DownloadedImage) -> _OcrOutcome:
    """Read the blob, dispatch OCR, apply the text-candidate gate."""
    try:
        image_bytes = cfg.blob_store.path_for(downloaded.blob_path).read_bytes()
        result = await cfg.pool.run(image_bytes)
    except Exception as exc:
        log.warning("ocr.failed", url=downloaded.url, error=str(exc))
        return _OcrOutcome(image_id=image_id, succeeded=False)

    has_text = result.is_text_candidate(
        min_confidence=cfg.min_confidence, min_word_count=cfg.min_word_count
    )
    return _OcrOutcome(
        image_id=image_id,
        succeeded=True,
        text=result.text,
        confidence=result.confidence,
        has_text=has_text,
        engine_version=result.engine_version,
    )


def _svg_text_hash(visible_text: str) -> str:
    """Content hash for inline SVG text — same text anywhere hashes the same."""
    return hashlib.sha256(b"inline-svg:" + visible_text.encode("utf-8")).hexdigest()
