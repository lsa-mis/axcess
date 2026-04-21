"""Unit tests for sitemap discovery + parsing."""

from __future__ import annotations

import httpx
import pytest
import respx

from audit.crawler.sitemap import discover_sitemaps, urls_from_sitemap

URLSET_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
</urlset>
"""

INDEX_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>
</sitemapindex>
"""

CHILD_1 = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/x</loc></url>
</urlset>
"""

CHILD_2 = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/y</loc></url>
</urlset>
"""


@pytest.mark.asyncio
@respx.mock
async def test_urls_from_urlset() -> None:
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=URLSET_XML)
    )
    async with httpx.AsyncClient() as client:
        urls = await urls_from_sitemap(client, "https://example.com/sitemap.xml")
    assert urls == ["https://example.com/a", "https://example.com/b"]


@pytest.mark.asyncio
@respx.mock
async def test_sitemap_index_follows_children() -> None:
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=INDEX_XML)
    )
    respx.get("https://example.com/sitemap-1.xml").mock(
        return_value=httpx.Response(200, content=CHILD_1)
    )
    respx.get("https://example.com/sitemap-2.xml").mock(
        return_value=httpx.Response(200, content=CHILD_2)
    )
    async with httpx.AsyncClient() as client:
        urls = await urls_from_sitemap(client, "https://example.com/sitemap.xml")
    assert urls == ["https://example.com/x", "https://example.com/y"]


@pytest.mark.asyncio
@respx.mock
async def test_urls_from_bad_xml_returns_empty() -> None:
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=b"<not-xml")
    )
    async with httpx.AsyncClient() as client:
        assert await urls_from_sitemap(client, "https://example.com/sitemap.xml") == []


@pytest.mark.asyncio
@respx.mock
async def test_urls_from_404_returns_empty() -> None:
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        assert await urls_from_sitemap(client, "https://example.com/sitemap.xml") == []


@pytest.mark.asyncio
@respx.mock
async def test_urls_from_network_error_returns_empty() -> None:
    respx.get("https://example.com/sitemap.xml").mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as client:
        assert await urls_from_sitemap(client, "https://example.com/sitemap.xml") == []


def test_discover_includes_robots_and_conventional() -> None:
    out = discover_sitemaps(
        "https://example.com/start",
        robots_declared=["https://example.com/custom.xml"],
    )
    assert out == [
        "https://example.com/custom.xml",
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap_index.xml",
    ]


def test_discover_dedupes_overlap() -> None:
    out = discover_sitemaps(
        "https://example.com/",
        robots_declared=["https://example.com/sitemap.xml"],
    )
    assert out == [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap_index.xml",
    ]
