"""Unit tests for the static httpx fetcher."""

from __future__ import annotations

import httpx
import pytest
import respx

from audit.crawler.fetcher import FetchError, StaticFetcher, _parse_retry_after


@pytest.mark.asyncio
@respx.mock
async def test_fetch_200_html() -> None:
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(
            200, content=b"<html><body>hi</body></html>", headers={"content-type": "text/html"}
        )
    )
    async with httpx.AsyncClient() as client:
        result = await StaticFetcher(client).fetch("https://example.com/")
    assert result.status_code == 200
    assert result.is_ok
    assert result.is_html
    assert b"hi" in result.body


@pytest.mark.asyncio
@respx.mock
async def test_fetch_404_still_returns_result() -> None:
    respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        result = await StaticFetcher(client).fetch("https://example.com/missing")
    assert result.status_code == 404
    assert not result.is_ok


@pytest.mark.asyncio
@respx.mock
async def test_fetch_non_html_content_type() -> None:
    respx.get("https://example.com/i.png").mock(
        return_value=httpx.Response(
            200, content=b"\x89PNG\r\n", headers={"content-type": "image/png"}
        )
    )
    async with httpx.AsyncClient() as client:
        result = await StaticFetcher(client).fetch("https://example.com/i.png")
    assert result.is_ok
    assert not result.is_html


@pytest.mark.asyncio
@respx.mock
async def test_fetch_html_with_charset_param_is_html() -> None:
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(
            200, content=b"<html></html>", headers={"content-type": "text/html; charset=utf-8"}
        )
    )
    async with httpx.AsyncClient() as client:
        result = await StaticFetcher(client).fetch("https://example.com/")
    assert result.is_html


@pytest.mark.asyncio
@respx.mock
async def test_fetch_network_error_raises() -> None:
    respx.get("https://example.com/").mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError):
            await StaticFetcher(client).fetch("https://example.com/")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_follows_redirect_and_records_final_url() -> None:
    respx.get("https://example.com/old").mock(
        return_value=httpx.Response(301, headers={"location": "https://example.com/new"})
    )
    respx.get("https://example.com/new").mock(
        return_value=httpx.Response(
            200, content=b"<html></html>", headers={"content-type": "text/html"}
        )
    )
    async with httpx.AsyncClient() as client:
        result = await StaticFetcher(client).fetch("https://example.com/old")
    assert result.url == "https://example.com/new"
    assert result.status_code == 200


@pytest.mark.asyncio
@respx.mock
async def test_fetch_parses_retry_after_seconds() -> None:
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(503, headers={"retry-after": "30"})
    )
    async with httpx.AsyncClient() as client:
        result = await StaticFetcher(client).fetch("https://example.com/")
    assert result.retry_after == 30.0


@pytest.mark.asyncio
@respx.mock
async def test_fetch_truncates_oversized_body() -> None:
    body = b"x" * 5000
    respx.get("https://example.com/big").mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "text/html"})
    )
    async with httpx.AsyncClient() as client:
        result = await StaticFetcher(client, max_body_bytes=1000).fetch("https://example.com/big")
    assert len(result.body) == 1000


def test_parse_retry_after_none() -> None:
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after("not-a-date") is None


def test_parse_retry_after_seconds() -> None:
    assert _parse_retry_after("15") == 15.0


def test_parse_retry_after_http_date_in_past_is_zero() -> None:
    past = "Wed, 21 Oct 2015 07:28:00 GMT"
    assert _parse_retry_after(past) == 0.0
