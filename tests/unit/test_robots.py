"""Unit tests for RobotsChecker and _extract_sitemaps."""

from __future__ import annotations

import httpx
import pytest
import respx

from audit.crawler.robots import RobotsChecker, _extract_sitemaps

UA = "audit-test/0.1"


def test_extract_sitemaps_finds_all_variants() -> None:
    body = (
        "User-agent: *\n"
        "Disallow: /admin\n"
        "Sitemap: https://example.com/sitemap.xml\n"
        "sitemap: https://example.com/sitemap2.xml\n"
        "# Sitemap: https://example.com/ignored.xml\n"
        "SITEMAP:https://example.com/sitemap3.xml  \n"
    )
    assert _extract_sitemaps(body) == [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap2.xml",
        "https://example.com/sitemap3.xml",
    ]


def test_extract_sitemaps_empty_when_none() -> None:
    assert _extract_sitemaps("User-agent: *\nDisallow:\n") == []


@pytest.mark.asyncio
@respx.mock
async def test_allowed_when_robots_404() -> None:
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        checker = RobotsChecker(client, user_agent=UA)
        assert await checker.allowed("https://example.com/anything")


@pytest.mark.asyncio
@respx.mock
async def test_disallows_per_rules() -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /admin\n")
    )
    async with httpx.AsyncClient() as client:
        checker = RobotsChecker(client, user_agent=UA)
        assert await checker.allowed("https://example.com/public")
        assert not await checker.allowed("https://example.com/admin/users")


@pytest.mark.asyncio
@respx.mock
async def test_cache_reuses_single_fetch() -> None:
    route = respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    async with httpx.AsyncClient() as client:
        checker = RobotsChecker(client, user_agent=UA)
        await checker.allowed("https://example.com/a")
        await checker.allowed("https://example.com/b")
        await checker.crawl_delay("https://example.com/c")
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_crawl_delay_parsed() -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nCrawl-delay: 5\nAllow: /\n")
    )
    async with httpx.AsyncClient() as client:
        checker = RobotsChecker(client, user_agent=UA)
        assert await checker.crawl_delay("https://example.com/") == 5.0


@pytest.mark.asyncio
@respx.mock
async def test_fail_open_on_network_error() -> None:
    respx.get("https://example.com/robots.txt").mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as client:
        checker = RobotsChecker(client, user_agent=UA)
        info = await checker.get_info("https://example.com/x")
        assert info.failed is True
        assert await checker.allowed("https://example.com/x")


@pytest.mark.asyncio
@respx.mock
async def test_5xx_disallows_all() -> None:
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as client:
        checker = RobotsChecker(client, user_agent=UA)
        assert not await checker.allowed("https://example.com/anything")


@pytest.mark.asyncio
@respx.mock
async def test_sitemaps_surfaced_through_info() -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n",
        )
    )
    async with httpx.AsyncClient() as client:
        checker = RobotsChecker(client, user_agent=UA)
        info = await checker.get_info("https://example.com/")
        assert info.sitemaps == ["https://example.com/sitemap.xml"]
