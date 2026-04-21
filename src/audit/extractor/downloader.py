"""Fetch image bytes, compute content hash, persist to the blob store.

Caps at :data:`MAX_IMAGE_BYTES` so a misbehaving origin can't exhaust disk.
The declared MIME is taken from the response's Content-Type; we don't try to
sniff from magic numbers here because later stages (OCR, VLM) need to decode
the bytes anyway and will raise loudly on unexpected formats.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import httpx
from PIL import Image, UnidentifiedImageError

from audit.blob_store import BlobStore
from audit.logging import get_logger

log = get_logger(__name__)

MAX_IMAGE_BYTES = 25 * 1024 * 1024


class ImageDownloadError(Exception):
    """Raised when the image cannot be fetched or is larger than ``MAX_IMAGE_BYTES``."""


@dataclass(frozen=True)
class DownloadedImage:
    """Successfully downloaded image with its content-addressed location."""

    url: str
    content_hash: str
    blob_path: str
    mime: str
    bytes_len: int
    width: int | None
    height: int | None


class ImageDownloader:
    """Wraps an ``httpx.AsyncClient`` + ``BlobStore`` to persist image bytes."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        blob_store: BlobStore,
        *,
        max_bytes: int = MAX_IMAGE_BYTES,
    ) -> None:
        self._client = client
        self._blobs = blob_store
        self._max_bytes = max_bytes

    async def download(self, url: str) -> DownloadedImage:
        """Fetch ``url`` and persist the bytes. Raises :class:`ImageDownloadError`."""
        try:
            resp = await self._client.get(url, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise ImageDownloadError(f"{url}: {exc}") from exc
        if resp.status_code != 200:
            raise ImageDownloadError(f"{url}: HTTP {resp.status_code}")

        data = resp.content
        if len(data) > self._max_bytes:
            raise ImageDownloadError(f"{url}: {len(data)} bytes exceeds max {self._max_bytes}")

        mime = (
            (resp.headers.get("content-type") or "application/octet-stream")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        content_hash, blob_path = self._blobs.store(data, mime)
        width, height = _dimensions(data, mime)
        return DownloadedImage(
            url=str(resp.url),
            content_hash=content_hash,
            blob_path=blob_path,
            mime=mime,
            bytes_len=len(data),
            width=width,
            height=height,
        )


def _dimensions(data: bytes, mime: str) -> tuple[int | None, int | None]:
    """Best-effort dimension read. SVG and unknown formats return (None, None)."""
    if mime == "image/svg+xml":
        return None, None
    try:
        with Image.open(io.BytesIO(data)) as img:
            return img.width, img.height
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        log.debug("image.dimensions_failed", mime=mime, error=str(exc))
        return None, None
