"""Async HTTP fetcher for static pages.

Returns every completed HTTP response as a :class:`FetchResult` — 4xx/5xx are
not raised, since the caller wants to persist the status. Only genuine network
failures (DNS, timeout, connection reset) raise :class:`FetchError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from audit.analyzer.axe import AxeViolation
    from audit.analyzer.focus import FocusFinding
    from audit.analyzer.interaction import RevealedViolation
    from audit.analyzer.keyboard import KeyboardTrap
    from audit.analyzer.responsive import ResponsiveFinding
    from audit.analyzer.visual import VisualFinding

_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})


class FetchError(Exception):
    """Raised when a URL cannot be fetched at all (timeout, DNS, connection error)."""


@dataclass(frozen=True)
class FetchResult:
    """One completed HTTP response.

    ``axe_violations`` is populated only by :class:`JsFetcher` when it
    has been constructed with an :class:`AxeAnalyzer`. The static
    :class:`StaticFetcher` always leaves it empty — axe needs a rendered
    DOM, which httpx cannot provide. Every page goes through Playwright
    by default; only ``--static-only`` crawls hit this gap.
    """

    url: str
    status_code: int
    content_type: str
    body: bytes
    retry_after: float | None
    axe_violations: tuple[AxeViolation, ...] = field(default=())
    # SC 2.1.2 keyboard-trap probe results. Populated only by JsFetcher
    # when a KeyboardProbe is attached (default on; ``--skip-keyboard``
    # disables). Static fetches always leave it empty (probing requires
    # a live Playwright page).
    keyboard_traps: tuple[KeyboardTrap, ...] = field(default=())
    # Responsive/zoom/text-spacing probe results (SC 1.4.4 / 1.4.10 /
    # 1.4.12). Same population rules as the keyboard probe; default on,
    # ``--skip-responsive`` disables.
    responsive_findings: tuple[ResponsiveFinding, ...] = field(default=())
    # SC 2.4.11 Focus Not Obscured — live-page focus probe results. Same
    # population rules: JsFetcher only, default on, ``--skip-focus`` disables.
    focus_findings: tuple[FocusFinding, ...] = field(default=())
    # SC 1.3.2 Meaningful Sequence — visual (VLM) probe. JsFetcher only;
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
    # target_hash -> highlighted element PNG bytes, captured at scan time
    # (empty for static fetches / when capture is disabled).
    screenshots: dict[str, bytes] = field(default_factory=dict)

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
