"""Unit tests for ImageDownloader."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
import respx
from PIL import Image

from audit.blob_store import BlobStore
from audit.extractor.downloader import ImageDownloader, ImageDownloadError


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
