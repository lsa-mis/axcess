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
from typing import TYPE_CHECKING, Any, Self

from audit.analyzer.axe import AxeAnalyzer, AxeViolation, Level
from audit.analyzer.focus import FocusFinding, FocusProbe
from audit.analyzer.keyboard import KeyboardProbe, KeyboardTrap
from audit.analyzer.responsive import ResponsiveFinding, ResponsiveProbe
from audit.analyzer.visual import VisualFinding, VisualProbe
from audit.crawler.fetcher import FetchError, FetchResult
from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright, ViewportSize

log = get_logger(__name__)

_DEFAULT_VIEWPORT: ViewportSize = {"width": 1440, "height": 900}
_NAV_TIMEOUT_MS = 30_000
_IDLE_TIMEOUT_MS = 10_000
# Per-page cap on highlighted element screenshots. Each capture costs a
# scroll + a screenshot (~50-150 ms); capping the count bounds the
# crawl-time cost on findings-dense pages without losing the typical
# handful of issues a reviewer actually wants evidence for.
MAX_SHOTS_PER_PAGE = 12


class RenderedPageTooLargeError(FetchError):
    """The caller-set rendered-HTML bound was exceeded before extraction.

    This is distinct from a navigation failure so a protected companion can
    record a safe coverage limitation instead of incorrectly asking the
    auditor to repeat MFA.
    """


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
        focus_probe: FocusProbe | None = None,
        visual_probe: VisualProbe | None = None,
        capture_screenshots: bool = False,
        shared_context: BrowserContext | None = None,
        private_context: bool = False,
        max_rendered_html_chars: int | None = None,
        headless: bool = True,
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
        # SC 2.4.11 focus probe. Runs before the responsive probe (it reads
        # geometry at the normal viewport) but after axe/keyboard. It only
        # focuses elements + reads layout — no lasting DOM mutation.
        self._focus_probe = focus_probe
        # SC 1.3.2 visual probe. Screenshots the page — must run before the
        # responsive probe resizes the viewport. No-op without a vision model.
        self._visual_probe = visual_probe
        # When set, capture a highlighted screenshot of each live-page
        # finding's element before the context closes (see ``_capture_element``).
        self._capture_screenshots = capture_screenshots
        # Protected scans own one manually-authenticated BrowserContext in the
        # local companion.  Reusing it here keeps cookies/session state in
        # memory without serialising them or creating a fresh anonymous
        # context per page.  Public scans keep the original isolated-context
        # behavior.
        self._shared_context = shared_context
        # A protected companion must never put target paths, redirect URLs, or
        # browser exception text (which can contain query/session material)
        # into the application log. Public crawling keeps the useful existing
        # diagnostics; the companion receives a generic FetchError instead.
        self._private_context = private_context
        # Public local scans can opt into a visible browser so the auditor can
        # watch page navigation. Protected scans inject their already-headed
        # shared context and ignore this launch preference.
        self._headless = headless
        if max_rendered_html_chars is not None and max_rendered_html_chars <= 0:
            raise ValueError("max_rendered_html_chars must be positive when configured")
        self._max_rendered_html_chars = max_rendered_html_chars
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> Self:
        if self._shared_context is not None:
            return self
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
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
        if self._browser is None and self._shared_context is None:
            raise RuntimeError("JsFetcher used outside its async context")
        if self._shared_context is not None:
            ctx = self._shared_context
            owns_context = False
        else:
            browser = self._browser
            if browser is None:  # Defensive narrowing for static type checking.
                raise RuntimeError("JsFetcher browser is unavailable")
            ctx = await browser.new_context(
                user_agent=self._user_agent,
                viewport=self._viewport,
            )
            owns_context = True
        page: Page | None = None
        try:
            page = await ctx.new_page()
            try:
                resp = await page.goto(url, timeout=self._nav_timeout_ms, wait_until="load")
            except Exception as exc:
                if self._private_context:
                    raise FetchError("Protected browser navigation failed.") from exc
                raise FetchError(f"{url}: {exc}") from exc
            # networkidle can reasonably time out on pages with live connections;
            # we still want the rendered HTML in that case.
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=self._idle_timeout_ms)
            if self._max_rendered_html_chars is not None:
                # Transfer only a scalar bound check to Python before asking
                # Playwright to serialize the full DOM. This prevents an
                # unexpectedly enormous authenticated document becoming a
                # retained FetchResult/evidence candidate in the companion.
                rendered_chars = await page.evaluate(
                    "() => document.documentElement ? document.documentElement.outerHTML.length : 0"
                )
                if (
                    not isinstance(rendered_chars, int)
                    or rendered_chars > self._max_rendered_html_chars
                ):
                    raise RenderedPageTooLargeError(
                        "Rendered page exceeded the configured extraction limit."
                    )
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
            # Focus probe runs before the viewport-mutating responsive probe.
            focus_findings: list[FocusFinding] = []
            if (
                self._focus_probe is not None
                and 200 <= status < 300
                and "text/html" in headers.get("content-type", "text/html")
            ):
                focus_findings = await self._focus_probe.run(page)

            # Visual (VLM) probe — screenshots, so also before the responsive
            # probe mutates the viewport.
            visual_findings: list[VisualFinding] = []
            if (
                self._visual_probe is not None
                and 200 <= status < 300
                and "text/html" in headers.get("content-type", "text/html")
            ):
                visual_findings = await self._visual_probe.run(page)

            responsive_findings: list[ResponsiveFinding] = []
            if (
                self._responsive_probe is not None
                and 200 <= status < 300
                and "text/html" in headers.get("content-type", "text/html")
            ):
                responsive_findings = await self._responsive_probe.run(page)

            # Per-finding element screenshots — captured LAST, after every
            # probe has produced its findings but before the context closes
            # (the page is still live). One bad selector or a screenshot
            # failure must never break the crawl, so the whole loop is
            # wrapped: on any error we log and ship whatever we captured.
            screenshots: dict[str, bytes] = {}
            if self._capture_screenshots:
                try:
                    all_findings: list[Any] = [
                        *axe_violations,
                        *keyboard_traps,
                        *focus_findings,
                        *visual_findings,
                        *responsive_findings,
                    ]
                    for finding in all_findings:
                        if len(screenshots) >= MAX_SHOTS_PER_PAGE:
                            break
                        kw = finding.to_repo_kwargs()
                        selector = kw["target_selector"]
                        th = kw["target_hash"]
                        if th in screenshots:
                            continue
                        if selector in ("", "body", "html", "(unknown)", "(none)"):
                            continue
                        png = await self._capture_element(page, selector)
                        if png:
                            screenshots[th] = png
                except Exception as exc:
                    if self._private_context:
                        log.warning("screenshot.capture_failed", protected_context=True)
                    else:
                        log.warning("screenshot.capture_failed", url=final_url, error=str(exc))

            return FetchResult(
                url=final_url,
                status_code=status,
                content_type=headers.get("content-type", "text/html"),
                body=html.encode("utf-8", errors="replace"),
                retry_after=None,
                axe_violations=tuple(axe_violations),
                keyboard_traps=tuple(keyboard_traps),
                responsive_findings=tuple(responsive_findings),
                focus_findings=tuple(focus_findings),
                visual_findings=tuple(visual_findings),
                screenshots=screenshots,
            )
        finally:
            # A shared authenticated context belongs to the companion, which
            # wipes it only when the scan reaches a terminal state.  Close the
            # per-page tab, never the session itself.  Public scans retain the
            # old "new context per fetch" isolation guarantee.
            if owns_context:
                await ctx.close()
            elif page is not None:
                with contextlib.suppress(Exception):
                    await page.close()

    async def _capture_element(self, page: Page, selector: str) -> bytes | None:
        """Screenshot the element at ``selector`` with a highlight outline.

        Returns padded-clip PNG bytes, or ``None`` if the element is
        missing, off-screen, too small, or anything goes wrong. The whole
        body is defensive — an invalid CSS selector, a detached node, or a
        screenshot timeout returns ``None`` rather than raising, so one bad
        finding never breaks the page's capture pass.
        """
        try:
            loc = page.locator(selector).first
            if await loc.count() == 0:
                return None
            box = await loc.bounding_box()
            if box is None or box["width"] < 2 or box["height"] < 2:
                return None
            with contextlib.suppress(Exception):
                await loc.scroll_into_view_if_needed(timeout=1500)
            box = await loc.bounding_box()
            if box is None:
                return None
            # Draw a red highlight outline so the reviewer sees the exact
            # element; stash the old inline outline to restore it after.
            with contextlib.suppress(Exception):
                await loc.evaluate(
                    "el => { el.setAttribute('data-axcess-old-outline', el.style.outline||''); "
                    "el.style.outline='3px solid #ff3b30'; el.style.outlineOffset='2px'; }"
                )
            pad = 14
            vp = page.viewport_size or {"width": 1440, "height": 900}
            x = max(0, box["x"] - pad)
            y = max(0, box["y"] - pad)
            width = min(box["width"] + 2 * pad, vp["width"] - x)
            height = min(box["height"] + 2 * pad, 700.0)
            if width < 2 or height < 2:
                return None
            png = await page.screenshot(clip={"x": x, "y": y, "width": width, "height": height})
            with contextlib.suppress(Exception):
                await loc.evaluate(
                    "el => { el.style.outline = el.getAttribute('data-axcess-old-outline')||''; "
                    "el.removeAttribute('data-axcess-old-outline'); }"
                )
            return png
        except Exception:
            return None
