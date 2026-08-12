"""Focused safety tests for authenticated/protected scan egress controls."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from audit.protected.egress import (
    EgressViolation,
    LoopbackEgressProxy,
    ProtectedEgressPolicy,
    redact_url,
)


def _public_resolver(host: str) -> tuple[str, ...]:
    assert host in {"app.example.edu", "cdn.example.edu", "xn--bcher-kva.example"}
    return ("8.8.8.8", "2001:4860:4860::8888")


def test_exact_https_origins_accept_default_port_and_only_configured_cdns() -> None:
    policy = ProtectedEgressPolicy(
        ["https://app.example.edu", "https://cdn.example.edu:8443"],
        resolver=_public_resolver,
    )

    assert policy.allowed_origins == (
        "https://app.example.edu",
        "https://cdn.example.edu:8443",
    )
    assert policy.validate_url("https://APP.example.edu:443/dashboard").url == (
        "https://app.example.edu/dashboard"
    )
    assert policy.validate_url("https://cdn.example.edu:8443/app.css").url == (
        "https://cdn.example.edu:8443/app.css"
    )

    for url in (
        "https://cdn.example.edu/app.css",
        "https://files.example.edu/export.csv",
        "http://app.example.edu/dashboard",
    ):
        with pytest.raises(EgressViolation):
            policy.validate_url(url)


@pytest.mark.parametrize(
    "allowed_origin",
    [
        "http://app.example.edu",
        "https://person@app.example.edu",
        "https://app.example.edu/a",
        "https://app.example.edu/?team=accessibility",
        "https://app.example.edu/#scope",
        "https://127.0.0.1",
        "https://[::1]",
    ],
)
def test_allowed_origin_configuration_reuses_the_persisted_exact_origin_boundary(
    allowed_origin: str,
) -> None:
    with pytest.raises(EgressViolation, match="invalid_approved_origin"):
        ProtectedEgressPolicy([allowed_origin], resolver=_public_resolver)


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://person:password@app.example.edu/", "userinfo_not_allowed"),
        ("https://@app.example.edu/", "userinfo_not_allowed"),
        ("https://app.example.edu:0/", "invalid_port"),
        ("https://app.example.edu/?access_token=secret", "sensitive_query_parameter"),
        ("https://app.example.edu/?access%5Ftoken=secret", "sensitive_query_parameter"),
        ("https://app.example.edu/?access%255Ftoken=secret", "sensitive_query_parameter"),
        ("https://app.example.edu/?oauth-token=secret", "sensitive_query_parameter"),
        ("https://app.example.edu/?continue=/;SAMLResponse=secret", "sensitive_query_parameter"),
        ("https://app.example.edu/?sessionToken=secret", "sensitive_query_parameter"),
        ("https://app.example.edu/?filter=recent#section", "fragment_not_allowed"),
        ("https://app.example.edu/%00", "invalid_url"),
    ],
)
def test_requests_reject_secret_bearing_or_ambiguous_urls(url: str, code: str) -> None:
    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=_public_resolver)

    with pytest.raises(EgressViolation, match=code):
        policy.validate_url(url)


def test_transient_manual_auth_urls_allow_oauth_query_parameters_but_not_fragments() -> None:
    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=_public_resolver)

    assert policy.validate_transient_auth_url(
        "https://app.example.edu/auth/callback?code=short-lived&state=opaque"
    ).url.endswith("callback?code=short-lived&state=opaque")
    with pytest.raises(EgressViolation, match="fragment_not_allowed"):
        policy.validate_transient_auth_url("https://app.example.edu/#access_token=secret")


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.0.0.8",),
        ("169.254.169.254",),
        ("192.168.1.1",),
        ("::1",),
        ("fe80::1",),
        ("8.8.8.8", "10.0.0.8"),
        ("2001:4860:4860::8888", "fc00::1"),
    ],
)
def test_dns_answer_must_contain_only_public_addresses(addresses: tuple[str, ...]) -> None:
    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=lambda _host: addresses)

    with pytest.raises(EgressViolation, match="non_public_address"):
        policy.validate_url("https://app.example.edu/dashboard")


def test_dns_is_rechecked_for_every_request_to_prevent_rebinding() -> None:
    answers = iter((("8.8.8.8",), ("127.0.0.1",)))
    calls: list[str] = []

    def resolver(host: str) -> tuple[str, ...]:
        calls.append(host)
        return next(answers)

    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=resolver)

    assert policy.validate_url("https://app.example.edu/first").url.endswith("/first")
    with pytest.raises(EgressViolation, match="non_public_address"):
        policy.validate_url("https://app.example.edu/second")
    assert calls == ["app.example.edu", "app.example.edu"]


def test_redirect_and_final_urls_both_must_stay_in_approved_scope() -> None:
    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=_public_resolver)

    assert policy.validate_redirect(
        "https://app.example.edu/start", "https://app.example.edu/after-login"
    ).url.endswith("/after-login")
    with pytest.raises(EgressViolation, match="origin_not_approved"):
        policy.validate_redirect("https://app.example.edu/start", "https://cdn.example.edu/after")
    with pytest.raises(EgressViolation, match="origin_not_approved"):
        policy.validate_final_url("https://cdn.example.edu/start", "https://app.example.edu/final")


def test_unicode_host_is_canonicalized_before_exact_origin_and_dns_lookup() -> None:
    seen: list[str] = []

    def resolver(host: str) -> tuple[str, ...]:
        seen.append(host)
        return ("8.8.8.8",)

    policy = ProtectedEgressPolicy(["https://bücher.example"], resolver=resolver)

    validated = policy.validate_url("https://BÜCHER.example/account")
    assert validated.url == "https://xn--bcher-kva.example/account"
    assert seen == ["xn--bcher-kva.example"]


def test_invalid_or_empty_dns_answers_are_rejected() -> None:
    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=lambda _host: ())
    with pytest.raises(EgressViolation, match="dns_resolution_failed"):
        policy.validate_url("https://app.example.edu/")

    malformed = ProtectedEgressPolicy(
        ["https://app.example.edu"], resolver=lambda _host: ("not-an-ip",)
    )
    with pytest.raises(EgressViolation, match="dns_resolution_failed"):
        malformed.validate_url("https://app.example.edu/")


@dataclass
class _FakeRequest:
    method: str
    url: str


@dataclass
class _FakeRoute:
    request: _FakeRequest
    actions: list[tuple[str, str | None]] = field(default_factory=list)

    async def abort(self, reason: str) -> None:
        self.actions.append(("abort", reason))

    async def continue_(self) -> None:
        self.actions.append(("continue", None))


@pytest.mark.asyncio
async def test_playwright_route_policy_allows_only_safe_read_requests() -> None:
    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=_public_resolver)
    routes = [
        _FakeRoute(_FakeRequest("GET", "https://app.example.edu/dashboard")),
        _FakeRoute(_FakeRequest("HEAD", "https://app.example.edu/health")),
        _FakeRoute(_FakeRequest("POST", "https://app.example.edu/form")),
        _FakeRoute(_FakeRequest("DELETE", "https://app.example.edu/account")),
        _FakeRoute(_FakeRequest("GET", "https://evil.example/track.js")),
        _FakeRoute(_FakeRequest("GET", "https://app.example.edu/?token=secret")),
    ]

    route_policy = policy.playwright_policy()
    for route in routes:
        await route_policy.handle_route(route)  # type: ignore[arg-type]

    assert routes[0].actions == [("continue", None)]
    assert routes[1].actions == [("continue", None)]
    for route in routes[2:]:
        assert route.actions == [("abort", "blockedbyclient")]
    assert route_policy.context_options == {
        "accept_downloads": False,
        "service_workers": "block",
    }


@dataclass
class _FakePage:
    closed: bool = False
    opener_page: object | None = None
    event_handlers: dict[str, object] = field(default_factory=dict)

    async def close(self, *, run_before_unload: bool) -> None:
        assert not run_before_unload
        self.closed = True

    async def opener(self) -> object | None:
        return self.opener_page

    def on(self, event: str, handler: object) -> None:
        self.event_handlers[event] = handler


@dataclass
class _FakeDownload:
    cancelled: bool = False

    async def cancel(self) -> None:
        self.cancelled = True


@dataclass
class _FakeWebSocketRoute:
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_playwright_route_policy_closes_popups_and_cancels_downloads() -> None:
    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=_public_resolver)
    route_policy = policy.playwright_policy()
    popup = _FakePage()
    download = _FakeDownload()
    web_socket = _FakeWebSocketRoute()

    await route_policy.handle_popup(popup)  # type: ignore[arg-type]
    await route_policy.handle_download(download)  # type: ignore[arg-type]
    await route_policy.handle_web_socket(web_socket)  # type: ignore[arg-type]

    assert popup.closed
    assert download.cancelled
    assert web_socket.closed


@dataclass
class _FakeContext:
    route_calls: list[tuple[str, object]] = field(default_factory=list)
    web_socket_route_calls: list[tuple[str, object]] = field(default_factory=list)
    event_handlers: dict[str, object] = field(default_factory=dict)

    async def route(self, pattern: str, handler: object) -> None:
        self.route_calls.append((pattern, handler))

    async def route_web_socket(self, pattern: str, handler: object) -> None:
        self.web_socket_route_calls.append((pattern, handler))

    def on(self, event: str, handler: object) -> None:
        self.event_handlers[event] = handler


@pytest.mark.asyncio
async def test_context_installation_covers_new_crawl_pages_but_closes_popups() -> None:
    policy = ProtectedEgressPolicy(["https://app.example.edu"], resolver=_public_resolver)
    route_policy = policy.playwright_policy()
    context = _FakeContext()

    await route_policy.install_on_context(context)  # type: ignore[arg-type]

    assert context.route_calls == [("**/*", route_policy.handle_route)]
    assert context.web_socket_route_calls == [("**/*", route_policy.handle_web_socket)]
    assert set(context.event_handlers) == {"page"}

    primary_page = _FakePage()
    popup_page = _FakePage(opener_page=primary_page)
    await route_policy.handle_context_page(primary_page)  # type: ignore[arg-type]
    await route_policy.handle_context_page(popup_page)  # type: ignore[arg-type]

    assert not primary_page.closed
    assert primary_page.event_handlers == {"download": route_policy.handle_download}
    assert popup_page.closed


def test_redact_url_never_returns_userinfo_query_values_or_fragments() -> None:
    value = redact_url(
        "https://user:password@app.example.edu/account?access_token=secret&tab=profile#private"
    )

    assert value == "https://app.example.edu/account?…"
    for secret in ("user", "password", "secret", "private", "profile"):
        assert secret not in value


def test_redact_url_returns_non_sensitive_marker_for_invalid_input() -> None:
    assert redact_url("not a URL") == "<invalid-url>"


@dataclass(eq=False)
class _FakeTunnelWriter:
    closed: bool = False

    def close(self) -> None:
        self.closed = True


def test_proxy_policy_transition_closes_pre_auth_tunnels_and_never_broadens() -> None:
    """Browser connection pooling cannot retain an IdP tunnel into scan mode."""

    setup = ProtectedEgressPolicy(
        ["https://app.example.edu", "https://login.example.edu"],
        resolver=lambda _host: ("8.8.8.8",),
    )
    scan = ProtectedEgressPolicy(["https://app.example.edu"], resolver=lambda _host: ("8.8.8.8",))
    proxy = LoopbackEgressProxy(setup)
    client_tunnel = _FakeTunnelWriter()
    upstream_tunnel = _FakeTunnelWriter()
    proxy._active_client_writers.add(client_tunnel)  # type: ignore[arg-type]
    proxy._active_upstream_writers.add(upstream_tunnel)  # type: ignore[arg-type]

    proxy.set_policy(scan)

    assert client_tunnel.closed
    assert upstream_tunnel.closed
    assert proxy._policy_generation == 1
    with pytest.raises(ValueError, match="only be tightened"):
        proxy.set_policy(setup)
