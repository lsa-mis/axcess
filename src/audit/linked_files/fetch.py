"""Download one linked file, with a size limit and a time limit.

The crawler's own fetcher (:class:`audit.crawler.fetcher.StaticFetcher`)
reads a whole response into memory before cutting it to size, which is fine
for pages and not for files: a linked file can be gigabytes. This reads the
body in chunks and stops one chunk past the limit, so a file too large is
never held whole. It uses the crawl's own HTTP client (same user agent,
same timeouts), and the caller applies the crawl's rate limit and robots.txt.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import urljoin

import httpx

if TYPE_CHECKING:
    from playwright.async_api import APIRequestContext

#: Largest file downloaded, the same as the crawler's largest page body
#: (``StaticFetcher.max_body_bytes``), so a PDF the crawler fetched itself and
#: one downloaded here are held to one limit.
MAX_FILE_BYTES = 10 * 1024 * 1024
#: Longest one download may take, start to finish.
FETCH_TIMEOUT_S = 30.0

FetchOutcome = Literal["ok", "http_error", "broken_link", "too_large", "timed_out", "blocked"]


@dataclass(frozen=True)
class FetchedFile:
    outcome: FetchOutcome
    http_status: int | None = None
    content_type: str | None = None
    body: bytes = b""


async def fetch_file(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = MAX_FILE_BYTES,
    timeout_s: float = FETCH_TIMEOUT_S,
) -> FetchedFile:
    """Fetch ``url``. Never raises for a network fault; says what happened."""
    try:
        async with asyncio.timeout(timeout_s):
            async with client.stream("GET", url, follow_redirects=True) as response:
                status = response.status_code
                content_type = response.headers.get("content-type")
                if status >= 400:
                    return FetchedFile("http_error", status, content_type)
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    return FetchedFile("too_large", status, content_type)
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        return FetchedFile("too_large", status, content_type)
                    chunks.append(chunk)
                return FetchedFile("ok", status, content_type, b"".join(chunks))
    except TimeoutError:
        return FetchedFile("timed_out")
    except httpx.TimeoutException:
        return FetchedFile("timed_out")
    except (httpx.HTTPError, ValueError):
        return FetchedFile("broken_link")


#: How a download is made: ``fetch_file`` with the crawl's client, or, in a
#: sign-in scan, ``SignedInFileFetcher``. Takes the address, says what happened.
FileFetcher = Callable[[str], Awaitable[FetchedFile]]

_REDIRECTS = {301, 302, 303, 307, 308}


class SignedInFileFetcher:
    """Download a linked file through a signed-in browser's request client.

    A sign-in scan's document check (the developer's decision, 2026-11-16):
    a PDF behind the sign-in is downloaded the way the person signed in
    would open it, with the browser context's cookies, never as an anonymous
    request that would get a sign-in page instead. Every address and every
    redirect is checked by ``validate_url``, the sign-in scan's egress
    policy, before it is requested, as ``AuthenticatedStaticFetcher`` does
    for pages; an address it refuses (a file on another site) is not
    downloaded at all, and is reported as ``blocked``.

    Playwright reads a response whole, so this cannot stop a download part
    way as ``fetch_file`` does. It asks first (HEAD) and does not download a
    file whose declared size is over the limit; a server that declares no
    size is downloaded, cut off by the time limit, and refused after if too
    large.
    """

    def __init__(
        self,
        request_context: APIRequestContext,
        *,
        validate_url: Callable[[str], str],
        max_bytes: int = MAX_FILE_BYTES,
        timeout_s: float = FETCH_TIMEOUT_S,
        max_redirects: int = 5,
    ) -> None:
        self._request = request_context
        self._validate_url = validate_url
        self._max_bytes = max_bytes
        self._timeout_s = timeout_s
        self._max_redirects = max_redirects

    async def __call__(self, url: str) -> FetchedFile:
        try:
            async with asyncio.timeout(self._timeout_s):
                return await self._fetch(url)
        except TimeoutError:
            return FetchedFile("timed_out")
        except Exception:  # Playwright raises its own errors for network faults
            return FetchedFile("broken_link")

    def _allowed(self, url: str) -> str | None:
        try:
            return self._validate_url(url)
        except Exception:
            return None

    async def _fetch(self, url: str) -> FetchedFile:
        current = self._allowed(url)
        if current is None:
            return FetchedFile("blocked")
        timeout_ms = self._timeout_s * 1000
        for _ in range(self._max_redirects + 1):
            head = await self._request.head(
                current, fail_on_status_code=False, max_redirects=0, timeout=timeout_ms
            )
            if head.status in _REDIRECTS and head.headers.get("location"):
                current = self._allowed(urljoin(current, head.headers["location"]))
                if current is None:
                    return FetchedFile("blocked")
                continue
            declared = head.headers.get("content-length", "")
            if head.status < 400 and declared.isdigit() and int(declared) > self._max_bytes:
                return FetchedFile("too_large", head.status, head.headers.get("content-type"))
            response = await self._request.get(
                current, fail_on_status_code=False, max_redirects=0, timeout=timeout_ms
            )
            status = response.status
            content_type = response.headers.get("content-type")
            if status in _REDIRECTS and response.headers.get("location"):
                current = self._allowed(urljoin(current, response.headers["location"]))
                if current is None:
                    return FetchedFile("blocked")
                continue
            if status >= 400:
                return FetchedFile("http_error", status, content_type)
            body = await response.body()
            if len(body) > self._max_bytes:
                return FetchedFile("too_large", status, content_type)
            return FetchedFile("ok", status, content_type, body)
        return FetchedFile("broken_link")
