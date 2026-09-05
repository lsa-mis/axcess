"""Per-host concurrency and rate limiting for the crawler.

``HostLimiter`` owns one :class:`asyncio.Semaphore` and one token-bucket
rate limiter per host. Acquire with :meth:`throttle` as an async context
manager, it blocks until both budgets allow the request.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit


class _TokenBucket:
    """Simple asyncio token bucket. Tokens regenerate at ``rps`` per second."""

    def __init__(self, rps: float, burst: float) -> None:
        self._rps = rps
        self._capacity = max(burst, 1.0)
        self._tokens = self._capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def take(self) -> None:
        """Await until one token is available, then consume it."""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rps)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                wait = deficit / self._rps if self._rps > 0 else 0.1
            await asyncio.sleep(wait)


class HostLimiter:
    """Coordinate per-host concurrency and rate limits for the crawler."""

    def __init__(self, *, rps: float = 2.0, concurrency_per_host: int = 2) -> None:
        self._rps = rps
        self._concurrency = concurrency_per_host
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._buckets: dict[str, _TokenBucket] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def host_of(url: str) -> str:
        return (urlsplit(url).hostname or "").lower()

    async def _get(self, host: str) -> tuple[asyncio.Semaphore, _TokenBucket]:
        async with self._lock:
            sem = self._semaphores.get(host)
            if sem is None:
                sem = asyncio.Semaphore(self._concurrency)
                self._semaphores[host] = sem
            bucket = self._buckets.get(host)
            if bucket is None:
                bucket = _TokenBucket(rps=self._rps, burst=self._rps)
                self._buckets[host] = bucket
        return sem, bucket

    @asynccontextmanager
    async def throttle(self, url: str) -> AsyncIterator[None]:
        """Acquire both the host semaphore and a token from its bucket."""
        host = self.host_of(url)
        sem, bucket = await self._get(host)
        async with sem:
            await bucket.take()
            yield
