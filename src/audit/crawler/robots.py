"""robots.txt fetch, cache, and policy check.

Network errors fail open (allow all) per RFC 9309 §2.3.1.3. 4xx responses also
allow all; 5xx responses disallow all (treat as transient unavailability that
shouldn't surprise-crawl a site). Honors ``--ignore-robots`` at the caller level.
"""

from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

from audit.logging import get_logger

log = get_logger(__name__)


@dataclass
class RobotsInfo:
    """Parsed robots.txt for a single origin."""

    parser: urllib.robotparser.RobotFileParser
    sitemaps: list[str] = field(default_factory=list)
    fetched_at: float = 0.0
    failed: bool = False


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _extract_sitemaps(robots_text: str) -> list[str]:
    """Pull ``Sitemap:`` directives out of a robots.txt body (case-insensitive)."""
    out: list[str] = []
    for raw_line in robots_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, value = line.partition(":")
        if head.strip().lower() == "sitemap":
            value = value.strip()
            if value:
                out.append(value)
    return out


class RobotsChecker:
    """Per-origin robots.txt cache + allowed/crawl-delay lookups."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        user_agent: str,
        ttl_seconds: float = 3600.0,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._ttl = ttl_seconds
        self._cache: dict[str, RobotsInfo] = {}

    async def get_info(self, url: str) -> RobotsInfo:
        """Return the cached (or freshly fetched) ``RobotsInfo`` for the url's origin."""
        origin = _origin_of(url)
        info = self._cache.get(origin)
        now = time.monotonic()
        if info is not None and (now - info.fetched_at) < self._ttl:
            return info
        info = await self._fetch(origin)
        self._cache[origin] = info
        return info

    async def allowed(self, url: str) -> bool:
        info = await self.get_info(url)
        return bool(info.parser.can_fetch(self._user_agent, url))

    async def crawl_delay(self, url: str) -> float | None:
        info = await self.get_info(url)
        delay = info.parser.crawl_delay(self._user_agent)
        if delay is None:
            return None
        try:
            return float(delay)
        except (TypeError, ValueError):
            return None

    async def _fetch(self, origin: str) -> RobotsInfo:
        robots_url = urljoin(origin + "/", "robots.txt")
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            resp = await self._client.get(robots_url, follow_redirects=True)
        except httpx.HTTPError as exc:
            log.warning("robots.fetch_failed", origin=origin, error=str(exc))
            parser.allow_all = True  # type: ignore[attr-defined]
            parser.parse([])
            return RobotsInfo(parser=parser, fetched_at=time.monotonic(), failed=True)

        if resp.status_code >= 500:
            parser.disallow_all = True  # type: ignore[attr-defined]
            parser.parse([])
            return RobotsInfo(parser=parser, fetched_at=time.monotonic(), failed=True)

        if resp.status_code >= 400:
            parser.allow_all = True  # type: ignore[attr-defined]
            parser.parse([])
            return RobotsInfo(parser=parser, fetched_at=time.monotonic())

        text = resp.text
        parser.parse(text.splitlines())
        sitemaps = _extract_sitemaps(text)
        return RobotsInfo(parser=parser, sitemaps=sitemaps, fetched_at=time.monotonic())
