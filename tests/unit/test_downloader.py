"""Unit tests for ImageDownloader."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
import respx
from PIL import Image

from audit.blob_store import BlobStore
from audit.extractor.downloader import (
    AuthenticatedImageDownloader,
    ImageDownloader,
    ImageDownloadError,
)


def _png_bytes(size: tuple[int, int] = (10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
@respx.mock
async def test_download_persists_to_blob_store(tmp_path: Path) -> None:
    png = _png_bytes((20, 30))
    respx.get("https://example.com/i.png").mock(
        return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
    )

    store = BlobStore(tmp_path)
    async with httpx.AsyncClient() as client:
        dl = ImageDownloader(client, store)
        result = await dl.download("https://example.com/i.png")

    assert result.mime == "image/png"
    assert result.bytes_len == len(png)
    assert result.width == 20
    assert result.height == 30
    assert (tmp_path / result.blob_path).read_bytes() == png


@pytest.mark.asyncio
@respx.mock
async def test_download_is_idempotent_for_same_bytes(tmp_path: Path) -> None:
    png = _png_bytes()
    respx.get("https://example.com/a.png").mock(
        return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
    )
    respx.get("https://example.com/b.png").mock(
        return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
    )

    store = BlobStore(tmp_path)
    async with httpx.AsyncClient() as client:
        dl = ImageDownloader(client, store)
        a = await dl.download("https://example.com/a.png")
        b = await dl.download("https://example.com/b.png")

    assert a.content_hash == b.content_hash
    assert a.blob_path == b.blob_path
    # Only one blob file total.
    files = list(tmp_path.rglob("*.png"))
    assert len(files) == 1


@pytest.mark.asyncio
@respx.mock
async def test_download_404_raises(tmp_path: Path) -> None:
    respx.get("https://example.com/missing.png").mock(return_value=httpx.Response(404))

    store = BlobStore(tmp_path)
    async with httpx.AsyncClient() as client:
        dl = ImageDownloader(client, store)
        with pytest.raises(ImageDownloadError):
            await dl.download("https://example.com/missing.png")


@pytest.mark.asyncio
@respx.mock
async def test_download_network_error_raises(tmp_path: Path) -> None:
    respx.get("https://example.com/i.png").mock(side_effect=httpx.ConnectError("boom"))
    store = BlobStore(tmp_path)
    async with httpx.AsyncClient() as client:
        dl = ImageDownloader(client, store)
        with pytest.raises(ImageDownloadError):
            await dl.download("https://example.com/i.png")


@pytest.mark.asyncio
@respx.mock
async def test_download_size_cap_enforced(tmp_path: Path) -> None:
    big = b"x" * 5000
    respx.get("https://example.com/big.png").mock(
        return_value=httpx.Response(200, content=big, headers={"content-type": "image/png"})
    )

    store = BlobStore(tmp_path)
    async with httpx.AsyncClient() as client:
        dl = ImageDownloader(client, store, max_bytes=1000)
        with pytest.raises(ImageDownloadError, match="exceeds max"):
            await dl.download("https://example.com/big.png")


@pytest.mark.asyncio
@respx.mock
async def test_download_svg_has_no_dimensions(tmp_path: Path) -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><text>x</text></svg>'
    respx.get("https://example.com/a.svg").mock(
        return_value=httpx.Response(200, content=svg, headers={"content-type": "image/svg+xml"})
    )
    store = BlobStore(tmp_path)
    async with httpx.AsyncClient() as client:
        dl = ImageDownloader(client, store)
        result = await dl.download("https://example.com/a.svg")
    assert result.width is None
    assert result.height is None
    assert result.blob_path.endswith(".svg")


class _BrowserResponse:
    def __init__(self, status: int, body: bytes, headers: dict[str, str]) -> None:
        self.status = status
        self.headers = headers
        self._body = body
        self.disposed = False

    async def body(self) -> bytes:
        return self._body

    async def dispose(self) -> None:
        self.disposed = True


class _BrowserRequest:
    def __init__(self, responses: list[_BrowserResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    async def get(self, url: str, **_kwargs: object) -> _BrowserResponse:
        self.urls.append(url)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_authenticated_download_validates_redirect_and_persists_image(
    tmp_path: Path,
) -> None:
    png = _png_bytes((16, 12))
    redirect = _BrowserResponse(302, b"", {"location": "/media/final.png"})
    image = _BrowserResponse(
        200,
        png,
        {"content-type": "image/png", "content-length": str(len(png))},
    )
    request = _BrowserRequest([redirect, image])
    approved: list[str] = []

    def validate(url: str) -> str:
        if not url.startswith("https://app.example.test/"):
            raise ValueError("outside scope")
        approved.append(url)
        return url

    downloader = AuthenticatedImageDownloader(
        request,  # type: ignore[arg-type]
        BlobStore(tmp_path),
        validate_url=validate,
    )
    result = await downloader.download("https://app.example.test/media/start.png")

    assert result.width == 16
    assert result.height == 12
    assert request.urls == [
        "https://app.example.test/media/start.png",
        "https://app.example.test/media/final.png",
    ]
    assert approved == request.urls
    assert redirect.disposed is True
    assert image.disposed is True


@pytest.mark.asyncio
async def test_authenticated_download_rejects_redirect_scope_escape(tmp_path: Path) -> None:
    redirect = _BrowserResponse(
        302,
        b"",
        {"location": "https://outside.example.test/private.png"},
    )
    request = _BrowserRequest([redirect])

    def validate(url: str) -> str:
        if not url.startswith("https://app.example.test/"):
            raise ValueError("outside scope")
        return url

    downloader = AuthenticatedImageDownloader(
        request,  # type: ignore[arg-type]
        BlobStore(tmp_path),
        validate_url=validate,
    )
    with pytest.raises(ImageDownloadError, match="left the approved scope"):
        await downloader.download("https://app.example.test/media/start.png")
    assert redirect.disposed is True
