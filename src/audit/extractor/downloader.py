"""Fetch image bytes, compute content hash, persist to the blob store.

Caps at :data:`MAX_IMAGE_BYTES` so a misbehaving origin can't exhaust disk.
The declared MIME is taken from the response's Content-Type; we don't try to
sniff from magic numbers here because later stages (OCR, VLM) need to decode
the bytes anyway and will raise loudly on unexpected formats.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urljoin

import httpx
from PIL import Image, UnidentifiedImageError

from audit.blob_store import BlobStore
from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import APIRequestContext

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


class ImageDownloaderProtocol(Protocol):
    """Minimal downloader seam used by the extraction pipeline."""

    async def download(self, url: str) -> DownloadedImage: ...


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


class AuthenticatedImageDownloader:
    """Fetch approved images through an authenticated Playwright context.

    The browser context's request client shares its in-memory cookies and
    proxy configuration. Every initial URL and redirect is independently
    validated by the scan policy supplied by ``validate_url``. No cookie,
    header, profile, or storage-state object is exposed to this class.
    """

    def __init__(
        self,
        request_context: APIRequestContext,
        blob_store: BlobStore,
        *,
        validate_url: Callable[[str], str],
        max_bytes: int = MAX_IMAGE_BYTES,
        max_redirects: int = 3,
    ) -> None:
        self._request = request_context
        self._blobs = blob_store
        self._validate_url = validate_url
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects

    async def download(self, url: str) -> DownloadedImage:
        """Fetch one image without allowing scope or redirect escape."""

        try:
            current = self._validate_url(url)
        except Exception as exc:
            raise ImageDownloadError("Protected image is outside the approved scope.") from exc

        for redirect_index in range(self._max_redirects + 1):
            response = None
            try:
                response = await self._request.get(
                    current,
                    fail_on_status_code=False,
                    max_redirects=0,
                    timeout=30_000,
                )
                status = response.status
                headers = response.headers
                if status in {301, 302, 303, 307, 308}:
                    if redirect_index >= self._max_redirects:
                        raise ImageDownloadError("Protected image redirected too many times.")
                    location = headers.get("location")
                    if not location:
                        raise ImageDownloadError("Protected image redirect had no destination.")
                    try:
                        current = self._validate_url(urljoin(current, location))
                    except Exception as exc:
                        raise ImageDownloadError(
                            "Protected image redirect left the approved scope."
                        ) from exc
                    continue
                if status != 200:
                    raise ImageDownloadError(f"Protected image returned HTTP {status}.")

                declared_size = headers.get("content-length")
                if declared_size:
                    try:
                        if int(declared_size) > self._max_bytes:
                            raise ImageDownloadError("Protected image exceeds the size limit.")
                    except ValueError as exc:
                        raise ImageDownloadError(
                            "Protected image has an invalid size header."
                        ) from exc
                mime = (
                    (headers.get("content-type") or "application/octet-stream")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                if not mime.startswith("image/"):
                    raise ImageDownloadError("Protected image response was not an image.")
                data = await response.body()
                if len(data) > self._max_bytes:
                    raise ImageDownloadError("Protected image exceeds the size limit.")
                content_hash, blob_path = self._blobs.store(data, mime)
                width, height = _dimensions(data, mime)
                return DownloadedImage(
                    url=current,
                    content_hash=content_hash,
                    blob_path=blob_path,
                    mime=mime,
                    bytes_len=len(data),
                    width=width,
                    height=height,
                )
            except ImageDownloadError:
                raise
            except Exception as exc:
                raise ImageDownloadError("Protected image could not be retrieved.") from exc
            finally:
                if response is not None:
                    await response.dispose()

        raise ImageDownloadError("Protected image could not be retrieved.")


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
