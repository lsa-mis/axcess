"""Review UI backend — FastAPI JSON API + the React SPA shell.

All UI is served by the React bundle under ``/app/``; every data route
lives under ``/api/*``. The legacy Jinja/HTMX server-rendered pages have
been removed — this module is now the JSON surface, the SPA shell, blob
serving, exports, and the optional shared-token gate.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import math
import re
import secrets
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from audit import __version__, coverage_matrix, evaluation
from audit.analyzer.alfa import AlfaAnalyzer, AlfaResult, chromium_executable_path
from audit.analyzer.alfa import availability as alfa_availability
from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.focus import FocusProbe
from audit.analyzer.keyboard import KeyboardProbe
from audit.analyzer.model_registry import get_pick
from audit.analyzer.responsive import ResponsiveProbe
from audit.analyzer.semantic.registry import supported_criteria
from audit.blob_store import BlobStore
from audit.config import Settings, get_settings
from audit.crawler import url_policy
from audit.crawler.orchestrator import CrawlConfig, CrawlSummary, run_crawl
from audit.db import repo
from audit.db.schema import connect
from audit.exports.audit_report import render_audit_report
from audit.exports.collector import collect_scan
from audit.exports.csv_export import render_csv
from audit.exports.jira_export import render_jira_csv
from audit.exports.json_export import render_json
from audit.exports.markdown_report import render_markdown
from audit.exports.xlsx_export import render_xlsx
from audit.logging import get_logger
from audit.protected.crypto import DeterministicLocalKms, ProtectedVault
from audit.protected.models import ProtectedScanStatus, normalize_exact_https_origin
from audit.protected.repository import (
    ProtectedDataError,
    destroy_protected_scan_key,
    get_protected_scan,
    purge_expired_protected_data,
    recover_stale_protected_run_leases,
)
from audit.protected.session import ManualAuthenticationError, ManualAuthenticationSession
from audit.protected.vaults import resolve_configured_protected_vault
from audit.synthesizer.diff import compute_diff
from audit.web.coverage_status import ROADMAP, SHIPPED, roadmap_counts
from audit.web.export_readiness import (
    IncompleteEvaluationExportError,
    assess_public_export_readiness,
    label_draft_export,
    public_export_filename,
)
from audit.web.protected_api import build_protected_router
from audit.web.protected_auth import (
    require_protected_identity,
    require_protected_report_owner,
    require_same_origin,
)

log = get_logger(__name__)

_STATUS_OPTIONS = (
    "new",
    "reviewing",
    "in_progress",
    "remediated",
    "accepted_risk",
    "false_positive",
)
_CLASSIFICATION_OPTIONS = (
    "essential",
    "informational",
    "logo",
    "decorative",
    "no_meaningful_text",
)
_SEVERITY_OPTIONS = ("critical", "major", "minor", "info")
_DESTRUCTIVE_TRANSITIONS = {"accepted_risk", "false_positive", "remediated"}
_PAGE_SIZE = 50
_CONTENT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class LocalLoginScanRequest(BaseModel):
    """Local-only manual-login scan input, never credentials or browser state."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    seed_url: str = Field(min_length=12, max_length=2048)
    approved_auth_origins: tuple[str, ...] = Field(default=(), max_length=32)
    authorization_acknowledged: bool
    max_pages: int = Field(default=2500, ge=1, le=2500)
    max_depth: int = Field(default=10, ge=1, le=20)
    rps: float = Field(default=1.0, ge=0.1, le=5.0)
    workers: int = Field(default=2, ge=1, le=4)
    whole_host: bool = False
    scan_engine: Literal["axe", "alfa", "both"] = "axe"
    axe_level: Literal["A", "AA", "AAA"] = "AA"
    skip_keyboard: bool = False
    skip_responsive: bool = False
    skip_ocr: bool = True
    skip_vlm: bool = True
    image_analysis_acknowledged: bool = False

    @field_validator("approved_auth_origins")
    @classmethod
    def normalize_auth_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_exact_https_origin(value) for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("sign-in origins contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_local_login_scope(self) -> LocalLoginScanRequest:
        if not self.authorization_acknowledged:
            raise ValueError("authorization acknowledgement is required")
        try:
            parsed = urlsplit(self.seed_url)
            _ = normalize_exact_https_origin(f"{parsed.scheme}://{parsed.netloc}")
        except ValueError as exc:
            raise ValueError("seed URL must use an exact public HTTPS host") from exc
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("seed URL must be HTTPS with no credentials, query, or fragment")
        if not self.skip_vlm and self.skip_ocr:
            raise ValueError("VLM classification requires OCR image analysis")
        if (not self.skip_ocr or not self.skip_vlm) and not self.image_analysis_acknowledged:
            raise ValueError("local protected-image storage acknowledgement is required")
        return self

    @property
    def target_origin(self) -> str:
        parsed = urlsplit(self.seed_url)
        return normalize_exact_https_origin(f"{parsed.scheme}://{parsed.netloc}")


@dataclass
class _LocalLoginRun:
    """One browser session owned by this loopback Axcess process."""

    scan_id: int
    session: ManualAuthenticationSession
    confirmation: asyncio.Event
    status: str = "opening_browser"
    error: str | None = None
    browser_backgrounded: bool = False
    task: asyncio.Task[Any] | None = None


class _ProtectedRequestBodyTooLargeError(Exception):
    """Stop parsing a protected request once its streaming body cap is exceeded."""


class _ProtectedRequestBodyLimitMiddleware:
    """Bound protected HTTP bodies before FastAPI/Pydantic buffers them.

    The protected browser and companion endpoints authenticate inside their
    route handlers. FastAPI normally reads a typed body *before* calling that
    handler, so a handler-level length check cannot prevent an unauthenticated
    chunked request from consuming process memory. This outer ASGI middleware
    rejects known oversized ``Content-Length`` values and counts every body
    chunk before it reaches the framework parser.
    """

    def __init__(self, app: ASGIApp, *, db_path: Path, max_body_bytes: int) -> None:
        self.app = app
        self.db_path = db_path
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _is_protected_request_path(scope["path"], self.db_path):
            await self.app(scope, receive, send)
            return

        declared_length = _request_content_length(scope)
        if declared_length is not None:
            if declared_length < 0:
                await _send_protected_request_error(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    detail="Invalid protected request length.",
                )
                return
            if declared_length > self.max_body_bytes:
                await _send_protected_request_error(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    detail="Protected request body is too large.",
                )
                return

        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise _ProtectedRequestBodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _ProtectedRequestBodyTooLargeError:
            # This occurs while FastAPI is trying to parse a request body, so
            # no endpoint response has started yet. Return a fixed error which
            # cannot echo a target URL, pairing code, or JSON fragment.
            await _send_protected_request_error(
                scope,
                receive,
                send,
                status_code=413,
                detail="Protected request body is too large.",
            )


def _request_content_length(scope: Scope) -> int | None:
    """Parse one unambiguous ASGI Content-Length value, if supplied.

    A duplicate or malformed value is invalid rather than an excuse to defer
    all bounds to a potentially unbounded body stream.
    """

    values = [
        value for name, value in scope.get("headers", []) if name.lower() == b"content-length"
    ]
    if not values:
        return None
    try:
        decoded = [value.decode("ascii") for value in values]
        if len(set(decoded)) != 1:
            return -1
        length = int(decoded[0])
    except (UnicodeDecodeError, ValueError):
        return -1
    return length if length >= 0 else -1


async def _send_protected_request_error(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    status_code: int,
    detail: str,
) -> None:
    """Emit a fixed, non-cacheable error without consuming an oversized body."""

    response = JSONResponse(
        {"detail": detail},
        status_code=status_code,
        headers={
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )
    await response(scope, receive, send)


class EvaluationUpdate(BaseModel):
    """Editable expert-review metadata; crawler evidence remains immutable."""

    model_config = ConfigDict(extra="forbid")

    target_standard: str | None = Field(default=None, max_length=64)
    target_level: Literal["A", "AA", "AAA"] | None = None
    purpose: str | None = Field(default=None, max_length=4000)
    scope_included: str | None = Field(default=None, max_length=12000)
    scope_excluded: str | None = Field(default=None, max_length=12000)
    sample_description: str | None = Field(default=None, max_length=12000)
    reviewer: str | None = Field(default=None, max_length=256)
    methods_note: str | None = Field(default=None, max_length=12000)
    limitations: str | None = Field(default=None, max_length=12000)
    status: Literal["draft", "in_progress", "completed"] | None = None


class ManualCheckUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["not_started", "pass", "fail", "not_tested", "needs_follow_up"]
    rationale: str = Field(default="", max_length=12000)


class ManualEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=12000)
    page_id: int | None = Field(default=None, ge=1)
    evidence_url: str = Field(default="", max_length=4096)


_EXPORT_RENDERERS: dict[str, Any] = {
    "csv": render_csv,
    "json": render_json,
    "jira": render_jira_csv,
    "markdown": render_markdown,
    # `audit` and `xlsx` are rendered via a special-case branch in the route
    # handler because they need the live `conn` (not just the collector
    # result) to build their issue tables. The entries here exist only so
    # the format-validation check (`fmt in _EXPORT_RENDERERS`) accepts them;
    # the values are unused for those formats.
    "audit": render_audit_report,
    "xlsx": render_xlsx,
}
_EXPORT_MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "jira": "text/csv; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
    "audit": "text/markdown; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_EXPORT_EXTENSIONS = {
    "csv": "csv",
    "json": "json",
    "jira": "jira.csv",
    "markdown": "md",
    "audit": "audit.md",
    "xlsx": "xlsx",
}

_BASE_DIR = Path(__file__).resolve().parent
_FRONTEND_DIST = _BASE_DIR / "frontend" / "dist"
# Favicon lives under frontend/public/ as the source of truth (Vite copies it
# verbatim into dist/ on build). We resolve at request time rather than import
# time so a fresh build is picked up without restarting the server, and so
# tests that haven't run `npm run build` still get a 200 from the public copy.
_FAVICON_PUBLIC = _BASE_DIR / "frontend" / "public" / "favicon.svg"
_FAVICON_DIST = _FRONTEND_DIST / "favicon.svg"


def _favicon_path() -> Path:
    """Return the deployed favicon if a build exists, else the source copy."""
    return _FAVICON_DIST if _FAVICON_DIST.is_file() else _FAVICON_PUBLIC


def _protected_scan_capability(
    settings: Settings,
    vault: ProtectedVault | None,
) -> tuple[bool, str | None]:
    """Return a non-secret deployment readiness summary for manual sign-in scans."""
    if not settings.protected_scans_enabled:
        return False, "Protected sign-in scanning is not enabled on this Axcess server."

    proxy_ready = bool(settings.protected_proxy_hmac_secret.get_secret_value().strip())
    agent_proxy_ready = bool(settings.protected_agent_proxy_hmac_secret.get_secret_value().strip())
    try:
        parsed = urlsplit(settings.protected_public_origin.strip())
        _ = parsed.port  # Validate an explicitly supplied port.
        origin_ready = (
            parsed.scheme.lower() == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        origin_ready = False
    vault_ready = vault is not None and vault.supports_irreversible_scan_key_destruction
    if not (proxy_ready and agent_proxy_ready and origin_ready and vault_ready):
        return (
            False,
            "Protected sign-in scanning is enabled but its identity, companion, or "
            "managed-key deployment setup is incomplete.",
        )
    return True, None


def create_app(
    db_path: Path | None = None,
    blob_dir: Path | None = None,
    *,
    protected_vault: ProtectedVault | None = None,
) -> FastAPI:
    """Build the FastAPI app. Accepts overrides so tests can point at tmp paths."""
    settings = get_settings()
    resolved_db = db_path or settings.db_path
    resolved_blob = blob_dir or settings.blob_dir
    blob_store = BlobStore(resolved_blob)
    resolved_protected_vault = _resolve_protected_vault(settings, protected_vault)

    app = FastAPI(title="Axcess", version=__version__)

    @app.exception_handler(RequestValidationError)
    async def _protected_validation_error(
        request: Request, exc: RequestValidationError
    ) -> Response:
        """Do not reflect protected input in framework-generated 422 JSON.

        FastAPI's normal validation response includes the invalid ``input``
        value. For a protected route that can be a pairing code, a target URL
        with a capability parameter, or an attempted form value. Return one
        fixed message instead, while leaving public API validation ergonomics
        unchanged.
        """

        if _is_protected_request_path(request.url.path, resolved_db):
            return JSONResponse(
                {"detail": "Invalid protected request."},
                status_code=422,
                headers={
                    "Cache-Control": "no-store, private, max-age=0",
                    "Pragma": "no-cache",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return await request_validation_exception_handler(request, exc)

    # Optional shared-token gate. No-op when ``AUDIT_ACCESS_TOKEN`` is
    # unset (the default) so local dev + the test suite are untouched.
    # When set, every request must carry the token — as ``?token=…``,
    # an ``X-Access-Token`` header, or a ``Bearer`` Authorization header.
    # On success we drop a cookie so the browser doesn't need the query
    # string on every navigation. This is intentionally simple: it's a
    # "not wide open the moment it's on the LAN" guard, not a real
    # multi-user auth system (that's Path B). ``/health`` stays open so
    # uptime checks work without the token.
    _access_token = settings.access_token.strip()
    if _access_token:
        _cookie_name = "aa_access"

        @app.middleware("http")
        async def _require_token(request: Request, call_next):  # type: ignore[no-untyped-def]
            if request.url.path == "/health":
                return await call_next(request)
            # A shared ingress token is intentionally not an identity or
            # companion credential.  Protected browser/agent APIs use their
            # own signed-proxy and mTLS gates below; requiring the public
            # token here would both blur that boundary and leak a second
            # secret into the companion deployment.
            if request.url.path.startswith(("/api/protected-scans", "/api/agents")):
                return await call_next(request)
            supplied = (
                request.query_params.get("token")
                or request.headers.get("x-access-token")
                or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
                or request.cookies.get(_cookie_name)
                or ""
            )
            if not secrets.compare_digest(supplied, _access_token):
                return PlainTextResponse(
                    "Access token required. Append ?token=… to the URL or set "
                    "the X-Access-Token header.",
                    status_code=401,
                )
            response = await call_next(request)
            # Persist a correct token as a cookie so the operator only
            # pastes ?token=… once. Session cookie (no Max-Age) — clears
            # on browser close; HttpOnly so page JS can't read it.
            if request.query_params.get("token") == _access_token:
                response.set_cookie(_cookie_name, _access_token, httponly=True, samesite="lax")
            return response

    # React bundle lives under /app/. The asset paths (/app/assets/…) are
    # served by Vite's hashed output directly from dist/; the SPA shell
    # (index.html) is served for every /app/* route so React Router can
    # handle client-side navigation. Mounted conditionally so tests that
    # don't need the bundle don't require a prior `npm run build`.
    _frontend_assets = _FRONTEND_DIST / "assets"
    if _frontend_assets.is_dir():
        app.mount(
            "/app/assets",
            StaticFiles(directory=_frontend_assets),
            name="app-assets",
        )

    # Single running crawl at a time. Tracked here (not in the DB) because
    # "running" in the scans table can be stale after a server restart.
    crawl_state: dict[str, asyncio.Task[Any] | int | None] = {
        "task": None,
        "scan_id": None,
    }
    # The reference crawler's useful interaction is deliberately small: open
    # a visible browser, wait for the auditor, then crawl with that exact
    # authenticated context. Keep those local sessions in process memory so
    # a password, OTP, cookie, or reusable Playwright state never crosses the
    # HTTP boundary or reaches SQLite.
    local_login_runs: dict[int, _LocalLoginRun] = {}

    # Startup sweep: any scan left in 'running' when the server boots is
    # stale by definition — its live asyncio task is gone. Flip those to
    # 'interrupted' so they don't pollute the UI or block "single crawl
    # at a time" gating for new submissions.
    _sweep_stale_running_scans(resolved_db)

    def get_conn() -> sqlite3.Connection:
        return connect(resolved_db)

    # Clean up expired protected evidence at application start. Crypto-erasure
    # fails closed: when due records exist, the vault must revoke their
    # per-scan key before ciphertext metadata can be removed. A database
    # created before the protected migration is simply awaiting `make migrate`.
    try:
        with get_conn() as cleanup_conn:
            purge_expired_protected_data(cleanup_conn, vault=resolved_protected_vault)
    except sqlite3.OperationalError:
        pass
    except ProtectedDataError:
        # A due protected report with a missing, rotated, or non-revocable
        # vault must remain encrypted and unavailable.  Do not turn that
        # protected maintenance fault into an outage for the public workbench;
        # the retention worker will retry after the operator restores the
        # scan-bound KMS configuration.  Keep the log deliberately free of
        # KMS/provider exception text.
        log.warning("protected.retention_purge_unavailable")

    # Crypto-erasure cannot depend on a subsequent browser visit.  Keep a
    # small in-process retention worker for the single-host application and
    # repeat the purge at a bounded cadence.  The repository operation is
    # idempotent; an installation awaiting migration simply has nothing to
    # purge.  Production deployments should also run their normal scheduled
    # maintenance, but this closes the continuously-running local/LAN gap.
    retention_task: asyncio.Task[None] | None = None

    async def _protected_retention_worker() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                with get_conn() as cleanup_conn:
                    expired_runs = recover_stale_protected_run_leases(cleanup_conn)
                    for scan_id in expired_runs:
                        cleanup_conn.execute(
                            "UPDATE scans SET status = 'interrupted', "
                            "finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP) WHERE id = ?",
                            (scan_id,),
                        )
                    purge_expired_protected_data(cleanup_conn, vault=resolved_protected_vault)
            except sqlite3.OperationalError:
                # Protected migration not yet applied; regular public scans
                # remain usable and the next interval will retry.
                continue
            except Exception as exc:  # pragma: no cover - defensive scheduler guard
                # A provider exception can include endpoint names or other
                # sensitive diagnostics.  The durable audit row records the
                # report lifecycle; process logs need only say maintenance
                # should be investigated.
                log.warning(
                    "protected.retention_purge_failed",
                    error_type=type(exc).__name__,
                )

    @app.on_event("startup")
    async def _start_protected_retention_worker() -> None:
        nonlocal retention_task
        if retention_task is None or retention_task.done():
            retention_task = asyncio.create_task(_protected_retention_worker())

    @app.on_event("shutdown")
    async def _stop_protected_retention_worker() -> None:
        nonlocal retention_task
        if retention_task is None:
            return
        retention_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await retention_task
        retention_task = None

    @app.middleware("http")
    async def _require_protected_scan_access(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Gate legacy evidence routes when their scan belongs to protected mode.

        The protected router performs its own browser/agent checks.  This
        middleware prevents an older public route (detail, issue, manual
        evidence, export, etc.) from becoming a token-only bypass.
        """
        path = request.url.path
        if path.startswith("/api/protected-scans") or path.startswith("/api/agents"):
            return await call_next(request)
        # FastAPI/Pydantic accepts signed and whitespace-padded integers for
        # an ``int`` path parameter.  Never let a non-canonical spelling skip
        # the database-backed protected-report lookup in this middleware.
        # Reject it before endpoint parsing instead of trying to guess which
        # permissive representation the framework will coerce.
        if _has_noncanonical_legacy_identifier(path):
            return JSONResponse(
                {"detail": "Not found"},
                status_code=404,
                headers={
                    "Cache-Control": "no-store, private, max-age=0",
                    "Pragma": "no-cache",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        scan_id = _protected_scan_id_for_request(path)
        if scan_id is None:
            scan_id = _protected_finding_scan_id(path, resolved_db)
        protected_owner = (
            _protected_scan_owner(resolved_db, scan_id) if scan_id is not None else None
        )
        if protected_owner is not None:
            try:
                identity = require_protected_identity(request, settings)
                require_protected_report_owner(identity, authorized_by=protected_owner)
                if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                    require_same_origin(request, settings)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)

    @app.middleware("http")
    async def _prevent_protected_response_caching(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Keep protected API responses out of browsers and intermediary caches.

        This applies to the one-time pairing-code/work-item endpoints as well
        as the legacy scan routes guarded above. A reverse proxy must still be
        configured not to log response bodies, but the application does not
        leave cache behavior to an upstream default.
        """

        protected_path = _is_protected_request_path(request.url.path, resolved_db)
        response = await call_next(request)
        if protected_path:
            response.headers["Cache-Control"] = "no-store, private, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # ``add_middleware`` inserts this outer ASGI guard ahead of the
    # decorator-based middleware above. It must see raw body chunks before
    # FastAPI can deserialize an unauthenticated protected request.
    app.add_middleware(
        _ProtectedRequestBodyLimitMiddleware,
        db_path=resolved_db,
        max_body_bytes=settings.protected_request_body_max_bytes,
    )

    app.include_router(
        build_protected_router(
            get_conn=get_conn,
            settings=settings,
            vault=resolved_protected_vault,
        ),
        prefix="/api",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/favicon.svg")
    @app.get("/favicon.ico")
    @app.get("/app/favicon.svg")
    def favicon() -> Response:
        """Serve the brand favicon as SVG.

        Three paths because browsers, tooling, and Vite are inconsistent:

        * ``/favicon.svg`` — modern browsers honor the ``<link rel="icon">``
          tag in the Jinja base template.
        * ``/favicon.ico`` — devtools, screenshot pipelines, and a handful
          of older clients still poke this URL from the root regardless of
          the link tag. Every browser we care about accepts an SVG payload
          at the ``.ico`` path.
        * ``/app/favicon.svg`` — the SPA's index.html ships with
          ``base: "/app/"`` (vite.config.ts), so Vite rewrites
          ``href="/favicon.svg"`` to ``href="/app/favicon.svg"`` at build
          time. We mirror the route under that prefix so the SPA tab
          icon resolves without an extra static mount or a build hack.

        All three URLs return the same SVG with ``image/svg+xml``. One
        source file, three callable paths.
        """
        return FileResponse(_favicon_path(), media_type="image/svg+xml")

    # ---------------------------------------------------------------- /api
    # JSON surface for the React SPA. Mirrors the Jinja routes below.
    # Kept inline here (rather than split into api.py) so the closure
    # can share `crawl_state`, `resolved_db`, and helpers.

    @app.get("/api/scans")
    def api_list_scans() -> JSONResponse:
        with get_conn() as conn:
            if _protected_scan_table_exists(conn):
                rows = conn.execute(
                    "SELECT id, seed_url, status, page_count, finding_count, "
                    "started_at, finished_at FROM scans "
                    "WHERE NOT EXISTS ("
                    "SELECT 1 FROM protected_scans p WHERE p.scan_id = scans.id"
                    ") ORDER BY id DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, seed_url, status, page_count, finding_count, "
                    "started_at, finished_at FROM scans ORDER BY id DESC"
                ).fetchall()
        return JSONResponse([_scan_row_to_summary(r) for r in rows])

    @app.get("/api/scans/{scan_id:int}")
    def api_scan_detail(scan_id: int) -> JSONResponse:
        with get_conn() as conn:
            scan = _load_scan_or_404(conn, scan_id)
            protection = _get_protected_scan_compat(conn, scan_id=scan_id)
            breakdown = _severity_breakdown(conn, scan_id)
            prev = conn.execute(
                "SELECT id FROM scans WHERE seed_url = ? AND id <> ? "
                "AND status = 'completed' ORDER BY id DESC LIMIT 1",
                (scan["seed_url"], scan_id),
            ).fetchone()
            blocked = _detect_blocked_scan(conn, scan_id, scan)
            progress = _scan_progress(conn, scan_id) if scan["status"] == "running" else None
            method_coverage = _scan_method_coverage(conn, scan_id)
        payload: dict[str, Any] = {
            **_scan_row_to_summary(scan),
            "error_count": int(scan.get("error_count") or 0),
            "by_severity": {level: int(breakdown.get(level, 0)) for level in _SEVERITY_OPTIONS},
            "previous_scan_id": int(prev["id"]) if prev is not None else None,
            "blocked": blocked,
            "progress": progress,
            # Axe counters denormalized on scans for cheap reads. The SPA
            # detail page uses them to label the "WCAG findings" CTA with
            # the count without a join.
            "axe_pages_scanned": int(scan.get("axe_pages_scanned") or 0),
            "axe_violations_total": int(scan.get("axe_violations_total") or 0),
            "alfa_pages_scanned": int(scan.get("alfa_pages_scanned") or 0),
            "alfa_failed_total": int(scan.get("alfa_failed_total") or 0),
            "alfa_cant_tell_total": int(scan.get("alfa_cant_tell_total") or 0),
            "failure_reason": (
                str(scan.get("failure_reason")) if scan.get("failure_reason") else None
            ),
            # Coverage truth: which detection methods were on for this
            # scan (derived from config_json + counters). Lets the UI
            # show when a scan was a partial / static-only run.
            "methods_used": _methods_used(scan, method_coverage),
        }
        if protection is not None:
            # The middleware has already required a verified proxy identity
            # for this scan. Keep the legacy response useful to existing UI
            # code without ever putting key material, evidence, or agent
            # enrollment data into it.
            payload["protection"] = _protected_summary(protection)
        return JSONResponse(payload)

    @app.get("/api/capabilities/alfa")
    def api_alfa_capability() -> JSONResponse:
        """Expose only local runner readiness for the new-scan form."""
        state = alfa_availability()
        return JSONResponse({"available": state.available, "reason": state.reason})

    @app.get("/api/capabilities/local-analysis")
    async def api_local_analysis_capability() -> JSONResponse:
        """Report bundled OCR and local Ollama readiness without model downloads.

        Merely opening the scan form must never pull a model or start an
        analyzer.  This endpoint performs one short read-only Ollama tags
        request and returns only model names/sizes already present locally.
        """

        installed: dict[str, int] = {}
        ollama_reachable = False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
                response.raise_for_status()
                payload = response.json()
            models = payload.get("models", []) if isinstance(payload, dict) else []
            for model in models if isinstance(models, list) else []:
                if not isinstance(model, dict):
                    continue
                name = str(model.get("name") or "").strip()
                if name:
                    installed[name] = max(0, int(model.get("size") or 0))
            ollama_reachable = True
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            pass

        def installed_size(model: str) -> int | None:
            for candidate in (model, f"{model}:latest"):
                if candidate in installed:
                    return installed[candidate]
            return None

        vision_model = settings.vlm_model
        vision_size = installed_size(vision_model)
        semantic_models = sorted({get_pick(sc).primary for sc in supported_criteria()})
        semantic_ready = [model for model in semantic_models if installed_size(model) is not None]
        semantic_missing = [model for model in semantic_models if model not in semantic_ready]

        return JSONResponse(
            {
                "ocr": {
                    "available": shutil.which("tesseract") is not None,
                    "engine": "Tesseract 5",
                    "language": settings.ocr_language,
                    "max_workers": settings.ocr_max_workers,
                    "bundled_in_desktop": bool(shutil.which("tesseract")),
                },
                "ollama": {"reachable": ollama_reachable},
                "vision": {
                    "available": vision_size is not None,
                    "model": vision_model,
                    "installed_size_bytes": vision_size,
                    "reason": (
                        None
                        if vision_size is not None
                        else (
                            f"Install the local model with: ollama pull {vision_model}"
                            if ollama_reachable
                            else "Ollama is not running on this computer."
                        )
                    ),
                },
                "semantic": {
                    "available": ollama_reachable and not semantic_missing,
                    "models": semantic_models,
                    "ready_models": semantic_ready,
                    "missing_models": semantic_missing,
                    "checks_per_page": len(supported_criteria()),
                    "reason": (
                        None
                        if ollama_reachable and not semantic_missing
                        else (
                            "Missing local model(s): " + ", ".join(semantic_missing)
                            if ollama_reachable
                            else "Ollama is not running on this computer."
                        )
                    ),
                },
            }
        )

    @app.get("/api/capabilities/protected-scans")
    def api_protected_scan_capability(request: Request) -> JSONResponse:
        """Describe manual sign-in readiness without exposing deployment secrets."""
        available, reason = _protected_scan_capability(
            settings,
            resolved_protected_vault,
        )
        local_available, local_reason = _local_login_capability(request)
        return JSONResponse(
            {
                "available": available,
                "reason": reason,
                "local_available": local_available,
                "local_reason": local_reason,
                "authentication": "manual",
                "supported_sign_in": ["password", "mfa"],
                "requirements": [
                    "U-M-approved identity-aware proxy",
                    "scan-bound companion mTLS certificate",
                    "managed per-report key revocation",
                ],
            }
        )

    @app.post("/api/local-login-scans", status_code=201)
    async def api_create_local_login_scan(
        request: Request, body: LocalLoginScanRequest
    ) -> JSONResponse:
        """Open a headed, memory-only login browser on the Axcess computer.

        This is the direct local equivalent of the reference crawler's
        ``requires login`` mode. Unlike that implementation it does not use a
        marker file or serialize ``storageState``; the subsequent crawl uses
        the same live Playwright context.
        """

        _require_local_login_request(request, mutation=True)
        task = crawl_state.get("task")
        if isinstance(task, asyncio.Task) and not task.done():
            scan_id_val = crawl_state.get("scan_id")
            return JSONResponse(
                {
                    "error": "A crawl or login browser is already running.",
                    "running_scan_id": (int(scan_id_val) if isinstance(scan_id_val, int) else None),
                },
                status_code=409,
            )

        local_vlm_url = _local_login_ollama_url(settings.ollama_base_url)
        if not body.skip_vlm and local_vlm_url is None:
            return JSONResponse(
                {
                    "error": (
                        "Protected VLM analysis requires Ollama on a literal loopback "
                        "address such as http://127.0.0.1:11434."
                    )
                },
                status_code=400,
            )

        if body.scan_engine in {"alfa", "both"}:
            alfa_state = alfa_availability()
            if not alfa_state.available:
                return JSONResponse(
                    {
                        "error": alfa_state.reason
                        or "Siteimprove Alfa is not installed on this Axcess computer."
                    },
                    status_code=400,
                )

        config = CrawlConfig(
            seed_url=body.seed_url,
            max_pages=body.max_pages,
            max_depth=body.max_depth,
            rps=body.rps,
            whole_host=body.whole_host,
            # Login scans reuse one authenticated BrowserContext, but each
            # crawler worker opens and closes its own tab. Keep the cap small
            # so concurrent pages cannot overwhelm the shared session or the
            # target application while still using modern laptop capacity.
            concurrency_per_host=body.workers,
            workers=body.workers,
            user_agent=settings.user_agent,
            request_timeout_s=settings.request_timeout_s,
            # Optional protected-image analysis uses the same authenticated
            # browser context and never falls back to anonymous downloads.
            ocr_enabled=not body.skip_ocr,
            ocr_language=settings.ocr_language,
            ocr_max_workers=settings.ocr_max_workers,
            ocr_min_confidence=settings.ocr_min_confidence,
            ocr_min_word_count=settings.ocr_min_word_count,
            vlm_enabled=not body.skip_vlm,
            vlm_model=settings.vlm_model,
            vlm_base_url=local_vlm_url or "http://127.0.0.1:11434",
            vlm_prompt_name=settings.vlm_prompt_name,
            vlm_concurrency=1,
            semantic_enabled=False,
            js_enabled=True,
            js_eager=True,
            browser_only=True,
            image_extraction_enabled=not body.skip_ocr,
            axe_enabled=body.scan_engine in {"axe", "both"},
            axe_level=body.axe_level,
            alfa_enabled=body.scan_engine in {"alfa", "both"},
            keyboard_probe_enabled=not body.skip_keyboard,
            responsive_checks_enabled=not body.skip_responsive,
            focus_checks_enabled=True,
            visual_checks_enabled=False,
            capture_screenshots=False,
            ignore_robots=True,
        )
        scan_id = _prepare_scan_row(resolved_db, config)
        session = ManualAuthenticationSession(
            seed_url=body.seed_url,
            approved_target_origins=(body.target_origin,),
            approved_auth_origins=body.approved_auth_origins,
            user_agent=settings.user_agent,
            # A local human-controlled login may cross dynamically assigned
            # public SSO/MFA origins. Scan mode still tightens to the exact
            # target origin before any page evidence is collected.
            allow_any_public_auth_origin=True,
        )
        run = _LocalLoginRun(
            scan_id=scan_id,
            session=session,
            confirmation=asyncio.Event(),
        )
        local_login_runs[scan_id] = run
        crawl_state["scan_id"] = scan_id
        run.task = asyncio.create_task(
            _run_local_login_background(resolved_db, resolved_blob, config, run)
        )
        crawl_state["task"] = run.task
        return JSONResponse(
            {
                "scan_id": scan_id,
                "status": run.status,
                "message": "Opening a visible Chromium window for manual sign-in.",
            },
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/local-login-scans/{scan_id:int}")
    async def api_local_login_scan_status(request: Request, scan_id: int) -> JSONResponse:
        """Return operational state only; never browser URLs or session data."""

        _require_local_login_request(request, mutation=False)
        run = local_login_runs.get(scan_id)
        if run is not None:
            return JSONResponse(
                {
                    "scan_id": scan_id,
                    "status": run.status,
                    "error": run.error,
                    "browser_backgrounded": run.browser_backgrounded,
                },
                headers={"Cache-Control": "no-store"},
            )
        with get_conn() as conn:
            row = conn.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Login scan not found.")
        status = str(row["status"])
        return JSONResponse(
            {
                "scan_id": scan_id,
                "status": (
                    status if status in {"completed", "failed", "interrupted"} else "interrupted"
                ),
                "error": (
                    None
                    if status == "completed"
                    else (
                        "The in-memory login browser is no longer available. "
                        "Start a new login scan."
                    )
                ),
                "browser_backgrounded": False,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/local-login-scans/{scan_id:int}/confirm")
    async def api_confirm_local_login(request: Request, scan_id: int) -> JSONResponse:
        """Human confirmation signal; the server independently verifies target scope."""

        _require_local_login_request(request, mutation=True)
        run = local_login_runs.get(scan_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Login browser is not available.")
        if run.status != "awaiting_authentication":
            raise HTTPException(
                status_code=409,
                detail="Wait for the visible browser before confirming sign-in.",
            )
        run.confirmation.set()
        return JSONResponse(
            {"scan_id": scan_id, "status": "verifying_authentication"},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/scans")
    async def api_create_scan(
        request: Request, body: Annotated[dict[str, Any], Body()]
    ) -> JSONResponse:
        """Kick off a crawl. Body mirrors the new-scan form fields."""
        url = str(body.get("url") or "").strip()
        validation_error = _validate_seed_url(url)
        if validation_error is not None:
            return JSONResponse({"error": validation_error}, status_code=400)

        task = crawl_state.get("task")
        if isinstance(task, asyncio.Task) and not task.done():
            scan_id_val = crawl_state.get("scan_id")
            return JSONResponse(
                {
                    "error": "A crawl is already running.",
                    "running_scan_id": int(scan_id_val) if isinstance(scan_id_val, int) else None,
                },
                status_code=409,
            )

        requested_engine = str(body.get("scan_engine") or "").strip().lower()
        # Existing API callers use the pre-selector `skip_axe` field. Preserve
        # that contract when no engine is sent, while making explicit engine
        # selection authoritative for the redesigned form.
        if not requested_engine:
            requested_engine = (
                "alfa" if bool(body.get("skip_axe")) and bool(body.get("alfa_enabled")) else "axe"
            )
        if requested_engine not in {"axe", "alfa", "both"}:
            return JSONResponse(
                {"error": "Scan engine must be axe, alfa, or both."}, status_code=422
            )
        if requested_engine in {"alfa", "both"}:
            alfa_state = alfa_availability()
            if not alfa_state.available:
                return JSONResponse(
                    {
                        "error": alfa_state.reason
                        or "Alfa is not installed. Run `make alfa-install` before selecting it."
                    },
                    status_code=422,
                )
        static_only = bool(
            body.get("static_only") or (body.get("js_eager") is False and "js_eager" in body)
        )
        if static_only and requested_engine in {"axe", "both"}:
            return JSONResponse(
                {
                    "error": "axe-core needs Axcess browser rendering. Turn off static-only mode "
                    "or select Alfa only."
                },
                status_code=422,
            )

        form = {
            "url": url,
            "max_pages": int(body.get("max_pages") or 2500),
            "max_depth": int(body.get("max_depth") or 10),
            "rps": float(body.get("rps") or 2.0),
            "workers": int(body.get("workers") or 8),
            "include_subdomain": bool(body.get("include_subdomain")),
            "whole_host": bool(body.get("whole_host")),
            "ignore_robots": bool(body.get("ignore_robots")),
            "skip_ocr": bool(body.get("skip_ocr")),
            "skip_vlm": bool(body.get("skip_vlm")),
            # Render-every-page is the default; `static_only` is the
            # opt-out fast path. (`js_eager` accepted for older callers.)
            "static_only": static_only,
            "show_browser": bool(body.get("show_browser")),
            "skip_axe": bool(body.get("skip_axe")),
            "scan_engine": requested_engine,
            "skip_keyboard": bool(body.get("skip_keyboard")),
            "skip_responsive": bool(body.get("skip_responsive")),
            "skip_semantic": bool(body.get("skip_semantic")),
            "skip_focus": bool(body.get("skip_focus")),
            "skip_visual": bool(body.get("skip_visual")),
            "axe_level": str(body.get("axe_level", "AA")),
        }
        config = _build_crawl_config(form, settings)
        scan_id = _prepare_scan_row(resolved_db, config)
        crawl_state["scan_id"] = scan_id

        async def _runner() -> None:
            await _run_background_crawl(resolved_db, config)

        crawl_state["task"] = asyncio.create_task(_runner())
        return JSONResponse({"scan_id": scan_id}, status_code=201)

    @app.post("/api/scans/{scan_id:int}/cancel")
    async def api_cancel_scan(scan_id: int) -> JSONResponse:
        task = crawl_state.get("task")
        active_scan_id = crawl_state.get("scan_id")
        if isinstance(task, asyncio.Task) and not task.done() and active_scan_id == scan_id:
            task.cancel()
        with get_conn() as conn:
            protected = _get_protected_scan_compat(conn, scan_id=scan_id)
            if protected is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Use the protected report Stop action for an authenticated scan.",
                )
            existing = conn.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Scan not found")
            if existing["status"] == "running":
                conn.execute(
                    "UPDATE scans SET status = 'interrupted', "
                    "finished_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (scan_id,),
                )
                conn.execute(
                    "DELETE FROM jobs WHERE json_extract(payload_json, '$.scan_id') = ? "
                    "AND state = 'pending'",
                    (scan_id,),
                )
        return JSONResponse({"ok": True})

    @app.delete("/api/scans/{scan_id:int}")
    async def api_delete_scan(scan_id: int) -> JSONResponse:
        """Permanently delete a scan and everything it owns.

        Cascades take care of the obvious children (pages, page_images,
        findings, finding_history) via the FK declarations in
        0001_initial_schema.sql. Two things they don't cover and we have
        to handle ourselves:

        * ``images.first_seen_scan_id`` has no ``ON DELETE`` action — if
          left pointing at a doomed scan, the DELETE FK-violates. We NULL
          it instead of cascading because images are dedupe'd by
          ``content_hash`` and may be referenced by later scans; losing
          the image row would orphan blobs and break diff history.
        * ``jobs`` rows aren't FK-bound (``scan_id`` lives inside
          ``payload_json``), so they need an explicit DELETE keyed on
          ``json_extract`` — same trick the cancel endpoint uses.

        We refuse to delete a currently-running scan: the live asyncio
        task would keep writing rows after the DELETE, leaving
        half-resurrected state. Caller must cancel first, then delete.
        """
        task = crawl_state.get("task")
        active_scan_id = crawl_state.get("scan_id")
        if isinstance(task, asyncio.Task) and not task.done() and active_scan_id == scan_id:
            raise HTTPException(
                status_code=409,
                detail="Cancel the running scan before deleting it.",
            )
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id, status FROM scans WHERE id = ?", (scan_id,)
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Scan not found")
            protected = _get_protected_scan_compat(conn, scan_id=scan_id)
            if protected is not None and protected.protection_status in {
                ProtectedScanStatus.AWAITING_AUTHENTICATION,
                ProtectedScanStatus.RUNNING,
                ProtectedScanStatus.AUTHENTICATION_REQUIRED,
            }:
                raise HTTPException(
                    status_code=409,
                    detail="Stop the protected companion before deleting this report.",
                )
            if protected is not None:
                if resolved_protected_vault is None:
                    # Do not turn an operational KMS misconfiguration into a
                    # misleading "deleted" report while historical database
                    # or WAL copies remain decryptable by a managed KEK.
                    raise HTTPException(
                        status_code=503,
                        detail="Protected report deletion requires its configured key manager.",
                    )
                try:
                    # Production adapters revoke a per-scan KMS key/grant.
                    # This must happen before SQLite cascade deletion so a
                    # backup snapshot cannot later unwrap retained ciphertext.
                    destroy_protected_scan_key(
                        conn,
                        scan_id=scan_id,
                        vault=resolved_protected_vault,
                    )
                except ProtectedDataError as exc:
                    log.warning("protected.scan_key_delete_failed", scan_id=scan_id)
                    raise HTTPException(
                        status_code=503,
                        detail="Protected report deletion could not revoke its evidence key.",
                    ) from exc
            # Belt-and-braces: status can lie if the server crashed mid-run
            # before the startup sweep flipped it to 'interrupted'. The
            # in-memory crawl_state check above is the authoritative gate.
            if existing["status"] == "running" and active_scan_id == scan_id:
                raise HTTPException(
                    status_code=409,
                    detail="Cancel the running scan before deleting it.",
                )
            with conn:
                conn.execute(
                    "UPDATE images SET first_seen_scan_id = NULL WHERE first_seen_scan_id = ?",
                    (scan_id,),
                )
                conn.execute(
                    "DELETE FROM jobs WHERE json_extract(payload_json, '$.scan_id') = ?",
                    (scan_id,),
                )
                conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
        return JSONResponse({"ok": True, "deleted_scan_id": scan_id})

    @app.get("/api/scans/{scan_id:int}/evaluation")
    def api_get_evaluation(scan_id: int) -> JSONResponse:
        """Return expert-review metadata without mutating the scan record."""
        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            _deny_legacy_protected_review(conn, scan_id)
            payload = evaluation.get_evaluation(conn, scan_id)
        return JSONResponse(jsonable_encoder(payload))

    @app.put("/api/scans/{scan_id:int}/evaluation")
    def api_put_evaluation(scan_id: int, body: EvaluationUpdate) -> JSONResponse:
        """Persist the human-authored evaluation context for a completed scan."""
        with get_conn() as conn:
            scan = _load_scan_or_404(conn, scan_id)
            _deny_legacy_protected_review(conn, scan_id)
            _require_completed_scan(scan)
            existing = evaluation.get_evaluation(conn, scan_id)
            changes = body.model_dump(exclude_none=True)
            values = {
                key: str(changes.get(key, existing[key]))
                for key in (
                    "target_standard",
                    "target_level",
                    "purpose",
                    "scope_included",
                    "scope_excluded",
                    "sample_description",
                    "reviewer",
                    "methods_note",
                    "limitations",
                    "status",
                )
            }
            try:
                payload = evaluation.upsert_evaluation(conn, scan_id, values)
            except evaluation.EvaluationCompletionError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "evaluation_not_ready",
                        "message": "The evaluation is not ready to be completed.",
                        "blockers": list(exc.blockers),
                    },
                ) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(jsonable_encoder(payload))

    @app.get("/api/scans/{scan_id:int}/manual-checks")
    def api_list_manual_checks(scan_id: int) -> JSONResponse:
        """Return the full WCAG 2.2 A/AA expert-review matrix for a report."""
        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            _deny_legacy_protected_review(conn, scan_id)
            payload = {
                "evaluation": evaluation.get_evaluation(conn, scan_id),
                "checks": evaluation.list_manual_checks(conn, scan_id),
            }
        return JSONResponse(jsonable_encoder(payload))

    @app.patch("/api/scans/{scan_id:int}/manual-checks/{criterion_sc}")
    def api_update_manual_check(
        scan_id: int, criterion_sc: str, body: ManualCheckUpdate
    ) -> JSONResponse:
        with get_conn() as conn:
            scan = _load_scan_or_404(conn, scan_id)
            _deny_legacy_protected_review(conn, scan_id)
            _require_completed_scan(scan)
            try:
                payload = evaluation.update_manual_check(
                    conn,
                    scan_id=scan_id,
                    criterion_sc=criterion_sc,
                    outcome=body.outcome,
                    rationale=body.rationale,
                )
            except evaluation.EvaluationCompletionError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "evaluation_not_ready",
                        "message": "Reopen the evaluation before making this change.",
                        "blockers": list(exc.blockers),
                    },
                ) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(jsonable_encoder(payload))

    @app.post("/api/scans/{scan_id:int}/manual-checks/{criterion_sc}/evidence")
    def api_add_manual_evidence(
        scan_id: int, criterion_sc: str, body: ManualEvidenceCreate
    ) -> JSONResponse:
        with get_conn() as conn:
            scan = _load_scan_or_404(conn, scan_id)
            _deny_legacy_protected_review(conn, scan_id)
            _require_completed_scan(scan)
            try:
                payload = evaluation.add_manual_evidence(
                    conn,
                    scan_id=scan_id,
                    criterion_sc=criterion_sc,
                    note=body.note,
                    page_id=body.page_id,
                    evidence_url=body.evidence_url,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(jsonable_encoder(payload), status_code=201)

    @app.get("/api/scans/{scan_id:int}/pages/{page_id:int}")
    def api_page_evidence(scan_id: int, page_id: int) -> JSONResponse:
        """Return page evidence only when the page belongs to this report."""
        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            payload = evaluation.get_page_evidence(conn, scan_id=scan_id, page_id=page_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Page is not part of this report")
        return JSONResponse(jsonable_encoder(payload))

    @app.get("/api/scans/{scan_id:int}/findings")
    def api_list_findings(
        scan_id: int,
        severity: str = Query(default=""),
        status: str = Query(default=""),
        classification: str = Query(default=""),
        q: str = Query(default=""),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=_PAGE_SIZE, ge=1, le=500),
    ) -> JSONResponse:
        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            filters = {
                "severity": severity if severity in _SEVERITY_OPTIONS else "",
                "status": status if status in _STATUS_OPTIONS else "",
                "classification": (
                    classification if classification in _CLASSIFICATION_OPTIONS else ""
                ),
                "q": q,
            }
            findings, total = _query_findings(
                conn, scan_id=scan_id, filters=filters, page=page, size=page_size
            )
        total_pages = max(1, math.ceil(total / page_size))
        return JSONResponse(
            {
                "findings": findings,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )

    @app.get("/api/scans/{scan_id:int}/issues/{issue_key:path}")
    def api_scan_issue_detail(
        scan_id: int,
        issue_key: str,
        sort: str = Query(default="occurrences_desc"),
    ) -> JSONResponse:
        """JSON form of the per-issue detail — used by the SPA."""
        from dataclasses import asdict

        from audit.web import issues as issues_mod

        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            detail = issues_mod.get_issue_detail(conn, scan_id, issue_key, sort=sort)
        if detail is None:
            raise HTTPException(
                status_code=404,
                detail=f"Issue {issue_key!r} not found in scan {scan_id}",
            )
        # asdict converts the IssueRow nested inside the IssueDetail.
        return JSONResponse(asdict(detail))

    @app.get("/api/scans/{scan_id:int}/issues")
    def api_scan_issues(
        scan_id: int,
        conformance: str = Query(default=""),
        responsibility: str = Query(default=""),
        abilities: str = Query(default=""),
        status: str = Query(default=""),
        review_lane: str = Query(default=""),
        q: str = Query(default=""),
        sort: str = Query(default="priority_desc"),
    ) -> JSONResponse:
        """JSON form of the unified Issues list — used by the SPA."""
        from dataclasses import asdict

        from audit.web import issues as issues_mod

        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            filtered = issues_mod.list_issues(
                conn,
                scan_id,
                conformance=_split_csv(conformance),
                responsibility=_split_csv(responsibility),
                abilities=_split_csv(abilities),
                status=status or None,
                search=q or None,
                review_lane=(
                    review_lane
                    if review_lane in {"likely_barrier", "expert_review", "informational"}
                    else None
                ),
                sort=sort,
            )
            unfiltered = issues_mod.list_issues(conn, scan_id)
        return JSONResponse(
            {
                "rows": [asdict(r) for r in filtered],
                "conformance_counts": issues_mod.conformance_breakdown(unfiltered),
                "responsibility_counts": issues_mod.responsibility_breakdown(unfiltered),
                "abilities_counts": issues_mod.abilities_breakdown(unfiltered),
                "review_lane_counts": issues_mod.review_lane_breakdown(unfiltered),
                "occurrence_counts": {
                    "all_evidence": sum(row.occurrence_count for row in unfiltered),
                    "high_confidence": sum(
                        row.high_confidence_occurrence_count for row in unfiltered
                    ),
                },
                "total_unfiltered": len(unfiltered),
            }
        )

    @app.get("/api/scans/{scan_id:int}/a11y/by-rule")
    def api_scan_a11y_by_rule(
        scan_id: int,
        status: str = Query(default=""),
    ) -> JSONResponse:
        """JSON form of the per-rule rollup. Used by the SPA."""
        from audit.web import a11y_queries

        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            coverage = a11y_queries.coverage(conn, scan_id)
            groups = a11y_queries.grouped_by_rule(conn, scan_id, status=status if status else None)
        return JSONResponse({"coverage": coverage, "groups": groups})

    @app.get("/api/scans/{scan_id:int}/a11y")
    def api_scan_a11y(scan_id: int) -> JSONResponse:
        """Roll-up of source-attributed DOM-engine WCAG findings by SC and level.

        Shape:

            {
                "coverage": {pages_total, axe_pages_scanned, alfa_pages_scanned, ...},
                "by_level": {"A": n, "AA": n, "AAA": n, "best_practice": n},
                "by_impact": {"critical": n, "serious": n, ...},
                "by_status": {"new": n, "reviewing": n, ...},
                "groups": [{ wcag_sc, wcag_level, violation_count,
                             page_count, worst_impact,
                             rules: [{ pipeline, rule_id, impact, help, help_url,
                                       violation_count, page_count }] }]
            }
        """
        from audit.web import a11y_queries

        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            return JSONResponse(
                {
                    "coverage": a11y_queries.coverage(conn, scan_id),
                    "by_level": a11y_queries.by_level(conn, scan_id),
                    "by_impact": a11y_queries.by_impact(conn, scan_id),
                    "by_status": a11y_queries.by_status(conn, scan_id),
                    "groups": a11y_queries.by_sc(conn, scan_id),
                }
            )

    @app.get("/api/scans/{scan_id:int}/a11y/findings")
    def api_scan_a11y_findings(
        scan_id: int,
        wcag_sc: str | None = Query(default=None),
        status: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> JSONResponse:
        """Drill-down list for a single WCAG SC (or null = best-practice).

        Optional ``status`` filter mirrors the Jinja side — pass a
        status name to hide already-handled findings; omit (or pass
        empty) for all rows.
        """
        from audit.web import a11y_queries

        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            rows = a11y_queries.findings_for_sc(
                conn,
                scan_id,
                # An empty-string query param means "best-practice (NULL SC)".
                # `None` means "client didn't ask for a drill-down."
                wcag_sc=None if wcag_sc == "" else wcag_sc,
                status=status if status else None,
                limit=limit,
                offset=offset,
            )
        return JSONResponse({"findings": rows})

    @app.get("/api/findings/{finding_id:int}")
    def api_finding_detail(finding_id: int) -> JSONResponse:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT f.id, f.scan_id, f.status, f.severity, f.priority_score,
                       f.remediation_hint, f.wcag_criterion,
                       i.id AS image_id, i.content_hash, i.blob_path, i.mime,
                       i.width, i.height, i.has_svg_text, i.src_url_canonical,
                       a.ocr_text, a.ocr_confidence, a.vlm_classification,
                       a.vlm_rationale
                  FROM findings f
                  JOIN images i ON i.id = f.image_id
                  LEFT JOIN analyses a ON a.image_id = i.id
                 WHERE f.id = ?
                 ORDER BY
                    CASE WHEN a.vlm_classification IS NOT NULL THEN 0 ELSE 1 END,
                    a.analyzed_at DESC
                 LIMIT 1
                """,
                (finding_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Finding not found")
            occurrences = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT pi.page_id, pi.alt_text, pi.above_fold,
                           p.url_normalized AS page_url
                      FROM page_images pi
                      JOIN pages p ON p.id = pi.page_id
                     WHERE pi.image_id = ? AND p.scan_id = ?
                     ORDER BY pi.position
                    """,
                    (row["image_id"], row["scan_id"]),
                ).fetchall()
            ]
        payload = dict(row)
        payload["has_svg_text"] = bool(payload.get("has_svg_text"))
        payload["occurrences"] = [{**o, "above_fold": bool(o["above_fold"])} for o in occurrences]
        return JSONResponse(payload)

    @app.get("/api/scans/{scan_id:int}/findings/grouped")
    def api_scan_findings_grouped(
        scan_id: int,
        status: str = Query(default=""),
    ) -> JSONResponse:
        """Image findings grouped by ``(classification, alt_adequacy)``.

        Mirrors the Jinja roll-up at ``/scans/{id}/findings/grouped``.
        Each group carries its shared remediation hint, a severity +
        status breakdown, and an ordered list of contained findings
        with their occurrences attached. ``status`` narrows to one
        triage state; empty means all.
        """
        from audit.web import image_findings_queries

        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            cov = image_findings_queries.coverage(conn, scan_id)
            groups = image_findings_queries.grouped_by_remediation(
                conn, scan_id, status=status if status else None
            )
        return JSONResponse({"coverage": cov, "groups": groups})

    @app.post("/api/findings/{finding_id:int}/status")
    async def api_set_finding_status(
        finding_id: int, body: Annotated[dict[str, Any], Body()]
    ) -> JSONResponse:
        status = str(body.get("status") or "")
        if status not in _STATUS_OPTIONS:
            raise HTTPException(status_code=400, detail="Unknown status value")
        rationale = body.get("rationale")
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Finding not found")
            try:
                updated = repo.bulk_set_findings_status(
                    conn,
                    finding_ids=[finding_id],
                    status=status,
                    actor="user",
                    rationale=rationale,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"status": status, "updated": updated})

    @app.post("/api/findings/bulk-status")
    async def api_bulk_set_finding_status(
        request: Request,
        body: Annotated[dict[str, Any], Body()],
    ) -> JSONResponse:
        """Update many image-of-text findings at once.

        Body: ``{"finding_ids": [1, 2, 3], "status": "accepted_risk"}``.

        Designed for the grouped-by-issue view: every finding in a group
        shares one remediation hint, so the natural operator move is
        "all 96 of these are accepted_risk." A loop of per-row POSTs
        works but burns a request per finding and produces N rerenders;
        one transaction here is the right shape.
        """
        status = str(body.get("status") or "")
        if status not in _STATUS_OPTIONS:
            raise HTTPException(status_code=400, detail="Unknown status value")
        rationale = body.get("rationale")
        raw_ids = body.get("finding_ids") or []
        if not isinstance(raw_ids, list):
            raise HTTPException(status_code=400, detail="finding_ids must be a list")
        try:
            finding_ids = [int(x) for x in raw_ids]
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="finding_ids must be integers") from exc
        if len(finding_ids) > 500:
            raise HTTPException(
                status_code=400, detail="At most 500 findings can be updated at once"
            )
        with get_conn() as conn:
            _require_protected_bulk_access(conn, request, settings, finding_ids, table="findings")
            try:
                updated = repo.bulk_set_findings_status(
                    conn,
                    finding_ids=finding_ids,
                    status=status,
                    actor="user",
                    rationale=rationale,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"status": status, "updated": updated})

    @app.post("/api/a11y-findings/bulk-status")
    async def api_bulk_set_a11y_finding_status(
        request: Request,
        body: Annotated[dict[str, Any], Body()],
    ) -> JSONResponse:
        """Update many WCAG axe findings at once. See bulk-findings doc."""
        status = str(body.get("status") or "")
        if status not in _STATUS_OPTIONS:
            raise HTTPException(status_code=400, detail="Unknown status value")
        rationale = body.get("rationale")
        raw_ids = body.get("finding_ids") or []
        if not isinstance(raw_ids, list):
            raise HTTPException(status_code=400, detail="finding_ids must be a list")
        try:
            finding_ids = [int(x) for x in raw_ids]
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="finding_ids must be integers") from exc
        if len(finding_ids) > 500:
            raise HTTPException(
                status_code=400, detail="At most 500 findings can be updated at once"
            )
        with get_conn() as conn:
            _require_protected_bulk_access(
                conn, request, settings, finding_ids, table="page_a11y_findings"
            )
            try:
                updated = repo.bulk_set_a11y_findings_status(
                    conn,
                    finding_ids=finding_ids,
                    status=status,
                    actor="user",
                    rationale=rationale,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except sqlite3.OperationalError as exc:
                if "a11y_finding_history" not in str(exc):
                    raise
                raise HTTPException(
                    status_code=503,
                    detail="Database migrations are incomplete. Run `make migrate` and retry.",
                ) from exc
        return JSONResponse({"status": status, "updated": updated})

    @app.post("/api/a11y-findings/{finding_id:int}/status")
    async def api_set_a11y_finding_status(
        finding_id: int, body: Annotated[dict[str, Any], Body()]
    ) -> JSONResponse:
        """Update a WCAG axe finding's triage status.

        Mirrors ``api_set_finding_status`` (image-of-text findings) but
        targets ``page_a11y_findings``. We deliberately reuse the same
        status enum so the SPA's StatusChip / shortcuts work without a
        second vocabulary.

        Migration 0019 gives page-scoped findings the same durable status
        decision trail as image findings. Decisive dispositions require a
        bounded rationale; workflow-only transitions remain compatible with
        older callers that send only ``status``.
        """
        status = str(body.get("status") or "")
        if status not in _STATUS_OPTIONS:
            raise HTTPException(status_code=400, detail="Unknown status value")
        rationale = body.get("rationale")
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM page_a11y_findings WHERE id = ?", (finding_id,)
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Finding not found")
            try:
                updated = repo.bulk_set_a11y_findings_status(
                    conn,
                    finding_ids=[finding_id],
                    status=status,
                    actor="user",
                    rationale=rationale,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except sqlite3.OperationalError as exc:
                if "a11y_finding_history" not in str(exc):
                    raise
                raise HTTPException(
                    status_code=503,
                    detail="Database migrations are incomplete. Run `make migrate` and retry.",
                ) from exc
        return JSONResponse({"status": status, "updated": updated})

    @app.get("/api/scans/{scan_id:int}/diff")
    def api_scan_diff(scan_id: int, compare_to: int = Query(...)) -> JSONResponse:
        with get_conn() as conn:
            _load_scan_or_404(conn, scan_id)
            _load_scan_or_404(conn, compare_to)
            if _get_protected_scan_compat(conn, scan_id=scan_id) or _get_protected_scan_compat(
                conn, scan_id=compare_to
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Protected scans cannot be compared with another report.",
                )
            report = compute_diff(conn, current_scan_id=scan_id, compare_to_scan_id=compare_to)
        return JSONResponse(
            {
                "current_scan_id": scan_id,
                "compare_to_scan_id": compare_to,
                "counts": report.counts,
                "new": [vars(e) for e in report.new],
                "resolved": [vars(e) for e in report.resolved],
                "still_open": [vars(e) for e in report.still_open],
                "status_changed": [vars(e) for e in report.status_changed],
            }
        )

    @app.get("/api/scope-preview")
    def api_scope_preview(
        url: str = Query(default=""), whole_host: str = Query(default="")
    ) -> JSONResponse:
        url = (url or "").strip()
        if not url:
            return JSONResponse(
                {
                    "normalized_url": "",
                    "host": "",
                    "path_prefix": "",
                    "auto_slash_added": False,
                    "whole_host": False,
                    "error": None,
                }
            )
        error = _validate_seed_url(url)
        if error is not None:
            return JSONResponse(
                {
                    "normalized_url": url,
                    "host": "",
                    "path_prefix": "",
                    "auto_slash_added": False,
                    "whole_host": bool(whole_host),
                    "error": error,
                }
            )
        normalized = url_policy.normalize_seed_url(url)
        whole = bool(whole_host)
        scope = url_policy.build_scope(normalized, whole_host=whole)
        return JSONResponse(
            {
                "normalized_url": normalized,
                "host": scope.seed_host,
                "path_prefix": scope.path_prefix,
                "auto_slash_added": normalized != url,
                "whole_host": whole,
                "error": None,
            }
        )

    @app.get("/api/tracking")
    def api_tracking() -> JSONResponse:
        """Coverage & feature tracker data for the SPA /tracking page.

        Pipeline/roadmap data comes from ``coverage_status``; the per-WCAG
        coverage breakdown comes from the ``coverage_matrix`` (the
        authoritative A/AA source of truth). Both drive the page directly
        so it can't drift from the code.
        """
        counts = roadmap_counts()
        cov = coverage_matrix.summary()
        criteria = [
            {
                "sc": c.sc,
                "name": c.name,
                "level": c.level,
                "method": c.method,
                "pipelines": list(c.pipelines),
                "confidence": c.confidence,
                "automated_check": c.automated_check,
                "manual_check": c.manual_check,
            }
            for c in coverage_matrix.load_matrix()
        ]
        return JSONResponse(
            {
                "shipped": [vars(p) for p in SHIPPED],
                "roadmap": [vars(r) for r in ROADMAP],
                "counts": {
                    "shipped": counts.shipped,
                    "in_progress": counts.in_progress,
                    "planned": counts.planned,
                },
                "coverage": {
                    "total": cov.total,
                    "by_method": cov.by_method,
                    "covered": cov.covered,
                    "manual_only": cov.manual_only,
                    "methods": list(coverage_matrix.METHODS),
                    "method_labels": coverage_matrix.METHOD_LABELS,
                    "method_blurb": coverage_matrix.METHOD_BLURB,
                    "criteria": criteria,
                },
            }
        )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        # The React SPA is the only UI. /app/ serves a 503 "build the
        # frontend" notice if the bundle isn't built yet, so it's always
        # the right redirect target.
        return RedirectResponse("/app/", status_code=307)

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    def spa_shell(path: str = "") -> Response:
        """Serve the React bundle's index.html for every /app/* URL.

        Client-side routing means /app/scans/3, /app/findings/7, etc. all
        need to return the same shell HTML; React Router parses the path.
        Static assets requested under /app/assets/* are served by the
        StaticFiles mount above before this catch-all is reached.
        """
        _ = path  # consumed by React Router, not by us
        index = _FRONTEND_DIST / "index.html"
        if not index.exists():
            return HTMLResponse(
                "<p>Frontend bundle not built. Run "
                "<code>cd src/audit/web/frontend && npm install && npm run build</code>.</p>",
                status_code=503,
            )
        return FileResponse(index, media_type="text/html")

    # The SPA's ``exportUrl()`` helper downloads from this ``/api/*`` route
    # (a plain <a download>, bypassing the React-Router basename).
    @app.get("/api/scans/{scan_id:int}/export/{fmt}")
    def export_scan(
        request: Request,
        scan_id: int,
        fmt: str,
        draft: Annotated[
            str | None,
            Query(
                description=(
                    "Set exactly to 'acknowledged' to download an incomplete "
                    "expert evaluation as a visibly labeled draft."
                )
            ),
        ] = None,
    ) -> Response:
        """Download a scan export as CSV / JSON / Jira CSV / Markdown / Audit."""
        fmt_lower = fmt.lower()
        if fmt_lower not in _EXPORT_RENDERERS:
            raise HTTPException(status_code=400, detail="Unknown export format")
        ui_base = str(request.base_url).rstrip("/")
        with get_conn() as conn:
            if _get_protected_scan_compat(conn, scan_id=scan_id) is not None:
                # Protected output needs an explicit owner-authorized,
                # reviewed-redaction workflow.  The ordinary collectors can
                # never be treated as such a handoff just because the caller
                # has a proxy identity.
                raise HTTPException(
                    status_code=403,
                    detail="Protected reports require an authorized redacted export workflow.",
                )
            try:
                scan = collect_scan(conn, scan_id, ui_base_url=ui_base)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            try:
                readiness = assess_public_export_readiness(
                    conn,
                    scan_id,
                    draft_acknowledged=draft == "acknowledged",
                )
            except IncompleteEvaluationExportError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            # The audit-report renderer needs the live connection so it
            # can call the grouping helpers. The other renderers operate
            # on the pre-collected `scan` only.
            rendered: str | bytes
            if fmt_lower == "audit":
                rendered = render_audit_report(scan, conn=conn)
            elif fmt_lower == "xlsx":
                # Pass the blob store so the Issues Overview sheet can embed
                # each finding's circled location screenshot as evidence.
                rendered = render_xlsx(scan, conn=conn, blob_store=blob_store)
            else:
                rendered = _EXPORT_RENDERERS[fmt_lower](scan)
            rendered = label_draft_export(
                rendered,
                export_format=fmt_lower,
                readiness=readiness,
            )
        media = _EXPORT_MEDIA_TYPES[fmt_lower]
        ext = _EXPORT_EXTENSIONS[fmt_lower]
        filename = public_export_filename(scan_id, ext, readiness)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if readiness.is_draft:
            headers["X-Axcess-Export-State"] = "draft"
        return Response(
            content=rendered,
            media_type=media,
            headers=headers,
        )

    @app.get("/blobs/{content_hash}")
    def serve_blob(content_hash: str) -> Response:
        """Serve an image blob by content hash. Hash format is validated."""
        if not _CONTENT_HASH_RE.match(content_hash):
            raise HTTPException(status_code=400, detail="Invalid content hash")
        with get_conn() as conn:
            if _protected_scan_table_exists(conn):
                row = conn.execute(
                    """
                    SELECT i.mime, i.blob_path
                      FROM images i
                     WHERE i.content_hash = ? AND i.blob_path IS NOT NULL
                       AND NOT EXISTS (
                           SELECT 1
                             FROM page_images pi
                             JOIN pages p ON p.id = pi.page_id
                             JOIN protected_scans ps ON ps.scan_id = p.scan_id
                            WHERE pi.image_id = i.id
                       )
                    """,
                    (content_hash,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT mime, blob_path FROM images "
                    "WHERE content_hash = ? AND blob_path IS NOT NULL",
                    (content_hash,),
                ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Blob not found")
        full = blob_store.path_for(row["blob_path"]).resolve()
        try:
            full.relative_to(blob_store.root.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Path outside blob root") from exc
        if not full.exists():
            raise HTTPException(status_code=404, detail="Blob file missing")
        return FileResponse(full, media_type=row["mime"] or "application/octet-stream")

    return app


def _sweep_stale_running_scans(db_path: Path) -> int:
    """Mark scans left in 'running' as 'interrupted' on server boot.

    A 'running' scan in the DB but no live asyncio task is always stale
    (the task died with the previous process). Returns the number of
    rows updated.
    """
    conn = connect(db_path)
    try:
        # A protected browser session only exists in its local companion, so a
        # server restart can never safely resume it.  Preserve the redacted
        # report metadata but require a new manual sign-in.
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(
                """
                UPDATE protected_scans
                   SET protection_status = CASE
                           WHEN protection_status IN ('awaiting_authentication', 'running')
                           THEN 'interrupted' ELSE protection_status END,
                       run_lease_id = NULL, run_lease_expires_at = NULL,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE run_lease_id IS NOT NULL OR protection_status = 'running'
                """
            )
        cur = conn.execute(
            "UPDATE scans SET status = 'interrupted', "
            "finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP) "
            "WHERE status = 'running'"
        )
        swept = int(cur.rowcount or 0)
        if swept:
            log.info("web.sweep_stale_scans", count=swept)
        return swept
    finally:
        conn.close()


def _resolve_protected_vault(
    settings: Settings, injected: ProtectedVault | None
) -> ProtectedVault | None:
    """Resolve an explicit production vault or an opt-in local dev adapter.

    Protected routes intentionally do not invent a key from the access-token
    or proxy HMAC secret. Production may inject a U-M KMS-backed vault in an
    embedding process or configure its reviewed vault factory; local
    development must explicitly opt into a separate development seed.
    """
    if injected is not None:
        return injected
    configured = resolve_configured_protected_vault(settings)
    if configured is not None:
        return configured
    if not settings.protected_allow_local_kms:
        return None
    seed = settings.protected_local_kms_seed.get_secret_value().encode("utf-8")
    if not seed:
        return None
    return ProtectedVault(
        DeterministicLocalKms(seed, key_id=f"local-dev:{settings.protected_kms_key_id}")
    )


_SCAN_ROUTE_RE = re.compile(r"^/api/scans/(?P<identifier>[^/]+)(?:/|$)")
_FINDING_ROUTE_RE = re.compile(
    r"^/api/(?P<kind>findings|a11y-findings)/(?P<identifier>[^/]+)(?:/|$)"
)
_CANONICAL_POSITIVE_IDENTIFIER_RE = re.compile(r"^[1-9][0-9]*$")


def _protected_scan_id_for_request(path: str) -> int | None:
    match = _SCAN_ROUTE_RE.match(path)
    if match is None:
        return None
    identifier = match.group("identifier")
    return int(identifier) if _is_canonical_positive_identifier(identifier) else None


def _is_protected_request_path(path: str, db_path: Path) -> bool:
    """Return whether a request can carry protected input or report data.

    The dedicated routes are protected before a scan record exists (for
    example draft creation and companion enrollment). Legacy scan/finding
    routes are protected only when their resolved record belongs to the
    protected workflow. Keeping this decision in one helper prevents cache,
    validation, and body-size boundaries from drifting apart.
    """

    if path.startswith(("/api/protected-scans", "/api/agents")):
        return True
    if _has_noncanonical_legacy_identifier(path):
        # The access middleware rejects this before FastAPI can permissively
        # coerce it to an integer. Mark it protected here as well so its fixed
        # error response is never cached and its body is bounded before route
        # dispatch.
        return True
    scan_id = _protected_scan_id_for_request(path)
    if scan_id is None:
        scan_id = _protected_finding_scan_id(path, db_path)
    return scan_id is not None and _protected_scan_owner(db_path, scan_id) is not None


def _protected_finding_scan_id(path: str, db_path: Path) -> int | None:
    """Resolve a direct finding route to its owning scan without leaking it."""
    match = _FINDING_ROUTE_RE.match(path)
    if match is None:
        return None
    identifier = match.group("identifier")
    # ``bulk-status`` is a named collection route, not a malformed finding
    # ID. It is separately guarded from its JSON body before mutation.
    if identifier == "bulk-status" or not _is_canonical_positive_identifier(identifier):
        return None
    finding_id = int(identifier)
    table = "a11y" if match.group("kind") == "a11y-findings" else "image"
    query = (
        "SELECT scan_id FROM page_a11y_findings WHERE id = ?"
        if table == "a11y"
        else "SELECT scan_id FROM findings WHERE id = ?"
    )
    try:
        conn = connect(db_path)
        try:
            row = conn.execute(query, (finding_id,)).fetchone()
            return int(row["scan_id"]) if row is not None else None
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None


def _is_canonical_positive_identifier(value: str) -> bool:
    """Return whether a route identifier has Axcess's one accepted spelling."""

    return _CANONICAL_POSITIVE_IDENTIFIER_RE.fullmatch(value) is not None


def _has_noncanonical_legacy_identifier(path: str) -> bool:
    """Identify a legacy ID route that must never reach Pydantic coercion.

    Starlette's ``:int`` route converters protect registered endpoints, while
    this guard runs even earlier and covers all raw decoded spellings such as
    ``+7``, ``01``, ``1_0``, and whitespace-padded IDs.  The named collection
    bulk-status routes are intentionally excluded and have their own
    database-backed protected-report barrier.
    """

    scan_match = _SCAN_ROUTE_RE.match(path)
    if scan_match is not None:
        return not _is_canonical_positive_identifier(scan_match.group("identifier"))
    finding_match = _FINDING_ROUTE_RE.match(path)
    if finding_match is None:
        return False
    identifier = finding_match.group("identifier")
    if identifier == "bulk-status":
        return False
    return not _is_canonical_positive_identifier(identifier)


def _protected_scan_owner(db_path: Path, scan_id: int) -> str | None:
    """Return the narrow single-expert ACL subject for a protected scan."""

    try:
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT authorized_by FROM protected_scans WHERE scan_id = ?", (scan_id,)
            ).fetchone()
            return str(row["authorized_by"]) if row is not None else None
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None


def _require_protected_bulk_access(
    conn: sqlite3.Connection,
    request: Request,
    settings: Settings,
    finding_ids: list[int],
    *,
    table: Literal["findings", "page_a11y_findings"],
) -> None:
    """Require proxy identity when a bulk update includes protected evidence.

    Direct finding routes are covered by the path middleware. Bulk routes do
    not reveal an ID in their path, so they need this database-backed guard
    before their repository mutation. ``table`` is a closed literal rather
    than caller-supplied SQL.
    """
    if not finding_ids:
        return
    # Protected scanning is an optional, later migration. Public finding
    # triage must remain usable while an existing installation is upgraded
    # from the pre-protected schema; there cannot be a protected row to guard
    # when the owning table does not exist yet.
    if not _protected_scan_table_exists(conn):
        return
    ids_json = json.dumps(finding_ids)
    if table == "findings":
        query = """
            SELECT DISTINCT ps.authorized_by
              FROM findings f
              JOIN protected_scans ps ON ps.scan_id = f.scan_id
             WHERE f.id IN (SELECT value FROM json_each(?))
        """
    else:
        query = """
            SELECT DISTINCT ps.authorized_by
              FROM page_a11y_findings f
              JOIN protected_scans ps ON ps.scan_id = f.scan_id
             WHERE f.id IN (SELECT value FROM json_each(?))
        """
    rows = conn.execute(query, (ids_json,)).fetchall()
    if rows:
        identity = require_protected_identity(request, settings)
        for row in rows:
            require_protected_report_owner(identity, authorized_by=str(row["authorized_by"]))
        require_same_origin(request, settings)


def _protected_summary(record: Any) -> dict[str, Any]:
    """Return the non-sensitive protection state embedded in scan detail."""
    return {
        "mode": "protected",
        "status": record.protection_status.value,
        "environment": record.environment.value,
        "data_classification": record.data_classification.value,
        "evidence_available": bool(record.is_evidence_available),
        "cleanup_at": _to_iso_string(record.cleanup_at),
    }


def _protected_scan_table_exists(conn: sqlite3.Connection) -> bool:
    """Return whether the optional protected-scan schema has been installed.

    Protected scanning arrived after the public report workbench. Deployments
    can briefly run new application code against a database that is still at
    migration 0010 (for example, an auto-reloading development server while
    ``make migrate`` is being run). Public report APIs must not turn that
    expected upgrade window into a dashboard-wide 500 response.
    """

    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'protected_scans'"
    ).fetchone()
    return row is not None


def _get_protected_scan_compat(conn: sqlite3.Connection, *, scan_id: int) -> Any | None:
    """Read protected metadata without making it mandatory for public scans.

    Absence of the table means the optional feature has never been installed,
    so every existing scan is necessarily public. A *partially* migrated
    protected schema is different: fail closed with an actionable 503 instead
    of either exposing a protected row or leaking SQLite's schema error.
    """

    if not _protected_scan_table_exists(conn):
        return None
    # A deployment interrupted between protected migrations can still serve
    # all public reports. Avoid selecting columns introduced by later
    # protected migrations unless this exact scan is actually protected.
    protected_row = conn.execute(
        "SELECT 1 FROM protected_scans WHERE scan_id = ?", (scan_id,)
    ).fetchone()
    if protected_row is None:
        return None
    try:
        return get_protected_scan(conn, scan_id=scan_id)
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        if "no such column" in message or "no such table" in message:
            raise HTTPException(
                status_code=503,
                detail="Database migrations are incomplete. Run `make migrate` and retry.",
            ) from exc
        raise


def _deny_legacy_protected_review(conn: sqlite3.Connection, scan_id: int) -> None:
    """Keep free-text expert-review tables out of protected scan storage.

    ``evaluation_reports`` and ``manual_check_evidence`` are intentionally
    plaintext tables for public reports.  A proxy identity is necessary but
    not sufficient to put protected page details in them.  Protected reports
    use their own outcome-only manual-check API and reviewed encrypted
    artifacts instead.
    """
    if _get_protected_scan_compat(conn, scan_id=scan_id) is not None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Protected reports do not use the legacy free-text evaluation or "
                "manual-evidence workflow."
            ),
        )


def _scan_row_to_summary(scan: Any) -> dict[str, Any]:
    """Coerce a sqlite3.Row or dict into the ScanSummary JSON shape."""
    row = dict(scan) if not isinstance(scan, dict) else scan
    return {
        "id": int(row["id"]),
        "seed_url": str(row["seed_url"]),
        "status": str(row["status"]),
        "page_count": int(row.get("page_count") or 0),
        "finding_count": int(row.get("finding_count") or 0),
        "started_at": _to_iso_string(row.get("started_at")),
        "finished_at": _to_iso_string(row.get("finished_at")),
    }


def _to_iso_string(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _validate_seed_url(url: str) -> str | None:
    """Return an error message if ``url`` is unsuitable as a seed, else ``None``."""
    url = (url or "").strip()
    if not url:
        return "Seed URL is required."
    try:
        parts = urlsplit(url)
    except ValueError:
        return "Seed URL is not a valid URL."
    if parts.scheme not in ("http", "https"):
        return "Seed URL must start with http:// or https://."
    if not parts.hostname:
        return "Seed URL is missing a host."
    return None


def _build_crawl_config(form: dict[str, Any], settings: Settings) -> CrawlConfig:
    scan_engine = str(form.get("scan_engine") or "").lower()
    if scan_engine not in {"axe", "alfa", "both"}:
        # Legacy non-browser callers retain the original axe-default behavior.
        scan_engine = "axe"
    return CrawlConfig(
        seed_url=str(form["url"]).strip(),
        max_pages=int(form["max_pages"]),
        max_depth=int(form["max_depth"]),
        rps=float(form["rps"]),
        workers=int(form["workers"]),
        allow_subdomains=bool(form["include_subdomain"]),
        whole_host=bool(form.get("whole_host")),
        ignore_robots=bool(form["ignore_robots"]),
        user_agent=settings.user_agent,
        request_timeout_s=settings.request_timeout_s,
        ocr_enabled=not bool(form["skip_ocr"]),
        ocr_language=settings.ocr_language,
        ocr_max_workers=settings.ocr_max_workers,
        ocr_min_confidence=settings.ocr_min_confidence,
        ocr_min_word_count=settings.ocr_min_word_count,
        vlm_enabled=not bool(form["skip_vlm"]),
        vlm_model=settings.vlm_model,
        vlm_base_url=settings.ollama_base_url,
        vlm_prompt_name=settings.vlm_prompt_name,
        vlm_concurrency=settings.vlm_concurrency,
        # Render-every-page is the default (audit mode). `static_only`
        # is the opt-out fast path — HTML checkboxes can't post
        # "unchecked", so the form field is the inversion.
        js_eager=not bool(form.get("static_only")),
        browser_headless=not bool(form.get("show_browser")),
        axe_enabled=scan_engine in {"axe", "both"},
        axe_level=str(form.get("axe_level", "AA")).upper(),
        alfa_enabled=scan_engine in {"alfa", "both"},
        # Per-criterion semantic analyzers (Phase 9+). Opt-out like axe;
        # the wiring to the runner lands in Phase 9.1 — for now this
        # just plumbs the flag through so the web form has the same
        # surface as the CLI's `--skip-semantic`.
        semantic_enabled=not bool(form.get("skip_semantic")),
        keyboard_probe_enabled=not bool(form.get("skip_keyboard")),
        responsive_checks_enabled=not bool(form.get("skip_responsive")),
        focus_checks_enabled=not bool(form.get("skip_focus")),
        visual_checks_enabled=not bool(form.get("skip_visual")),
    )


def _prepare_scan_row(db_path: Path, config: CrawlConfig) -> int:
    """Create the scan row up front so the UI can redirect immediately.

    ``run_crawl`` canonicalizes directory-like seeds before discovering its
    row (for example, ``/about`` becomes ``/about/``).  Store and match that
    exact canonical value here as well.  Otherwise the browser can finish a
    crawl under a second scan ID while the progress screen remains attached
    to the original, permanently ``running`` row.
    """
    from audit.crawler.orchestrator import config_json_for_scan

    seed_url = _canonical_scan_seed(config.seed_url)
    conn = connect(db_path)
    try:
        if _protected_scan_table_exists(conn):
            existing = conn.execute(
                "SELECT id FROM scans "
                "WHERE seed_url = ? AND status IN ('running', 'interrupted') "
                "AND NOT EXISTS ("
                "SELECT 1 FROM protected_scans p WHERE p.scan_id = scans.id"
                ") ORDER BY id DESC LIMIT 1",
                (seed_url,),
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM scans "
                "WHERE seed_url = ? AND status IN ('running', 'interrupted') "
                "ORDER BY id DESC LIMIT 1",
                (seed_url,),
            ).fetchone()
        if existing is not None:
            scan_id = int(existing["id"])
            conn.execute(
                "UPDATE scans SET status = 'running', finished_at = NULL, "
                "failure_reason = NULL, config_json = ? WHERE id = ?",
                (config_json_for_scan(config), scan_id),
            )
            return scan_id
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', ?)",
            (seed_url, config_json_for_scan(config)),
        )
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


async def _run_background_crawl(db_path: Path, config: CrawlConfig) -> None:
    """Open a private DB connection and run the crawl. Never raises."""
    log.info("web.crawl_start", seed=config.seed_url)
    conn = connect(db_path)
    try:
        await run_crawl(conn, config)
    except Exception as exc:
        # A failure can happen before the durable queue is seeded (for
        # example while starting Playwright or an optional analyzer).  Do not
        # leave the up-front scan row looking "running" forever: that makes a
        # failed startup indistinguishable from a very slow first page.
        log.warning("web.crawl_failed", seed=config.seed_url, error=str(exc))
        conn.execute(
            "UPDATE scans SET status = 'failed', finished_at = CURRENT_TIMESTAMP, "
            "failure_reason = ? "
            "WHERE id = ("
            "SELECT id FROM scans WHERE seed_url = ? AND status = 'running' "
            "ORDER BY id DESC LIMIT 1"
            ")",
            (str(exc)[:1000], _canonical_scan_seed(config.seed_url)),
        )
    finally:
        conn.close()


def _canonical_scan_seed(seed_url: str) -> str:
    """Return the same seed identity used by the crawler orchestrator."""

    return url_policy.normalize(url_policy.normalize_seed_url(seed_url))


async def _run_local_login_background(
    db_path: Path,
    blob_dir: Path,
    config: CrawlConfig,
    run: _LocalLoginRun,
) -> None:
    """Own one visible sign-in and reuse its context for the standard report.

    Session material exists only inside ``ManualAuthenticationSession``. The
    user-facing report still stores the rendered accessibility evidence in the
    local Axcess database, but never a password, OTP, cookie, authorization
    header, browser profile, or reusable storage-state object.
    """

    conn: sqlite3.Connection | None = None
    try:
        run.status = "opening_browser"
        await run.session.start()
        run.status = "awaiting_authentication"
        await run.confirmation.wait()
        run.status = "verifying_authentication"
        run.session.verify_authenticated_target()
        run.browser_backgrounded = await run.session.minimize_for_background_scan()
        await run.session.discard_manual_auth_page()

        # The orchestrator normally constructs these around a fresh browser.
        # For an authenticated scan they must be attached before we inject the
        # already-signed-in fetcher, otherwise the injected context would crawl
        # successfully but silently skip its DOM and interaction checks.
        fetcher = run.session.create_shared_js_fetcher(
            axe_analyzer=(
                AxeAnalyzer.from_bundled(suppress_diagnostics=True) if config.axe_enabled else None
            ),
            axe_level=config.axe_level,  # type: ignore[arg-type]
            keyboard_probe=(
                KeyboardProbe(suppress_diagnostics=True) if config.keyboard_probe_enabled else None
            ),
            responsive_probe=(
                ResponsiveProbe(suppress_diagnostics=True)
                if config.responsive_checks_enabled
                else None
            ),
            focus_probe=FocusProbe(suppress_diagnostics=True),
            capture_screenshots=False,
        )
        run.status = "scanning"
        authenticated_alfa: _AuthenticatedAlfaRunner | None = None
        if config.alfa_enabled:
            authenticated_alfa = _AuthenticatedAlfaRunner(
                run.session,
                AlfaAnalyzer(
                    user_agent=config.user_agent,
                    timeout_s=config.alfa_timeout_s,
                    concurrency=1,
                    chromium_path=await chromium_executable_path(),
                ),
            )
        image_downloader = (
            run.session.create_authenticated_image_downloader(BlobStore(blob_dir))
            if config.image_extraction_enabled
            else None
        )
        conn = connect(db_path)
        # This client is used only for the optional loopback model provider;
        # browser_only prevents it from fetching protected documents.
        async with httpx.AsyncClient(trust_env=False) as local_client:
            summary = await run_crawl(
                conn,
                config,
                http_client=local_client,
                js_fetcher=fetcher,
                image_downloader=image_downloader,
                alfa_analyzer=authenticated_alfa,
            )
        run.status, run.error = _local_login_completion(summary)
        # run_crawl historically records an exhausted queue as completed even
        # when every page job failed.  That is useful for general best-effort
        # crawls, but a login handoff with zero captured pages is not a report.
        # Override the row so the UI explains the failure instead of opening a
        # misleading empty report.
        if run.status != summary.status:
            _finish_local_login_scan(db_path, run.scan_id, run.status)
    except asyncio.CancelledError:
        run.status = "interrupted"
        _finish_local_login_scan(db_path, run.scan_id, "interrupted")
        raise
    except ManualAuthenticationError:
        run.status = "authentication_required"
        run.error = (
            "Sign-in did not finish on the approved website. Return to the visible "
            "browser, or add every exact sign-in origin and start again."
        )
        _finish_local_login_scan(db_path, run.scan_id, "interrupted")
    except Exception:
        # Do not surface a browser/target exception: it can contain a private
        # URL, response detail, or text from the authenticated application.
        run.status = "failed"
        run.error = (
            "The local login scan could not continue. Check the approved sign-in "
            "origins and make sure Playwright Chromium is installed."
        )
        _finish_local_login_scan(db_path, run.scan_id, "failed")
        log.warning("web.local_login_scan_failed", scan_id=run.scan_id)
    finally:
        if conn is not None:
            conn.close()
        await run.session.close()


class _AuthenticatedAlfaRunner:
    """Give the crawler Alfa results from the one live signed-in session."""

    def __init__(
        self,
        session: ManualAuthenticationSession,
        analyzer: AlfaAnalyzer,
    ) -> None:
        self._session = session
        self._analyzer = analyzer

    async def run(self, url: str, *, level: str) -> AlfaResult:
        return await self._session.run_alfa(self._analyzer, url, level=level)


def _local_login_completion(summary: CrawlSummary) -> tuple[str, str | None]:
    """Translate a crawl result into an honest manual-login UI outcome."""

    if summary.pages_fetched == 0:
        return (
            "failed",
            "Sign-in succeeded, but Axcess could not scan an application page. "
            "Start a new login scan; if it happens again, check the server log.",
        )
    if summary.status in {"completed", "failed", "interrupted"}:
        return summary.status, None
    return "failed", "The login scan ended before Axcess could finish the report."


def _local_login_ollama_url(value: str) -> str | None:
    """Return a literal loopback Ollama URL suitable for protected content."""

    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return None
    if host.lower() == "localhost":
        literal_host = "127.0.0.1"
    else:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return None
        if not address.is_loopback:
            return None
        literal_host = f"[{address}]" if address.version == 6 else str(address)
    authority = f"{literal_host}:{port}" if port is not None else literal_host
    return parsed._replace(netloc=authority, path="").geturl()


def _finish_local_login_scan(db_path: Path, scan_id: int, status: str) -> None:
    """Finish a local-login row without retaining target/browser diagnostics."""

    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE scans SET status = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, scan_id),
        )
    finally:
        conn.close()


def _local_login_capability(request: Request) -> tuple[bool, str | None]:
    """Expose direct login only to a browser connected over loopback."""

    try:
        _require_local_login_request(request, mutation=False)
    except HTTPException:
        return (
            False,
            "Direct login scanning is available only from this Axcess computer.",
        )
    return True, None


def _require_local_login_request(request: Request, *, mutation: bool) -> None:
    """Reject LAN/proxy use of the intentionally certificate-free local flow."""

    client_host = request.client.host if request.client is not None else ""
    host_header = request.headers.get("host", "")
    host_name = _authority_hostname(host_header)
    if not (_is_loopback_host(client_host) and _is_loopback_host(host_name)):
        raise HTTPException(
            status_code=403,
            detail="Direct login scanning is restricted to this Axcess computer.",
        )
    if not mutation:
        return
    origin = request.headers.get("origin", "")
    try:
        parsed_origin = urlsplit(origin)
        origin_host = parsed_origin.hostname or ""
        origin_authority = parsed_origin.netloc.lower()
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Local request origin is invalid.") from exc
    if (
        parsed_origin.scheme not in {"http", "https"}
        or not _is_loopback_host(origin_host)
        or origin_authority != host_header.lower()
    ):
        raise HTTPException(
            status_code=403,
            detail="Direct login scanning requires the same local Axcess origin.",
        )


def _authority_hostname(authority: str) -> str:
    try:
        return urlsplit(f"//{authority}").hostname or ""
    except ValueError:
        return ""


def _is_loopback_host(host: str) -> bool:
    candidate = host.strip().strip("[]").lower()
    if candidate == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def _scan_progress(conn: sqlite3.Connection, scan_id: int) -> dict[str, Any]:
    """Live, factual snapshot for the Scan -> Progress experience.

    The crawler cannot know its final page total while it is still following
    links, so this deliberately exposes queue/state counts instead of a made-up
    percentage.  ``stage`` is derived from durable work state: it is safe to
    announce to assistive technology and remains truthful after a page reload.
    """
    jobs = conn.execute(
        "SELECT state, COUNT(*) AS n FROM jobs "
        "WHERE json_extract(payload_json, '$.scan_id') = ? GROUP BY state",
        (scan_id,),
    ).fetchall()
    job_counts = {r["state"]: int(r["n"]) for r in jobs}
    pending = int(job_counts.get("pending", 0))
    leased = int(job_counts.get("leased", 0))
    completed = int(job_counts.get("completed", 0))
    failed = int(job_counts.get("failed", 0))
    discovered = sum(job_counts.values())
    recent = conn.execute(
        "SELECT url_normalized, status_code, render_mode, fetched_at "
        "FROM pages WHERE scan_id = ? ORDER BY id DESC LIMIT 5",
        (scan_id,),
    ).fetchall()
    # Currently-leased jobs: which URLs are in a worker right now. Useful so
    # the UI can show *what* is in flight, not just the count. Scoped to this
    # scan via json_extract on payload_json so cross-scan jobs don't leak.
    #
    # ``CAST(lease_until AS TEXT)`` defeats SQLite's PARSE_DECLTYPES converter:
    # the queue writes ISO-8601 strings via ``_iso(dt)`` (``2026-04-27T16:48:53
    # +00:00``), but the default ``convert_timestamp`` expects space-separated
    # ``YYYY-MM-DD HH:MM:SS`` and raises ``ValueError`` on the ``T`` form. We
    # don't need the parsed datetime — ``_to_iso_string`` will pass the raw
    # string through unchanged. (We can't use the ``[text]`` colname alias
    # trick because schema.py only opens connections with PARSE_DECLTYPES,
    # not PARSE_COLNAMES.)
    in_flight = conn.execute(
        "SELECT json_extract(payload_json, '$.url') AS url, "
        "       json_extract(payload_json, '$.depth') AS depth, "
        "       attempts, "
        "       CAST(lease_until AS TEXT) AS lease_until "
        "FROM jobs WHERE state = 'leased' "
        "AND json_extract(payload_json, '$.scan_id') = ? "
        "ORDER BY id LIMIT 10",
        (scan_id,),
    ).fetchall()
    image_count = conn.execute(
        "SELECT COUNT(DISTINCT pi.image_id) AS n FROM page_images pi "
        "JOIN pages p ON p.id = pi.page_id WHERE p.scan_id = ?",
        (scan_id,),
    ).fetchone()["n"]
    render_counts = conn.execute(
        "SELECT render_mode, COUNT(*) AS n FROM pages WHERE scan_id = ? GROUP BY render_mode",
        (scan_id,),
    ).fetchall()
    rendered_by_mode = {str(r["render_mode"] or "unknown"): int(r["n"]) for r in render_counts}
    timing = conn.execute(
        "SELECT CAST(MAX(0, (julianday('now') - julianday(MIN(fetched_at))) * 86400) "
        "AS INTEGER) AS observed_seconds FROM pages WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    observed_seconds = (
        int(timing["observed_seconds"])
        if timing is not None and timing["observed_seconds"] is not None
        else None
    )

    if discovered == 0:
        stage = "starting"
    elif pending == 0 and leased == 0:
        # The crawl queue is settled but the scan row is still running: final
        # synthesis and report materialization are the only remaining work.
        stage = "preparing_report"
    else:
        stage = "scanning"
    eta = _estimate_scan_eta(
        stage=stage,
        completed=completed,
        failed=failed,
        pending=pending,
        leased=leased,
        observed_seconds=observed_seconds,
    )
    return {
        "stage": stage,
        "discovered": int(discovered),
        "completed": completed,
        "pending": pending,
        "leased": leased,
        "failed": failed,
        "images_seen": int(image_count),
        "rendered_pages": int(rendered_by_mode.get("js", 0)),
        "static_pages": int(rendered_by_mode.get("static", 0)),
        "eta": eta,
        "recent_pages": [
            {
                "url_normalized": r["url_normalized"],
                "status_code": r["status_code"],
                "render_mode": r["render_mode"],
                # sqlite returns this as a datetime under PARSE_DECLTYPES;
                # JSONResponse can't serialize raw datetimes — coerce here.
                "fetched_at": _to_iso_string(r["fetched_at"]),
            }
            for r in recent
        ],
        "in_flight_pages": [
            {
                "url": str(r["url"]) if r["url"] is not None else "",
                "depth": int(r["depth"]) if r["depth"] is not None else 0,
                "attempts": int(r["attempts"] or 0),
                "lease_until": _to_iso_string(r["lease_until"]),
            }
            for r in in_flight
        ],
    }


def _estimate_scan_eta(
    *,
    stage: str,
    completed: int,
    failed: int,
    pending: int,
    leased: int,
    observed_seconds: int | None,
) -> dict[str, Any]:
    """Return a conservative ETA range from observed completed-page pace.

    Crawl scope can expand whenever a page reveals more links, so an exact
    completion time would be misleading. The range covers only work currently
    discovered and widens observed pace substantially to account for slower
    pages and final synthesis. Login time is excluded because measurement
    starts at the first stored page.
    """

    if stage == "preparing_report":
        return {
            "state": "finalizing",
            "min_seconds": 5,
            "max_seconds": 30,
            "based_on_pages": completed,
        }
    remaining = pending + leased
    settled = completed + failed
    if remaining <= 0:
        return {
            "state": "estimating",
            "min_seconds": None,
            "max_seconds": None,
            "based_on_pages": completed,
        }
    if completed < 2 or observed_seconds is None or observed_seconds <= 0:
        return {
            "state": "estimating",
            "min_seconds": None,
            "max_seconds": None,
            "based_on_pages": completed,
        }

    observed_intervals = max(1, completed - 1)
    seconds_per_page = max(0.5, observed_seconds / observed_intervals)
    baseline = remaining * seconds_per_page
    # A deliberately broad interval: newly discovered pages can still extend
    # the run, and axe/Alfa/OCR costs vary with page complexity.
    eta_min = max(5, round(baseline * 0.65))
    eta_max = max(eta_min + 10, round(baseline * 1.75 + 15))
    return {
        "state": "range",
        "min_seconds": eta_min,
        "max_seconds": eta_max,
        "based_on_pages": settled,
    }


def _detect_blocked_scan(
    conn: sqlite3.Connection, scan_id: int, scan: dict[str, Any]
) -> dict[str, Any] | None:
    """Return a warning payload when a completed crawl looks like it was blocked.

    Two heuristics we trust without false-positiving:

      * The seed URL is present in ``pages`` and its ``status_code`` is not 2xx.
        That's the classic "crawler hit a WAF challenge / 403 / login wall"
        pattern — the crawl completed but found no real content.
      * ``page_count == 1`` AND that page is non-2xx.

    Returns ``{'status_code': int | None, 'title': str | None, 'seed_url': str}``
    when a warning should be shown, or ``None`` to render normally.
    """
    if scan.get("status") != "completed":
        return None
    page_count = int(scan.get("page_count") or 0)
    if page_count == 0:
        return None
    seed = str(scan["seed_url"])
    row = conn.execute(
        "SELECT status_code, title FROM pages WHERE scan_id = ? AND url_normalized = ? LIMIT 1",
        (scan_id, seed),
    ).fetchone()
    if row is None:
        return None
    code = row["status_code"]
    if code is None:
        return None
    if 200 <= int(code) < 300:
        return None
    # Non-2xx seed: show warning. Include the scan in the signal so the UI can
    # suggest re-running with --use-js / "Use real browser" when relevant.
    return {
        "status_code": int(code),
        "title": row["title"],
        "seed_url": seed,
        "page_count": page_count,
    }


def _methods_used(scan: dict[str, Any], coverage: dict[str, int]) -> list[dict[str, Any]]:
    """Describe configured methods and the evidence that they actually ran.

    Selection and completion are deliberately separate. A configured local
    model can be unavailable, and a browser-only probe cannot evaluate a page
    that fell back to static HTML. Older reports without durable method
    counters are labeled unknown instead of having coverage inferred from a
    zero-finding result.
    """
    import json as _json

    try:
        cfg = _json.loads(scan.get("config_json") or "{}")
    except (TypeError, ValueError):
        cfg = {}
    axe_ran_counters = int(scan.get("axe_pages_scanned") or 0) > 0
    alfa_ran_counters = int(scan.get("alfa_pages_scanned") or 0) > 0
    coverage_version = int(cfg.get("method_coverage_version") or 0)
    scan_status = str(scan.get("status") or "")
    page_count = int(scan.get("page_count") or 0)

    def flag(name: str, default: bool = True) -> bool:
        value = cfg.get(name)
        return bool(value) if value is not None else default

    rendered = flag("js_eager")
    method_specs = [
        {
            "key": "rendered",
            "label": "Browser rendering",
            "enabled": rendered or axe_ran_counters,
            "checked_count": coverage["rendered_pages"],
            "total_count": page_count,
            "unit": "page",
            "verb": "rendered",
            "description": (
                "Loads JavaScript in a real browser so dynamic content and "
                "browser-based checks can be evaluated."
            ),
            "caveat": "A rendered page is not, by itself, an accessibility pass.",
        },
        {
            "key": "axe",
            "label": f"axe-core ({cfg.get('axe_level', 'AA')})",
            "enabled": (flag("axe_enabled") and rendered) or axe_ran_counters,
            "checked_count": int(scan.get("axe_pages_scanned") or 0),
            "total_count": coverage["rendered_pages"],
            "unit": "page",
            "verb": "checked",
            "description": (
                "Runs deterministic DOM rules for automatically testable WCAG "
                "requirements at the selected level."
            ),
            "caveat": "No axe violation does not mean the page conforms to WCAG.",
        },
        {
            "key": "alfa",
            "label": "Siteimprove Alfa — ACT (Accessibility Conformance Testing)",
            "enabled": flag("alfa_enabled", default=False) or alfa_ran_counters,
            "checked_count": int(scan.get("alfa_pages_scanned") or 0),
            "total_count": page_count,
            "unit": "page",
            "verb": "checked",
            "description": (
                "Checks specific accessibility conditions using standardized ACT "
                "rules. Each rule defines what is tested and can return pass, "
                "fail, or cannot-tell."
            ),
            "caveat": (
                "A failed rule is evidence about that condition—not proof that the "
                "whole page or site fails WCAG. Cannot-tell requires expert review."
            ),
        },
        {
            "key": "image",
            "label": "Image-of-text (OCR+VLM)",
            "enabled": flag("ocr_enabled") and flag("vlm_enabled"),
            "checked_count": coverage["analyzed_images"],
            "total_count": coverage["discovered_images"],
            "unit": "image",
            "verb": "analyzed",
            "description": (
                "Finds images containing visible text, uses OCR to read it, and "
                "uses a local vision model to create expert-review leads."
            ),
            "caveat": "OCR and vision-model judgments require human confirmation.",
        },
        {
            "key": "semantic",
            "label": "Semantic review (local AI)",
            "enabled": flag("semantic_enabled"),
            "checked_count": int(scan.get("semantic_pages_analyzed") or 0),
            "total_count": page_count,
            "unit": "page",
            "verb": "reviewed",
            "coverage_known": coverage_version >= 1,
            "description": (
                "Reviews page context that rule engines cannot fully judge, "
                "including link purpose, descriptive headings and labels, form "
                "instructions, and prerecorded-audio transcript cues."
            ),
            "caveat": "Local-AI results are leads, never conformance verdicts.",
        },
        {
            "key": "keyboard",
            "label": "Keyboard probe",
            # Pre-flip scans never ran it (old default False).
            "enabled": flag("keyboard_probe_enabled", default=False) and rendered,
            "checked_count": int(scan.get("keyboard_pages_probed") or 0),
            "total_count": coverage["rendered_pages"],
            "unit": "page",
            "verb": "checked",
            "coverage_known": coverage_version >= 1,
            "description": (
                "Walks focus with Tab and Shift+Tab and tests Escape behavior to "
                "find repeated evidence that keyboard focus cannot leave a region."
            ),
            "caveat": "This conservative probe does not replace a full manual keyboard test.",
        },
        {
            "key": "responsive",
            "label": "Responsive & zoom probe",
            "enabled": flag("responsive_checks_enabled", default=False) and rendered,
            "checked_count": int(scan.get("responsive_pages_probed") or 0),
            "total_count": coverage["rendered_pages"],
            "unit": "page",
            "verb": "checked",
            "coverage_known": coverage_version >= 1,
            "description": (
                "Checks 320 CSS-pixel reflow, approximately 200% text zoom, and "
                "WCAG text-spacing overrides for clipping or lost content."
            ),
            "caveat": "An expert must confirm whether observed clipping is a barrier.",
        },
    ]

    for method in method_specs:
        method.setdefault("coverage_known", True)
        method.update(_method_result(method, scan_status=scan_status))
    return method_specs


def _method_result(method: dict[str, Any], *, scan_status: str) -> dict[str, str]:
    """Return an honest, plain-language state and count label for one method."""

    if not method["enabled"]:
        return {"state": "not_selected", "result": "Not selected"}
    if not method["coverage_known"]:
        return {
            "state": "coverage_unknown",
            "result": "Coverage not recorded for this older scan",
        }

    checked = int(method["checked_count"] or 0)
    total = int(method["total_count"] or 0)
    unit = str(method["unit"])
    verb = str(method["verb"])
    plural = unit if checked == 1 else f"{unit}s"

    if scan_status == "running":
        if checked == 0:
            return {"state": "waiting", "result": "Selected; waiting to run"}
        return {"state": "running", "result": f"{checked} {plural} {verb} so far"}

    if method["key"] == "image" and total == 0:
        return {"state": "checked", "result": "No images found to analyze"}
    if checked == 0:
        return {
            "state": "not_run",
            "result": f"Selected, but no completed {verb} work recorded",
        }
    if total > checked:
        total_plural = unit if total == 1 else f"{unit}s"
        return {
            "state": "partial",
            "result": f"{checked} of {total} {total_plural} {verb}",
        }
    return {"state": "checked", "result": f"{checked} {plural} {verb}"}


def _scan_method_coverage(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    """Return scan-scoped, non-inferred counts used by the method ledger."""

    pages = conn.execute(
        "SELECT COUNT(*) AS pages, "
        "SUM(CASE WHEN render_mode = 'js' THEN 1 ELSE 0 END) AS rendered "
        "FROM pages WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    images = conn.execute(
        "SELECT COUNT(DISTINCT pi.image_id) AS discovered, "
        "COUNT(DISTINCT CASE WHEN a.id IS NOT NULL THEN pi.image_id END) AS analyzed "
        "FROM page_images pi "
        "JOIN pages p ON p.id = pi.page_id "
        "LEFT JOIN analyses a ON a.image_id = pi.image_id "
        "WHERE p.scan_id = ?",
        (scan_id,),
    ).fetchone()
    return {
        "pages": int(pages["pages"] or 0),
        "rendered_pages": int(pages["rendered"] or 0),
        "discovered_images": int(images["discovered"] or 0),
        "analyzed_images": int(images["analyzed"] or 0),
    }


def _split_csv(value: str) -> list[str]:
    """Comma-separated query param to a clean list. Empty string → []."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _load_scan_or_404(conn: sqlite3.Connection, scan_id: int) -> dict[str, Any]:
    # ``SELECT *`` keeps public report browsing compatible while a newly added
    # optional coverage column is being migrated. Accessors below use ``get``
    # and label missing coverage as unknown rather than failing the report.
    row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return dict(row)


def _require_completed_scan(scan: dict[str, Any]) -> None:
    """Guard review writes: a live crawl cannot be a stable evaluation."""
    if scan["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail="Expert review can begin after this scan completes.",
        )


def _severity_breakdown(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT severity, COUNT(*) AS n FROM findings WHERE scan_id = ? GROUP BY severity",
        (scan_id,),
    ).fetchall()
    return {r["severity"]: int(r["n"]) for r in rows}


def _query_findings(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    filters: dict[str, str],
    page: int,
    size: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["f.scan_id = ?"]
    params: list[Any] = [scan_id]
    if filters["severity"]:
        clauses.append("f.severity = ?")
        params.append(filters["severity"])
    if filters["status"]:
        clauses.append("f.status = ?")
        params.append(filters["status"])
    if filters["classification"]:
        clauses.append("a.vlm_classification = ?")
        params.append(filters["classification"])
    if filters["q"]:
        clauses.append("(i.src_url_canonical LIKE ? OR a.ocr_text LIKE ? OR pi.alt_text LIKE ?)")
        like = f"%{filters['q']}%"
        params.extend([like, like, like])
    where = " AND ".join(clauses)

    count_sql = f"""
        SELECT COUNT(DISTINCT f.id) AS n
          FROM findings f
          JOIN images i ON i.id = f.image_id
          LEFT JOIN analyses a ON a.image_id = i.id
          LEFT JOIN page_images pi ON pi.image_id = i.id
         WHERE {where}
    """  # noqa: S608  # `where` built from a closed enum list, not user input
    total = int(conn.execute(count_sql, params).fetchone()["n"])
    offset = (page - 1) * size
    list_sql = f"""
        SELECT DISTINCT f.id, f.severity, f.priority_score, f.status,
               a.vlm_classification, a.ocr_text,
               i.src_url_canonical, i.content_hash, i.has_svg_text, i.mime,
               i.width, i.height
          FROM findings f
          JOIN images i ON i.id = f.image_id
          LEFT JOIN analyses a ON a.image_id = i.id
          LEFT JOIN page_images pi ON pi.image_id = i.id
         WHERE {where}
         ORDER BY f.priority_score DESC, f.id ASC
         LIMIT ? OFFSET ?
    """  # noqa: S608
    rows = conn.execute(list_sql, [*params, size, offset]).fetchall()
    findings: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        item["src_url_short"] = _short_url(item["src_url_canonical"])
        item["alt_adequacy"] = None
        # Pull a sample occurrence for scannable context on the card.
        sample = conn.execute(
            """
            SELECT pi.alt_text, p.url_normalized AS page_url
              FROM page_images pi
              JOIN pages p ON p.id = pi.page_id
             WHERE pi.image_id = ? AND p.scan_id = ?
             ORDER BY pi.above_fold DESC, pi.position ASC
             LIMIT 1
            """,
            (item.get("content_hash") and _image_id_for_hash(conn, item["content_hash"]), scan_id),
        ).fetchone()
        if sample is not None:
            item["sample_alt"] = sample["alt_text"]
            item["sample_page"] = sample["page_url"]
        else:
            item["sample_alt"] = None
            item["sample_page"] = None
        findings.append(item)
    return findings, total


def _image_id_for_hash(conn: sqlite3.Connection, content_hash: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM images WHERE content_hash = ? LIMIT 1", (content_hash,)
    ).fetchone()
    return int(row["id"]) if row is not None else None


def _pagination(*, page: int, size: int, total: int, filters: dict[str, str]) -> dict[str, Any]:
    total_pages = max(1, math.ceil(total / size))
    base = {k: v for k, v in filters.items() if v}
    prev_qs = urlencode({**base, "page": max(1, page - 1)})
    next_qs = urlencode({**base, "page": min(total_pages, page + 1)})
    return {
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "prev_qs": prev_qs,
        "next_qs": next_qs,
    }


def _short_url(url: str | None) -> str:
    if not url:
        return "—"
    if url.startswith("inline-svg://"):
        return "(inline svg)"
    match = re.match(r"^https?://[^/]+(/.*)?$", url)
    if match:
        return match.group(1) or "/"
    return url


# Module-level app instance so `uvicorn audit.web.server:app` works.
app = create_app()
