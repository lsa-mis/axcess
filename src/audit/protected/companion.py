"""Paired local companion for authorized, manually authenticated scans.

The companion is deliberately a narrow worker, not a general browser remote
control service. It connects to one Axcess server over mTLS, receives one
scan-bound work item, opens a headed browser on the auditor's computer, and waits
for the auditor to complete sign-in directly with the target. It never asks
for, reads, stores, or forwards a password, MFA factor, passkey, recovery
code, cookie, authorization header, or Playwright profile.

Only opaque page keys and a carefully whitelisted issue index travel back to
the LAN service. URLs, DOM text, selectors, OCR output, screenshots, and
browser state stay in memory in this process and are discarded when the
browser context closes.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hashlib
import hmac
import io
import ipaddress
import warnings
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar, cast
from urllib.parse import urljoin, urlsplit

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator
from selectolax.parser import HTMLParser

from audit.analyzer.alfa import AlfaAnalyzer, AlfaError, AlfaFinding, chromium_executable_path
from audit.analyzer.alfa import availability as alfa_availability
from audit.analyzer.axe import AxeAnalyzer, AxeViolation
from audit.analyzer.focus import FocusFinding, FocusProbe
from audit.analyzer.keyboard import KeyboardProbe, KeyboardTrap
from audit.analyzer.responsive import ResponsiveFinding, ResponsiveProbe
from audit.crawler import url_policy
from audit.crawler.fetcher import FetchError, FetchResult
from audit.crawler.js_fetcher import RenderedPageTooLargeError
from audit.crawler.render_detect import looks_like_authentication_page
from audit.extractor.html_images import extract_image_refs
from audit.extractor.svg_text import find_inline_svg_text
from audit.protected.egress import EgressViolation, ProtectedEgressPolicy
from audit.protected.local_ai import ProtectedLocalOllama
from audit.protected.models import (
    ProtectedIndexFinding,
    ProtectedIndexPipeline,
    ProtectedPageIndex,
    ProtectedScanRecord,
    ProtectedScanStatus,
    ProtectedWorkSpec,
)
from audit.protected.session import ManualAuthenticationError, ManualAuthenticationSession

_MAX_PAGES = 10_000
_MAX_DEPTH = 20
_MAX_PAGE_FINDINGS = 250
_MAX_IMAGES_PER_PAGE = 50
_MAX_LOCAL_AI_IMAGES_PER_PAGE = 5
# A protected image is read through a browser-page ReadableStream with this
# hard cap, rather than Playwright's APIResponse.body() (which buffers the
# whole response before Python can reject it). Keep the bound modest because
# base64 is an unavoidable one-use bridge from page JavaScript to Python.
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_RENDERED_HTML_CHARS = 2_000_000
_NAVIGATION_TIMEOUT_MS = 30_000
_OCR_TIMEOUT_S = 30.0
_MAX_OCR_IMAGE_DIMENSION = 8_192
_MAX_OCR_IMAGE_PIXELS = 24_000_000
_MAX_OCR_STDOUT_BYTES = 1_000_000
_MAX_OCR_STDERR_BYTES = 64 * 1024
_HEARTBEAT_INTERVAL_S = 20.0
_Awaited = TypeVar("_Awaited")


class CompanionError(RuntimeError):
    """A safe, user-facing companion failure without browser evidence."""


class CompanionServiceStateError(CompanionError):
    """The service rejected work because its protected lifecycle changed."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__("The protected-scan service state changed during this session.")


class AuthenticationRequiredError(CompanionError):
    """The browser session needs an auditor to sign in again."""


class UnsafeProtectedNavigationError(CompanionError):
    """A browser result attempted to leave the approved protected scope."""


@dataclass(frozen=True, slots=True)
class CompanionTlsConfig:
    """Local mTLS material for one companion connection.

    The private key remains in the auditor-controlled local certificate store
    or file supplied to the TLS client. Axcess receives only the certificate
    fingerprint asserted by its reverse proxy after a successful handshake.
    """

    certificate: Path
    private_key: Path
    ca_bundle: Path | None = None

    def __post_init__(self) -> None:
        if not self.certificate.is_file() or not self.private_key.is_file():
            raise CompanionError("The companion mTLS certificate and key must exist locally.")
        if self.ca_bundle is not None and not self.ca_bundle.is_file():
            raise CompanionError("The configured mTLS CA bundle does not exist locally.")

    @property
    def fingerprint(self) -> str:
        """SHA-256 public-certificate fingerprint, without exposing the key."""
        try:
            certificate = x509.load_pem_x509_certificate(self.certificate.read_bytes())
        except Exception as exc:
            raise CompanionError("The companion certificate is not valid PEM.") from exc
        return certificate.fingerprint(hashes.SHA256()).hex()

    @property
    def verify(self) -> str | bool:
        return str(self.ca_bundle) if self.ca_bundle is not None else True


class CompanionWork(BaseModel):
    """One non-persisted, scan-bound work item received over mTLS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scan_id: int = Field(gt=0)
    seed_url: str = Field(min_length=12, max_length=2048)
    approved_target_origins: tuple[str, ...] = Field(min_length=1, max_length=32, repr=False)
    approved_auth_origins: tuple[str, ...] = Field(default=(), max_length=32, repr=False)
    approved_cdn_origins: tuple[str, ...] = Field(default=(), max_length=64, repr=False)
    index_hmac_key: str = Field(min_length=64, max_length=64, repr=False)
    config: dict[str, Any]
    run_lease_id: str = Field(min_length=24, max_length=200, repr=False)
    protection: ProtectedScanRecord

    @model_validator(mode="after")
    def verify_scan_binding_and_no_session_fields(self) -> CompanionWork:
        if self.protection.scan_id != self.scan_id:
            raise ValueError("companion work scan binding is invalid")
        # Treat a malformed/compromised service response as unsafe before a
        # local browser ever sees it. Reuse the encrypted work-spec contract
        # so origin normalization, seed containment, and config/session-field
        # checks stay identical on both sides of the mTLS boundary.
        ProtectedWorkSpec(
            seed_url=self.seed_url,
            approved_target_origins=self.approved_target_origins,
            approved_auth_origins=self.approved_auth_origins,
            approved_cdn_origins=self.approved_cdn_origins,
            index_hmac_key=self.index_hmac_key,
            config=self.config,
        )
        forbidden = {"password", "cookie", "authorization", "storage_state", "credential"}
        if forbidden & {str(key).lower() for key in self.config}:
            raise ValueError("companion work cannot contain browser or credential state")
        return self


@dataclass(frozen=True, slots=True)
class CompanionCrawlStats:
    """Non-sensitive progress values suitable for a terminal summary."""

    pages_indexed: int = 0
    pages_failed: int = 0
    issue_leads_indexed: int = 0
    images_checked: int = 0
    image_text_leads: int = 0
    alfa_failed: int = 0
    alfa_cant_tell: int = 0


class ProtectedCompanionClient:
    """Small mTLS client for the companion-only API surface.

    This client deliberately does not use redirects, cookies, proxy
    environment variables, or a persisted token cache. It does not log
    request/response bodies because a pairing code is an enrollment secret.
    """

    def __init__(self, *, server: str, enrollment_id: str, tls: CompanionTlsConfig) -> None:
        self._server = _normalize_companion_server(server)
        self._enrollment_id = enrollment_id
        self._tls = tls
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ProtectedCompanionClient:
        self._client = httpx.AsyncClient(
            base_url=self._server,
            cert=(str(self._tls.certificate), str(self._tls.private_key)),
            verify=self._tls.verify,
            follow_redirects=False,
            timeout=httpx.Timeout(30.0, connect=15.0),
            trust_env=False,
            headers={"User-Agent": "axcess-companion/0.1"},
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None

    async def claim(self, pairing_code: str) -> dict[str, Any]:
        """Claim the one-time enrollment; code is held only for this request."""
        if len(pairing_code) < 16:
            raise CompanionError("The one-time pairing code is invalid.")
        response = await self._request(
            "POST",
            "/api/agents/enroll",
            json={
                "enrollment_id": self._enrollment_id,
                "pairing_code": pairing_code,
            },
        )
        return _json_object(response)

    async def get_work(self) -> CompanionWork:
        response = await self._request("GET", f"/api/agents/{self._enrollment_id}/work")
        try:
            return CompanionWork.model_validate(_json_object(response))
        except Exception as exc:
            raise CompanionError("The server returned invalid companion work.") from exc

    async def heartbeat(self, run_lease_id: str) -> None:
        await self._request(
            "POST",
            f"/api/agents/{self._enrollment_id}/heartbeat",
            json={"run_lease_id": run_lease_id},
        )

    async def event(
        self,
        event_type: str,
        *,
        status: ProtectedScanStatus | None = None,
        page_index: ProtectedPageIndex | None = None,
        details: dict[str, str | int | float | bool | None] | None = None,
        run_lease_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"event_type": event_type, "run_lease_id": run_lease_id}
        if status is not None:
            payload["status"] = status.value
        if page_index is not None:
            payload["page_index"] = page_index.model_dump(mode="json")
        if details:
            payload["details"] = details
        response = await self._request(
            "POST", f"/api/agents/{self._enrollment_id}/events", json=payload
        )
        return _json_object(response)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        client = self._client
        if client is None:
            raise CompanionError("The companion TLS client is not open.")
        try:
            response = await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise CompanionError(
                "The companion could not reach the protected-scan service."
            ) from exc
        if 200 <= response.status_code < 300:
            return response
        if response.status_code in {409, 410}:
            # A service restart, retention deadline, or terminal transition
            # is authoritative. Do not reinterpret it as a crawler failure
            # and overwrite the paused lifecycle with ``failed``.
            raise CompanionServiceStateError(response.status_code)
        # Never include the body: it might include an upstream reverse-proxy
        # diagnostic or request context. The bounded status is enough for the
        # auditor to retry pairing or contact the deployment owner.
        raise CompanionError(
            f"The protected-scan service rejected the request ({response.status_code})."
        )


class ProtectedCompanionRunner:
    """Run one locally authenticated protected scan from a paired companion."""

    def __init__(self, client: ProtectedCompanionClient) -> None:
        self._client = client

    async def run(
        self,
        *,
        wait_for_auditor: Callable[[], Awaitable[None]] | None = None,
    ) -> CompanionCrawlStats:
        """Complete the human handoff, crawl, and return safe progress totals."""
        work = await self._client.get_work()
        session = ManualAuthenticationSession(
            seed_url=work.seed_url,
            approved_target_origins=work.approved_target_origins,
            approved_auth_origins=work.approved_auth_origins,
            approved_cdn_origins=work.approved_cdn_origins,
            user_agent=_config_text(work.config, "user_agent", "axcess-companion/0.1"),
        )
        heartbeat_task = asyncio.create_task(self._heartbeat_until_cancelled(work.run_lease_id))
        authentication_notice_sent = False
        try:
            try:
                await self._await_with_lease(
                    self._client.event(
                        "companion.manual_authentication_started",
                        status=ProtectedScanStatus.AWAITING_AUTHENTICATION,
                        run_lease_id=work.run_lease_id,
                    ),
                    heartbeat_task,
                )
                await self._await_with_lease(session.start(), heartbeat_task)
                if wait_for_auditor is None:
                    await self._await_with_lease(_wait_for_terminal_confirmation(), heartbeat_task)
                else:
                    await self._await_with_lease(wait_for_auditor(), heartbeat_task)
                landed = session.verify_authenticated_target()
                # Keep the context (and its in-memory session) but close the
                # visible tab that handled sign-in before crawling fresh pages.
                # This terminates any pre-auth page activity once policy switches
                # to GET/HEAD-only protected crawling.
                await self._await_with_lease(session.discard_manual_auth_page(), heartbeat_task)
            except ManualAuthenticationError as exc:
                authentication_notice_sent = True
                await self._best_effort_terminal_event(
                    "companion.authentication_required",
                    status=ProtectedScanStatus.AUTHENTICATION_REQUIRED,
                    run_lease_id=work.run_lease_id,
                )
                raise AuthenticationRequiredError(
                    "Manual sign-in did not reach an approved protected application page."
                ) from exc

            await self._await_with_lease(
                self._client.event(
                    "companion.authenticated_crawl_started",
                    status=ProtectedScanStatus.RUNNING,
                    run_lease_id=work.run_lease_id,
                ),
                heartbeat_task,
            )
            crawler = _ProtectedBrowserCrawler(
                session=session, work=work, client=self._client, entry_url=landed.url
            )
            stats = await self._await_with_lease(crawler.crawl(), heartbeat_task)
            await self._await_with_lease(
                self._client.event(
                    "companion.completed",
                    status=ProtectedScanStatus.COMPLETED,
                    run_lease_id=work.run_lease_id,
                ),
                heartbeat_task,
            )
            return stats
        except AuthenticationRequiredError:
            if not authentication_notice_sent:
                authentication_notice_sent = True
                await self._best_effort_terminal_event(
                    "companion.authentication_required",
                    status=ProtectedScanStatus.AUTHENTICATION_REQUIRED,
                    run_lease_id=work.run_lease_id,
                )
            raise
        except CompanionServiceStateError as exc:
            # Most commonly the Axcess process restarted and deliberately
            # marked the report ``interrupted``. The old browser session must
            # close, but only the auditor can begin a fresh manual handoff.
            raise CompanionError(
                "The protected-scan service was interrupted or the retention window ended. "
                "The browser session was closed; begin a new manual handoff before retrying."
            ) from exc
        except asyncio.CancelledError:
            await self._best_effort_terminal_event(
                "companion.interrupted",
                status=ProtectedScanStatus.INTERRUPTED,
                run_lease_id=work.run_lease_id,
            )
            raise
        except CompanionError:
            await self._best_effort_terminal_event(
                "companion.failed",
                status=ProtectedScanStatus.FAILED,
                run_lease_id=work.run_lease_id,
            )
            raise
        except Exception as exc:
            await self._best_effort_terminal_event(
                "companion.failed",
                status=ProtectedScanStatus.FAILED,
                run_lease_id=work.run_lease_id,
            )
            raise CompanionError("The protected companion crawl failed.") from exc
        finally:
            # Close the authenticated browser before awaiting/cancelling any
            # background task. A rejected heartbeat must never skip profile
            # teardown or leave an authenticated GET-capable context alive.
            await session.close()
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, CompanionError, Exception):
                await heartbeat_task

    async def _heartbeat_until_cancelled(self, run_lease_id: str) -> None:
        """Keep the server's sole companion lease alive while this run exists."""

        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
            await self._client.heartbeat(run_lease_id)

    async def _await_with_lease(
        self,
        operation: Awaitable[_Awaited],
        heartbeat_task: asyncio.Task[None],
    ) -> _Awaited:
        """Stop the current handoff/crawl operation as soon as its lease dies.

        A companion cannot continue driving an authenticated browser after the
        server has been stopped, restarted, or explicitly revoked its run.
        Race each potentially long operation against the heartbeat and cancel
        it before the enclosing ``finally`` closes the browser context.
        """

        task: asyncio.Future[_Awaited] = asyncio.ensure_future(operation)
        try:
            # ``asyncio.wait`` requires homogeneous Future result types, but
            # this race intentionally combines the operation's generic value
            # with a ``None`` heartbeat. Keep the operation task itself typed
            # so callers receive their concrete result type below.
            done, _pending = await asyncio.wait(
                {
                    cast(asyncio.Future[Any], task),
                    cast(asyncio.Future[Any], heartbeat_task),
                },
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
                if heartbeat_task.cancelled():
                    raise CompanionServiceStateError(409)
                error = heartbeat_task.exception()
                if isinstance(error, CompanionError):
                    raise error
                if error is not None:
                    raise CompanionError(
                        "The protected-scan heartbeat stopped unexpectedly."
                    ) from error
                raise CompanionServiceStateError(409)
            return await task
        except BaseException:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            raise

    async def _best_effort_terminal_event(
        self,
        event_type: str,
        *,
        status: ProtectedScanStatus,
        run_lease_id: str,
    ) -> None:
        """Report a terminal state if the service still accepts this lease."""

        with contextlib.suppress(TimeoutError, CompanionError):
            await asyncio.wait_for(
                self._client.event(
                    event_type,
                    status=status,
                    run_lease_id=run_lease_id,
                ),
                timeout=5.0,
            )


class _ProtectedBrowserCrawler:
    """A serial, in-memory, browser-only crawl within an authenticated session."""

    def __init__(
        self,
        *,
        session: ManualAuthenticationSession,
        work: CompanionWork,
        client: ProtectedCompanionClient,
        entry_url: str | None = None,
    ) -> None:
        self._session = session
        self._work = work
        self._client = client
        self._target_policy = ProtectedEgressPolicy(work.approved_target_origins)
        self._scope = url_policy.build_scope(url_policy.normalize_seed_url(work.seed_url))
        # Where sign-in actually landed. Scope above stays anchored to the
        # work spec's seed, the auditor's approved area does not move
        # because an identity provider redirected somewhere deeper, but the
        # crawl starts from the signed-in page rather than re-fetching a seed
        # that is often the sign-in form itself. Out-of-scope landings fall
        # back to the seed, since every URL is scope-checked again below and
        # an out-of-scope entry would yield a zero-page scan.
        self._entry_url = work.seed_url
        if entry_url is not None:
            candidate = url_policy.normalize(entry_url)
            if url_policy.is_in_scope(candidate, self._scope, allow_subdomains=False):
                self._entry_url = candidate
        self._max_pages = min(_config_int(work.config, "max_pages", 100), _MAX_PAGES)
        self._max_depth = min(_config_int(work.config, "max_depth", 10), _MAX_DEPTH)
        self._seconds_between_pages = 1.0 / _config_float(work.config, "rps", 1.0)
        self._config = work.config
        # The work-spec model validates the exact hexadecimal shape before a
        # companion reaches this point. Keep the key only in this process and
        # use it to make page/finding aliases stable across a lost event
        # response or a manual re-authentication handoff.
        self._index_hmac_key = bytes.fromhex(work.index_hmac_key)

    async def crawl(self) -> CompanionCrawlStats:
        axe = (
            AxeAnalyzer.from_bundled(suppress_diagnostics=True)
            if _config_bool(self._config, "axe_enabled", True)
            else None
        )
        keyboard = (
            KeyboardProbe(suppress_diagnostics=True)
            if _config_bool(self._config, "keyboard_probe_enabled", True)
            else None
        )
        responsive = (
            ResponsiveProbe(suppress_diagnostics=True)
            if _config_bool(self._config, "responsive_checks_enabled", True)
            else None
        )
        focus = (
            FocusProbe(suppress_diagnostics=True)
            if _config_bool(self._config, "focus_checks_enabled", True)
            else None
        )
        fetcher = self._session.create_shared_js_fetcher(
            axe_analyzer=axe,
            axe_level=_config_level(self._config),
            keyboard_probe=keyboard,
            responsive_probe=responsive,
            focus_probe=focus,
            capture_screenshots=False,
            max_rendered_html_chars=_MAX_RENDERED_HTML_CHARS,
        )
        alfa = (
            await self._build_alfa() if _config_bool(self._config, "alfa_enabled", False) else None
        )
        local_ai = await self._open_local_ai()
        queue: deque[tuple[str, int]] = deque([(self._entry_url, 0)])
        seen: set[str] = {self._entry_url}
        stats = CompanionCrawlStats()

        try:
            async with fetcher:
                while queue and stats.pages_indexed < self._max_pages:
                    url, depth = queue.popleft()
                    await asyncio.sleep(self._seconds_between_pages)
                    try:
                        result = await fetcher.fetch(url)
                        self._validate_page_result(requested_url=url, result=result)
                    except RenderedPageTooLargeError:
                        # Do not turn an oversized document into Python-side
                        # report evidence or misreport it as expired MFA.
                        # The bounded audit event documents a coverage gap
                        # without retaining a URL or response detail.
                        await self._client.event(
                            "companion.page_skipped",
                            details={"reason": "rendered_content_too_large"},
                            run_lease_id=self._work.run_lease_id,
                        )
                        stats = _replace_stats(stats, pages_failed=stats.pages_failed + 1)
                        continue
                    except FetchError as exc:
                        # In a protected context a failed navigation is treated as
                        # potentially expired authentication. Do not log the
                        # browser's raw error text or retry automatically.
                        raise AuthenticationRequiredError(
                            "The protected browser session needs re-authentication."
                        ) from exc
                    except UnsafeProtectedNavigationError:
                        raise

                    if result.status_code in {401, 403} or looks_like_authentication_page(
                        result.url, result.body
                    ):
                        # A same-origin login screen may return 200, so the
                        # status alone cannot distinguish an expired session
                        # from an authenticated page.  Do this in memory and
                        # before any page/finding index is sent to Axcess.
                        raise AuthenticationRequiredError(
                            "The protected browser session needs re-authentication."
                        )
                    if not result.is_html or not result.is_ok:
                        stats = _replace_stats(stats, pages_failed=stats.pages_failed + 1)
                        continue

                    findings = _index_findings_from_result(
                        result, index_hmac_key=self._index_hmac_key
                    )
                    alfa_failed = 0
                    alfa_cant_tell = 0
                    alfa_evaluated = False
                    if alfa is not None:
                        try:
                            alfa_result = await self._session.run_alfa(
                                alfa, result.url, level=_config_level(self._config)
                            )
                            if alfa_result.authentication_required:
                                # Alfa has an independent browser context.
                                # Treat a same-origin sign-in/reverification
                                # surface there exactly like the primary
                                # browser: no page index is sent and a human
                                # must complete a fresh manual handoff.
                                raise AuthenticationRequiredError(
                                    "The protected browser session needs re-authentication."
                                )
                            alfa_evaluated = True
                            alfa_failed = alfa_result.failed_total
                            alfa_cant_tell = alfa_result.cant_tell_total
                            findings.extend(
                                _index_findings_from_alfa(
                                    alfa_result.findings,
                                    page_url=result.url,
                                    index_hmac_key=self._index_hmac_key,
                                )
                            )
                        except (AlfaError, ManualAuthenticationError):
                            # Engine failure is a coverage limitation, not a clean
                            # page and not a reason to leak runner diagnostics.
                            await self._client.event(
                                "companion.alfa_unavailable",
                                details={"page": "omitted"},
                                run_lease_id=self._work.run_lease_id,
                            )

                    image_findings, images_checked = await self._image_text_leads(
                        result.body,
                        result.url,
                        local_ai=local_ai,
                        index_hmac_key=self._index_hmac_key,
                    )
                    findings.extend(image_findings)
                    kept = tuple(findings[:_MAX_PAGE_FINDINGS])
                    page_index = ProtectedPageIndex(
                        page_key=_opaque_index_hmac(self._index_hmac_key, "page", result.url),
                        status_code=result.status_code,
                        axe_evaluated=axe is not None,
                        axe_violations_total=len(result.axe_violations),
                        alfa_evaluated=alfa_evaluated,
                        alfa_failed_total=alfa_failed,
                        alfa_cant_tell_total=alfa_cant_tell,
                        findings=kept,
                    )
                    await self._client.event(
                        "companion.page_indexed",
                        page_index=page_index,
                        run_lease_id=self._work.run_lease_id,
                    )
                    stats = _replace_stats(
                        stats,
                        pages_indexed=stats.pages_indexed + 1,
                        issue_leads_indexed=stats.issue_leads_indexed + len(kept),
                        images_checked=stats.images_checked + images_checked,
                        image_text_leads=stats.image_text_leads
                        + sum(
                            1
                            for finding in image_findings
                            if finding.pipeline is ProtectedIndexPipeline.PROTECTED_IMAGE
                        ),
                        alfa_failed=stats.alfa_failed + alfa_failed,
                        alfa_cant_tell=stats.alfa_cant_tell + alfa_cant_tell,
                    )

                    if depth < self._max_depth:
                        for child in self._child_urls(result.body, result.url):
                            if child not in seen:
                                seen.add(child)
                                queue.append((child, depth + 1))
        finally:
            if local_ai is not None:
                await local_ai.__aexit__(None, None, None)
        return stats

    def _validate_page_result(self, *, requested_url: str, result: FetchResult) -> None:
        try:
            self._target_policy.validate_page_url(requested_url)
            self._target_policy.validate_page_url(result.url)
        except EgressViolation as exc:
            raise UnsafeProtectedNavigationError(
                "The protected browser attempted to leave the approved target scope."
            ) from exc

    async def _build_alfa(self) -> AlfaAnalyzer:
        availability = alfa_availability()
        if not availability.available:
            raise CompanionError(
                "The selected local Alfa engine is not available on this companion."
            )
        return AlfaAnalyzer(
            user_agent=_config_text(self._config, "user_agent", "axcess-companion/0.1"),
            timeout_s=float(_config_float(self._config, "alfa_timeout_s", 75.0)),
            concurrency=1,
            chromium_path=await chromium_executable_path(),
        )

    async def _open_local_ai(self) -> ProtectedLocalOllama | None:
        """Open an explicitly allowed, companion-verified local AI client.

        The server also validates its configured endpoint when it creates the
        draft, but that check says nothing about the auditor's computer.  Recheck
        DNS here immediately before opening the client; an unavailable or
        non-loopback endpoint simply removes optional AI assistance rather
        than causing data egress or blocking deterministic checks.
        """
        if not self._work.protection.allow_local_ai or not _config_bool(
            self._config, "vlm_enabled", False
        ):
            return None
        base_url = _config_text(self._config, "vlm_base_url", "")
        if not is_loopback_ollama_url(base_url):
            await self._client.event(
                "companion.local_ai_disabled",
                details={"reason": "loopback_required"},
                run_lease_id=self._work.run_lease_id,
            )
            return None
        client = ProtectedLocalOllama(
            base_url=base_url,
            model=_config_text(self._config, "vlm_model", "qwen3-vl:2b-instruct"),
            timeout_s=_config_float(self._config, "protected_local_ai_timeout_s", 60.0),
        )
        await client.__aenter__()
        return client

    def _child_urls(self, body: bytes, base_url: str) -> Iterable[str]:
        try:
            tree = HTMLParser(body)
        except Exception:
            return ()
        children: list[str] = []
        for anchor in tree.css("a[href]"):
            href = anchor.attributes.get("href")
            if not href:
                continue
            try:
                candidate = self._target_policy.validate_page_url(urljoin(base_url, href)).url
            except (EgressViolation, ValueError):
                continue
            if url_policy.is_in_scope(candidate, self._scope, allow_subdomains=False):
                children.append(candidate)
        return tuple(children)

    async def _image_text_leads(
        self,
        body: bytes,
        base_url: str,
        *,
        local_ai: ProtectedLocalOllama | None,
        index_hmac_key: bytes,
    ) -> tuple[list[ProtectedIndexFinding], int]:
        findings: list[ProtectedIndexFinding] = []
        checked = 0
        try:
            refs = extract_image_refs(body, base_url)
            inline_svg = find_inline_svg_text(body)
        except Exception:
            return findings, checked
        for hit in inline_svg[:_MAX_IMAGES_PER_PAGE]:
            findings.append(
                _image_index_finding(
                    "inline-svg-text",
                    page_url=base_url,
                    source_identity=(
                        f"inline-svg:{hit.position}:{hit.visible_text}:{hit.alt_context or ''}"
                    ),
                    index_hmac_key=index_hmac_key,
                )
            )
        remaining = max(0, _MAX_IMAGES_PER_PAGE - len(inline_svg))
        for ref in refs[:remaining]:
            try:
                image = await self._fetch_image_in_memory(ref.url, page_url=base_url)
            except CompanionError:
                continue
            checked += 1
            try:
                ocr_lead = await _image_has_text(
                    image, language=_config_text(self._config, "ocr_language", "eng")
                )
                assessment = (
                    await local_ai.assess_image(image)
                    if local_ai is not None and checked <= _MAX_LOCAL_AI_IMAGES_PER_PAGE
                    else None
                )
                # Local AI is an additional lead, never a reason to discard
                # deterministic OCR output.  We retain only its bounded
                # severity suggestion—not labels, rationale, OCR, or image
                # bytes—in the non-sensitive index.
                if ocr_lead or (assessment is not None and assessment.contains_meaningful_text):
                    findings.append(
                        _image_index_finding(
                            "image-of-text",
                            impact=assessment.impact if assessment is not None else "moderate",
                            page_url=base_url,
                            source_identity=f"image:{ref.position}:{ref.url}",
                            index_hmac_key=index_hmac_key,
                        )
                    )
            finally:
                # Drop image bytes before the next network request. Python
                # cannot guarantee physical zeroization, but this avoids any
                # deliberate retention or blob/temp-file path.
                image.clear()
        return findings, checked

    async def _fetch_image_in_memory(self, url: str, *, page_url: str) -> bytearray:
        """Read one same-origin protected image through a bounded JS stream.

        ``APIResponse.body()`` buffers an entire response before Axcess can
        apply a byte limit, so it is unsafe for a controlled account facing a
        malicious or broken image server. Use a fresh page on the approved
        target origin and a ``ReadableStream`` reader instead. The browser
        cancels the reader as soon as the cap is exceeded; redirects are
        refused rather than followed. CDN images are deliberately skipped in
        this first protected release because a target-origin page cannot read
        a cross-origin response safely without relaxing CORS or copying
        authenticated state into another HTTP client.
        """
        try:
            current = self._target_policy.validate_url(url).url
            source_page = self._target_policy.validate_page_url(page_url).url
        except EgressViolation as exc:
            raise CompanionError(
                "Protected image URL is outside the approved target scope."
            ) from exc
        page: Any = None
        try:
            page = await self._session.context.new_page()
            await page.goto(
                source_page,
                timeout=_NAVIGATION_TIMEOUT_MS,
                wait_until="domcontentloaded",
            )
            response = await page.evaluate(
                """async ({ url, maxBytes }) => {
                    try {
                      const response = await fetch(url, {
                        method: "GET",
                        credentials: "include",
                        cache: "no-store",
                        redirect: "error",
                      });
                      const declared = Number(response.headers.get("content-length") || 0);
                      const contentType = response.headers.get("content-type") || "";
                      if (declared > maxBytes) return { kind: "too_large" };
                      if (!response.ok || !response.body) {
                        return { kind: "not_ok", status: response.status, contentType };
                      }
                      const reader = response.body.getReader();
                      const chunks = [];
                      let total = 0;
                      while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        total += value.byteLength;
                        if (total > maxBytes) {
                          await reader.cancel();
                          return { kind: "too_large" };
                        }
                        chunks.push(value);
                      }
                      const bytes = new Uint8Array(total);
                      let offset = 0;
                      for (const chunk of chunks) {
                        bytes.set(chunk, offset);
                        offset += chunk.byteLength;
                      }
                      let binary = "";
                      const block = 0x8000;
                      for (let start = 0; start < bytes.length; start += block) {
                        binary += String.fromCharCode(...bytes.subarray(start, start + block));
                      }
                      return {
                        kind: "ok",
                        status: response.status,
                        contentType,
                        bodyBase64: btoa(binary),
                      };
                    } catch (_) {
                      return { kind: "blocked" };
                    }
                }""",
                {"url": current, "maxBytes": _MAX_IMAGE_BYTES},
            )
            if not isinstance(response, dict) or response.get("kind") != "ok":
                raise CompanionError("A protected image could not be retrieved safely.")
            if int(response.get("status") or 0) != 200:
                raise CompanionError("A protected image request was not successful.")
            content_type = str(response.get("contentType") or "").lower()
            if not (content_type.startswith("image/") or "svg" in content_type):
                raise CompanionError("A protected image response was not an image.")
            encoded = response.get("bodyBase64")
            if not isinstance(encoded, str) or len(encoded) > (_MAX_IMAGE_BYTES * 4 // 3) + 8:
                raise CompanionError("A protected image exceeded the in-memory size limit.")
            try:
                data = bytearray(base64.b64decode(encoded.encode("ascii"), validate=True))
            except (UnicodeEncodeError, binascii.Error) as exc:
                raise CompanionError("A protected image could not be read safely.") from exc
            if not data or len(data) > _MAX_IMAGE_BYTES:
                data.clear()
                raise CompanionError("A protected image exceeded the in-memory size limit.")
            return data
        except Exception as exc:
            if isinstance(exc, CompanionError):
                raise
            raise CompanionError("A protected image could not be retrieved safely.") from exc
        finally:
            if page is not None:
                with contextlib.suppress(Exception):
                    await page.close(run_before_unload=False)


def _index_findings_from_result(
    result: FetchResult, *, index_hmac_key: bytes
) -> list[ProtectedIndexFinding]:
    findings: list[ProtectedIndexFinding] = []
    findings.extend(
        _index_findings_from_axe(
            result.axe_violations, page_url=result.url, index_hmac_key=index_hmac_key
        )
    )
    findings.extend(
        _index_findings_from_probe(
            "keyboard",
            result.keyboard_traps,
            page_url=result.url,
            index_hmac_key=index_hmac_key,
        )
    )
    findings.extend(
        _index_findings_from_probe(
            "responsive",
            result.responsive_findings,
            page_url=result.url,
            index_hmac_key=index_hmac_key,
        )
    )
    findings.extend(
        _index_findings_from_probe(
            "focus",
            result.focus_findings,
            page_url=result.url,
            index_hmac_key=index_hmac_key,
        )
    )
    return findings


def _index_findings_from_axe(
    findings: Iterable[AxeViolation], *, page_url: str, index_hmac_key: bytes
) -> list[ProtectedIndexFinding]:
    return [
        ProtectedIndexFinding(
            pipeline=ProtectedIndexPipeline.AXE,
            rule_id=finding.rule_id,
            occurrence_key=_opaque_index_hmac(
                index_hmac_key,
                "occurrence",
                "axe",
                page_url,
                finding.rule_id,
                finding.target_hash,
            ),
            wcag_sc=finding.wcag_sc,
            wcag_scs=tuple(part for part in (finding.wcag_scs or "").split(",") if part),
            wcag_level=finding.wcag_level,
            impact=finding.impact,
        )
        for finding in findings
    ]


def _index_findings_from_probe(
    pipeline: Literal["keyboard", "responsive", "focus"],
    findings: Iterable[KeyboardTrap | ResponsiveFinding | FocusFinding],
    *,
    page_url: str,
    index_hmac_key: bytes,
) -> list[ProtectedIndexFinding]:
    source = ProtectedIndexPipeline(pipeline)
    out: list[ProtectedIndexFinding] = []
    for finding in findings:
        out.append(
            ProtectedIndexFinding(
                pipeline=source,
                rule_id=finding.rule_id,
                occurrence_key=_opaque_index_hmac(
                    index_hmac_key,
                    "occurrence",
                    pipeline,
                    page_url,
                    finding.rule_id,
                    finding.target_hash,
                ),
                wcag_sc=finding.criterion_sc,
                wcag_scs=(finding.criterion_sc,),
                wcag_level=finding.wcag_level,
                impact=finding.impact,
            )
        )
    return out


def _index_findings_from_alfa(
    findings: Iterable[AlfaFinding], *, page_url: str, index_hmac_key: bytes
) -> list[ProtectedIndexFinding]:
    return [
        ProtectedIndexFinding(
            pipeline=ProtectedIndexPipeline.ALFA,
            rule_id=finding.rule_id,
            occurrence_key=_opaque_index_hmac(
                index_hmac_key,
                "occurrence",
                "alfa",
                page_url,
                finding.rule_id,
                finding.outcome,
                finding.target_hash,
            ),
            wcag_sc=finding.wcag_sc,
            wcag_scs=tuple(part for part in (finding.wcag_scs or "").split(",") if part),
            wcag_level=finding.wcag_level,
            impact=None,
            engine_outcome=finding.outcome,
        )
        for finding in findings
    ]


def _image_index_finding(
    rule_id: str,
    *,
    page_url: str,
    source_identity: str,
    index_hmac_key: bytes,
    impact: Literal["critical", "serious", "moderate", "minor"] = "moderate",
) -> ProtectedIndexFinding:
    return ProtectedIndexFinding(
        pipeline=ProtectedIndexPipeline.PROTECTED_IMAGE,
        rule_id=rule_id,
        occurrence_key=_opaque_index_hmac(
            index_hmac_key,
            "occurrence",
            "protected_image",
            page_url,
            rule_id,
            source_identity,
        ),
        wcag_sc="1.4.5",
        wcag_scs=("1.4.5",),
        wcag_level="AA",
        impact=impact,
    )


def _opaque_index_hmac(index_hmac_key: bytes, *parts: str) -> str:
    """Return a stable opaque page/finding key without retaining input text.

    URL, selector, OCR-adjacent, and rule data stay only in the companion's
    transient process memory. A random key encrypted inside the scan's work
    specification makes the digest unlinkable across reports while allowing a
    resumed companion to idempotently address the same page/occurrence.
    Length-prefix every component so attacker-controlled delimiter text cannot
    create an ambiguous HMAC input.
    """

    mac = hmac.new(index_hmac_key, digestmod=hashlib.sha256)
    mac.update(b"axcess-protected-index:v1\x00")
    for part in parts:
        encoded = part.encode("utf-8", errors="replace")
        mac.update(len(encoded).to_bytes(8, "big"))
        mac.update(encoded)
    return mac.hexdigest()


async def _image_has_text(data: bytearray, *, language: str) -> bool:
    """Run Tesseract through stdin/stdout only and discard its text result.

    ``pytesseract`` can create temporary image files, which is unacceptable
    for protected image bytes. The command-line engine accepts ``stdin`` and
    emits TSV on stdout, so the bytes and OCR words remain in local process
    pipes. Compressed byte size is not a decoded-pixel bound, so reject
    unreasonably large dimensions before spawning Tesseract and cap both
    stdout/stderr pipes. Only the boolean decision leaves this function.
    """
    if not _is_ocr_safe_image(data):
        return False
    process: asyncio.subprocess.Process | None = None
    readers: tuple[asyncio.Task[bytes], ...] = ()
    try:
        process = await asyncio.create_subprocess_exec(
            "tesseract",
            "stdin",
            "stdout",
            "-l",
            language,
            "tsv",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if process.stdin is None or process.stdout is None or process.stderr is None:
            return False
        stdout_reader = asyncio.create_task(
            _read_ocr_pipe(process.stdout, limit=_MAX_OCR_STDOUT_BYTES)
        )
        stderr_reader = asyncio.create_task(
            _read_ocr_pipe(process.stderr, limit=_MAX_OCR_STDERR_BYTES)
        )
        readers = (stdout_reader, stderr_reader)
        process.stdin.write(bytes(data))
        await process.stdin.drain()
        process.stdin.close()
        stdout, _stderr = await asyncio.wait_for(
            asyncio.gather(stdout_reader, stderr_reader), _OCR_TIMEOUT_S
        )
        await process.wait()
    except (OSError, TimeoutError, _OcrPipeLimitError):
        await _stop_ocr_process(process, readers)
        return False
    except Exception:
        await _stop_ocr_process(process, readers)
        return False
    if process.returncode != 0:
        return False
    word_count = 0
    confidence_total = 0.0
    for line in stdout.decode("utf-8", errors="replace").splitlines()[1:]:
        columns = line.split("\t", 11)
        if len(columns) != 12 or not columns[11].strip():
            continue
        try:
            confidence = float(columns[10])
        except ValueError:
            continue
        if confidence < 0:
            continue
        word_count += 1
        confidence_total += confidence
    return word_count >= 3 and confidence_total / max(word_count, 1) >= 60.0


class _OcrPipeLimitError(RuntimeError):
    """A local OCR process exceeded its explicitly bounded output budget."""


def _is_ocr_safe_image(data: bytearray) -> bool:
    """Validate raster dimensions without decoding or writing protected pixels."""

    if not data or len(data) > _MAX_IMAGE_BYTES:
        return False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if (
                    width <= 0
                    or height <= 0
                    or width > _MAX_OCR_IMAGE_DIMENSION
                    or height > _MAX_OCR_IMAGE_DIMENSION
                    or width * height > _MAX_OCR_IMAGE_PIXELS
                ):
                    return False
                image.verify()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
        UnidentifiedImageError,
    ):
        return False
    return True


async def _read_ocr_pipe(reader: asyncio.StreamReader, *, limit: int) -> bytes:
    """Read one local OCR pipe without retaining an unbounded TSV/diagnostic."""

    content = bytearray()
    while True:
        chunk = await reader.read(16 * 1024)
        if not chunk:
            return bytes(content)
        content.extend(chunk)
        if len(content) > limit:
            content.clear()
            raise _OcrPipeLimitError


async def _stop_ocr_process(
    process: asyncio.subprocess.Process | None,
    readers: tuple[asyncio.Task[bytes], ...],
) -> None:
    """Kill an OCR child and discard its output without a second full read."""

    if process is not None and process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        with contextlib.suppress(Exception):
            await process.wait()
    for reader in readers:
        if not reader.done():
            reader.cancel()
    if readers:
        with contextlib.suppress(Exception):
            await asyncio.gather(*readers, return_exceptions=True)


def _normalize_companion_server(value: str) -> str:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise CompanionError("The companion service URL is invalid.") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise CompanionError("The companion service URL must be an exact HTTPS origin.")
    return f"https://{parsed.netloc}".rstrip("/")


def is_loopback_ollama_url(value: str) -> bool:
    """Require a literal loopback endpoint for companion-local AI.

    Accepting ``localhost`` after resolving it is not sufficient here: httpx
    would resolve the hostname again when connecting, which leaves a small
    DNS-rebinding window. A literal loopback address makes the location check
    and the actual connection target identical.
    """
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return False
    _ = port
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def _wait_for_terminal_confirmation() -> None:
    await asyncio.to_thread(
        input,
        "Complete the site's sign-in and any MFA in the headed browser. "
        "When you have returned to the approved application, press Enter here: ",
    )


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise CompanionError("The protected-scan service returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise CompanionError("The protected-scan service returned an invalid response.")
    return payload


def _config_bool(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    return value if isinstance(value, bool) else default


def _config_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    return (
        value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default
    )


def _config_float(config: dict[str, Any], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0:
        return float(value)
    return default


def _config_text(config: dict[str, Any], key: str, default: str) -> str:
    value = config.get(key, default)
    return value if isinstance(value, str) and value else default


def _config_level(config: dict[str, Any]) -> Literal["A", "AA", "AAA"]:
    value = _config_text(config, "axe_level", "AA")
    if value == "A":
        return "A"
    if value == "AAA":
        return "AAA"
    return "AA"


def _replace_stats(stats: CompanionCrawlStats, **updates: int) -> CompanionCrawlStats:
    values = {
        "pages_indexed": stats.pages_indexed,
        "pages_failed": stats.pages_failed,
        "issue_leads_indexed": stats.issue_leads_indexed,
        "images_checked": stats.images_checked,
        "image_text_leads": stats.image_text_leads,
        "alfa_failed": stats.alfa_failed,
        "alfa_cant_tell": stats.alfa_cant_tell,
    }
    values.update(updates)
    return CompanionCrawlStats(**values)
