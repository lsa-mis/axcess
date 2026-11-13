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
from dataclasses import dataclass
from typing import Literal

import httpx

#: Largest file downloaded, the same as the crawler's largest page body
#: (``StaticFetcher.max_body_bytes``), so a PDF the crawler fetched itself and
#: one downloaded here are held to one limit.
MAX_FILE_BYTES = 10 * 1024 * 1024
#: Longest one download may take, start to finish.
FETCH_TIMEOUT_S = 30.0

FetchOutcome = Literal["ok", "http_error", "broken_link", "too_large", "timed_out"]


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
