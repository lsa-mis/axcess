"""Playwright chromium fetcher for JS-rendered pages.

Reuses a single browser across the whole crawl; each fetch gets a fresh
``BrowserContext`` so cookies and storage don't leak between pages. The result
shape mirrors :class:`audit.crawler.fetcher.FetchResult` so callers can treat
static and JS fetches uniformly.

When constructed with an :class:`audit.analyzer.axe.AxeAnalyzer`, each
fetch *also* runs a full WCAG axe-core pass against the rendered DOM and
attaches the violations to :attr:`FetchResult.axe_violations`. This is
the integration point for the broader WCAG 2.x AA scan — axe needs a
fully-loaded, fully-rendered DOM, and that's exactly what we have here
between ``page.goto`` and ``ctx.close``.
"""

from __future__ import annotations

import contextlib
from types import TracebackType
from typing import TYPE_CHECKING, Self

from audit.analyzer.axe import AxeAnalyzer, AxeViolation, Level
from audit.analyzer.keyboard import KeyboardProbe, KeyboardTrap
from audit.analyzer.responsive import ResponsiveFinding, ResponsiveProbe
from audit.crawler.fetcher import FetchError, FetchResult

if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright, ViewportSize

_DEFAULT_VIEWPORT: ViewportSize = {"width": 1440, "height": 900}
_NAV_TIMEOUT_MS = 30_000
_IDLE_TIMEOUT_MS = 10_000


class JsFetcher:
    """Shared-browser Playwright fetcher. Use as an async context manager.

    Pass ``axe_analyzer`` to run a WCAG axe-core scan on every fetched
    page; the violations show up on the returned :class:`FetchResult`'s
    ``axe_violations`` attribute. Pass ``None`` (the default) to skip
    the axe pass — crawl is materially faster (~50-150 ms per page saved)
    so we make it explicit, not implicit.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        viewport: ViewportSize | None = None,
        nav_timeout_ms: int = _NAV_TIMEOUT_MS,
        idle_timeout_ms: int = _IDLE_TIMEOUT_MS,
        axe_analyzer: AxeAnalyzer | None = None,
        axe_level: Level = "AA",
        keyboard_probe: KeyboardProbe | None = None,
        responsive_probe: ResponsiveProbe | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._viewport = viewport or _DEFAULT_VIEWPORT
        self._nav_timeout_ms = nav_timeout_ms
        self._idle_timeout_ms = idle_timeout_ms
        self._axe_analyzer = axe_analyzer
        self._axe_level: Level = axe_level
        # SC 2.1.2 keyboard probe. When set, runs *after* the axe scan
        # (which is read-only) but before the page closes. Order
        # matters: the probe presses Tab/Esc and alters focus state,
        # so axe must come first.
        self._keyboard_probe = keyboard_probe
        # Responsive/zoom probe. Runs LAST of all: it resizes the
        # viewport and injects CSS — the most page-mutating step —
        # and restores the viewport when done.
        self._responsive_probe = responsive_probe
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
            # Run axe against the fully-rendered DOM. We do this *before*
            # closing the context so the page is still live; the analyzer
            # injects axe.min.js and calls `axe.run` over the document.
            # On any axe failure the analyzer logs + returns []; one bad
            # page must never tank a 1000-page crawl.
            axe_violations: list[AxeViolation] = []
            if (
                self._axe_analyzer is not None
                and 200 <= status < 300
                and "text/html" in headers.get("content-type", "text/html")
            ):
                axe_violations = await self._axe_analyzer.run(page, level=self._axe_level)
            # Keyboard probe (SC 2.1.2) runs *after* axe because it
            # presses keys and alters focus — axe needs a quiet DOM.
            # Same gating as axe (success page, HTML content). Probe
            # itself never raises (it catches internally).
            keyboard_traps: list[KeyboardTrap] = []
            if (
                self._keyboard_probe is not None
                and 200 <= status < 300
                and "text/html" in headers.get("content-type", "text/html")
            ):
                keyboard_traps = await self._keyboard_probe.run(page)
            # Responsive probe LAST — it resizes the viewport and
            # injects CSS, so every read-only/quiet-DOM consumer must
            # already be done. Probe never raises; restores viewport.
            responsive_findings: list[ResponsiveFinding] = []
            if (
                self._responsive_probe is not None
                and 200 <= status < 300
                and "text/html" in headers.get("content-type", "text/html")
            ):
                responsive_findings = await self._responsive_probe.run(page)
            return FetchResult(
                url=final_url,
                status_code=status,
                content_type=headers.get("content-type", "text/html"),
                body=html.encode("utf-8", errors="replace"),
                retry_after=None,
                axe_violations=tuple(axe_violations),
                keyboard_traps=tuple(keyboard_traps),
                responsive_findings=tuple(responsive_findings),
            )
        finally:
            await ctx.close()
