"""Async HTTP fetcher for static pages.

Returns every completed HTTP response as a :class:`FetchResult` — 4xx/5xx are
not raised, since the caller wants to persist the status. Only genuine network
failures (DNS, timeout, connection reset) raise :class:`FetchError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})


class FetchError(Exception):
    """Raised when a URL cannot be fetched at all (timeout, DNS, connection error)."""


@dataclass(frozen=True)
class FetchResult:
    """One completed HTTP response."""

    url: str
    status_code: int
    content_type: str
    body: bytes
    retry_after: float | None

    @property
    def is_html(self) -> bool:
        return self.content_type.split(";", 1)[0].strip().lower() in _HTML_CONTENT_TYPES

    @property
    def is_ok(self) -> bool:
        return 200 <= self.status_code < 300


class StaticFetcher:
    """Thin wrapper around ``httpx.AsyncClient`` with a uniform result type."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_body_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._client = client
        self._max_body_bytes = max_body_bytes

    async def fetch(self, url: str) -> FetchResult:
        """Fetch ``url``. Raises :class:`FetchError` on network failure."""
        try:
            resp = await self._client.get(url, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise FetchError(f"{url}: {exc}") from exc

        body = resp.content[: self._max_body_bytes]
        return FetchResult(
            url=str(resp.url),
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type", ""),
            body=body,
            retry_after=_parse_retry_after(resp.headers.get("retry-after")),
        )


def _parse_retry_after(raw: str | None) -> float | None:
    """Parse ``Retry-After`` (RFC 7231 §7.1.3) as either seconds or HTTP-date.

    Returns the delay in seconds from now, or ``None`` if missing/unparseable.
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    from datetime import UTC, datetime

    delta = (dt - datetime.now(UTC)).total_seconds()
    return max(0.0, delta)
