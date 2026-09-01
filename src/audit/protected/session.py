"""Companion-side, manual authentication for protected accessibility scans.

This module owns a headed Playwright browser context only on the auditor's
machine. The auditor completes sign-in and any second factor directly in that
window. No method exports Playwright storage state, cookies, credentials, or
MFA material; closing the context destroys the session in memory.

It is intentionally independent of FastAPI, the public crawler, the CLI, and
database persistence. A future paired companion can use it as the narrow
boundary between manual sign-in and a shared-context accessibility fetcher.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urlsplit

from audit.analyzer.alfa import AlfaAnalyzer, AlfaResult
from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.axe import Level as AxeLevel
from audit.analyzer.focus import FocusProbe
from audit.analyzer.interaction import InteractionProbe
from audit.analyzer.keyboard import KeyboardProbe
from audit.analyzer.responsive import ResponsiveProbe
from audit.analyzer.visual import VisualProbe
from audit.blob_store import BlobStore
from audit.crawler.js_fetcher import JsFetcher
from audit.extractor.downloader import AuthenticatedImageDownloader
from audit.logging import get_logger
from audit.protected.egress import (
    EgressViolation,
    HostResolver,
    LoopbackEgressProxy,
    PlaywrightRoutePolicy,
    ProtectedEgressPolicy,
    PublicHttpsManualAuthPolicy,
    ValidatedUrl,
)

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright, Route

_DEFAULT_USER_AGENT = "axcess/0.1 (+authorized protected accessibility audit)"
_DEFAULT_NAV_TIMEOUT_MS = 30_000
log = get_logger(__name__)

_DEFAULT_AUTH_WAIT_MS = 5 * 60 * 1000
_AUTH_POLL_INTERVAL_S = 0.25
_SETUP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "POST"})
_EPHEMERAL_PROFILE_PREFIX = "axcess-protected-browser-"
_WEBRTC_BLOCK_INIT_SCRIPT = """
// Protected scans must not establish a direct UDP/STUN path around the
// loopback egress proxy. This is defense in depth alongside Chromium's
// disable_non_proxied_udp policy; page content is untrusted and never gets a
// working WebRTC constructor.
for (const name of ["RTCPeerConnection", "webkitRTCPeerConnection", "mozRTCPeerConnection"]) {
  try {
    Object.defineProperty(globalThis, name, {
      value: undefined,
      configurable: false,
      writable: false,
    });
  } catch (_) {}
}
"""


class ManualAuthState(StrEnum):
    """Lifecycle of a local headed companion browser context."""

    NEW = "new"
    AWAITING_MANUAL_AUTHENTICATION = "awaiting_manual_authentication"
    AUTHENTICATED = "authenticated"
    CLOSED = "closed"


class ManualAuthenticationError(RuntimeError):
    """Manual authentication did not reach a safe, approved target page."""


@dataclass(frozen=True, slots=True)
class ManualAuthPolicies:
    """Immutable egress policies for setup and post-authenticated crawling."""

    target: ProtectedEgressPolicy
    setup: ProtectedEgressPolicy
    scan: ProtectedEgressPolicy
    setup_navigation_origins: frozenset[str] | None
    setup_write_origins: frozenset[str] | None


def build_manual_auth_policies(
    *,
    approved_target_origins: Iterable[str],
    approved_auth_origins: Iterable[str] = (),
    approved_cdn_origins: Iterable[str] = (),
    resolver: HostResolver | None = None,
    allow_any_public_auth_origin: bool = False,
) -> ManualAuthPolicies:
    """Build explicit setup and scan policies from approved origin groups.

    The setup policy can reach exact target, identity-provider, and CDN
    origins. After successful manual verification, the scan policy removes
    identity-provider origins while retaining explicitly approved CDN assets.
    """
    targets = tuple(approved_target_origins)
    auth = tuple(approved_auth_origins)
    cdns = tuple(approved_cdn_origins)
    target_policy = ProtectedEgressPolicy(targets, resolver=resolver)
    setup_policy = (
        PublicHttpsManualAuthPolicy(resolver=resolver)
        if allow_any_public_auth_origin
        else ProtectedEgressPolicy((*targets, *auth, *cdns), resolver=resolver)
    )
    # An origin allowlist cannot describe a real web application. Its data
    # comes from a sibling host, its assets from CDNs, its fonts and payment
    # widgets from third parties, and the course tools this exists to audit
    # are whole products embedded from other companies. Approving only the
    # origin the auditor typed meant the application could not load its own
    # data once scanning began, so it rendered its signed-out view and every
    # scan captured a login form instead of the product.
    #
    # a11y-crawler scans these applications successfully and intercepts
    # nothing at all. Public HTTPS with a public-address check is what
    # remains here: a scan still cannot be pointed at a loopback or private
    # host, and nothing else is second-guessed.
    scan_policy = PublicHttpsManualAuthPolicy(resolver=resolver)
    target_origin_values = frozenset(target_policy.allowed_origins)
    auth_origin_values = frozenset(
        ProtectedEgressPolicy(auth, resolver=resolver).allowed_origins if auth else ()
    )
    return ManualAuthPolicies(
        target=target_policy,
        setup=setup_policy,
        scan=scan_policy,
        setup_navigation_origins=(
            None if allow_any_public_auth_origin else target_origin_values | auth_origin_values
        ),
        setup_write_origins=(
            None if allow_any_public_auth_origin else target_origin_values | auth_origin_values
        ),
    )


def validate_protected_seed_url(seed_url: str, policies: ManualAuthPolicies) -> ValidatedUrl:
    """Require the manual-auth entry URL to be an approved application origin."""
    try:
        return policies.target.validate_url(seed_url)
    except EgressViolation as exc:
        raise ManualAuthenticationError(
            "The protected scan seed is not an approved target URL."
        ) from exc


def _origin_only(url: str) -> str:
    """Scheme and host of ``url``; never its path, query, or fragment.

    A protected request path can carry identifiers or session material, so
    diagnostics record only which origin was involved.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "(unparseable)"
    if not parts.scheme or not parts.hostname:
        return "(opaque)"
    return f"{parts.scheme}://{parts.hostname}"


def verify_authenticated_target_url(url: str, policies: ManualAuthPolicies) -> ValidatedUrl:
    """Accept only a clean page at an approved *target* origin.

    This is deliberately not a claim that a browser session has been proven
    authenticated. It verifies the minimum safe boundary: the auditor has
    returned from an IdP page to an approved application URL with no
    credential-bearing query or fragment suitable for stored evidence.
    """
    try:
        return policies.target.validate_url(url)
    except EgressViolation as exc:
        raise ManualAuthenticationError(
            "Manual sign-in has not returned to an approved target page."
        ) from exc


class _SessionRouteGuard:
    """One context route handler whose constraints tighten after sign-in."""

    def __init__(self, policies: ManualAuthPolicies) -> None:
        self._policies = policies
        self._state = ManualAuthState.AWAITING_MANUAL_AUTHENTICATION
        self._auxiliary = PlaywrightRoutePolicy(policies.scan)
        self._last_scan_block_code: str | None = None
        self._on_auth_page: Callable[[Page], None] | None = None

    def observe_auth_pages(self, callback: Callable[[Page], None]) -> None:
        """Register the session's hook for a tab sign-in opened for itself."""

        self._on_auth_page = callback

    @property
    def context_options(self) -> dict[str, bool | str]:
        return self._auxiliary.context_options

    def activate_scan_mode(self) -> None:
        self._state = ManualAuthState.AUTHENTICATED

    def consume_scan_block_code(self) -> str | None:
        """Return one local policy denial so the crawler can fail safely.

        The value is intentionally a stable code, never a URL or browser
        diagnostic. It prevents a blocked redirect from being misreported as
        an MFA expiry while retaining no protected request detail.
        """

        code = self._last_scan_block_code
        self._last_scan_block_code = None
        return code

    async def install_on_context(self, context: BrowserContext) -> None:
        await context.route("**/*", self.handle_route)
        await context.route_web_socket("**/*", self._auxiliary.handle_web_socket)
        context.on("page", self.handle_context_page)

    async def handle_context_page(self, page: Page) -> None:
        """Close an auxiliary tab — unless sign-in is what opened it.

        While scanning, a tab with an opener is never legitimate: the crawler
        creates every page it uses, so anything else is uncontrolled
        navigation that must not become evidence. That rule stays exactly as
        it was once scan mode activates.

        During manual sign-in it is wrong. Institutional SSO routinely hands
        off through a new tab — an LTI launch from a VLE into the tool it
        embeds is the ordinary case, not an edge case — and closing it on
        arrival made those applications impossible to sign in to at all. The
        auditor watched the tab they needed vanish.

        Keeping the tab is a much smaller concession than it looks, because
        it is not what constrains the popup. Every request the tab makes
        still goes through ``handle_route`` under the setup policy, so it can
        only reach approved target and auth origins whether or not the tab
        itself survives. Closing it was defence in depth over that check, and
        during sign-in that depth costs more than it buys.
        """

        if self._state is ManualAuthState.AUTHENTICATED:
            await self._auxiliary.handle_context_page(page)
            return
        # Playwright exposes downloads per page, so the cancellation guard has
        # to be attached to each tab individually.
        page.on("download", self._auxiliary.handle_download)
        if self._on_auth_page is not None:
            self._on_auth_page(page)

    async def handle_route(self, route: Route) -> None:
        request = route.request
        method = request.method.upper()
        try:
            if self._state is ManualAuthState.AUTHENTICATED:
                self._validate_scan_request(
                    method=method,
                    url=request.url,
                    resource_type=request.resource_type,
                )
            else:
                self._validate_setup_request(
                    method=method,
                    url=request.url,
                    resource_type=request.resource_type,
                )
        except EgressViolation as exc:
            if self._state is ManualAuthState.AUTHENTICATED:
                self._last_scan_block_code = "egress_policy_blocked"
            # Log the shape of what was refused, never the URL: a protected
            # request path can carry session material. Method, resource type,
            # and the policy's own reason code are enough to tell "the app
            # could not check its session" apart from "the app tried to reach
            # an origin nobody approved" — a distinction that previously left
            # no trace at all, so a scan that captured a login form gave no
            # indication why.
            log.info(
                "protected.request_blocked",
                phase=self._state.value,
                method=method,
                resource_type=request.resource_type,
                reason=str(exc.args[0]) if exc.args else "unknown",
                origin=_origin_only(request.url),
            )
            await route.abort("blockedbyclient")
            return
        if self._state is not ManualAuthState.AUTHENTICATED:
            await route.continue_()
            return

        # Do not use ``route.fetch`` / ``route.fulfill`` here. Playwright
        # retains APIResponse bodies until they are disposed, so intercepting
        # every script, image, or response would silently buffer authenticated
        # content in the companion process. Native continuation streams the
        # resource through Chromium instead. Each routed request (including
        # redirect requests when surfaced by Playwright) is still validated;
        # the loopback CONNECT proxy independently validates every actual
        # destination origin and freshly resolved IP before it dials it. The
        # crawler validates its final document URL before extracting evidence.
        await route.continue_()

    def _validate_setup_request(self, *, method: str, url: str, resource_type: str) -> None:
        if method not in _SETUP_METHODS:
            raise EgressViolation("unsafe_method")
        # OAuth/SAML query parameters are a narrow document-navigation
        # exception while a human is actively signing in. The local direct
        # flow also permits them on public-HTTPS IdP subresources because Duo
        # and similar providers can carry opaque transaction identifiers in
        # iframe/XHR URLs. None of these URLs becomes scan evidence or a log.
        policy = (
            self._policies.setup.validate_transient_auth_url
            if resource_type == "document" or self._policies.setup_navigation_origins is None
            else self._policies.setup.validate_url
        )
        validated = policy(url)
        if (
            resource_type == "document"
            and self._policies.setup_navigation_origins is not None
            and validated.origin.value not in self._policies.setup_navigation_origins
        ):
            raise EgressViolation("document_origin_not_approved")
        if method in {"POST", "OPTIONS"} and (
            self._policies.setup_write_origins is not None
            and validated.origin.value not in self._policies.setup_write_origins
        ):
            raise EgressViolation("setup_write_origin_not_approved")

    def _validate_scan_request(self, *, method: str, url: str, resource_type: str) -> None:
        # A GET/HEAD gate stopped an application checking its own session,
        # and a resource-type gate refused images, fonts, and manifests on
        # the target origin itself — which for an accessibility audit
        # discards the alternative-text, contrast, and layout evidence being
        # collected. Neither survived contact with a real application.
        # Documents were checked against the approved *target* origins rather
        # than the scan policy, which refused a sub-frame served from
        # anywhere else — an embedded course tool from another company being
        # exactly that, and exactly what these audits are for. Which pages
        # the crawl visits is already decided by crawl scope; this layer does
        # not need a second, narrower opinion.
        self._policies.scan.validate_url(url)


async def _start_playwright() -> Playwright:
    from playwright.async_api import async_playwright

    return await async_playwright().start()


class ManualAuthenticationSession:
    """A headed, ephemeral browser session for auditor-completed sign-in.

    Call :meth:`start`, let the auditor perform sign-in in the visible browser,
    then call :meth:`wait_for_authenticated_target` after explicit human
    confirmation. Only then may :meth:`create_shared_js_fetcher` be used.
    """

    def __init__(
        self,
        *,
        seed_url: str,
        approved_target_origins: Iterable[str],
        approved_auth_origins: Iterable[str] = (),
        approved_cdn_origins: Iterable[str] = (),
        resolver: HostResolver | None = None,
        user_agent: str = _DEFAULT_USER_AGENT,
        nav_timeout_ms: int = _DEFAULT_NAV_TIMEOUT_MS,
        playwright_start: Callable[[], Awaitable[Playwright]] | None = None,
        allow_any_public_auth_origin: bool = False,
    ) -> None:
        self._policies = build_manual_auth_policies(
            approved_target_origins=approved_target_origins,
            approved_auth_origins=approved_auth_origins,
            approved_cdn_origins=approved_cdn_origins,
            resolver=resolver,
            allow_any_public_auth_origin=allow_any_public_auth_origin,
        )
        self._seed_url = validate_protected_seed_url(seed_url, self._policies).url
        self._user_agent = user_agent
        self._nav_timeout_ms = nav_timeout_ms
        self._playwright_start = playwright_start or _start_playwright
        self._route_guard = _SessionRouteGuard(self._policies)
        self._state = ManualAuthState.NEW
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        # Every tab open during sign-in, oldest first. SSO can hand off into
        # a tab it opens for itself, and the auditor finishes there — so that
        # tab, not the one we opened, is where verification must read the
        # landing URL from, and all of them have to be closed afterwards.
        self._auth_pages: list[Page] = []
        self._egress_proxy = LoopbackEgressProxy(self._policies.setup)
        self._profile_dir: str | None = None

    @property
    def state(self) -> ManualAuthState:
        return self._state

    @property
    def page(self) -> Page:
        if self._page is None:
            raise ManualAuthenticationError("The manual authentication browser is not running.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise ManualAuthenticationError("The manual authentication browser is not running.")
        return self._context

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def start(self) -> Page:
        """Open the approved seed in a headed, protected browser context."""
        if self._state is not ManualAuthState.NEW:
            raise ManualAuthenticationError(
                "The manual authentication session has already started."
            )
        try:
            self._playwright = await self._playwright_start()
            self._profile_dir = _create_ephemeral_profile_dir()
            await self._egress_proxy.start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                self._profile_dir,
                headless=False,
                args=[
                    "--incognito",
                    "--disable-background-timer-throttling",
                    "--disable-quic",
                    "--disable-background-networking",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-component-update",
                    "--disable-renderer-backgrounding",
                    "--disable-sync",
                    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                    "--disk-cache-size=1",
                    "--media-cache-size=1",
                ],
                user_agent=self._user_agent,
                accept_downloads=False,
                service_workers="block",
                proxy={"server": self._egress_proxy.server_url, "bypass": ""},
            )
            # Keep WebRTC from opening a direct UDP/STUN connection outside
            # the CONNECT-only companion proxy. The init script is applied
            # before any document script runs; Chromium's launch policy above
            # remains the transport-level enforcement.
            await self._context.add_init_script(_WEBRTC_BLOCK_INIT_SCRIPT)
            self._route_guard.observe_auth_pages(self._adopt_auth_page)
            await self._route_guard.install_on_context(self._context)
            self._page = await self._context.new_page()
            self._auth_pages.append(self._page)
            self._state = ManualAuthState.AWAITING_MANUAL_AUTHENTICATION
            await self._page.goto(
                self._seed_url,
                timeout=self._nav_timeout_ms,
                wait_until="domcontentloaded",
            )
            return self._page
        except Exception as exc:
            await self.close()
            raise ManualAuthenticationError(
                "Could not open the approved manual authentication browser."
            ) from exc

    def _adopt_auth_page(self, page: Page) -> None:
        """Make a tab that sign-in opened the one the session speaks for.

        Verification reads ``self.page``. If SSO finished in a tab it opened,
        that is where the approved landing URL is, and leaving ``_page`` on
        the original tab would verify a stale sign-in URL — and then start
        the crawl from it.
        """

        if page in self._auth_pages:
            return
        self._auth_pages.append(page)
        self._page = page
        page.on("close", self._forget_auth_page)

    def _forget_auth_page(self, page: Page) -> None:
        """Fall back to the newest surviving tab when one closes.

        An OAuth handoff window often closes itself after returning control
        to its opener, so the tab that is current a moment ago may be gone by
        the time the auditor confirms.
        """

        if page in self._auth_pages:
            self._auth_pages.remove(page)
        if self._page is page:
            self._page = self._auth_pages[-1] if self._auth_pages else None

    def verify_authenticated_target(self, url: str | None = None) -> ValidatedUrl:
        """Verify a manually confirmed return to an approved target page.

        A target-origin check is deliberately not a substitute for the human
        auditor's confirmation that sign-in completed. It does, however,
        prevent an IdP URL, a CDN URL, or a callback containing OAuth/SAML
        parameters from transitioning into scan mode.
        """
        self._require_started()
        candidate = url if url is not None else self.page.url
        verified = verify_authenticated_target_url(candidate, self._policies)
        self._route_guard.activate_scan_mode()
        self._egress_proxy.set_policy(self._policies.scan)
        self._state = ManualAuthState.AUTHENTICATED
        return verified

    async def prepare_background_scan_pages(self, count: int) -> tuple[Page, ...]:
        """Create the fixed authenticated tab pool before hiding Chromium.

        macOS restores a minimized Chromium window whenever Playwright creates
        a new top-level page. Preparing every worker tab first lets the crawl
        reuse those pages without repeatedly bringing the browser to the
        foreground. The pages and their shared authenticated context remain
        memory-only and are destroyed together at session close.
        """

        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before preparing scan tabs."
            )
        if count <= 0:
            raise ValueError("Background scan page count must be positive.")
        pages: list[Page] = []
        try:
            for _ in range(count):
                pages.append(await self.context.new_page())
        except Exception:
            for page in pages:
                with contextlib.suppress(Exception):
                    await page.close(run_before_unload=False)
            raise
        return tuple(pages)

    async def minimize_for_background_scan(self, page: Page | None = None) -> bool:
        """Minimize the headed sign-in window before reusing its context.

        Chromium cannot switch a live authenticated context from headed to
        headless mode. Minimizing the existing window preserves the memory-only
        session while allowing the auditor to keep using the computer. Some
        macOS Chromium builds ignore the minimized state, so an off-screen
        window is the verified fallback. CDP window management is best-effort
        because a platform or Chromium build may not expose a native window.
        """

        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before backgrounding the browser."
            )
        target_page = page or self._page
        if target_page is None:
            return False
        cdp_session: Any | None = None
        try:
            cdp_session = await self.context.new_cdp_session(target_page)
            window = await cdp_session.send("Browser.getWindowForTarget")
            window_id = window.get("windowId")
            if not isinstance(window_id, int):
                return False
            await cdp_session.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": {"windowState": "minimized"},
                },
            )
            bounds = await cdp_session.send("Browser.getWindowBounds", {"windowId": window_id})
            native_bounds = bounds.get("bounds", {})
            if native_bounds.get("windowState") == "minimized":
                return True

            # macOS may acknowledge but ignore `windowState=minimized`.
            # Move the persistent scan window out of the working area instead;
            # Chromium clamps it to a small off-screen edge while keeping the
            # renderer active for Playwright.
            await cdp_session.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": {
                        "windowState": "normal",
                        "left": -10_000,
                        "top": -10_000,
                        "width": 1280,
                        "height": 800,
                    },
                },
            )
            bounds = await cdp_session.send("Browser.getWindowBounds", {"windowId": window_id})
            native_bounds = bounds.get("bounds", {})
            left = native_bounds.get("left")
            return isinstance(left, int) and left < 0
        except Exception:
            return False
        finally:
            if cdp_session is not None:
                with contextlib.suppress(Exception):
                    await cdp_session.detach()

    async def discard_manual_auth_page(self) -> None:
        """Close the original headed tab once its session has been verified.

        The authenticated browser context remains in memory for the crawl,
        but the tab used for sign-in no longer has a reason to stay alive.
        Closing it stops any pre-authentication document activity that could
        otherwise continue after route policy tightens (for example a live
        identity-provider callback or event stream).
        """

        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before discarding its browser page."
            )
        pages = list(self._auth_pages)
        self._auth_pages.clear()
        self._page = None
        # Every tab sign-in used, including any SSO opened for itself: each
        # can hold a live callback or event stream that would otherwise keep
        # running after route policy tightens.
        for page in pages:
            with contextlib.suppress(Exception):
                await page.close(run_before_unload=False)

    async def wait_for_authenticated_target(
        self,
        *,
        timeout_ms: int = _DEFAULT_AUTH_WAIT_MS,
        poll_interval_s: float = _AUTH_POLL_INTERVAL_S,
    ) -> ValidatedUrl:
        """Wait for the headed browser to return to an approved target URL.

        Invoke this only after the auditor has chosen to complete manual
        sign-in. It polls the current page URL; it never reads form fields,
        cookies, local storage, passwords, OTPs, or passkey material.
        """
        self._require_started()
        if timeout_ms <= 0 or poll_interval_s <= 0:
            raise ValueError("Authentication wait timeout and poll interval must be positive.")
        deadline = monotonic() + timeout_ms / 1000
        last_error: ManualAuthenticationError | None = None
        while monotonic() < deadline:
            try:
                return self.verify_authenticated_target()
            except ManualAuthenticationError as exc:
                last_error = exc
            await asyncio.sleep(poll_interval_s)
        raise ManualAuthenticationError(
            "Timed out waiting for manual sign-in to return to an approved target page."
        ) from last_error

    def create_shared_js_fetcher(
        self,
        *,
        axe_analyzer: AxeAnalyzer | None = None,
        axe_level: AxeLevel = "AA",
        keyboard_probe: KeyboardProbe | None = None,
        responsive_probe: ResponsiveProbe | None = None,
        focus_probe: FocusProbe | None = None,
        visual_probe: VisualProbe | None = None,
        # Operates the page's controls and re-runs axe on each state a click
        # reveals. Omitting it was silent: a login scan ran with interaction
        # enabled in its config, recorded every page as probed, and reached
        # zero DOM states, because the fetcher had no probe to run.
        interaction_probe: InteractionProbe | None = None,
        capture_screenshots: bool = False,
        max_rendered_html_chars: int | None = None,
        shared_pages: tuple[Page, ...] = (),
    ) -> JsFetcher:
        """Return a fetcher that reuses this in-memory authenticated context.

        The returned fetcher closes only its per-page tabs. The companion owns
        and ultimately closes the browser context, which removes the session.
        It deliberately exposes no Playwright ``storage_state`` export.
        """
        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before starting a protected crawl."
            )
        return JsFetcher(
            user_agent=self._user_agent,
            axe_analyzer=axe_analyzer,
            axe_level=axe_level,
            keyboard_probe=keyboard_probe,
            responsive_probe=responsive_probe,
            focus_probe=focus_probe,
            visual_probe=visual_probe,
            interaction_probe=interaction_probe,
            capture_screenshots=capture_screenshots,
            shared_context=self.context,
            shared_pages=shared_pages,
            private_context=True,
            max_rendered_html_chars=max_rendered_html_chars,
        )

    def create_authenticated_image_downloader(
        self, blob_store: BlobStore
    ) -> AuthenticatedImageDownloader:
        """Use the live authenticated context for approved image requests."""

        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before retrieving protected images."
            )

        def validate_image_url(url: str) -> str:
            return self._policies.scan.validate_url(url).url

        return AuthenticatedImageDownloader(
            self.context.request,
            blob_store,
            validate_url=validate_image_url,
        )

    async def run_alfa(
        self,
        analyzer: AlfaAnalyzer,
        url: str,
        *,
        level: str = "AA",
    ) -> AlfaResult:
        """Run Alfa with one in-memory, one-use copy of the browser session.

        Alfa's maintained Playwright adapter launches its own browser, so it
        cannot attach to our existing context directly.  The companion obtains
        a transient state object only after manual verification and streams it
        straight to the local Node child through its inherited stdin pipe.
        It is never returned to a caller, written as a reusable state file,
        logged, placed in an environment variable, or retained after the
        child exits. Chromium may materialize the supplied state only inside
        the documented mode-0700 ephemeral runner profile, which is removed
        on runner cleanup and must live on encrypted ephemeral storage.
        """
        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before running Alfa."
            )
        storage_state: Any | None = None
        try:
            validated = self._policies.scan.validate_url(url)
            storage_state = await self.context.storage_state()
            return await analyzer.run(
                validated.url,
                level=level,
                storage_state=storage_state,
                # The scan policy no longer carries an allowlist, and Alfa's
                # runner keeps its own copy of the restrictions this module
                # dropped — handing it an empty set would block every
                # subresource. Give it the approved targets so it behaves as
                # it did before; lifting Alfa's own gates is separate work.
                allowed_origins=self._policies.target.allowed_origins,
                target_origins=self._policies.target.allowed_origins,
                egress_proxy=self._egress_proxy.server_url,
            )
        except EgressViolation as exc:
            raise ManualAuthenticationError("Alfa URL is outside the approved scan scope.") from exc
        finally:
            # Python cannot promise physical zeroization of immutable strings,
            # but dropping the only companion-side aggregate reference as
            # soon as the local child exits prevents deliberate retention.
            storage_state = None

    async def close(self) -> None:
        """Close the context and destroy its in-memory browser session."""
        if self._state is ManualAuthState.CLOSED:
            return
        self._state = ManualAuthState.CLOSED
        context = self._context
        browser = self._browser
        playwright = self._playwright
        self._page = None
        self._auth_pages.clear()
        self._context = None
        self._browser = None
        self._playwright = None
        if context is not None:
            with contextlib.suppress(Exception):
                await context.close()
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()
        await self._egress_proxy.close()
        profile_dir = self._profile_dir
        self._profile_dir = None
        if profile_dir is not None:
            with contextlib.suppress(Exception):
                shutil.rmtree(profile_dir)

    def _require_started(self) -> None:
        if self._state not in {
            ManualAuthState.AWAITING_MANUAL_AUTHENTICATION,
            ManualAuthState.AUTHENTICATED,
        }:
            raise ManualAuthenticationError("The manual authentication browser is not running.")

    def consume_scan_egress_block(self) -> str | None:
        """Expose only a non-sensitive post-auth egress denial code."""

        return self._route_guard.consume_scan_block_code()


def _create_ephemeral_profile_dir() -> str:
    """Create a companion-owned, mode-0700 browser scratch directory.

    Chromium can still create internal cache/profile state even for a
    Playwright nonpersistent context. Axcess never persists or reuses it: the
    controlled directory is removed on close, and stale sibling directories
    are removed before a new single-companion session starts. Production must
    place the OS temp volume on encrypted, non-backed-up ephemeral storage.
    """

    root = os.path.join(tempfile.gettempdir(), "axcess-protected-browser")
    os.makedirs(root, mode=0o700, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(root, 0o700)
    # The companion intentionally supports one protected run at a time. A
    # stale prior process cannot retain a browser profile after the next
    # launch; ignore malformed/unowned names rather than broad temp cleanup.
    with contextlib.suppress(OSError):
        for entry in os.scandir(root):
            if entry.is_dir(follow_symlinks=False) and entry.name.startswith(
                _EPHEMERAL_PROFILE_PREFIX
            ):
                shutil.rmtree(entry.path)
    path = tempfile.mkdtemp(prefix=_EPHEMERAL_PROFILE_PREFIX, dir=root)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)
    return path
