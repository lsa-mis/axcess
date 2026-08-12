"""Unit tests for companion-side manual protected authentication."""

from __future__ import annotations

import asyncio
import io
import os
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
    verify_authenticated_target_url,
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


def test_setup_policy_allows_explicit_identity_provider_and_cdn_only_during_setup() -> None:
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
    with pytest.raises(EgressViolation, match="origin_not_approved"):
        policies.scan.validate_url("https://login.example.edu/authorize")


def test_local_manual_login_allows_dynamic_public_mfa_then_tightens_to_target() -> None:
    """A Duo-style redirect works only before the human confirms sign-in."""

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
    with pytest.raises(EgressViolation, match="origin_not_approved"):
        policies.scan.validate_url("https://api-12345.duosecurity.com/frame/v4/auth")
    assert (
        verify_authenticated_target_url("https://app.example.edu/dashboard", policies).origin.value
        == "https://app.example.edu"
    )


def test_seed_and_authenticated_verification_require_target_not_identity_provider() -> None:
    policies = _policies()

    assert validate_protected_seed_url("https://app.example.edu/start", policies).url.endswith(
        "/start"
    )
    assert verify_authenticated_target_url(
        "https://app.example.edu/dashboard", policies
    ).url.endswith("/dashboard")

    for value in (
        "https://login.example.edu/authorize",
        "https://cdn.example.edu/app.css",
        "https://app.example.edu/callback?code=temporary",
    ):
        with pytest.raises(ManualAuthenticationError):
            verify_authenticated_target_url(value, policies)
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


@dataclass
class _FakePage:
    url: str = "about:blank"
    goto_calls: list[tuple[str, int, str]] = field(default_factory=list)
    event_handlers: dict[str, object] = field(default_factory=dict)
    closed: bool = False

    async def goto(self, url: str, *, timeout: int, wait_until: str) -> object:
        self.url = url
        self.goto_calls.append((url, timeout, wait_until))
        return object()

    async def opener(self) -> None:
        return None

    async def close(self, *, run_before_unload: bool) -> None:
        assert not run_before_unload
        self.closed = True

    def on(self, event: str, handler: object) -> None:
        self.event_handlers[event] = handler


@dataclass
class _FakeContext:
    page: _FakePage
    route_calls: list[tuple[str, object]] = field(default_factory=list)
    web_socket_route_calls: list[tuple[str, object]] = field(default_factory=list)
    event_handlers: dict[str, object] = field(default_factory=dict)
    init_scripts: list[str] = field(default_factory=list)
    closed: bool = False

    async def route(self, pattern: str, handler: object) -> None:
        self.route_calls.append((pattern, handler))

    async def route_web_socket(self, pattern: str, handler: object) -> None:
        self.web_socket_route_calls.append((pattern, handler))

    async def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)

    def on(self, event: str, handler: object) -> None:
        self.event_handlers[event] = handler

    async def new_page(self) -> _FakePage:
        return self.page

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
async def test_manual_session_is_headed_ephemeral_and_tightens_after_target_verification() -> None:
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
    assert len(context.init_scripts) == 1
    assert "RTCPeerConnection" in context.init_scripts[0]
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
    with pytest.raises(ManualAuthenticationError):
        session.verify_authenticated_target("https://login.example.edu/authorize")

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
    verified = session.verify_authenticated_target()
    assert verified.url == "https://app.example.edu/dashboard"
    assert session.state is ManualAuthState.AUTHENTICATED

    # The authenticated context remains available for new crawl tabs, but
    # the original headed sign-in tab is discarded as soon as it is safe.
    await session.discard_manual_auth_page()
    assert page.closed
    with pytest.raises(ManualAuthenticationError):
        _ = session.page

    after_auth_idp = _FakeRoute(_FakeRequest("GET", "https://login.example.edu/authorize"))
    unsafe_scan_post = _FakeRoute(_FakeRequest("POST", "https://app.example.edu/form", "fetch"))
    unsafe_worker = _FakeRoute(_FakeRequest("GET", "https://app.example.edu/worker.js", "worker"))
    for route in (after_auth_idp, unsafe_scan_post, unsafe_worker):
        await session._route_guard.handle_route(route)  # type: ignore[arg-type]
        assert route.actions == [("abort", "blockedbyclient")]

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
    assert chunked_image.actions == [("abort", "blockedbyclient")]
    assert session.consume_scan_egress_block() == "egress_policy_blocked"

    fetcher = session.create_shared_js_fetcher()
    assert fetcher._shared_context is context  # Shared context, never exported state.

    await session.close()
    assert session.state is ManualAuthState.CLOSED
    assert context.closed
    assert chromium.user_data_dir is not None
    assert not os.path.exists(chromium.user_data_dir)
    assert playwright.stopped


@pytest.mark.asyncio
async def test_wait_for_authenticated_target_polls_without_reading_browser_storage() -> None:
    session, _playwright, _browser, _context, page = _session_with_fake_browser()
    await session.start()
    page.url = "https://login.example.edu/authorize"

    async def complete_manually() -> None:
        await asyncio.sleep(0.01)
        page.url = "https://app.example.edu/after-sign-in"

    task = asyncio.create_task(complete_manually())
    verified = await session.wait_for_authenticated_target(timeout_ms=500, poll_interval_s=0.001)
    await task

    assert verified.url.endswith("/after-sign-in")
    assert session.state is ManualAuthState.AUTHENTICATED
    await session.close()


@pytest.mark.asyncio
async def test_wait_times_out_at_identity_provider_without_claiming_authenticated() -> None:
    session, _playwright, _browser, _context, page = _session_with_fake_browser()
    await session.start()
    page.url = "https://login.example.edu/authorize"

    with pytest.raises(ManualAuthenticationError, match="Timed out"):
        await session.wait_for_authenticated_target(timeout_ms=5, poll_interval_s=0.001)
    assert session.state is ManualAuthState.AWAITING_MANUAL_AUTHENTICATION
    await session.close()
