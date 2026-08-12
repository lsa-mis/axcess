"""Network safety controls for authorized protected-site scans.

Protected scans must not turn an authenticated browser into a general-purpose
request proxy.  This module admits only explicitly approved HTTPS origins,
re-resolves a host for every request to defend against DNS rebinding, and
blocks non-public addresses.  It intentionally does *not* store, inspect, or
serialize any browser session material.

The policy is synchronous so it can be used by HTTP redirect handlers and by
Playwright's asynchronous routing callback.  Inject ``resolver`` in tests or
in a deployment that supplies an approved DNS resolver.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import re
import socket
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from audit.protected.models import normalize_exact_https_origin

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Download, Page, Route, WebSocketRoute

HostResolver = Callable[[str], Sequence[str]]

_DEFAULT_HTTPS_PORT = 443
_ALLOWED_METHODS = frozenset({"GET", "HEAD"})

# Normalize separator/case variants before comparison, e.g.
# ``access_token``, ``access-token``, and ``access%5ftoken`` all become
# ``accesstoken``.  A protected scan should fail closed here: false positives
# are preferable to storing or following a credential-bearing URL.
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "assertion",
        "auth",
        "authorization",
        "client_secret",
        "code",
        "credential",
        "id_token",
        "jwt",
        "key",
        "oauth_token",
        "password",
        "passwd",
        "pwd",
        "refresh_token",
        "relaystate",
        "samlrequest",
        "samlresponse",
        "secret",
        "session",
        "sessionid",
        "sid",
        "sig",
        "signature",
        "state",
        "ticket",
        "token",
        "x_amz_credential",
        "x_amz_security_token",
        "x_amz_signature",
        "x_goog_signature",
        "x_goog_credential",
        "x_ms_signature",
    }
)
_NORMALIZED_SENSITIVE_QUERY_KEYS = frozenset(
    re.sub(r"[-_.\s]", "", key).casefold() for key in _SENSITIVE_QUERY_KEYS
)


class ProtectedEgressError(ValueError):
    """A request is unsafe for a protected crawl.

    ``code`` is intentionally stable and safe to put in an audit event.  The
    exception message never includes the rejected URL, which may include a
    credential-bearing query string.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Protected crawl request rejected: {code}.")


# Kept as a concise import name for callers that need to distinguish a policy
# refusal from an ordinary network failure.
EgressViolation = ProtectedEgressError


@dataclass(frozen=True, slots=True, order=True)
class ApprovedOrigin:
    """One exact, normalized HTTPS origin allowed for a protected scan."""

    host: str
    port: int = _DEFAULT_HTTPS_PORT

    @property
    def value(self) -> str:
        host = f"[{self.host}]" if _is_ip_literal(self.host, version=6) else self.host
        port = "" if self.port == _DEFAULT_HTTPS_PORT else f":{self.port}"
        return f"https://{host}{port}"


@dataclass(frozen=True, slots=True)
class ValidatedUrl:
    """A canonical protected-scan URL that passed scope and DNS checks."""

    url: str
    origin: ApprovedOrigin
    # The exact public answers checked for this request.  A loopback proxy
    # connects to one of these literals rather than asking the OS resolver a
    # second time, closing the normal DNS-rebinding time-of-check/time-of-use
    # gap for browser traffic.
    resolved_addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ParsedUrl:
    """Internal normalized URL components after syntax and secret checks."""

    host: str
    port: int
    path: str
    query: str

    @property
    def origin(self) -> ApprovedOrigin:
        return ApprovedOrigin(host=self.host, port=self.port)

    @property
    def canonical_url(self) -> str:
        host = f"[{self.host}]" if _is_ip_literal(self.host, version=6) else self.host
        netloc = host if self.port == _DEFAULT_HTTPS_PORT else f"{host}:{self.port}"
        return urlunsplit(("https", netloc, self.path, self.query, ""))


class ProtectedEgressPolicy:
    """Validate network requests for one authorized protected scan.

    The allowed origins are exact origins, not host suffixes or wildcard
    patterns.  A URL is re-resolved every time it is validated; callers must
    call :meth:`validate_url` for the seed, redirects, final navigation URL,
    and every browser resource request.
    """

    def __init__(
        self,
        allowed_origins: Iterable[str],
        *,
        resolver: HostResolver | None = None,
    ) -> None:
        origins = frozenset(_parse_approved_origin(value) for value in allowed_origins)
        if not origins:
            raise ValueError("Protected scans require at least one approved HTTPS origin.")
        self._origins = origins
        self._resolver = resolver or _resolve_hostname

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        """Approved origin strings, sorted for stable API/UI output."""
        return tuple(origin.value for origin in sorted(self._origins))

    def validate_url(self, url: str) -> ValidatedUrl:
        """Return a canonical URL only when it is safe to request.

        This includes a fresh DNS/IP check.  The method is deliberately not
        memoized: caching hostname results would allow a changed DNS answer to
        bypass the protected scan's address policy.
        """
        parsed = _parse_request_url(url)
        if parsed.origin not in self._origins:
            raise EgressViolation("origin_not_approved")
        addresses = _require_public_resolution(parsed.host, self._resolver)
        return ValidatedUrl(
            url=parsed.canonical_url,
            origin=parsed.origin,
            resolved_addresses=addresses,
        )

    def validate_transient_auth_url(self, url: str) -> ValidatedUrl:
        """Validate an in-memory manual-authentication navigation.

        OAuth/SAML redirects commonly carry short-lived ``code`` or ``state``
        parameters. They cannot be followed by the normal crawler policy,
        because those URLs must never become evidence or logs. The companion
        may use this narrow method only while a person is actively signing in
        in its headed, ephemeral browser. Userinfo, URL fragments, unapproved
        origins, and non-public DNS answers remain prohibited.
        """
        parsed = _parse_request_url(url, allow_sensitive_query=True)
        if parsed.origin not in self._origins:
            raise EgressViolation("origin_not_approved")
        addresses = _require_public_resolution(parsed.host, self._resolver)
        return ValidatedUrl(
            url=parsed.canonical_url,
            origin=parsed.origin,
            resolved_addresses=addresses,
        )

    def validate_redirect(self, source_url: str, redirect_url: str) -> ValidatedUrl:
        """Validate both ends of a redirect before following it."""
        self.validate_url(source_url)
        return self.validate_url(redirect_url)

    def validate_final_url(self, requested_url: str, final_url: str) -> ValidatedUrl:
        """Validate the initial request and browser/HTTP final URL.

        Browser and HTTP stacks can expose only the final URL after automatic
        redirects.  Calling this before evidence extraction prevents a
        successful cross-origin redirect from being stored as scan evidence.
        """
        return self.validate_redirect(requested_url, final_url)

    def allows_url(self, url: str) -> bool:
        """Return whether ``url`` can be requested without exposing a reason."""
        try:
            self.validate_url(url)
        except EgressViolation:
            return False
        return True

    def allows_origin(self, origin: str) -> bool:
        """Return whether an exact origin is admitted by this policy."""

        try:
            parsed = _parse_request_url(f"{origin.rstrip('/')}/")
        except EgressViolation:
            return False
        return parsed.origin in self._origins

    def playwright_policy(self) -> PlaywrightRoutePolicy:
        """Create a routing adapter for an authenticated Playwright page."""
        return PlaywrightRoutePolicy(self)


class PublicHttpsManualAuthPolicy(ProtectedEgressPolicy):
    """Public-HTTPS policy used only by a human-controlled local login tab.

    This intentionally mirrors a normal browser during the manual SSO/MFA
    handoff, where an IdP can redirect to a dynamically assigned provider
    origin (for example a Duo universal-prompt host). It still rejects HTTP,
    URL userinfo, fragments, private/loopback/metadata addresses, and unsafe
    DNS answers. The browser switches irreversibly to an exact-origin
    :class:`ProtectedEgressPolicy` before the crawler opens its first page.
    """

    def __init__(self, *, resolver: HostResolver | None = None) -> None:
        self._resolver = resolver or _resolve_hostname

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        # The setup policy is intentionally dynamic and is never serialized.
        return ()

    def validate_url(self, url: str) -> ValidatedUrl:
        return self._validate_public(url, allow_sensitive_query=False)

    def validate_transient_auth_url(self, url: str) -> ValidatedUrl:
        return self._validate_public(url, allow_sensitive_query=True)

    def allows_origin(self, origin: str) -> bool:
        try:
            parsed = _parse_request_url(f"{origin.rstrip('/')}/")
            _require_public_resolution(parsed.host, self._resolver)
        except EgressViolation:
            return False
        return True

    def _validate_public(self, url: str, *, allow_sensitive_query: bool) -> ValidatedUrl:
        parsed = _parse_request_url(url, allow_sensitive_query=allow_sensitive_query)
        addresses = _require_public_resolution(parsed.host, self._resolver)
        return ValidatedUrl(
            url=parsed.canonical_url,
            origin=parsed.origin,
            resolved_addresses=addresses,
        )


class LoopbackEgressProxy:
    """A tiny CONNECT-only browser egress guard bound to ``127.0.0.1``.

    Playwright routing is useful for request method and resource-type policy,
    but it is not a transport boundary: redirects and a browser DNS lookup
    can otherwise escape a preflight check.  This proxy accepts only HTTPS
    ``CONNECT`` tunnels, reuses :class:`ProtectedEgressPolicy` for every
    connection, and dials an already-validated public IP literal.  It never
    logs request lines, headers, or bytes flowing through a tunnel.

    It is intentionally an in-process companion component, not a public
    proxy.  The browser receives it only through a loopback context proxy;
    closing the manual-authentication session closes every tunnel and the
    listening socket.
    """

    def __init__(self, policy: ProtectedEgressPolicy) -> None:
        self._policy = policy
        self._policy_generation = 0
        self._server: asyncio.AbstractServer | None = None
        self._server_url: str | None = None
        # These contain only live socket writer objects. They are never
        # logged, inspected, or serialized; retaining them lets a change from
        # the manual-auth setup policy to the narrower scan policy actively
        # tear down pre-authentication tunnels instead of relying on browser
        # connection pooling to eventually retire them.
        self._active_client_writers: set[asyncio.StreamWriter] = set()
        self._active_upstream_writers: set[asyncio.StreamWriter] = set()

    @property
    def server_url(self) -> str:
        if self._server is None or self._server_url is None:
            raise RuntimeError("Protected loopback egress proxy is not running.")
        return self._server_url

    def set_policy(self, policy: ProtectedEgressPolicy) -> None:
        """Tighten the allowed connection set after manual sign-in.

        Existing CONNECT tunnels were admitted under the preceding policy.
        They may carry an IdP or other setup-origin session, so they are not
        safe to keep after the authenticated crawler becomes target-scoped.
        Closing both tunnel ends forces Chromium to reconnect; each new
        CONNECT is then admitted under ``policy`` and freshly DNS-validated.
        The generation check in :meth:`_handle_client` also closes a tunnel
        that happened to be opening while the policy changed.
        """

        if not all(self._policy.allows_origin(origin) for origin in policy.allowed_origins):
            raise ValueError("Loopback egress policy may only be tightened.")

        self._policy = policy
        self._policy_generation += 1
        self._close_active_tunnels()

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            self._handle_client,
            host="127.0.0.1",
            port=0,
            limit=16 * 1024,
            start_serving=True,
        )
        # Typeshed's ``AbstractServer`` omits ``sockets`` even though the
        # asyncio server returned by ``start_server`` exposes the bound
        # listener sequence. Read it once, retain only a loopback URL, and
        # avoid leaking socket objects into the companion API.
        sockets = cast(list[socket.socket] | None, getattr(self._server, "sockets", None))
        if not sockets:
            await self.close()
            raise RuntimeError("Protected loopback egress proxy did not bind a listener.")
        host, port = sockets[0].getsockname()[:2]
        self._server_url = f"http://{host}:{port}"

    async def close(self) -> None:
        self._close_active_tunnels()
        server = self._server
        self._server = None
        self._server_url = None
        if server is not None:
            server.close()
            await server.wait_closed()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        self._active_client_writers.add(writer)
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10.0)
            host, port = _parse_connect_authority(header)
            # A CONNECT request contains no path/query. Build a synthetic
            # canonical HTTPS URL solely for exact-origin/DNS admission.
            host_part = f"[{host}]" if _is_ip_literal(host, version=6) else host
            suffix = "" if port == _DEFAULT_HTTPS_PORT else f":{port}"
            generation = self._policy_generation
            policy = self._policy
            validated = policy.validate_url(f"https://{host_part}{suffix}/")
            # ``validated`` always carries freshly resolved, public-only
            # answers. Dial the literal so a later OS resolver answer cannot
            # turn a permitted name into private/metadata traffic.
            upstream_reader, upstream_writer = await _open_validated_connection(validated)
            # ``set_policy`` may run while opening a socket. Do not ever send
            # a successful CONNECT response for a tunnel admitted by an old
            # policy after scan mode has taken effect.
            if generation != self._policy_generation:
                raise EgressViolation("policy_changed")
            self._active_upstream_writers.add(upstream_writer)
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            if generation != self._policy_generation:
                raise EgressViolation("policy_changed")
            to_upstream = asyncio.create_task(_copy_stream(reader, upstream_writer))
            to_client = asyncio.create_task(_copy_stream(upstream_reader, writer))
            done, pending = await asyncio.wait(
                {to_upstream, to_client}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done | pending:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        except Exception:
            # Do not reflect a hostname, request line, or DNS error to the
            # browser. A generic proxy rejection is enough for the companion
            # to surface its safe re-authentication/scope message.
            with contextlib.suppress(Exception):
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                await writer.drain()
        finally:
            if upstream_writer is not None:
                self._active_upstream_writers.discard(upstream_writer)
                upstream_writer.close()
                with contextlib.suppress(Exception):
                    await upstream_writer.wait_closed()
            self._active_client_writers.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _close_active_tunnels(self) -> None:
        """Initiate close on every accepted tunnel without retaining bytes.

        ``StreamWriter.close`` is intentionally non-blocking. The serving
        coroutines own their corresponding ``wait_closed`` calls and remove
        the writers from these sets in ``finally``; keeping this operation
        synchronous makes it safe to invoke during the state transition that
        verifies a manual login.
        """

        for tunnel_writer in (
            *tuple(self._active_client_writers),
            *tuple(self._active_upstream_writers),
        ):
            with contextlib.suppress(Exception):
                tunnel_writer.close()


class PlaywrightRoutePolicy:
    """Apply a :class:`ProtectedEgressPolicy` to a Playwright page/context.

    Use :attr:`context_options` when creating the browser context, then attach
    the route policy *before* navigating the primary page.  Route callbacks
    check every browser request, including subresources and redirect targets.
    Downloads and popup pages are cancelled/closed rather than treated as
    evidence.
    """

    def __init__(self, egress: ProtectedEgressPolicy) -> None:
        self._egress = egress

    @property
    def context_options(self) -> dict[str, bool | str]:
        """Safe browser-context options required alongside route interception."""
        return {"accept_downloads": False, "service_workers": "block"}

    async def handle_route(self, route: Route) -> None:
        """Continue only GET/HEAD requests that pass the egress policy."""
        request = route.request
        if request.method.upper() not in _ALLOWED_METHODS:
            await route.abort("blockedbyclient")
            return
        try:
            self._egress.validate_url(request.url)
        except EgressViolation:
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    async def handle_popup(self, page: Page) -> None:
        """Close a popup immediately; it is never an authenticated scan page."""
        with contextlib.suppress(Exception):
            await page.close(run_before_unload=False)

    async def handle_download(self, download: Download) -> None:
        """Cancel downloads so protected files cannot enter local artifacts."""
        with contextlib.suppress(Exception):
            await download.cancel()

    async def handle_web_socket(self, route: WebSocketRoute) -> None:
        """Deny WebSockets through Playwright's dedicated interception API.

        Normal ``context.route`` handlers do not reliably see a WebSocket
        handshake. A WebSocket can be an authenticated, long-lived egress
        channel even when document/resource requests are GET-only, so block
        it before it connects rather than trying to inspect messages.
        """

        with contextlib.suppress(Exception):
            await route.close()

    async def install_on_page(self, page: Page) -> None:
        """Install request, popup, and download controls on a primary page.

        The caller should invoke this after ``context.new_page()`` and before
        ``page.goto()``.  It supplements ``context_options`` rather than
        replacing it: service workers must be blocked at context creation.
        """
        await page.route("**/*", self.handle_route)
        await page.route_web_socket("**/*", self.handle_web_socket)
        page.on("popup", self.handle_popup)
        page.on("download", self.handle_download)

    async def install_on_context(self, context: BrowserContext) -> None:
        """Install controls once on a context shared by many crawl pages.

        Use this variant when a companion creates a new page for every
        crawled URL. Context-level routing covers each page and its
        subresources. A context ``page`` listener closes only pages with an
        opener, leaving deliberately created crawl pages (which have no
        opener) usable. Each non-popup page also gets a download-cancellation
        listener; Playwright exposes downloads on pages rather than contexts.
        """
        await context.route("**/*", self.handle_route)
        await context.route_web_socket("**/*", self.handle_web_socket)
        context.on("page", self.handle_context_page)

    async def handle_context_page(self, page: Page) -> None:
        """Close a context page when it was opened by another page.

        Treat an inability to inspect the opener as unsafe. This cannot stop
        a target browser from attempting a popup, but it prevents the new
        page from becoming scan evidence or an uncontrolled navigation.
        """
        try:
            opener = await page.opener()
        except Exception:
            await self.handle_popup(page)
            return
        if opener is not None:
            await self.handle_popup(page)
            return
        page.on("download", self.handle_download)


def redact_url(url: str) -> str:
    """Return a URL safe for logs and non-sensitive audit events.

    Credentials, query values, and fragments are deliberately omitted.  This
    helper is for display only; callers must use :class:`ProtectedEgressPolicy`
    for admission decisions.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except (TypeError, ValueError):
        return "<invalid-url>"
    if not host or not parts.scheme:
        return "<invalid-url>"
    try:
        safe_host = _canonical_host(host)
    except EgressViolation:
        return "<invalid-url>"
    host_for_url = f"[{safe_host}]" if _is_ip_literal(safe_host, version=6) else safe_host
    safe_port = "" if port in (None, _DEFAULT_HTTPS_PORT) else f":{port}"
    query_marker = "?…" if parts.query else ""
    safe_base = urlunsplit(
        (parts.scheme.lower(), f"{host_for_url}{safe_port}", parts.path or "/", "", "")
    )
    return safe_base + query_marker


def _parse_approved_origin(value: str) -> ApprovedOrigin:
    # Persisted protected-scan config and runtime egress policy use one static
    # exact-origin parser. Runtime validation below adds per-request DNS/IP
    # checks, but must not accidentally accept an origin the configuration
    # boundary would reject.
    try:
        normalized = normalize_exact_https_origin(value)
    except ValueError as exc:
        raise EgressViolation("invalid_approved_origin") from exc
    parsed = _parse_url(normalized, allow_fragment=False)
    return parsed.origin


def _parse_request_url(value: str, *, allow_sensitive_query: bool = False) -> _ParsedUrl:
    return _parse_url(
        value,
        allow_fragment=False,
        allow_sensitive_query=allow_sensitive_query,
    )


def _parse_url(
    value: str,
    *,
    allow_fragment: bool,
    allow_sensitive_query: bool = False,
) -> _ParsedUrl:
    if not value or value != value.strip():
        raise EgressViolation("invalid_url")
    if _contains_control_characters(value):
        raise EgressViolation("invalid_url")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except (TypeError, ValueError) as exc:
        raise EgressViolation("invalid_url") from exc
    if parts.scheme.lower() != "https":
        raise EgressViolation("https_required")
    # Check the raw netloc too: an empty user name (``https://@host``) is
    # still userinfo and must not silently pass through urllib's parser.
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise EgressViolation("userinfo_not_allowed")
    if not host:
        raise EgressViolation("missing_host")
    if port == 0:
        raise EgressViolation("invalid_port")
    if parts.fragment and not allow_fragment:
        raise EgressViolation("fragment_not_allowed")
    if not allow_sensitive_query:
        _reject_unsafe_query(parts.query)
    _reject_decoded_control_characters(parts.path, parts.query)
    return _ParsedUrl(
        host=_canonical_host(host),
        port=port if port is not None else _DEFAULT_HTTPS_PORT,
        path=parts.path or "/",
        query=parts.query,
    )


def _canonical_host(host: str) -> str:
    candidate = host.rstrip(".")
    if not candidate:
        raise EgressViolation("invalid_host")
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        pass
    try:
        canonical = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise EgressViolation("invalid_host") from exc
    if len(canonical) > 253 or not _valid_dns_name(canonical):
        raise EgressViolation("invalid_host")
    return canonical


def _valid_dns_name(host: str) -> bool:
    if host.startswith(".") or host.endswith(".") or ".." in host:
        return False
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is not None
        for label in host.split(".")
    )


def _reject_unsafe_query(query: str) -> None:
    # Treat both '&' and legacy ';' separators as parameters.  ``parse_qsl``
    # no longer recognizes ';' by default, which could otherwise hide a token
    # key in a URL accepted by older target infrastructure.
    for part in re.split(r"[&;]", query):
        raw_key = part.split("=", 1)[0]
        key = _bounded_unquote_plus(raw_key)
        if _contains_control_characters(key):
            raise EgressViolation("invalid_url")
        normalized = re.sub(r"[-_.\s]", "", key).casefold()
        if (
            normalized in _NORMALIZED_SENSITIVE_QUERY_KEYS
            or normalized.endswith("token")
            or normalized.endswith("secret")
            or normalized.endswith("password")
            or normalized.endswith("credential")
            or normalized.endswith("assertion")
        ):
            raise EgressViolation("sensitive_query_parameter")


def _reject_decoded_control_characters(*components: str) -> None:
    for component in components:
        if _contains_control_characters(_bounded_unquote_plus(component)):
            raise EgressViolation("invalid_url")


def _bounded_unquote_plus(value: str) -> str:
    """Decode enough nested URL encoding to catch common parser mismatches.

    Targets should decode a query only once, but stacks sometimes decode a
    redirect parameter again. Three bounded passes catch normal single and
    double encoding without allowing attacker-controlled input to drive an
    unbounded transformation.
    """
    decoded = value
    for _ in range(3):
        next_value = unquote_plus(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def _contains_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _resolve_hostname(host: str) -> Sequence[str]:
    try:
        answers = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise EgressViolation("dns_resolution_failed") from exc
    addresses: set[str] = set()
    for answer in answers:
        address = answer[4][0]
        if isinstance(address, str):
            addresses.add(address)
    return tuple(sorted(addresses))


def _require_public_resolution(host: str, resolver: HostResolver) -> tuple[str, ...]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        _require_global_ip(literal)
        return (literal.compressed,)
    try:
        addresses = resolver(host)
    except EgressViolation:
        raise
    except Exception as exc:
        raise EgressViolation("dns_resolution_failed") from exc
    if not addresses:
        raise EgressViolation("dns_resolution_failed")
    normalized: list[str] = []
    for raw_address in addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise EgressViolation("dns_resolution_failed") from exc
        _require_global_ip(address)
        normalized.append(address.compressed)
    return tuple(sorted(set(normalized)))


def _require_global_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    # ``is_global`` rejects loopback, private, link-local, multicast,
    # unspecified, reserved, documentation, and carrier-grade NAT ranges.
    if not address.is_global:
        raise EgressViolation("non_public_address")


def _is_ip_literal(host: str, *, version: int) -> bool:
    try:
        return ipaddress.ip_address(host).version == version
    except ValueError:
        return False


def _parse_connect_authority(header: bytes) -> tuple[str, int]:
    """Parse one minimal HTTP CONNECT preface without retaining it.

    The listener is loopback-only and accepts no authentication, absolute
    HTTP URL, or arbitrary method.  The policy performs the definitive exact
    origin and DNS checks after this syntax boundary.
    """

    try:
        first_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="strict")
        method, authority, version = first_line.split(" ", 2)
    except (UnicodeDecodeError, ValueError) as exc:
        raise EgressViolation("invalid_proxy_request") from exc
    if method != "CONNECT" or version not in {"HTTP/1.0", "HTTP/1.1"}:
        raise EgressViolation("invalid_proxy_request")
    try:
        parsed = urlsplit(f"//{authority}")
        port = parsed.port
    except ValueError as exc:
        raise EgressViolation("invalid_proxy_request") from exc
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "@" in parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or port is None
        or not 1 <= port <= 65535
    ):
        raise EgressViolation("invalid_proxy_request")
    return _canonical_host(parsed.hostname), port


async def _open_validated_connection(
    validated: ValidatedUrl,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to a freshly policy-validated literal address.

    Try each current public DNS answer. A failed address does not trigger a
    second hostname lookup, which preserves the validation/connection binding.
    """

    last_error: OSError | None = None
    for address in validated.resolved_addresses:
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(address, validated.origin.port), timeout=15.0
            )
        except OSError as exc:
            last_error = exc
    raise EgressViolation("egress_connection_failed") from last_error


async def _copy_stream(
    source: asyncio.StreamReader,
    destination: asyncio.StreamWriter,
) -> None:
    while chunk := await source.read(64 * 1024):
        destination.write(chunk)
        await destination.drain()
