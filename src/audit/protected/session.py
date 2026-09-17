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
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urlsplit

from audit.analyzer.alfa import AlfaAnalyzer, AlfaResult
from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.axe import Level as AxeLevel
from audit.analyzer.focus import FocusProbe
from audit.analyzer.interaction import InteractionProbe
from audit.analyzer.interaction.safety import report_refused_popup
from audit.analyzer.keyboard import KeyboardProbe
from audit.analyzer.responsive import ResponsiveProbe
from audit.analyzer.visual import VisualProbe
from audit.blob_store import BlobStore
from audit.crawler.js_fetcher import JsFetcher
from audit.crawler.search import SearchExplorer
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
# A tab the scanned application opens for itself was never evidence: the
# route guard closes it on arrival. Closing it is too late for the window,
# though. Chromium raises a minimized window the moment a tab is created in
# it, so every such click put the browser back in front of the auditor. While
# scanning, the request is refused where it starts instead, and only the
# request for a *new* tab: ``window.open(url, "_self")``, a named frame, and
# every ordinary navigation go through untouched, because a legacy application
# that redirects that way has to keep working. Where a refused tab was headed
# is reported through a binding, as its first request used to be, because a
# button that opens a tab leaves no href for the crawler to find (see
# ``report_refused_popup``). Playwright starts Chromium with popup blocking
# off, so a tab opened without a gesture was learned from before and still is.
#
# The ways in are wider than ``window.open``. A script can build an anchor it
# never attaches and call ``click()`` on it, call ``form.submit()`` (which
# fires no event), or put the link inside a shadow root, where ``event.target``
# names the host. Each is covered below. What is not: a closed shadow root,
# and a synthetic event dispatched at a detached node. The session re-hides
# the window for those (``_keep_hidden``); they cost a flash, not the scan.
#
# Native dialogs get the same treatment. ``print()`` blocks its tab on a
# preview nobody can see: a click that reached it never returned. A file
# chooser is refused in the page rather than left to Playwright to intercept,
# because an intercepted chooser stays pending, and measured on macOS one in
# six of those put the minimized window back on screen when the tab navigated.
_SCAN_QUIET_INIT_SCRIPT = """
(() => {
  try {
    Object.defineProperty(window, "print", {
      configurable: false,
      get: () => () => undefined,
      set: () => {},
    });
  } catch (_) {}

  const report = (url) => {
    try {
      const send = window.__axcessPopupRefused;
      if (url && typeof send === "function") send(new URL(String(url), document.baseURI).href);
    } catch (_) {}
  };

  // A target that names a browsing context which already exists is a
  // navigation inside the page: this window, an ancestor, or any frame under
  // the same top. A cross-origin frame hides its own name, but the element
  // that embeds it is readable from its parent.
  const namesExistingContext = (name) => {
    const search = (win, depth) => {
      if (depth > 8) return false;
      try { if (win.name === name) return true; } catch (_) {}
      try {
        for (const el of win.document.querySelectorAll("iframe[name], frame[name], object[name]")) {
          if (el.getAttribute("name") === name) return true;
        }
      } catch (_) {}
      try {
        for (let i = 0; i < win.frames.length; i++) {
          if (search(win.frames[i], depth + 1)) return true;
        }
      } catch (_) {}
      return false;
    };
    let top = window;
    try { top = window.top || window; } catch (_) {}
    return search(top, 0);
  };
  const opensNewContext = (target) => {
    const name = String(target === undefined || target === null ? "" : target).trim();
    if (/^_(self|top|parent)$/i.test(name)) return false;
    if (!name || /^_blank$/i.test(name)) return true;
    return !namesExistingContext(name);
  };
  const baseTarget = () => {
    const base = document.querySelector("base[target]");
    return base ? base.getAttribute("target") : "";
  };

  // What the caller gets instead of a window. ``null`` is what a popup
  // blocker returns, but code written against a browser that allows popups
  // goes straight to ``w.focus()`` or ``w.location = url`` and would throw
  // half way through its handler, leaving the page in a state a public scan
  // never sees.
  const inertWindow = () => {
    let closed = false;
    const location = {
      get href() { return "about:blank"; },
      set href(value) { report(value); },
      assign: report,
      replace: report,
      reload() {},
      toString: () => "about:blank",
    };
    return {
      get closed() { return closed; },
      close() { closed = true; },
      focus() {}, blur() {}, print() {}, postMessage() {},
      addEventListener() {}, removeEventListener() {},
      dispatchEvent: () => false,
      document: document.implementation.createHTMLDocument(""),
      get location() { return location; },
      set location(value) { report(value); },
      opener: window,
      name: "",
      length: 0,
    };
  };
  const nativeOpen = window.open;
  const open = function (url, target) {
    // No target, or an empty one, means a new tab.
    if (!opensNewContext(target)) return nativeOpen.apply(window, arguments);
    report(url);
    return inertWindow();
  };
  try {
    // An accessor, not a read-only value: strict-mode code that assigns its
    // own wrapper to window.open must not throw.
    Object.defineProperty(window, "open", { configurable: false, get: () => open, set: () => {} });
  } catch (_) {
    try { window.open = open; } catch (_) {}
  }

  const isElement = (node) => !!node && node.nodeType === 1;
  const isFileInput = (node) =>
    isElement(node) && node.localName === "input" &&
    String(node.getAttribute("type") || "").toLowerCase() === "file";
  const isLink = (node) =>
    isElement(node) && (node.localName === "a" || node.localName === "area") &&
    (node.hasAttribute("href") || node.hasAttributeNS("http://www.w3.org/1999/xlink", "href"));
  const hrefOf = (node) =>
    node.getAttribute("href") || node.getAttributeNS("http://www.w3.org/1999/xlink", "href");
  const isNewTabLink = (node) =>
    isLink(node) && opensNewContext(node.getAttribute("target") || baseTarget() || "_self");
  const formTarget = (form, submitter) =>
    (submitter && submitter.getAttribute && submitter.getAttribute("formtarget")) ||
    form.getAttribute("target") || baseTarget() || "_self";

  try {
    const showPicker = HTMLInputElement.prototype.showPicker;
    if (typeof showPicker === "function") {
      HTMLInputElement.prototype.showPicker = function () {
        if (!isFileInput(this)) return showPicker.call(this);
      };
    }
  } catch (_) {}
  for (const name of ["showOpenFilePicker", "showSaveFilePicker", "showDirectoryPicker"]) {
    try {
      if (typeof window[name] === "function") {
        window[name] = () => Promise.reject(new DOMException("Aborted", "AbortError"));
      }
    } catch (_) {}
  }
  try {
    // An element the page never attached has no path to this document, so
    // the listeners below never hear its click. Anchors navigate detached.
    const click = HTMLElement.prototype.click;
    HTMLElement.prototype.click = function () {
      if (isFileInput(this)) return;
      if (isNewTabLink(this)) { report(hrefOf(this)); return; }
      return click.apply(this, arguments);
    };
  } catch (_) {}
  try {
    // form.submit() fires no submit event.
    const submit = HTMLFormElement.prototype.submit;
    HTMLFormElement.prototype.submit = function () {
      if (opensNewContext(formTarget(this, null))) return;
      return submit.apply(this, arguments);
    };
  } catch (_) {}

  const onClick = (event) => {
    // composedPath sees into open shadow roots; event.target stops at the host.
    const path = typeof event.composedPath === "function" ? event.composedPath() : [event.target];
    // Reached by a direct click, a label, or a script calling input.click().
    if (isFileInput(path[0])) { event.preventDefault(); return; }
    const link = path.find(isLink);
    if (!link) return;
    const newWindowGesture = event.button === 1 || event.ctrlKey || event.metaKey || event.shiftKey;
    if (newWindowGesture || isNewTabLink(link)) {
      event.preventDefault();
      report(hrefOf(link));
    }
  };
  window.addEventListener("click", onClick, true);
  window.addEventListener("auxclick", onClick, true);
  window.addEventListener("submit", (event) => {
    const form = event.target;
    if (!isElement(form) || form.localName !== "form") return;
    if (opensNewContext(formTarget(form, event.submitter))) event.preventDefault();
  }, true);
})();
"""
# The crawl's standard viewport, the same one a public scan renders at. The
# context is launched without a default viewport (see ``start``), so every
# scan tab is given this explicitly.
_SCAN_VIEWPORT = {"width": 1440, "height": 900}
# The tab left in front of the hidden window. It never navigates anywhere.
_COVER_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Axcess is scanning in the background</title>
<style>
  body { font: 18px/1.5 system-ui, sans-serif; margin: 0; padding: 3rem; color: #1a1a1a; }
  main { max-width: 38rem; }
  h1 { font-size: 1.6rem; margin: 0 0 1rem; }
</style>
</head>
<body>
<main>
<h1>Axcess is scanning in the background</h1>
<p>You are signed in, and Axcess is checking pages in the other tabs of this
window. Progress is shown in Axcess.</p>
<p>Axcess keeps this window minimized while it scans, so it will put it away
again if you open it from the Dock or taskbar. To watch the scan, choose
<strong>Show browser window</strong> in Axcess.</p>
<p><strong>Closing this window or quitting Chromium stops the scan.</strong></p>
</main>
</body>
</html>
"""
_HIDE_RECHECK_SECONDS = 0.5
# Consecutive passes that fail to put the browser away before it is left alone.
_HIDE_GIVE_UP_AFTER = 10
# Once given up on, the window's state is still read, this many passes apart.
_GAVE_UP_LOOK_EVERY = 10
# How many more passes a hide request waits for the OS to finish animating.
_HIDE_SETTLE_PASSES = 4
# A minimize ignored this many times running is not an animation in the way.
_PARK_AFTER_IGNORED_MINIMIZES = 6
# How far off any display the fallback parks a window that will not minimize.
_OFFSCREEN_EDGE = -10_000


_REFUSED_POPUP_BINDING = "__axcessPopupRefused"


def _ignore_file_chooser(_chooser: object) -> None:
    """Leave a file chooser unanswered; nothing is ever uploaded by a scan."""


def _on_refused_popup(source: dict[str, Any], url: object) -> None:
    """Hand a refused popup's destination to whoever is exploring that tab."""

    page = source.get("page")
    if page is not None and isinstance(url, str):
        report_refused_popup(page, url)


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
        return policies.target.validate_page_url(seed_url)
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
        """Close an auxiliary tab, unless sign-in is what opened it.

        While scanning, a tab with an opener is never legitimate: the crawler
        creates every page it uses, so anything else is uncontrolled
        navigation that must not become evidence. That rule stays exactly as
        it was once scan mode activates.

        During manual sign-in it is wrong. Institutional SSO routinely hands
        off through a new tab, an LTI launch from a VLE into the tool it
        embeds is the ordinary case, not an edge case, and closing it on
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
            # an origin nobody approved", a distinction that previously left
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
        # the target origin itself, which for an accessibility audit
        # discards the alternative-text, contrast, and layout evidence being
        # collected. Neither survived contact with a real application.
        # Documents were checked against the approved *target* origins rather
        # than the scan policy, which refused a sub-frame served from
        # anywhere else, an embedded course tool from another company being
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
    then call :meth:`enter_scan_mode` after explicit human confirmation. Only
    then may :meth:`create_shared_js_fetcher` be used.
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
        # a tab it opens for itself, and the auditor finishes there, so that
        # tab, not the one we opened, is where verification must read the
        # landing URL from, and all of them have to be closed afterwards.
        self._auth_pages: list[Page] = []
        self._egress_proxy = LoopbackEgressProxy(self._policies.setup)
        self._profile_dir: str | None = None
        # The inert tab left in front of the hidden window, and the task that
        # keeps the window hidden for as long as the auditor wants it so.
        self._cover_page: Page | None = None
        self._hide_wanted = False
        self._hidden = False
        self._hide_lock = asyncio.Lock()
        self._hide_task: asyncio.Task[None] | None = None
        self._hide_recheck = asyncio.Event()
        self._scan_pages: tuple[Page, ...] = ()
        self._cover_fronted = False
        # A tab opened or closed since the last hide: which tab is in front,
        # and which windows exist, both have to be looked at again.
        self._tabs_changed = False
        self._hide_failures = 0
        self._window_cdp: Any | None = None
        self._window_cdp_anchor: Page | None = None
        self._window_pages: dict[int, list[Page]] = {}
        self._minimize_ignored: dict[int, int] = {}
        # Windows the off-screen fallback moved: where each stood before
        # ("from") and where the OS let it go ("at").
        self._parked: dict[int, dict[str, dict[str, Any]]] = {}

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

    @property
    def backgrounded(self) -> bool:
        """Whether the browser was out of the auditor's way when last checked."""

        return self._hidden

    @property
    def parked(self) -> bool:
        """The browser would not minimize and was moved to the screen's edge."""

        return bool(self._parked) and not self._hidden

    @property
    def hiding_wanted(self) -> bool:
        """False once the auditor has asked to see the browser.

        Tells "showing because they asked" from "showing because it could not
        be hidden", which deserve different words.
        """

        return self._hide_wanted

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
                    # No --incognito. With a persistent context that flag adds
                    # a second, off-to-the-side incognito window while the
                    # sign-in page created below lives in the ordinary profile
                    # -- so it never protected the session, it only doubled the
                    # windows the auditor has to find. Isolation here is the
                    # ephemeral mode-0700 profile directory, which is removed
                    # on close (see _create_ephemeral_profile_dir).
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
                # With a default viewport Playwright owns the OS window: every
                # ``set_viewport_size`` also resizes it, and Chromium answers a
                # resize of a minimized window by putting it back on screen.
                # The responsive probe resizes four times a page, so the
                # browser returned to the foreground on the first page of
                # every scan. Without one Playwright emulates the viewport
                # and leaves the window alone; scan tabs are sized explicitly
                # in ``prepare_background_scan_pages``. Sign-in also gets a
                # page that follows the window the auditor is resizing.
                no_viewport=True,
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
            # The context's page event can already have adopted this tab
            # before new_page returns. Register it idempotently: a duplicate
            # would survive removal from the sign-in list when the scanner
            # retains this tab, so sign-in cleanup would close the scan tab.
            self._adopt_auth_page(self._page)
            # Chromium always opens a blank startup tab, which left the
            # auditor two windows to choose between and no way to tell which
            # one Axcess was watching. Closed after the sign-in page exists,
            # never before: closing a context's last page can take the browser
            # with it. Only the startup leftovers go -- an SSO popup arrives
            # later, through the page event, and is adopted rather than closed.
            for startup_page in list(self._context.pages):
                if startup_page is not self._page:
                    with contextlib.suppress(Exception):
                        await startup_page.close(run_before_unload=False)
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
        the original tab would verify a stale sign-in URL, and then start
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

    def enter_scan_mode(self) -> str:
        """Switch the session from sign-in to scanning. Returns where it landed.

        The auditor's confirmation is the only signal that sign-in finished.
        Axcess used to second-guess it by requiring the landed URL to sit on an
        approved target origin, and refused to scan otherwise. Real sign-ins
        land wherever the application sends them -- a different subdomain, a
        tenant host, a marketing shell -- so the check rejected sessions that
        were signed in perfectly well and there was no way past it.
        """
        self._require_started()
        self._route_guard.activate_scan_mode()
        self._egress_proxy.set_policy(self._policies.scan)
        self._state = ManualAuthState.AUTHENTICATED
        return self.page.url

    async def prepare_background_scan_pages(self, count: int) -> tuple[Page, ...]:
        """Prepare up to ``count`` authenticated tabs before hiding Chromium.

        Chromium raises a minimized window whenever a tab is created in it, so
        every tab the crawl will use has to exist before the window is hidden,
        and the crawl reuses them from then on. The pages and their shared
        authenticated context remain memory-only and are destroyed together
        at session close.
        If sign-in uses sessionStorage, the pool retains its single tab;
        workers serialize access to preserve that tab-scoped session.
        """

        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before preparing scan tabs."
            )
        if count <= 0:
            raise ValueError("Background scan page count must be positive.")
        # Applies to every document loaded from here on, in every tab.
        await self.context.expose_binding(_REFUSED_POPUP_BINDING, _on_refused_popup)
        await self.context.add_init_script(_SCAN_QUIET_INIT_SCRIPT)
        # sessionStorage belongs to a tab, not its BrowserContext. Opening
        # fresh worker tabs and closing sign-in silently signs out SPAs that
        # keep their session there. Retain that tab and serialize the pool
        # instead of exporting or copying any authentication material.
        auth_page = self.page
        pages: list[Page] = []
        created: list[Page] = []
        try:
            if await auth_page.evaluate("() => sessionStorage.length > 0"):
                self._auth_pages.remove(auth_page)
                self._page = None
                pages.append(auth_page)
            else:
                for _ in range(count):
                    created.append(await self.context.new_page())
                pages.extend(created)
            for page in pages:
                await page.set_viewport_size(_SCAN_VIEWPORT)  # type: ignore[arg-type]
                # The scan script refuses file choosers in the page. Should
                # one open anyway, a listener makes Playwright hold it rather
                # than let Chromium put a native dialog on screen.
                page.on("filechooser", _ignore_file_chooser)
            self._scan_pages = tuple(pages)
            await self._open_cover_page()
        except Exception:
            for page in created:
                with contextlib.suppress(Exception):
                    await page.close(run_before_unload=False)
            raise
        return tuple(pages)

    async def _open_cover_page(self) -> Page:
        """Put an inert tab in front of the window that is about to be hidden.

        Chromium stops compositing the front tab of a minimized window, and a
        screenshot of that tab never returns: measured on macOS, every capture
        timed out, while the same capture of a tab behind the front one took
        40 ms. So no scan tab may be in front. A new tab opens in front, which
        makes this the last one created before hiding.
        """

        cover = await self.context.new_page()
        await cover.set_content(_COVER_PAGE_HTML)
        self._cover_page = cover
        return cover

    async def hide_for_background_scan(self) -> bool:
        """Take the signed-in browser out of the auditor's way and keep it there.

        Chromium cannot switch a live authenticated context from headed to
        headless mode, so the window is minimized instead, which preserves the
        memory-only session while the auditor keeps using the computer. It is
        re-checked for as long as hiding is wanted: see ``_keep_hidden``.
        Returns whether the browser is minimized now; a window that was
        fullscreen takes a second or two longer, and ``backgrounded`` follows
        it. CDP window management is best-effort because a platform or
        Chromium build may not expose a native window.
        """

        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before backgrounding the browser."
            )
        async with self._hide_lock:
            self._hide_wanted = True
            self._hide_failures = 0
            self._hidden = await self._hide_windows()
            # The OS ignores a minimize while it is still animating: straight
            # after the auditor asked to see the window, or as it leaves
            # fullscreen. Measured at one or two passes. Waiting that out here
            # means the answer given to the caller is the true one.
            for _ in range(_HIDE_SETTLE_PASSES):
                if self._hidden or self._parked:
                    break
                await asyncio.sleep(_HIDE_RECHECK_SECONDS)
                self._hidden = await self._hide_windows()
        if self._hide_task is None:
            self.context.on("page", self._on_page_while_scanning)
            self._hide_task = asyncio.create_task(self._keep_hidden())
        return self._hidden

    async def show_browser(self) -> bool:
        """Put the scanning browser back on screen until it is hidden again."""

        if self._state is not ManualAuthState.AUTHENTICATED:
            raise ManualAuthenticationError(
                "Complete and verify manual sign-in before showing the scan browser."
            )
        async with self._hide_lock:
            # Off first, so the watchdog cannot minimize what is being shown.
            self._hide_wanted = False
            try:
                cdp = await self._window_cdp_session()
                for window_id in await self._windows():
                    await cdp.send(
                        "Browser.setWindowBounds",
                        {"windowId": window_id, "bounds": {"windowState": "normal"}},
                    )
                    parked = self._parked.pop(window_id, None)
                    if parked is not None and parked["from"]:
                        await cdp.send(
                            "Browser.setWindowBounds",
                            {"windowId": window_id, "bounds": parked["from"]},
                        )
                # What the auditor asked to see is the scan, not the notice
                # that it is running.
                watched = next(
                    (page for page in self._scan_pages if not page.is_closed()),
                    self._cover_page,
                )
                if watched is not None and not watched.is_closed():
                    await watched.bring_to_front()
                    self._cover_fronted = False
            except Exception:
                await self._drop_window_cdp()
                # Nothing is known to have moved, so nothing has changed: the
                # browser is where it was and is still being kept there.
                self._hide_wanted = True
                return False
            self._hidden = False
            return True

    def _on_page_while_scanning(self, page: Page) -> None:
        """A tab appeared despite the popup block: the window is up again."""

        self._tabs_changed = True
        self._hide_failures = 0
        self._hide_recheck.set()
        # The route guard closes it, and Chromium then fronts the tab that
        # opened it: a scan tab, in front of a window about to be minimized.
        page.on("close", self._on_page_closed_while_scanning)

    def _on_page_closed_while_scanning(self, _page: Page) -> None:
        self._tabs_changed = True
        self._hide_failures = 0
        self._hide_recheck.set()

    async def _keep_hidden(self) -> None:
        """Re-hide the browser whenever something puts it back on screen.

        Hiding once was not enough. A scan runs for minutes against an
        application nobody here has read: a tab that slips past the scan
        script, a native dialog, or a Chromium behaviour not yet met can each
        raise the window again, and the auditor was left looking at it for
        the rest of the scan. While hiding is wanted the window's state is
        re-read twice a second, and at once when a tab opens or closes. The
        auditor's own way to see the browser is ``show_browser``, which
        switches this off until they hide it again.

        It does not fight for ever. On a machine where nothing works, asking
        twice a second would move and resize a window the auditor is trying
        to place themselves; after a few seconds of failure the window is
        left alone until a tab opens or hiding is asked for again.
        """

        idle_passes = 0
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._hide_recheck.wait(), _HIDE_RECHECK_SECONDS)
            self._hide_recheck.clear()
            async with self._hide_lock:
                if not self._hide_wanted or self._state is not ManualAuthState.AUTHENTICATED:
                    continue
                gave_up = self._hide_failures >= _HIDE_GIVE_UP_AFTER
                if gave_up and not self._tabs_changed:
                    # Still worth a look now and then: the auditor may have
                    # minimized it themselves, and the UI should say so.
                    idle_passes += 1
                    if idle_passes % _GAVE_UP_LOOK_EVERY:
                        continue
                try:
                    if not self._tabs_changed and await self._windows_settled():
                        self._hide_failures = 0
                        continue
                    if gave_up:
                        continue
                    log.info(
                        "protected.browser_hidden_again",
                        reason="tab_changed" if self._tabs_changed else "window_restored",
                    )
                    self._hidden = await self._hide_windows()
                    settled = await self._windows_settled()
                except Exception:
                    await self._drop_window_cdp()
                    self._hidden = False
                    settled = False
                self._hide_failures = 0 if settled else self._hide_failures + 1
                if self._hide_failures == _HIDE_GIVE_UP_AFTER:
                    log.warning("protected.browser_hide_gave_up")

    async def _hide_windows(self) -> bool:
        """Front the cover tab, then put every window of the context away.

        Returns whether every window is minimized, which is the only state
        known to leave nothing on screen.
        """

        try:
            cover = self._cover_page
            if cover is None or cover.is_closed():
                cover = await self._open_cover_page()
            elif self._tabs_changed or not self._cover_fronted:
                # Fronting a tab raises a minimized window, so only when the
                # front tab can have changed since the last hide.
                await cover.bring_to_front()
            self._cover_fronted = True
            self._tabs_changed = False
            cdp = await self._window_cdp_session()
            windows = await self._windows(refresh=True)
            # No window to ask about is not the same as nothing on screen.
            minimized = bool(windows)
            for window_id, pages in windows.items():
                covered = cover in pages
                holds_scan_tab = any(page in pages for page in self._scan_pages)
                if holds_scan_tab and not covered:
                    # A scan tab in a window of its own (an SSO popup window
                    # kept for its sessionStorage, a tab the auditor dragged
                    # out) would be the front tab of a minimized window, where
                    # its screenshots hang. A new tab cannot be aimed at a
                    # window, so this one is parked instead: still rendering.
                    await self._park_window(cdp, window_id)
                    minimized = False
                else:
                    minimized = await self._minimize_window(cdp, window_id) and minimized
            return minimized
        except Exception:
            await self._drop_window_cdp()
            return False

    async def _minimize_window(self, cdp: Any, window_id: int) -> bool:
        state = (await self._window_bounds(cdp, window_id)).get("windowState")
        if state in {"fullscreen", "maximized"}:
            # Chromium refuses to minimize a fullscreen window outright, and
            # the OS is still animating for a moment after it leaves either
            # state. Step down now; the next pass minimizes.
            await cdp.send(
                "Browser.setWindowBounds",
                {"windowId": window_id, "bounds": {"windowState": "normal"}},
            )
            return False
        await cdp.send(
            "Browser.setWindowBounds",
            {"windowId": window_id, "bounds": {"windowState": "minimized"}},
        )
        if (await self._window_bounds(cdp, window_id)).get("windowState") == "minimized":
            self._minimize_ignored.pop(window_id, None)
            self._parked.pop(window_id, None)
            return True
        # Ignored while an animation plays is ordinary; ignored every time is
        # a Chromium build that does not minimize at all.
        ignored = self._minimize_ignored.get(window_id, 0) + 1
        self._minimize_ignored[window_id] = ignored
        if ignored >= _PARK_AFTER_IGNORED_MINIMIZES:
            await self._park_window(cdp, window_id)
        return False

    async def _park_window(self, cdp: Any, window_id: int) -> None:
        """Move a window that cannot be minimized as far off screen as it goes.

        macOS keeps a strip of any titled window reachable (measured: 40 px),
        so a parked window is out of the way, not out of sight, and is never
        reported as hidden.
        """

        if window_id in self._parked:
            return
        before = await self._window_bounds(cdp, window_id)
        await cdp.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "windowState": "normal",
                    "left": _OFFSCREEN_EDGE,
                    "top": _OFFSCREEN_EDGE,
                    "width": 1280,
                    "height": 800,
                },
            },
        )
        after = await self._window_bounds(cdp, window_id)
        self._parked[window_id] = {
            "from": {
                key: before[key]
                for key in ("left", "top", "width", "height")
                if isinstance(before.get(key), int)
            },
            "at": {key: after.get(key) for key in ("left", "top")},
        }

    async def _windows_settled(self) -> bool:
        """Whether every window is still where hiding left it.

        Also refreshes ``backgrounded``: minimized everywhere, or not.
        """

        cdp = await self._window_cdp_session()
        windows = await self._windows()
        settled = bool(windows)
        minimized = bool(windows)
        for window_id in windows:
            try:
                bounds = await self._window_bounds(cdp, window_id)
            except Exception:
                # The window is gone (its last tab closed, or the auditor
                # closed it while it was showing). Look again next pass.
                self._tabs_changed = True
                return False
            if bounds.get("windowState") == "minimized":
                continue
            minimized = False
            parked = self._parked.get(window_id)
            if parked is None or any(bounds.get(k) != v for k, v in parked["at"].items()):
                settled = False
        self._hidden = minimized and settled
        return settled

    @staticmethod
    async def _window_bounds(cdp: Any, window_id: int) -> dict[str, Any]:
        reply = await cdp.send("Browser.getWindowBounds", {"windowId": window_id})
        bounds = reply.get("bounds", {})
        return bounds if isinstance(bounds, dict) else {}

    async def _window_cdp_session(self) -> Any:
        """One CDP session for window management, attached to a live tab."""

        if self._window_cdp is not None:
            return self._window_cdp
        anchor = self._cover_page
        if anchor is None or anchor.is_closed():
            anchor = next((page for page in self.context.pages if not page.is_closed()), None)
        if anchor is None:
            raise ManualAuthenticationError("The scan browser has no open tab.")
        self._window_cdp = await self.context.new_cdp_session(anchor)
        if anchor is not self._window_cdp_anchor:
            self._window_cdp_anchor = anchor
            anchor.on("close", self._forget_window_cdp)
        return self._window_cdp

    def _forget_window_cdp(self, _page: Page) -> None:
        self._window_cdp = None
        self._window_cdp_anchor = None

    async def _drop_window_cdp(self) -> None:
        """Detach a session that failed, so a retry does not pile up sessions."""

        session, self._window_cdp = self._window_cdp, None
        if session is not None:
            with contextlib.suppress(Exception):
                await session.detach()

    async def _windows(self, *, refresh: bool = False) -> dict[int, list[Page]]:
        """Every native window of the context, with the tabs each one holds.

        Not only the window sign-in used: an identity provider may have
        opened its own, and the auditor can drag a tab out of any of them.
        """

        if self._window_pages and not refresh:
            return self._window_pages
        found: dict[int, list[Page]] = {}
        for page in list(self.context.pages):
            if page.is_closed():
                continue
            session: Any | None = None
            # A tab can close between being listed and being asked.
            with contextlib.suppress(Exception):
                session = await self.context.new_cdp_session(page)
                window_id = (await session.send("Browser.getWindowForTarget")).get("windowId")
                if isinstance(window_id, int):
                    found.setdefault(window_id, []).append(page)
            if session is not None and session is not self._window_cdp:
                with contextlib.suppress(Exception):
                    await session.detach()
        self._window_pages = found
        return found

    async def discard_manual_auth_page(self) -> None:
        """Close sign-in tabs that have not been retained for scanning.

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
        search_explorer: SearchExplorer | None = None,
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
            search_explorer=search_explorer,
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
                # dropped, handing it an empty set would block every
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
        self._hide_wanted = False
        self._hidden = False
        hide_task = self._hide_task
        self._hide_task = None
        if hide_task is not None:
            hide_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await hide_task
        self._window_cdp = None
        self._window_cdp_anchor = None
        self._window_pages = {}
        self._parked = {}
        self._cover_page = None
        self._scan_pages = ()
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
