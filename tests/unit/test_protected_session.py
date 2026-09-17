"""Unit tests for companion-side manual protected authentication."""

from __future__ import annotations

import asyncio
import inspect
import io
import os
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from PIL import Image

from audit.protected import companion
from audit.protected.egress import EgressViolation
from audit.protected.session import (
    ManualAuthenticationError,
    ManualAuthenticationSession,
    ManualAuthPolicies,
    ManualAuthState,
    build_manual_auth_policies,
    validate_protected_seed_url,
)


def test_protected_ocr_refuses_excessive_decoded_image_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An 8 MiB transport cap is not treated as a decoded-pixel cap."""

    class OversizedImage:
        size = (companion._MAX_OCR_IMAGE_DIMENSION + 1, 2)

        def __enter__(self) -> object:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def verify(self) -> None:
            raise AssertionError("oversized images must be rejected before decode")

    monkeypatch.setattr(companion.Image, "open", lambda _stream: OversizedImage())
    assert companion._is_ocr_safe_image(bytearray(b"small-image-header")) is False


def test_protected_ocr_accepts_a_small_verified_image() -> None:
    """Normal raster images remain eligible for bounded in-memory OCR."""

    output = io.BytesIO()
    Image.new("RGB", (8, 8), color="white").save(output, format="PNG")
    assert companion._is_ocr_safe_image(bytearray(output.getvalue())) is True


def _resolver(host: str) -> tuple[str, ...]:
    assert host in {"app.example.edu", "login.example.edu", "cdn.example.edu"}
    return ("8.8.8.8",)


def _policies() -> ManualAuthPolicies:
    return build_manual_auth_policies(
        approved_target_origins=["https://app.example.edu"],
        approved_auth_origins=["https://login.example.edu"],
        approved_cdn_origins=["https://cdn.example.edu"],
        resolver=_resolver,
    )


def test_a_scan_reaches_any_public_https_origin() -> None:
    """The scan policy is no longer an origin allowlist.

    It was, and it could not describe a real web application: data from a
    sibling host, assets from CDNs, fonts and payment widgets from third
    parties, and — for the course tools this exists to audit — entire
    products embedded from other companies. Approving only the origin the
    auditor typed meant the application could not load its own data once
    scanning began, so it rendered its signed-out view and the scan captured
    a login form instead of the product.

    This test previously asserted the opposite, that scan mode tightened to
    the approved target and refused everything else. That property was
    removed deliberately, and this records what replaced it.
    """
    policies = _policies()

    assert (
        policies.setup.validate_transient_auth_url(
            "https://login.example.edu/authorize?code=temporary&state=opaque"
        ).origin.value
        == "https://login.example.edu"
    )
    assert policies.setup.validate_url("https://cdn.example.edu/app.css").origin.value == (
        "https://cdn.example.edu"
    )
    assert policies.scan.validate_url("https://cdn.example.edu/app.css").origin.value == (
        "https://cdn.example.edu"
    )
    # An identity-provider origin is reachable during a scan now. It is a
    # public HTTPS origin like any other, and the application decides what it
    # loads, not an allowlist written before the page was ever seen.
    assert policies.scan.validate_url("https://login.example.edu/authorize").origin.value == (
        "https://login.example.edu"
    )


def test_a_scan_still_refuses_a_private_or_plaintext_destination() -> None:
    """What the scan policy does still enforce, now that origins are open.

    Dropping the allowlist is not the same as dropping every boundary: a
    scan cannot be pointed at a loopback or private address, and cannot be
    downgraded to plaintext.
    """
    policies = _policies()

    for unsafe in (
        "http://app.example.edu/insecure",
        "https://127.0.0.1:8000/admin",
        "https://localhost/admin",
        "https://192.168.1.10/admin",
    ):
        with pytest.raises(EgressViolation):
            policies.scan.validate_url(unsafe)


def test_local_manual_login_allows_a_dynamic_public_mfa_origin() -> None:
    """A Duo-style redirect to an unpredictable host must work.

    Previously this also asserted that the same origin became unreachable
    once scanning began. That tightening is gone: the scan policy is no
    longer an allowlist, because one cannot describe a real application.
    What still gates the scan is verification — sign-in must return to an
    approved target page, which is asserted below and unchanged.
    """

    def resolver(host: str) -> tuple[str, ...]:
        assert host in {
            "app.example.edu",
            "login.example.edu",
            "api-12345.duosecurity.com",
        }
        return ("8.8.8.8",)

    policies = build_manual_auth_policies(
        approved_target_origins=["https://app.example.edu"],
        approved_auth_origins=["https://login.example.edu"],
        resolver=resolver,
        allow_any_public_auth_origin=True,
    )

    assert (
        policies.setup.validate_transient_auth_url(
            "https://api-12345.duosecurity.com/frame/v4/auth?state=temporary"
        ).origin.value
        == "https://api-12345.duosecurity.com"
    )


def test_the_seed_must_be_the_application_not_its_identity_provider() -> None:
    """The one URL the auditor types is still checked. Where sign-in *lands* is not."""
    policies = _policies()

    assert validate_protected_seed_url("https://app.example.edu/start", policies).url.endswith(
        "/start"
    )
    with pytest.raises(ManualAuthenticationError):
        validate_protected_seed_url("https://login.example.edu/authorize", policies)


@dataclass
class _FakeRequest:
    method: str
    url: str
    resource_type: str = "document"


@dataclass
class _FakeRoute:
    request: _FakeRequest
    actions: list[tuple[str, str | None]] = field(default_factory=list)
    response_status: int = 200

    async def abort(self, reason: str) -> None:
        self.actions.append(("abort", reason))

    async def continue_(self) -> None:
        self.actions.append(("continue", None))

    async def fetch(self, *, max_redirects: int) -> _FakeResponse:
        assert max_redirects == 0
        self.actions.append(("fetch", None))
        return _FakeResponse(status=self.response_status)

    async def fulfill(self, *, response: _FakeResponse) -> None:
        self.actions.append(("fulfill", None))


@dataclass
class _FakeResponse:
    status: int
    disposed: bool = False

    async def dispose(self) -> None:
        self.disposed = True


@dataclass(eq=False)
class _FakePage:
    url: str = "about:blank"
    goto_calls: list[tuple[str, int, str]] = field(default_factory=list)
    event_handlers: dict[str, object] = field(default_factory=dict)
    closed: bool = False
    has_session_storage: bool = False
    viewport: dict[str, int] | None = None
    content: str | None = None
    fronted: int = 0
    context: _FakeContext | None = None

    async def evaluate(self, script: str) -> bool:
        assert script == "() => sessionStorage.length > 0"
        return self.has_session_storage

    async def set_viewport_size(self, size: dict[str, int]) -> None:
        self.viewport = dict(size)

    async def set_content(self, html: str) -> None:
        self.content = html

    async def bring_to_front(self) -> None:
        self.fronted += 1
        # Measured on macOS: fronting a tab raises a minimized window, even
        # when that tab was already in front. Hiding has to come after it.
        if self.context is not None:
            cdp = self.context.cdp_session
            cdp.window(cdp.window_of.get(id(self), 7))["windowState"] = "normal"

    def is_closed(self) -> bool:
        return self.closed

    async def goto(self, url: str, *, timeout: int, wait_until: str) -> object:
        self.url = url
        self.goto_calls.append((url, timeout, wait_until))
        return object()

    async def opener(self) -> None:
        return None

    async def close(self, *, run_before_unload: bool) -> None:
        assert not run_before_unload
        if self.closed:
            return
        self.closed = True
        handler = self.event_handlers.get("close")
        if handler is not None:
            handler(self)  # type: ignore[operator]

    def on(self, event: str, handler: object) -> None:
        self.event_handlers[event] = handler


@dataclass
class _FakeCdpSession:
    calls: list[tuple[str, object | None]] = field(default_factory=list)
    detached: bool = False
    #: Some macOS Chromium builds acknowledge a minimize and ignore it.
    honors_minimize: bool = False
    #: Native window of each tab; a tab not listed here lives in window 7.
    window_of: dict[int, int] = field(default_factory=dict)
    windows: dict[int, dict[str, object]] = field(default_factory=dict)
    attached_to: object | None = None

    def window(self, window_id: int) -> dict[str, object]:
        return self.windows.setdefault(
            window_id,
            {"windowState": "normal", "left": 40, "top": 60, "width": 1200, "height": 900},
        )

    def minimize_requests(self, window_id: int = 7) -> int:
        wanted = {"windowId": window_id, "bounds": {"windowState": "minimized"}}
        return sum(
            1
            for method, params in self.calls
            if method == "Browser.setWindowBounds" and params == wanted
        )

    async def send(self, method: str, params: object | None = None) -> dict[str, object]:
        self.calls.append((method, params))
        if method == "Browser.getWindowForTarget":
            return {"windowId": self.window_of.get(id(self.attached_to), 7)}
        if method == "Browser.setWindowBounds" and isinstance(params, dict):
            window = self.window(params["windowId"])
            bounds = params.get("bounds")
            assert isinstance(bounds, dict)
            if bounds.get("windowState") == "minimized":
                if window["windowState"] == "fullscreen":
                    raise RuntimeError(
                        "To minimize a fullscreen window, restore it to normal state first."
                    )
                if self.honors_minimize:
                    window["windowState"] = "minimized"
                return {}
            window["windowState"] = "normal"
            if bounds.get("left") == -10_000:
                # Match Chromium on macOS: it keeps a narrow edge reachable.
                window["left"] = -1240
            elif "left" in bounds:
                window["left"] = bounds["left"]
            return {}
        if method == "Browser.getWindowBounds" and isinstance(params, dict):
            return {"bounds": dict(self.window(params["windowId"]))}
        return {}

    async def detach(self) -> None:
        self.detached = True


@dataclass
class _FakeContext:
    page: _FakePage
    cdp_session: _FakeCdpSession = field(default_factory=_FakeCdpSession)
    route_calls: list[tuple[str, object]] = field(default_factory=list)
    web_socket_route_calls: list[tuple[str, object]] = field(default_factory=list)
    event_handlers: dict[str, object] = field(default_factory=dict)
    init_scripts: list[str] = field(default_factory=list)
    bindings: dict[str, object] = field(default_factory=dict)
    cdp_sessions_opened: int = 0
    additional_pages: list[_FakePage] = field(default_factory=list)
    new_page_calls: int = 0
    closed: bool = False
    #: Chromium opens one blank tab before Playwright asks for anything.
    #: Omitting it from the double hid a second window from every test.
    startup_pages: list[_FakePage] = field(default_factory=lambda: [_FakePage()])

    @property
    def pages(self) -> list[_FakePage]:
        live = [*self.startup_pages, *self.additional_pages]
        if self.new_page_calls:
            live.insert(len(self.startup_pages), self.page)
        return [p for p in live if not p.closed]

    async def route(self, pattern: str, handler: object) -> None:
        self.route_calls.append((pattern, handler))

    async def route_web_socket(self, pattern: str, handler: object) -> None:
        self.web_socket_route_calls.append((pattern, handler))

    async def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)

    async def expose_binding(self, name: str, callback: object) -> None:
        assert name not in self.bindings, "Playwright refuses to expose a binding twice"
        self.bindings[name] = callback

    def on(self, event: str, handler: object) -> None:
        self.event_handlers.setdefault(event, []).append(handler)  # type: ignore[attr-defined]

    async def emit_page(self, page: _FakePage) -> None:
        for handler in list(self.event_handlers.get("page", [])):  # type: ignore[call-overload]
            outcome = handler(page)
            if inspect.isawaitable(outcome):
                await outcome

    async def new_page(self) -> _FakePage:
        self.new_page_calls += 1
        if self.new_page_calls == 1:
            page = self.page
        else:
            page = _FakePage()
            self.additional_pages.append(page)
        page.context = self
        # Playwright emits the context's page event before new_page returns.
        # Omitting it hid duplicate registration of the initial sign-in tab.
        await self.emit_page(page)
        return page

    async def new_cdp_session(self, page: _FakePage) -> _FakeCdpSession:
        assert page is self.page or page in self.additional_pages or page in self.startup_pages
        self.cdp_sessions_opened += 1
        self.cdp_session.attached_to = page
        return self.cdp_session

    async def close(self) -> None:
        self.closed = True


@dataclass
class _FakeChromium:
    context: _FakeContext
    launch_headless: bool | None = None
    user_data_dir: str | None = None
    context_options: dict[str, object] | None = None

    async def launch_persistent_context(
        self, user_data_dir: str, *, headless: bool, **kwargs: object
    ) -> _FakeContext:
        self.launch_headless = headless
        self.user_data_dir = user_data_dir
        self.context_options = kwargs
        return self.context


@dataclass
class _FakePlaywright:
    chromium: _FakeChromium
    stopped: bool = False

    async def stop(self) -> None:
        self.stopped = True


def _session_with_fake_browser() -> tuple[
    ManualAuthenticationSession,
    _FakePlaywright,
    _FakeChromium,
    _FakeContext,
    _FakePage,
]:
    page = _FakePage()
    context = _FakeContext(page=page)
    chromium = _FakeChromium(context=context)
    playwright = _FakePlaywright(chromium=chromium)

    async def start_playwright() -> _FakePlaywright:
        return playwright

    session = ManualAuthenticationSession(
        seed_url="https://app.example.edu/start",
        approved_target_origins=["https://app.example.edu"],
        approved_auth_origins=["https://login.example.edu"],
        approved_cdn_origins=["https://cdn.example.edu"],
        resolver=_resolver,
        playwright_start=start_playwright,  # type: ignore[arg-type]
    )
    return session, playwright, chromium, context, page


@pytest.mark.asyncio
async def test_tab_scoped_session_survives_login_handoff() -> None:
    session, _, _, context, page = _session_with_fake_browser()
    await session.start()
    page.url = "https://app.example.edu/#/dashboard"
    page.has_session_storage = True
    assert session.enter_scan_mode() == page.url
    scan_pages = await session.prepare_background_scan_pages(4)
    await session.discard_manual_auth_page()
    assert scan_pages == (page,)
    assert not page.closed
    # No worker tabs: only the inert tab that sits in front of the retained one.
    assert [p.content is not None for p in context.additional_pages] == [True]
    assert page.viewport == {"width": 1440, "height": 900}
    await session.close()
    assert context.closed


@pytest.mark.asyncio
async def test_manual_session_is_headed_ephemeral_and_scans_after_verification() -> None:
    session, playwright, chromium, context, page = _session_with_fake_browser()

    started_page = await session.start()

    assert started_page is page
    assert chromium.context_options is not None
    assert chromium.context_options["user_agent"] == (
        "axcess/0.1 (+authorized protected accessibility audit)"
    )
    assert chromium.context_options["accept_downloads"] is False
    assert chromium.context_options["service_workers"] == "block"
    assert chromium.context_options["proxy"] == {
        "server": session._egress_proxy.server_url,
        "bypass": "",
    }
    assert (
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"
        in chromium.context_options["args"]
    )
    assert "--disable-background-timer-throttling" in chromium.context_options["args"]
    assert "--disable-backgrounding-occluded-windows" in chromium.context_options["args"]
    assert "--disable-renderer-backgrounding" in chromium.context_options["args"]
    assert len(context.init_scripts) == 1
    assert "RTCPeerConnection" in context.init_scripts[0]
    # Playwright resizes the OS window for every viewport change unless the
    # context has no default viewport, and a resize un-minimizes the window.
    assert chromium.context_options["no_viewport"] is True
    assert chromium.user_data_dir is not None
    assert os.path.isdir(chromium.user_data_dir)
    assert os.stat(chromium.user_data_dir).st_mode & 0o777 == 0o700
    assert playwright.chromium.launch_headless is False
    assert page.goto_calls == [("https://app.example.edu/start", 30_000, "domcontentloaded")]
    assert context.route_calls == [("**/*", session._route_guard.handle_route)]
    assert context.web_socket_route_calls == [
        ("**/*", session._route_guard._auxiliary.handle_web_socket)
    ]
    assert set(context.event_handlers) == {"page"}
    assert session.state is ManualAuthState.AWAITING_MANUAL_AUTHENTICATION

    with pytest.raises(ManualAuthenticationError):
        session.create_shared_js_fetcher()

    setup_callback = _FakeRoute(
        _FakeRequest("GET", "https://login.example.edu/authorize?code=temporary&state=opaque")
    )
    setup_post = _FakeRoute(_FakeRequest("POST", "https://login.example.edu/session"))
    cdn_post = _FakeRoute(_FakeRequest("POST", "https://cdn.example.edu/event", "fetch"))
    secret_cdn = _FakeRoute(_FakeRequest("GET", "https://cdn.example.edu/a.js?token=no", "script"))
    for route in (setup_callback, setup_post, cdn_post, secret_cdn):
        await session._route_guard.handle_route(route)  # type: ignore[arg-type]
    assert setup_callback.actions == [("continue", None)]
    assert setup_post.actions == [("continue", None)]
    assert cdn_post.actions == [("abort", "blockedbyclient")]
    assert secret_cdn.actions == [("abort", "blockedbyclient")]

    page.url = "https://app.example.edu/dashboard"
    assert session.enter_scan_mode() == "https://app.example.edu/dashboard"
    assert session.state is ManualAuthState.AUTHENTICATED

    scan_pages = await session.prepare_background_scan_pages(2)
    # Two scan tabs, then the inert tab that stays in front of them.
    assert scan_pages == tuple(context.additional_pages[:2])
    assert len(set(map(id, scan_pages))) == 2
    cover = context.additional_pages[2]
    assert cover.content is not None and "scanning in the background" in cover.content
    assert not cover.goto_calls
    # No default viewport on the context, so each scan tab is sized to the
    # crawl's standard one explicitly.
    assert [p.viewport for p in scan_pages] == [{"width": 1440, "height": 900}] * 2
    assert len(context.init_scripts) == 2
    assert "window" in context.init_scripts[1] and '"open"' in context.init_scripts[1]
    assert set(context.bindings) == {"__axcessPopupRefused"}

    # Prepare the fixed worker tabs before minimizing. Creating a new tab
    # after this point restores a minimized Chromium window on macOS.
    await session.discard_manual_auth_page()
    assert page.closed
    with pytest.raises(ManualAuthenticationError):
        _ = session.page

    context.cdp_session.honors_minimize = True
    assert await session.hide_for_background_scan()
    assert session.backgrounded
    assert not session.parked
    assert cover.fronted == 1
    # Fronting the cover raises the window, so minimizing has to come last:
    # the fake un-minimizes on bring_to_front exactly as Chromium does.
    assert context.cdp_session.window(7)["windowState"] == "minimized"
    assert [
        params
        for method, params in context.cdp_session.calls
        if method == "Browser.setWindowBounds"
    ] == [{"windowId": 7, "bounds": {"windowState": "minimized"}}]

    # A scan no longer refuses these. An identity-provider origin is a public
    # HTTPS origin like any other; a POST is how a single-page application
    # asks whether it is still signed in; a worker is part of how the page
    # under audit runs. Refusing them did not make a scan safer — it made the
    # application render its signed-out view, so the audit described a login
    # form instead of the product.
    after_auth_idp = _FakeRoute(_FakeRequest("GET", "https://login.example.edu/authorize"))
    app_session_post = _FakeRoute(_FakeRequest("POST", "https://app.example.edu/form", "fetch"))
    app_worker = _FakeRoute(_FakeRequest("GET", "https://app.example.edu/worker.js", "worker"))
    for route in (after_auth_idp, app_session_post, app_worker):
        await session._route_guard.handle_route(route)  # type: ignore[arg-type]
        assert route.actions == [("continue", None)]

    # A private or plaintext destination is still refused.
    private = _FakeRoute(_FakeRequest("GET", "https://127.0.0.1:9000/admin"))
    await session._route_guard.handle_route(private)  # type: ignore[arg-type]
    assert private.actions == [("abort", "blockedbyclient")]

    safe_scan = _FakeRoute(_FakeRequest("GET", "https://app.example.edu/dashboard"))
    # The protected route guard must never use Playwright's API-response
    # interception for authenticated traffic: that API retains whole bodies.
    # Native continuation streams safe app XHR/scripts, while automatic
    # raster/media/font loading is denied before bytes enter the browser.
    safe_fetch = _FakeRoute(_FakeRequest("GET", "https://app.example.edu/api/dashboard", "fetch"))
    chunked_image = _FakeRoute(
        _FakeRequest("GET", "https://app.example.edu/unbounded-image", "image")
    )
    for route in (safe_scan, safe_fetch, chunked_image):
        await session._route_guard.handle_route(route)  # type: ignore[arg-type]
    assert safe_scan.actions == [("continue", None)]
    assert safe_fetch.actions == [("continue", None)]
    # Images are fetched now. Refusing them removed the alternative-text
    # and contrast evidence an accessibility audit exists to collect.
    assert chunked_image.actions == [("continue", None)]
    assert session.consume_scan_egress_block() == "egress_policy_blocked"

    fetcher = session.create_shared_js_fetcher(shared_pages=scan_pages)
    assert fetcher._shared_context is context  # Shared context, never exported state.
    assert fetcher._shared_pages == scan_pages

    hide_task = session._hide_task
    assert hide_task is not None and not hide_task.done()
    await session.close()
    assert hide_task.done(), "the window watchdog outlived the session"
    assert not session.backgrounded
    assert session.state is ManualAuthState.CLOSED
    assert context.closed
    assert chromium.user_data_dir is not None
    assert not os.path.exists(chromium.user_data_dir)
    assert playwright.stopped


async def _scanning_session(
    monkeypatch: pytest.MonkeyPatch, *, workers: int = 2
) -> tuple[ManualAuthenticationSession, _FakeContext, tuple[_FakePage, ...], _FakePage]:
    """A signed-in session, hidden, on a Chromium that honors minimize."""

    monkeypatch.setattr("audit.protected.session._HIDE_RECHECK_SECONDS", 0.01)
    session, _, _, context, page = _session_with_fake_browser()
    context.cdp_session.honors_minimize = True
    await session.start()
    page.url = "https://app.example.edu/dashboard"
    session.enter_scan_mode()
    scan_pages = await session.prepare_background_scan_pages(workers)
    await session.discard_manual_auth_page()
    assert await session.hide_for_background_scan()
    cover = context.additional_pages[workers]
    return session, context, scan_pages, cover  # type: ignore[return-value]


async def _until(condition: Callable[[], bool]) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the session never reacted")


@pytest.mark.asyncio
async def test_a_window_that_comes_back_is_hidden_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hiding once was the bug: anything later in the scan could undo it."""
    session, context, _, cover = await _scanning_session(monkeypatch)
    cdp = context.cdp_session
    try:
        assert cdp.window(7)["windowState"] == "minimized"
        assert cdp.minimize_requests() == 1

        cdp.window(7)["windowState"] = "normal"  # something raised it
        await _until(lambda: cdp.window(7)["windowState"] == "minimized")
        assert cdp.minimize_requests() == 2
        assert session.backgrounded
        # Nothing changed which tab is in front, and fronting a tab raises a
        # minimized window, so the cover is left alone.
        assert cover.fronted == 1
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_tab_opened_mid_scan_puts_the_cover_back_in_front(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chromium fronts the opener when a popup closes: a scan tab, whose
    screenshots then hang for as long as the window stays minimized."""
    session, context, scan_pages, cover = await _scanning_session(monkeypatch)
    cdp = context.cdp_session
    try:
        popup = _FakePopup(opener_page=scan_pages[0])
        context.additional_pages.append(popup)
        cdp.window(7)["windowState"] = "normal"  # a new tab raises the window
        await context.emit_page(popup)
        assert popup.closed, "the route guard still closes a tab opened while scanning"

        await _until(lambda: cover.fronted == 2 and cdp.window(7)["windowState"] == "minimized")
        assert session.backgrounded
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_every_window_of_the_context_is_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the window of the first scan tab used to be minimized."""
    monkeypatch.setattr("audit.protected.session._HIDE_RECHECK_SECONDS", 0.01)
    session, _, _, context, page = _session_with_fake_browser()
    context.cdp_session.honors_minimize = True
    await session.start()
    page.url = "https://app.example.edu/dashboard"
    session.enter_scan_mode()
    scan_pages = await session.prepare_background_scan_pages(2)
    context.cdp_session.window_of[id(scan_pages[1])] = 9  # a tab dragged out, or an SSO window
    await session.discard_manual_auth_page()
    stray = _FakePage()  # not a scan tab: an identity provider's leftover window
    context.additional_pages.append(stray)
    context.cdp_session.window_of[id(stray)] = 11
    try:
        assert not await session.hide_for_background_scan()
        cdp = context.cdp_session
        assert cdp.window(7)["windowState"] == "minimized"
        assert cdp.window(11)["windowState"] == "minimized"
        # A scan tab alone in a window would be the front tab of a minimized
        # window, where its screenshots hang. A cover tab cannot be aimed at
        # a window, so that one is moved aside and keeps rendering, and is
        # never reported as hidden: macOS leaves a strip of it on screen.
        assert cdp.window(9)["windowState"] == "normal"
        assert cdp.window(9)["left"] == -1240
        assert session.parked and not session.backgrounded
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_fullscreen_sign_in_window_is_stepped_down_then_minimized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chromium refuses to minimize a fullscreen window outright."""
    monkeypatch.setattr("audit.protected.session._HIDE_RECHECK_SECONDS", 0.01)
    session, _, _, context, page = _session_with_fake_browser()
    cdp = context.cdp_session
    cdp.honors_minimize = True
    await session.start()
    page.url = "https://app.example.edu/dashboard"
    session.enter_scan_mode()
    await session.prepare_background_scan_pages(1)
    await session.discard_manual_auth_page()
    cdp.window(7)["windowState"] = "fullscreen"  # the green button, during sign-in
    original_front = _FakePage.bring_to_front

    async def front_keeps_fullscreen(self: _FakePage) -> None:
        state = cdp.window(7)["windowState"]
        await original_front(self)
        if state == "fullscreen":
            cdp.window(7)["windowState"] = "fullscreen"

    monkeypatch.setattr(_FakePage, "bring_to_front", front_keeps_fullscreen)
    try:
        # The request waits out the step down rather than answering "no".
        assert await session.hide_for_background_scan()
        assert cdp.window(7)["windowState"] == "minimized"
        assert session.backgrounded
        states = [
            params["bounds"]["windowState"]  # type: ignore[index]
            for method, params in cdp.calls
            if method == "Browser.setWindowBounds"
        ]
        assert states == ["normal", "minimized"], "minimize was sent at a fullscreen window"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_window_that_appears_later_is_hidden_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """The list of windows was cached on the first hide and never looked at again."""
    session, context, _, _ = await _scanning_session(monkeypatch)
    cdp = context.cdp_session
    try:
        late = _FakePage()
        context.additional_pages.append(late)
        cdp.window_of[id(late)] = 9
        cdp.window(9)
        await context.emit_page(late)
        await _until(lambda: cdp.window(9)["windowState"] == "minimized")
        await _until(lambda: session.backgrounded)

        # And one that goes away does not strand the rest.
        await late.close(run_before_unload=False)
        cdp.window_of.pop(id(late))
        cdp.window(7)["windowState"] = "normal"
        await _until(lambda: cdp.window(7)["windowState"] == "minimized")
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_closed_cover_tab_is_replaced_before_hiding_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, context, scan_pages, cover = await _scanning_session(monkeypatch)
    try:
        assert await session.show_browser()
        await cover.close(run_before_unload=False)  # the auditor tidied up
        assert await session.hide_for_background_scan()
        replacement = context.additional_pages[-1]
        assert replacement is not cover and replacement not in scan_pages
        assert replacement.content is not None
        assert context.cdp_session.window(7)["windowState"] == "minimized"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_browser_that_will_not_minimize_is_parked_then_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Some macOS Chromium builds acknowledge a minimize and ignore it."""
    monkeypatch.setattr("audit.protected.session._HIDE_RECHECK_SECONDS", 0.005)
    session, _, _, context, page = _session_with_fake_browser()
    cdp = context.cdp_session
    await session.start()
    page.url = "https://app.example.edu/dashboard"
    session.enter_scan_mode()
    await session.prepare_background_scan_pages(1)
    await session.discard_manual_auth_page()
    try:
        assert not await session.hide_for_background_scan()
        await _until(lambda: session.parked)
        assert cdp.window(7)["left"] == -1240
        assert not session.backgrounded, "a parked window leaves a strip on screen"

        # Parked is as far as it goes. Asking again twice a second would move
        # and resize a window the auditor may be trying to place themselves.
        await asyncio.sleep(0.1)
        moves = len([c for c in cdp.calls if c[0] == "Browser.setWindowBounds"])
        sessions = context.cdp_sessions_opened
        await asyncio.sleep(0.2)
        assert len([c for c in cdp.calls if c[0] == "Browser.setWindowBounds"]) == moves
        assert context.cdp_sessions_opened == sessions, "CDP sessions are piling up"

        # Showing it puts it back where the auditor had it.
        assert await session.show_browser()
        assert cdp.window(7)["left"] == 40
        assert not session.parked
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_browser_that_cannot_be_managed_is_given_up_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("audit.protected.session._HIDE_RECHECK_SECONDS", 0.002)
    session, context, _, _ = await _scanning_session(monkeypatch)
    cdp = context.cdp_session
    attempts = 0

    async def refuse(method: str, params: object | None = None) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("no native window")

    try:
        monkeypatch.setattr(cdp, "send", refuse)
        await asyncio.sleep(0.2)
        assert not session.backgrounded
        settled = attempts
        await asyncio.sleep(0.2)
        # About a hundred passes went by. It may still look once in a while
        # (the auditor can minimize the window themselves), not every pass.
        assert attempts - settled <= 25, "the watchdog never stopped asking"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_show_that_fails_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """It used to report the browser as showing, and switch the watchdog off."""
    session, context, _, _ = await _scanning_session(monkeypatch)
    cdp = context.cdp_session
    real_send = cdp.send

    async def refuse_normal(method: str, params: object | None = None) -> dict[str, object]:
        if method == "Browser.setWindowBounds":
            raise RuntimeError("no native window")
        return await real_send(method, params)

    try:
        monkeypatch.setattr(cdp, "send", refuse_normal)
        assert not await session.show_browser()
        assert session.backgrounded and session.hiding_wanted
        assert cdp.window(7)["windowState"] == "minimized"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_the_auditor_can_show_the_browser_and_hide_it_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, context, scan_pages, cover = await _scanning_session(monkeypatch)
    cdp = context.cdp_session
    try:
        assert await session.show_browser()
        assert cdp.window(7)["windowState"] == "normal"
        assert not session.backgrounded
        # They asked to watch the scan, not the notice that it is running.
        assert scan_pages[0].fronted == 1

        await asyncio.sleep(0.1)  # many watchdog passes
        assert cdp.window(7)["windowState"] == "normal", "the watchdog overruled the auditor"
        assert cdp.minimize_requests() == 1

        assert await session.hide_for_background_scan()
        assert cdp.window(7)["windowState"] == "minimized"
        # A scan tab was in front; minimized like that, its screenshots hang.
        assert cover.fronted == 2
        assert session.backgrounded
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_window_that_cannot_be_hidden_is_reported_as_showing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The UI tells the auditor what is on their screen, not what was asked for."""
    monkeypatch.setattr("audit.protected.session._HIDE_RECHECK_SECONDS", 0.01)
    session, _, _, context, page = _session_with_fake_browser()

    async def refuse(method: str, params: object | None = None) -> dict[str, object]:
        raise RuntimeError("no native window")

    await session.start()
    page.url = "https://app.example.edu/dashboard"
    session.enter_scan_mode()
    await session.prepare_background_scan_pages(1)
    await session.discard_manual_auth_page()
    monkeypatch.setattr(context.cdp_session, "send", refuse)
    try:
        assert not await session.hide_for_background_scan()
        assert not session.backgrounded
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_the_browser_cannot_be_hidden_or_shown_before_sign_in_is_confirmed() -> None:
    session, _, _, _, _ = _session_with_fake_browser()
    await session.start()
    try:
        with pytest.raises(ManualAuthenticationError):
            await session.hide_for_background_scan()
        with pytest.raises(ManualAuthenticationError):
            await session.show_browser()
    finally:
        await session.close()


@dataclass
class _FakePopup(_FakePage):
    """A tab another page opened — what an SSO/LTI handoff produces."""

    opener_page: object | None = None

    async def opener(self) -> object | None:
        return self.opener_page


@pytest.mark.asyncio
async def test_sign_in_tab_opened_by_sso_is_kept_and_becomes_the_session_page() -> None:
    """An SSO handoff tab must survive, and be where verification looks.

    Institutional SSO routinely hands off through a tab it opens — an LTI
    launch from a VLE into the tool it embeds is the ordinary case. Closing
    it on arrival, which is correct while scanning, made those applications
    impossible to sign in to: the auditor watched the tab they needed vanish.
    """
    session, _playwright, _chromium, context, page = _session_with_fake_browser()
    await session.start()

    on_page = context.emit_page
    popup = _FakePopup(opener_page=page)
    popup.url = "https://app.example.edu/dashboard"

    await on_page(popup)  # type: ignore[operator]

    assert not popup.closed, "the tab SSO opened was closed and sign-in could not continue"
    # The entry point reads session.page; leaving it on the original tab would
    # report a stale sign-in URL and then start the crawl from it.
    assert session.page is popup
    assert session.enter_scan_mode() == "https://app.example.edu/dashboard"


@pytest.mark.asyncio
async def test_auxiliary_tab_is_still_closed_once_scanning_starts() -> None:
    """The control that motivated closing popups stays in force while scanning.

    During the crawl every page is one Axcess deliberately created, so a tab
    with an opener is uncontrolled navigation and must never become evidence.
    """
    session, _playwright, _chromium, context, page = _session_with_fake_browser()
    await session.start()
    page.url = "https://app.example.edu/dashboard"
    session.enter_scan_mode()

    on_page = context.emit_page
    popup = _FakePopup(opener_page=page)

    await on_page(popup)  # type: ignore[operator]

    assert popup.closed, "an opener-created tab survived into scan mode"


@pytest.mark.asyncio
async def test_a_handoff_tab_that_closes_itself_falls_back_to_the_previous_tab() -> None:
    """OAuth windows commonly close themselves after returning control."""
    session, _playwright, _chromium, context, page = _session_with_fake_browser()
    await session.start()

    on_page = context.emit_page
    popup = _FakePopup(opener_page=page)
    await on_page(popup)  # type: ignore[operator]
    assert session.page is popup

    # Playwright fires "close" on the page; the session registered for it.
    close_handler = popup.event_handlers["close"]
    close_handler(popup)  # type: ignore[operator]

    assert session.page is page, "the session kept pointing at a closed tab"


@pytest.mark.asyncio
async def test_closing_extra_login_tabs_preserves_the_original_for_scanning() -> None:
    session, _, _, context, page = _session_with_fake_browser()
    try:
        await session.start()
        page.url = "https://app.example.edu/dashboard"
        page.has_session_storage = True
        on_page = context.emit_page
        popups = [_FakePopup(opener_page=page), _FakePopup(opener_page=page)]
        for popup in popups:
            await on_page(popup)  # type: ignore[operator]
        for popup in reversed(popups):
            await popup.close(run_before_unload=False)

        assert session.page is page
        session.enter_scan_mode()
        scan_pages = await session.prepare_background_scan_pages(2)
        await session.discard_manual_auth_page()

        assert scan_pages == (page,)
        assert not page.closed, "sign-in cleanup closed the retained scan tab"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_closing_the_only_login_tab_clears_the_session_page() -> None:
    session, _, _, _, page = _session_with_fake_browser()
    try:
        await session.start()
        await page.close(run_before_unload=False)
        with pytest.raises(ManualAuthenticationError, match="not running"):
            session.enter_scan_mode()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_discarding_sign_in_closes_every_tab_it_used() -> None:
    """A handoff tab can hold a live callback or event stream of its own."""
    session, _playwright, _chromium, context, page = _session_with_fake_browser()
    await session.start()

    on_page = context.emit_page
    popup = _FakePopup(opener_page=page)
    popup.url = "https://app.example.edu/dashboard"
    await on_page(popup)  # type: ignore[operator]
    session.enter_scan_mode()

    await session.discard_manual_auth_page()

    assert page.closed, "the original sign-in tab was left open"
    assert popup.closed, "the tab SSO opened was left open after sign-in"


# ------------------------------------------- interaction on the login path


@pytest.mark.asyncio
async def test_the_shared_fetcher_carries_an_interaction_probe() -> None:
    """The authenticated fetcher must be able to operate page controls.

    The login handoff does not use the orchestrator's fetcher; it builds its
    own from the signed-in session. That builder accepted an axe analyzer and
    the keyboard, responsive, focus, and visual probes — and no interaction
    probe — so a 358-page authenticated scan ran with interaction enabled in
    its config, recorded 358 pages probed, and reached zero DOM states. The
    probe was never there to run.
    """
    from audit.analyzer.axe import AxeAnalyzer
    from audit.analyzer.interaction import InteractionProbe

    session, _playwright, _chromium, _context, page = _session_with_fake_browser()
    await session.start()
    page.url = "https://app.example.edu/dashboard"
    session.enter_scan_mode()

    axe = AxeAnalyzer(axe_source="/* stub */")
    fetcher = session.create_shared_js_fetcher(
        axe_analyzer=axe,
        interaction_probe=InteractionProbe(axe=axe),
    )

    assert fetcher._interaction_probe is not None, (
        "the authenticated fetcher cannot operate controls, so interaction "
        "silently does nothing on every login scan"
    )


@pytest.mark.asyncio
async def test_opening_the_sign_in_browser_leaves_exactly_one_tab() -> None:
    """Chromium opens a blank startup tab before Playwright asks for anything.

    With ``--incognito`` that tab was a whole second window, and the sign-in
    page created afterwards lived in the ordinary profile -- so the auditor got
    two windows and no way to tell which one Axcess was watching, while the
    flag protected nothing. Isolation is the ephemeral profile directory, which
    is removed on close.
    """
    session, _, _, context, page = _session_with_fake_browser()
    startup = context.startup_pages[0]

    await session.start()

    assert context.pages == [page], "the startup tab outlived sign-in"
    assert startup.closed, "the blank startup tab was left open"
    assert not page.closed, "the sign-in tab must survive"
    assert session.page is page


@pytest.mark.asyncio
async def test_a_popup_opened_during_sign_in_is_kept() -> None:
    """Only the startup leftovers are closed.

    An SSO handoff window arrives later, through the context's page event, and
    is adopted as the tab the session speaks for. Closing those would break
    every identity provider that completes sign-in in a second window.
    """
    session, _, _, context, page = _session_with_fake_browser()
    await session.start()

    popup = _FakePopup(opener_page=page)
    await context.emit_page(popup)

    assert not popup.closed
    assert session.page is popup, "the handoff window should become the live tab"
