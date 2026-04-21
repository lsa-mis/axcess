"""Unit tests for HostLimiter (per-host semaphore + token-bucket RPS)."""

from __future__ import annotations

import asyncio
import time

import pytest

from audit.crawler.rate_limit import HostLimiter


@pytest.mark.asyncio
async def test_host_of_extracts_lowercase_host() -> None:
    assert HostLimiter.host_of("HTTPS://Example.COM/x") == "example.com"
    assert HostLimiter.host_of("not a url") == ""


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_requests() -> None:
    limiter = HostLimiter(rps=1000.0, concurrency_per_host=2)
    in_flight = 0
    peak = 0

    async def worker() -> None:
        nonlocal in_flight, peak
        async with limiter.throttle("https://example.com/a"):
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1

    await asyncio.gather(*(worker() for _ in range(6)))
    assert peak == 2


@pytest.mark.asyncio
async def test_rps_throttles_host() -> None:
    limiter = HostLimiter(rps=5.0, concurrency_per_host=10)
    start = time.monotonic()

    async def hit() -> None:
        async with limiter.throttle("https://example.com/a"):
            pass

    await asyncio.gather(*(hit() for _ in range(6)))
    # 6 requests at 5 rps (burst=5) should take ~0.2s for the 6th.
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15


@pytest.mark.asyncio
async def test_separate_hosts_do_not_block_each_other() -> None:
    limiter = HostLimiter(rps=1.0, concurrency_per_host=1)

    async with limiter.throttle("https://a.example/"):
        start = time.monotonic()
        async with limiter.throttle("https://b.example/"):
            elapsed = time.monotonic() - start
    assert elapsed < 0.05
