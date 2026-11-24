"""Async HTTP fetcher for static pages.

Returns every completed HTTP response as a :class:`FetchResult`, 4xx/5xx are
not raised, since the caller wants to persist the status. Only genuine network
failures (DNS, timeout, connection reset) raise :class:`FetchError`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urljoin

import httpx

if TYPE_CHECKING:
    from playwright.async_api import APIRequestContext

    from audit.analyzer.alfa_states import AlfaPageChecks
    from audit.analyzer.axe import AxeViolation
    from audit.analyzer.focus import FocusFinding
    from audit.analyzer.forms import FormFinding
    from audit.analyzer.interaction import RevealedViolation, StateCapture
    from audit.analyzer.interaction.base import RevealedLink
    from audit.analyzer.keyboard import KeyboardTrap
    from audit.analyzer.markup import MarkupFinding
    from audit.analyzer.responsive import ResponsiveFinding
    from audit.analyzer.visual import VisualFinding
    from audit.crawler.frame_snapshot import SavedFrame
    from audit.crawler.search import SearchResult
    from audit.crawler.style_snapshot import StyleSnapshot

_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})


class FetchError(Exception):
    """Raised when a URL cannot be fetched at all (timeout, DNS, connection error)."""


@dataclass(frozen=True)
class FetchResult:
    """One completed HTTP response.

    ``axe_violations`` is populated only by :class:`JsFetcher` when it
    has been constructed with an :class:`AxeAnalyzer`. The static
    :class:`StaticFetcher` always leaves it empty, axe needs a rendered
    DOM, which httpx cannot provide. Every page goes through Playwright
    by default; only ``--static-only`` crawls hit this gap.
    """

    url: str
    status_code: int
    content_type: str
    body: bytes
    retry_after: float | None
    axe_violations: tuple[AxeViolation, ...] = field(default=())
    # Whether axe checked this page: True, False when it was asked and failed
    # (the log says why), None when the fetcher does not say (older fakes and
    # fetchers without axe), which the orchestrator reads as before.
    axe_checked: bool | None = None
    # SC 2.1.2 keyboard-trap probe results. Populated only by JsFetcher
    # when a KeyboardProbe is attached (default on; ``--skip-keyboard``
    # disables). Static fetches always leave it empty (probing requires
    # a live Playwright page).
    keyboard_traps: tuple[KeyboardTrap, ...] = field(default=())
    # Responsive/zoom/text-spacing probe results (SC 1.4.4 / 1.4.10 /
    # 1.4.12). Same population rules as the keyboard probe; default on,
    # ``--skip-responsive`` disables.
    responsive_findings: tuple[ResponsiveFinding, ...] = field(default=())
    # SC 2.4.11 Focus Not Obscured, live-page focus probe results. Same
    # population rules: JsFetcher only, default on, ``--skip-focus`` disables.
    focus_findings: tuple[FocusFinding, ...] = field(default=())
    # Page code check results (``pipeline='markup'``). JsFetcher only, run
    # right after axe; default on, ``--skip-markup`` disables. ``ran`` says
    # the check ran on this page, so a page with nothing found still counts.
    markup_findings: tuple[MarkupFinding, ...] = field(default=())
    markup_check_ran: bool = False
    # SC 1.3.2 Meaningful Sequence, visual (VLM) probe. JsFetcher only;
    # no-op without a vision model. ``--skip-visual`` disables.
    visual_findings: tuple[VisualFinding, ...] = field(default=())
    # Violations reachable only by operating a control (opening a menu,
    # expanding a form). Same population rules as the probes above;
    # opt-in via ``--interaction``. Each carries the accessible name of
    # the control that revealed it.
    interaction_findings: tuple[RevealedViolation, ...] = field(default=())
    # DOM states the interaction probe reached on this page: clicks that
    # actually changed the page. Counted whether or not the state held a
    # defect, because it measures the coverage interaction added, not the
    # findings it happened to produce.
    interaction_states: int = 0
    # Gzipped markup for the subset of those states that held a *new* finding,
    # which the stored page HTML cannot contain: that is the load state, taken
    # before the probe clicks anything. Always shorter than
    # ``interaction_states`` and not a substitute for it -- a state nothing was
    # found in is still coverage, it just has nothing to show.
    interaction_captures: tuple[StateCapture, ...] = field(default=())
    # target_hash -> highlighted element PNG bytes, captured at scan time
    # (empty for static fetches / when capture is disabled).
    screenshots: dict[str, bytes] = field(default_factory=dict)
    # True only when an attached interaction probe actually ran. Selection
    # alone cannot establish coverage (e.g. axe or the probe is unavailable).
    interaction_evaluated: bool = False
    # Per-page interaction ledger, carried separately from the findings so a
    # page whose clicks revealed no defect still reports what was operated.
    interaction_controls: int = 0
    interaction_clicks_attempted: int = 0
    interaction_clicks_succeeded: int = 0
    interaction_controls_operated: int = 0
    interaction_blocked_controls: int = 0
    interaction_limits: tuple[str, ...] = ()
    interaction_dialogs_opened: int = 0
    interaction_dialogs_stuck: int = 0
    interaction_detail: str = ""
    # The error type that stopped Click-Through early on this page, or "".
    interaction_stopped_by: str = ""
    discovered_urls: tuple[str, ...] = ()
    # Links that appeared after a click, with the control that revealed each,
    # for the Documents tab (``audit.linked_files``). JsFetcher only, when
    # the interaction probe ran.
    revealed_links: tuple[RevealedLink, ...] = ()
    search_result: SearchResult | None = None
    # The page's CSS and style fingerprint, read right after ``body`` was
    # serialized (see ``audit.crawler.style_snapshot``). Every JsFetcher
    # reads it; None from the static fetcher, for a non-HTML response, or when
    # reading failed. It is stored wherever the saved copy itself is stored.
    styles: StyleSnapshot | None = None
    # The documents of the page's frames, read with the page, before any probe
    # touched it (see ``audit.crawler.frame_snapshot``). JsFetcher only, and
    # never for a sign-in scan.
    frames: tuple[SavedFrame, ...] = field(default=())
    # SC 3.3.1 form error check: forms that detected an error without
    # describing it. JsFetcher only, when the check is turned on, and never
    # in a sign-in scan.
    form_findings: tuple[FormFinding, ...] = field(default=())
    # Their screenshots: target_hash -> (before the press, after it), each an
    # outlined PNG or None. Empty when the scan keeps no screenshots.
    form_screenshots: dict[str, tuple[bytes | None, bytes | None]] = field(default_factory=dict)
    # Whether the form error check ran on this page, and how many forms ended
    # in each outcome ("fail", "pass", "skipped", "not_checked", ...), for the
    # report's "What was checked" counts.
    form_check_ran: bool = False
    form_outcomes: dict[str, int] = field(default_factory=dict)
    # Alfa's checks of this page, at load and in each state Click-Through
    # opened. They finish in the background (the tab only took snapshots),
    # so the orchestrator awaits them with ``alfa_states.settle``. ``None``
    # when Alfa did not check this page in the crawler's tab.
    alfa_checks: AlfaPageChecks | None = None

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


class PageFetcher(Protocol):
    """What the crawl needs from a static fetcher: one page's response."""

    async def fetch(self, url: str) -> FetchResult: ...


class AuthenticatedStaticFetcher:
    """A static fetch through a signed-in browser's own request client.

    A sign-in scan's "Load pages without running scripts" (2026-11-16): the
    page's code comes from ``APIRequestContext.get``, which carries the
    signed-in context's cookies, so the response is the signed-in page, not
    an anonymous one. A sign-in kept only in sessionStorage is not sent this
    way, which the New scan form's hint says. Every address, and every
    redirect, is checked by ``validate_url`` (the sign-in scan's egress
    policy) before it is requested, the same rule as
    ``AuthenticatedImageDownloader``.
    """

    def __init__(
        self,
        request_context: APIRequestContext,
        *,
        validate_url: Callable[[str], str],
        max_body_bytes: int = 10 * 1024 * 1024,
        max_redirects: int = 5,
        timeout_ms: float = 30_000,
    ) -> None:
        self._request = request_context
        self._validate_url = validate_url
        self._max_body_bytes = max_body_bytes
        self._max_redirects = max_redirects
        self._timeout_ms = timeout_ms

    async def fetch(self, url: str) -> FetchResult:
        """Fetch ``url``. Raises :class:`FetchError` on failure or scope escape."""
        try:
            current = self._validate_url(url)
        except Exception as exc:
            raise FetchError("address is outside the scan's scope") from exc
        for _ in range(self._max_redirects + 1):
            response = None
            try:
                response = await self._request.get(
                    current,
                    fail_on_status_code=False,
                    max_redirects=0,
                    timeout=self._timeout_ms,
                )
                status = response.status
                headers = response.headers
                if status in {301, 302, 303, 307, 308} and headers.get("location"):
                    try:
                        current = self._validate_url(urljoin(current, headers["location"]))
                    except Exception as exc:
                        raise FetchError("redirect left the scan's scope") from exc
                    continue
                body = (await response.body())[: self._max_body_bytes]
                return FetchResult(
                    url=current,
                    status_code=status,
                    content_type=headers.get("content-type", ""),
                    body=body,
                    retry_after=_parse_retry_after(headers.get("retry-after")),
                )
            except FetchError:
                raise
            except Exception as exc:
                # The class only: a protected page's error text can carry
                # session detail.
                raise FetchError(type(exc).__name__) from exc
            finally:
                if response is not None:
                    await response.dispose()
        raise FetchError("too many redirects")


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
