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

from audit.analyzer.alfa import AlfaAnalyzer, AlfaResult
from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.axe import Level as AxeLevel
from audit.analyzer.focus import FocusProbe
from audit.analyzer.keyboard import KeyboardProbe
from audit.analyzer.responsive import ResponsiveProbe
from audit.analyzer.visual import VisualProbe
from audit.blob_store import BlobStore
from audit.crawler.js_fetcher import JsFetcher
from audit.extractor.downloader import AuthenticatedImageDownloader
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
_DEFAULT_AUTH_WAIT_MS = 5 * 60 * 1000
_AUTH_POLL_INTERVAL_S = 0.25
_SETUP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "POST"})
# Page-driven raster/media/font loads can be arbitrarily large and are not
# required for DOM checks. Optional OCR retrieves only explicitly discovered
# image URLs through the separate size-bounded authenticated downloader.
# Scripts, stylesheets, and app XHR/fetch traffic remain eligible after
# per-request origin/IP/method validation.
_BLOCKED_SCAN_RESOURCE_TYPES = frozenset(
    {
        "worker",
        "sharedworker",
        "websocket",
        "eventsource",
        "image",
        "media",
        "font",
        "manifest",
        "prefetch",
    }
)
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
    scan_policy = ProtectedEgressPolicy((*targets, *cdns), resolver=resolver)
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
        context.on("page", self._auxiliary.handle_context_page)

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
        except EgressViolation:
            if self._state is ManualAuthState.AUTHENTICATED:
                self._last_scan_block_code = "egress_policy_blocked"
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
        if method not in {"GET", "HEAD"}:
            raise EgressViolation("unsafe_method")
        # Service workers are disabled at context creation.  Block dedicated
        # workers, shared workers, WebSocket handshakes, and event streams as
        # well: they can outlive the current page or turn an ostensibly
        # read-only browser crawl into a long-lived authenticated channel.
        if resource_type.lower() in _BLOCKED_SCAN_RESOURCE_TYPES:
            raise EgressViolation("unsafe_resource_type")
        policy = self._policies.target if resource_type == "document" else self._policies.scan
        policy.validate_url(url)


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
                    "--disable-quic",
                    "--disable-background-networking",
                    "--disable-component-update",
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
            await self._route_guard.install_on_context(self._context)
            self._page = await self._context.new_page()
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
        page = self._page
        self._page = None
        if page is not None:
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
        capture_screenshots: bool = False,
        max_rendered_html_chars: int | None = None,
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
            capture_screenshots=capture_screenshots,
            shared_context=self.context,
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
                allowed_origins=self._policies.scan.allowed_origins,
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
