"""Playwright chromium fetcher for JS-rendered pages.

Reuses a single browser across the whole crawl; each fetch gets a fresh
``BrowserContext`` so cookies and storage don't leak between pages. The result
shape mirrors :class:`audit.crawler.fetcher.FetchResult` so callers can treat
static and JS fetches uniformly.
"""

from __future__ import annotations

import contextlib
from types import TracebackType
from typing import TYPE_CHECKING, Self

from audit.crawler.fetcher import FetchError, FetchResult

if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright, ViewportSize

_DEFAULT_VIEWPORT: ViewportSize = {"width": 1440, "height": 900}
_NAV_TIMEOUT_MS = 30_000
_IDLE_TIMEOUT_MS = 10_000


class JsFetcher:
    """Shared-browser Playwright fetcher. Use as an async context manager."""

    def __init__(
        self,
        *,
        user_agent: str,
        viewport: ViewportSize | None = None,
        nav_timeout_ms: int = _NAV_TIMEOUT_MS,
        idle_timeout_ms: int = _IDLE_TIMEOUT_MS,
    ) -> None:
        self._user_agent = user_agent
        self._viewport = viewport or _DEFAULT_VIEWPORT
        self._nav_timeout_ms = nav_timeout_ms
        self._idle_timeout_ms = idle_timeout_ms
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> Self:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    async def fetch(self, url: str) -> FetchResult:
        """Render ``url`` with chromium and return the settled HTML.

        Raises :class:`FetchError` on navigation failure or timeout.
        """
        if self._browser is None:
            raise RuntimeError("JsFetcher used outside its async context")
        ctx = await self._browser.new_context(
            user_agent=self._user_agent,
            viewport=self._viewport,
        )
        try:
            page = await ctx.new_page()
            try:
                resp = await page.goto(url, timeout=self._nav_timeout_ms, wait_until="load")
            except Exception as exc:
                raise FetchError(f"{url}: {exc}") from exc
            # networkidle can reasonably time out on pages with live connections;
            # we still want the rendered HTML in that case.
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=self._idle_timeout_ms)
            html = await page.content()
            status = resp.status if resp is not None else 0
            headers = resp.headers if resp is not None else {}
            final_url = resp.url if resp is not None else url
            return FetchResult(
                url=final_url,
                status_code=status,
                content_type=headers.get("content-type", "text/html"),
                body=html.encode("utf-8", errors="replace"),
                retry_after=None,
            )
        finally:
            await ctx.close()
