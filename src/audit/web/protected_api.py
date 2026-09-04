"""Browser and companion API for manually authenticated protected scans.

The routes in this module are intentionally separate from the public scan API:
they never accept credentials or browser state, require a signed identity for
human actions, and require mTLS assertions for companion actions.  The
companion owns the temporary Playwright session on the auditor's computer.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from audit import evaluation
from audit.config import Settings
from audit.crawler import url_policy
from audit.crawler.orchestrator import CrawlConfig, config_json_for_scan
from audit.protected.crypto import ProtectedVault
from audit.protected.egress import EgressViolation, ProtectedEgressPolicy
from audit.protected.export import ProtectedExportError, render_redacted_protected_report
from audit.protected.models import (
    AgentEnrollmentCreate,
    ProtectedPageIndex,
    ProtectedScanCreate,
    ProtectedScanStatus,
    ProtectedScopeFingerprints,
    ProtectedWorkSpec,
    normalize_exact_https_origin,
    scope_fingerprint_message,
    validate_certificate_fingerprint,
)
from audit.protected.repository import (
    AgentEnrollmentError,
    ProtectedDataError,
    acquire_protected_run_lease,
    claim_agent_enrollment,
    create_agent_enrollment,
    create_protected_scan,
    find_active_protected_scan_by_seed_locator,
    get_claimed_agent_enrollment,
    get_protected_scan,
    get_protected_scan_for_owner,
    get_protected_work_spec,
    heartbeat_protected_run_lease,
    interrupt_protected_scan,
    record_protected_audit_event,
    record_protected_page_index,
    recover_stale_protected_run_leases,
    set_protected_scan_status,
)
from audit.web.protected_auth import (
    ProtectedIdentity,
    protected_identity_context_fingerprint,
    require_agent_mtls,
    require_protected_identity,
    require_protected_report_owner,
    require_same_origin,
)


class ProtectedScanRequest(ProtectedScanCreate):
    """Public draft request; no field can carry a credential or session."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    seed_url: str = Field(min_length=12, max_length=2048)
    scan_engine: Literal["axe", "alfa", "both"] = "axe"
    max_pages: int = Field(default=100, ge=1, le=10_000)
    max_depth: int = Field(default=10, ge=1, le=20)
    rps: float = Field(default=1.0, ge=0.1, le=10.0)

    @field_validator("seed_url")
    @classmethod
    def no_query_or_userinfo_in_seed(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise ValueError("seed URL is invalid") from exc
        # Protected scans deliberately use a path-scoped seed.  Query strings
        # often carry identifiers or capability tokens and would need a
        # separate encrypted work-spec contract; do not normalize them into
        # the ordinary scans table.
        if parsed.query or parsed.fragment:
            raise ValueError("protected seed URLs cannot include a query or fragment")
        if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
            raise ValueError("protected seed URLs cannot include credentials")
        return value

    @model_validator(mode="after")
    def seed_must_be_a_target_origin(self) -> ProtectedScanRequest:
        try:
            parsed = urlsplit(self.seed_url)
            # Use exactly the same IDNA-aware canonicalizer as the persisted
            # allowlists.  Building this from ``parsed.hostname`` directly
            # would make a valid Unicode hostname disagree with its approved
            # punycode representation.
            origin = normalize_exact_https_origin(f"{parsed.scheme}://{parsed.netloc}")
        except ValueError as exc:
            raise ValueError("seed URL is invalid") from exc
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError("protected seed URL must use HTTPS and include a hostname")
        if origin not in self.approved_target_origins:
            raise ValueError("approved target origins must include the seed URL origin")
        return self


class AgentClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enrollment_id: str = Field(min_length=8, max_length=64)
    pairing_code: str = Field(min_length=16, max_length=256, repr=False)


class AgentEnrollmentRequest(BaseModel):
    """Browser-approved fingerprint for the one companion that may pair."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    certificate_fingerprint: str = Field(min_length=64, max_length=128)

    @field_validator("certificate_fingerprint")
    @classmethod
    def validate_certificate(cls, value: str) -> str:
        return validate_certificate_fingerprint(value)


class AgentEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=64)
    run_lease_id: str = Field(min_length=24, max_length=200, repr=False)
    status: ProtectedScanStatus | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    page_index: ProtectedPageIndex | None = None

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", value):
            raise ValueError("event_type must be a lowercase dotted identifier")
        return value

    @field_validator("details")
    @classmethod
    def validate_safe_event_details(
        cls, values: dict[str, str | int | float | bool | None]
    ) -> dict[str, str | int | float | bool | None]:
        # Generic agent-provided diagnostics become a plaintext side channel
        # for target URLs, selectors, OCR, and user data. Keep the companion
        # audit vocabulary closed: only two fixed operational limitations may
        # carry a bounded enum marker.
        if len(values) > 1:
            raise ValueError("agent event details are not allowed")
        return values

    @model_validator(mode="after")
    def keep_index_events_dedicated(self) -> AgentEventRequest:
        if self.page_index is not None and (
            self.event_type != "companion.page_indexed" or self.status is not None
        ):
            raise ValueError("a protected page index requires its dedicated event type")
        if self.status is not None:
            expected_event = _STATUS_EVENT_TYPES[self.status]
            if self.event_type != expected_event:
                raise ValueError("protected status requires its dedicated companion event")
        allowed_details: dict[str, dict[str, str]] = {
            "companion.alfa_unavailable": {"page": "omitted"},
            "companion.local_ai_disabled": {"reason": "loopback_required"},
        }
        if self.details != allowed_details.get(self.event_type, {}):
            raise ValueError("agent event details are not allowed for this event")
        return self


class AgentHeartbeatRequest(BaseModel):
    """Opaque lease presentation for a companion liveness heartbeat."""

    model_config = ConfigDict(extra="forbid")

    run_lease_id: str = Field(min_length=24, max_length=200, repr=False)


class ProtectedManualCheckUpdate(BaseModel):
    """One deliberately non-narrative manual-check outcome.

    Protected report details cannot go into the public-report evaluation
    tables.  The only manual state kept in the ordinary index is the bounded
    WCAG outcome itself; rationale, evidence URLs, notes, and page references
    are intentionally not accepted by this browser contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["not_started", "pass", "fail", "not_tested", "needs_follow_up"]


_STATUS_EVENT_TYPES: dict[ProtectedScanStatus, str] = {
    ProtectedScanStatus.AWAITING_AUTHENTICATION: "companion.manual_authentication_started",
    ProtectedScanStatus.RUNNING: "companion.authenticated_crawl_started",
    ProtectedScanStatus.AUTHENTICATION_REQUIRED: "companion.authentication_required",
    ProtectedScanStatus.COMPLETED: "companion.completed",
    ProtectedScanStatus.FAILED: "companion.failed",
    ProtectedScanStatus.INTERRUPTED: "companion.interrupted",
}


def build_protected_router(
    *,
    get_conn: Callable[[], sqlite3.Connection],
    settings: Settings,
    vault: ProtectedVault | None,
) -> APIRouter:
    """Build routes; unavailable KMS configuration fails closed on writes."""
    router = APIRouter()

    @router.post("/protected-scans", status_code=201)
    async def create_scan(request: Request, body: ProtectedScanRequest) -> dict[str, Any]:
        # Verify the stronger protected identity before reporting deployment
        # configuration. A public ingress token must not learn whether this
        # optional feature is configured. ``_browser_identity`` uses the
        # configured public origin for the mutation CSRF check, never Host.
        identity = require_protected_identity(request, settings)
        _companion_public_origin(settings)
        require_same_origin(request, settings)
        active_vault = _require_vault(vault)
        # Retention is a protected-data invariant in staging as well as
        # production. A non-revocable development KEK cannot make a prior
        # SQLite/WAL/backup snapshot unreadable, so it is not eligible for
        # any enabled protected scan.
        if not active_vault.supports_irreversible_scan_key_destruction:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Protected scans require a key manager that can "
                    "irreversibly revoke each report's evidence key."
                ),
            )
        if body.allow_local_ai and not _is_loopback_ollama_url(settings.ollama_base_url):
            raise HTTPException(
                status_code=422,
                detail="Protected local AI requires a loopback-only Ollama endpoint.",
            )
        try:
            policy = ProtectedEgressPolicy(body.approved_target_origins)
            validated = policy.validate_url(body.seed_url)
        except EgressViolation as exc:
            raise HTTPException(
                status_code=422, detail=f"Unsafe protected seed: {exc.code}"
            ) from exc

        # ``safe_seed`` is still private protected scope, even though it has
        # no query or credential. Keep it in memory only; the ordinary scan
        # row receives a random opaque alias and the companion work spec is
        # encrypted with the per-scan protected data key.
        safe_seed = url_policy.normalize_seed_url(validated.url)
        config = _protected_crawl_config(body, settings, safe_seed)
        opaque_alias = _new_opaque_scan_alias()
        public_config = _protected_public_config_json(config, opaque_alias)
        private_work_config = _protected_work_config(config, allow_local_ai=body.allow_local_ai)
        work_spec = ProtectedWorkSpec(
            seed_url=safe_seed,
            approved_target_origins=body.approved_target_origins,
            approved_auth_origins=body.approved_auth_origins,
            approved_cdn_origins=body.approved_cdn_origins,
            index_hmac_key=secrets.token_hex(32),
            config=private_work_config,
        )
        seed_locator = _seed_locator(safe_seed, settings)
        # The browser can describe the owner approval, but it cannot assert
        # who created the protected record.  Bind the durable ``authorized_by``
        # field to the identity-aware proxy subject; retain the human-entered
        # approval reference only as a redacted audit detail.
        verified_body = body.model_copy(update={"authorized_by": identity.subject})
        with get_conn() as conn:
            existing = find_active_protected_scan_by_seed_locator(
                conn, seed_locator=seed_locator, authorized_by=identity.subject
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A protected scan draft already exists for this seed. "
                        "Use its companion setup."
                    ),
                )
            # A draft is intentionally not a running/public crawler job. The
            # protected workflow status owns the human-authentication phase.
            cur = conn.execute(
                "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'interrupted', ?)",
                (opaque_alias, public_config),
            )
            scan_id = int(cur.lastrowid or 0)
            try:
                record = create_protected_scan(
                    conn,
                    scan_id=scan_id,
                    protected_scan=verified_body,
                    work_spec=work_spec,
                    scope_fingerprints=_scope_fingerprints(body, settings),
                    seed_locator=seed_locator,
                    vault=active_vault,
                )
                record_protected_audit_event(
                    conn,
                    scan_id=scan_id,
                    actor_subject=identity.subject,
                    event_type="protected_scan.requested",
                    details={
                        "seed_alias": opaque_alias,
                        "declared_authorization_reference": body.authorized_by,
                    },
                )
            except Exception:
                conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
                raise
        return {"scan_id": scan_id, "protection_status": record.protection_status.value}

    @router.get("/protected-scans")
    async def list_protected_scans(request: Request) -> dict[str, Any]:
        """List only the current proxy subject's non-sensitive reports.

        Protected reports are intentionally omitted from the public scan list.
        This separate list exposes no seed, owner, origin, evidence, or
        companion state—only enough information to resume the protected
        workflow after the SPA is reloaded.
        """

        identity = require_protected_identity(request, settings)
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT p.scan_id, p.protection_status, p.environment,
                       p.data_classification, p.cleanup_at, p.evidence_purged_at,
                       p.created_at, p.updated_at, s.page_count,
                       s.axe_violations_total, s.alfa_failed_total,
                       s.alfa_cant_tell_total
                  FROM protected_scans p
                  JOIN scans s ON s.id = p.scan_id
                 WHERE p.authorized_by = ?
                 ORDER BY p.updated_at DESC, p.scan_id DESC
                 LIMIT 200
                """,
                (identity.subject,),
            ).fetchall()
        reports: list[dict[str, Any]] = []
        for row in rows:
            cleanup_at = _as_utc_payload(row["cleanup_at"])
            evidence_purged = row["evidence_purged_at"] is not None
            reports.append(
                {
                    "scan_id": int(row["scan_id"]),
                    "protection_status": str(row["protection_status"]),
                    "environment": str(row["environment"]),
                    "data_classification": str(row["data_classification"]),
                    "page_count": _safe_index_count(row["page_count"]),
                    "issue_occurrences": _safe_index_count(row["axe_violations_total"])
                    + _safe_index_count(row["alfa_failed_total"])
                    + _safe_index_count(row["alfa_cant_tell_total"]),
                    "cleanup_at": cleanup_at,
                    "evidence_available": not evidence_purged
                    and datetime.fromisoformat(cleanup_at.replace("Z", "+00:00"))
                    > datetime.now(UTC),
                    "created_at": _as_utc_payload(row["created_at"]),
                    "updated_at": _as_utc_payload(row["updated_at"]),
                }
            )
        return {"reports": reports}

    @router.get("/protected-scans/identity-context")
    async def protected_identity_context(request: Request) -> JSONResponse:
        """Return a non-reversible cache partition for the current proxy user.

        This endpoint deliberately appears before ``/{scan_id}`` so the
        static path cannot be interpreted as a malformed scan identifier.
        It returns neither a proxy subject nor any report metadata.
        """

        identity = require_protected_identity(request, settings)
        return JSONResponse(
            {"subject_fingerprint": protected_identity_context_fingerprint(identity, settings)},
            headers={
                "Cache-Control": "no-store, private, max-age=0",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get("/protected-scans/{scan_id:int}")
    async def get_scan(request: Request, scan_id: int) -> dict[str, Any]:
        identity = _browser_identity(request, settings)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            progress_row = conn.execute(
                """
                SELECT s.page_count,
                       COUNT(a.id) AS issue_occurrences,
                       SUM(CASE WHEN a.pipeline = 'axe' THEN 1 ELSE 0 END) AS axe_occurrences,
                       SUM(CASE WHEN a.pipeline = 'alfa' AND a.engine_outcome = 'failed'
                                THEN 1 ELSE 0 END) AS alfa_failed_occurrences,
                       SUM(CASE WHEN a.pipeline = 'alfa' AND a.engine_outcome = 'cant_tell'
                                THEN 1 ELSE 0 END) AS alfa_review_occurrences,
                       SUM(CASE WHEN a.pipeline NOT IN ('axe', 'alfa')
                                THEN 1 ELSE 0 END) AS probe_occurrences
                  FROM scans s
                  LEFT JOIN page_a11y_findings a ON a.scan_id = s.id
                 WHERE s.id = ?
                 GROUP BY s.id, s.page_count
                """,
                (scan_id,),
            ).fetchone()
        if record is None:
            raise HTTPException(status_code=403, detail="Protected-report permission required.")
        _browser_report_identity(request, settings, record=record, identity=identity)
        payload = _record_payload(record)
        payload["progress"] = _protected_progress_payload(progress_row)
        return payload

    @router.get("/protected-scans/{scan_id:int}/issue-index")
    async def protected_issue_index(request: Request, scan_id: int) -> dict[str, Any]:
        """Return a grouped, page-anonymous index for protected review."""

        identity = _browser_identity(request, settings)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            if record is None:
                raise HTTPException(status_code=403, detail="Protected-report permission required.")
            _browser_report_identity(request, settings, record=record, identity=identity)
            rows = conn.execute(
                """
                SELECT pipeline, rule_id, wcag_sc, wcag_level, impact, engine_outcome,
                       COUNT(*) AS occurrence_count, COUNT(DISTINCT page_id) AS page_count
                  FROM page_a11y_findings
                 WHERE scan_id = ?
                 GROUP BY pipeline, rule_id, wcag_sc, wcag_level, impact, engine_outcome
                 ORDER BY occurrence_count DESC, page_count DESC, pipeline ASC, rule_id ASC
                 LIMIT 250
                """,
                (scan_id,),
            ).fetchall()
        groups = [_protected_issue_group_payload(row) for row in rows]
        return {
            "scan_id": scan_id,
            "groups": groups,
            "manual_verification_required": True,
            "evidence_available": bool(record.is_evidence_available),
        }

    @router.get("/protected-scans/{scan_id:int}/manual-checks")
    async def list_protected_manual_checks(request: Request, scan_id: int) -> dict[str, Any]:
        """List outcome-only WCAG manual review state for one protected scan.

        Criterion guidance is static product content. The response deliberately
        excludes result IDs, rationale, page references, evidence URLs, and
        evidence notes, which are not safe to retain through the public
        evaluation tables for a protected report.
        """

        identity = _browser_identity(request, settings)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            if record is None:
                raise HTTPException(status_code=403, detail="Protected-report permission required.")
            _browser_report_identity(request, settings, record=record, identity=identity)
            checks = evaluation.list_manual_check_outcomes(conn, scan_id)
        return {
            "scan_id": scan_id,
            "checks": [_protected_manual_check_payload(check) for check in checks],
        }

    @router.patch("/protected-scans/{scan_id:int}/manual-checks/{criterion_sc}")
    async def update_protected_manual_check(
        request: Request,
        scan_id: int,
        criterion_sc: str,
        body: ProtectedManualCheckUpdate,
    ) -> dict[str, Any]:
        """Persist a bounded result without accepting protected narrative.

        A manual authentication review may be recorded before, during, or
        after the companion crawl: supporting a post-MFA crawl is never an
        automatic verdict on WCAG 2.2 SC 3.3.8. The v1 protected API does not
        accept detailed evidence or attachment uploads.
        """

        identity = _browser_identity(request, settings)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            if record is None:
                raise HTTPException(status_code=403, detail="Protected-report permission required.")
            _browser_report_identity(request, settings, record=record, identity=identity)
            try:
                check = evaluation.update_manual_check_outcome_only(
                    conn,
                    scan_id=scan_id,
                    criterion_sc=criterion_sc,
                    outcome=body.outcome,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            record_protected_audit_event(
                conn,
                scan_id=scan_id,
                actor_subject=identity.subject,
                event_type="protected_manual_check.updated",
                details={"criterion_sc": criterion_sc, "outcome": body.outcome},
            )
        return _protected_manual_check_payload(check)

    @router.post("/protected-scans/{scan_id:int}/exports/redacted")
    async def export_redacted_report(request: Request, scan_id: int) -> Response:
        """Download one explicitly requested, redacted protected summary.

        The normal export collectors intentionally remain unavailable for
        protected scans: they can include raw page evidence.  This operation
        reads only the bounded ordinary issue index and returns Markdown
        directly from memory.  No generated export is persisted on the host.
        """

        identity = _browser_identity(request, settings)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            if record is None:
                raise HTTPException(status_code=403, detail="Protected-report permission required.")
            _browser_report_identity(request, settings, record=record, identity=identity)
            try:
                rendered = render_redacted_protected_report(
                    conn,
                    scan_id=scan_id,
                    record=record,
                )
            except ProtectedExportError as exc:
                if not record.is_evidence_available:
                    status_code = 410
                elif record.protection_status is not ProtectedScanStatus.COMPLETED:
                    status_code = 409
                else:  # Defensive: do not disclose storage details on malformed records.
                    status_code = 404
                raise HTTPException(status_code=status_code, detail=str(exc)) from exc
            # Accountability without retaining the recipient's document or
            # any report evidence. The repository redacts event details.
            record_protected_audit_event(
                conn,
                scan_id=scan_id,
                actor_subject=identity.subject,
                event_type="protected_export.redacted_downloaded",
                details={
                    "format": "redacted_markdown",
                    "delivery": "in_memory",
                },
            )
        return Response(
            content=rendered,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="protected_scan_{scan_id}_redacted.md"'
                ),
                # Browsers/proxies must not retain a protected document after
                # delivery. The user still controls any downloaded copy.
                "Cache-Control": "no-store, private, max-age=0",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )

    @router.post("/protected-scans/{scan_id:int}/agent-enrollments", status_code=201)
    async def create_enrollment(
        request: Request, scan_id: int, body: AgentEnrollmentRequest
    ) -> dict[str, Any]:
        identity = _browser_identity(request, settings)
        _require_vault(vault)
        companion_origin = _companion_public_origin(settings)
        pairing_code = secrets.token_urlsafe(24)
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            if record is None:
                raise HTTPException(status_code=403, detail="Protected-report permission required.")
            _browser_report_identity(request, settings, record=record, identity=identity)
            try:
                enrollment = create_agent_enrollment(
                    conn,
                    scan_id=scan_id,
                    enrollment=AgentEnrollmentCreate(
                        identity_subject=identity.subject,
                        certificate_fingerprint=body.certificate_fingerprint,
                        expires_at=expires_at,
                    ),
                    pairing_code=pairing_code,
                )
            except AgentEnrollmentError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="This protected scan is not available for a new companion enrollment.",
                ) from exc
            except ProtectedDataError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Protected evidence is no longer available for companion enrollment.",
                ) from exc
        # This is the sole response that contains the pairing code; the DB
        # keeps an scrypt verifier only.  The UI deliberately does not place
        # it in a URL, clipboard, log, or persisted client state.
        certificate_args = (
            "--certificate /path/to/companion-cert.pem --private-key /path/to/companion-key.pem"
        )
        return {
            "enrollment_id": enrollment.id,
            "pairing_code": pairing_code,
            "expires_at": enrollment.expires_at,
            "companion_command": (
                f"axcess-companion pair --server {companion_origin} "
                f"--enrollment-id {enrollment.id} "
                f"{certificate_args}"
            ),
            "companion_run_command": (
                f"axcess-companion run --server {companion_origin} "
                f"--enrollment-id {enrollment.id} {certificate_args}"
            ),
        }

    @router.get("/protected-scans/{scan_id:int}/companion")
    async def get_companion(request: Request, scan_id: int) -> dict[str, Any]:
        """Return only non-secret re-run information for the paired computer.

        A session can expire long after the one-time pairing code disappears
        from the browser. The existing scan-bound certificate is the correct
        way to re-authenticate, so this avoids minting a second pairing secret
        merely to rediscover an enrollment id. It never returns a pairing
        verifier/code, certificate fingerprint, target URL, or work item.
        """

        identity = _browser_identity(request, settings)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            if record is None:
                raise HTTPException(status_code=403, detail="Protected-report permission required.")
            _browser_report_identity(request, settings, record=record, identity=identity)
            enrollment = get_claimed_agent_enrollment(conn, scan_id=scan_id)
        if enrollment is None:
            return {"companion": None}
        companion_origin = _companion_public_origin(settings)
        certificate_args = (
            "--certificate /path/to/companion-cert.pem --private-key /path/to/companion-key.pem"
        )
        return {
            "companion": {
                "enrollment_id": enrollment.id,
                "status": enrollment.status.value,
                "companion_run_command": (
                    f"axcess-companion run --server {companion_origin} "
                    f"--enrollment-id {enrollment.id} {certificate_args}"
                ),
            }
        }

    @router.post("/protected-scans/{scan_id:int}/companion-start")
    async def companion_start(request: Request, scan_id: int) -> dict[str, Any]:
        identity = _browser_identity(request, settings)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            if record is None:
                raise HTTPException(status_code=403, detail="Protected-report permission required.")
            _browser_report_identity(request, settings, record=record, identity=identity)
            if record.protection_status not in {
                ProtectedScanStatus.AWAITING_AUTHENTICATION,
                ProtectedScanStatus.AUTHENTICATION_REQUIRED,
                ProtectedScanStatus.INTERRUPTED,
            }:
                raise HTTPException(
                    status_code=409,
                    detail="This protected scan is not available for another manual handoff.",
                )
            # The browser API cannot start a remote companion or bypass a
            # login. This event exists solely to make the handoff explicit.
            record_protected_audit_event(
                conn,
                scan_id=scan_id,
                actor_subject=identity.subject,
                event_type="companion.handoff_requested",
            )
        return {"ok": True, "protection_status": record.protection_status.value}

    @router.post("/protected-scans/{scan_id:int}/stop")
    async def stop_protected_scan(request: Request, scan_id: int) -> dict[str, Any]:
        """Explicit owner stop; invalidate the paired companion immediately."""

        identity = _browser_identity(request, settings)
        with get_conn() as conn:
            record = get_protected_scan_for_owner(
                conn, scan_id=scan_id, authorized_by=identity.subject
            )
            if record is None:
                raise HTTPException(status_code=403, detail="Protected-report permission required.")
            _browser_report_identity(request, settings, record=record, identity=identity)
            try:
                stopped = interrupt_protected_scan(
                    conn, scan_id=scan_id, actor_subject=identity.subject
                )
            except ProtectedDataError as exc:
                raise HTTPException(
                    status_code=409, detail="This protected scan cannot be stopped."
                ) from exc
            _sync_legacy_scan_status(conn, scan_id, ProtectedScanStatus.INTERRUPTED)
        return _record_payload(stopped)

    # Agent enrollment is intentionally separate from the browser routes: a
    # one-time code gets a certificate fingerprint bound to exactly one scan;
    # all later agent traffic must arrive through the mTLS proxy assertion.
    @router.post("/agents/enroll", status_code=201)
    async def claim_enrollment(request: Request, body: AgentClaimRequest) -> dict[str, Any]:
        # The pairing code is deliberately not sufficient on its own. The
        # browser pre-bound one certificate fingerprint when it created the
        # enrollment; the TLS terminator must prove this exact certificate
        # before a claim may read any work. A leaked pairing code plus a
        # different valid managed-device certificate is therefore useless.
        with get_conn() as conn:
            pending = conn.execute(
                (
                    "SELECT certificate_fingerprint, status "
                    "FROM protected_agent_enrollments WHERE id = ?"
                ),
                (body.enrollment_id,),
            ).fetchone()
        if (
            pending is None
            or str(pending["status"]) != "pending"
            or pending["certificate_fingerprint"] is None
        ):
            raise HTTPException(status_code=403, detail="Agent enrollment was not accepted.")
        expected_fingerprint = str(pending["certificate_fingerprint"])
        await require_agent_mtls(
            request,
            settings,
            expected_fingerprint=expected_fingerprint,
        )
        if not settings.protected_scans_enabled:
            raise HTTPException(status_code=404, detail="Protected scans are not enabled.")
        with get_conn() as conn:
            try:
                enrollment = claim_agent_enrollment(
                    conn,
                    enrollment_id=body.enrollment_id,
                    pairing_code=body.pairing_code,
                    certificate_fingerprint=expected_fingerprint,
                )
            except (AgentEnrollmentError, ProtectedDataError) as exc:
                raise HTTPException(
                    status_code=403, detail="Agent enrollment was not accepted."
                ) from exc
        return {
            "enrollment_id": enrollment.id,
            "scan_id": enrollment.scan_id,
            "status": enrollment.status.value,
            "mtls_required": True,
        }

    @router.get("/agents/{enrollment_id}/work")
    async def agent_work(request: Request, enrollment_id: str) -> dict[str, Any]:
        active_vault = _require_vault(vault)
        with get_conn() as conn:
            enrollment = await _require_agent(conn, request, settings, enrollment_id)
            # Expired heartbeats are an interruption, not a reason to keep a
            # browser session or let its late events mutate this report.
            recover_stale_protected_run_leases(conn)
            record = get_protected_scan(conn, scan_id=enrollment["scan_id"])
            if record is None:
                raise HTTPException(status_code=404, detail="Protected scan work is unavailable")
            if record.protection_status not in {
                ProtectedScanStatus.AWAITING_AUTHENTICATION,
                ProtectedScanStatus.AUTHENTICATION_REQUIRED,
                ProtectedScanStatus.INTERRUPTED,
            }:
                # Do not release a private target URL after the report has
                # reached a terminal state—or while another authenticated
                # crawl is active. Re-authentication starts from the explicit
                # paused states only.
                raise HTTPException(
                    status_code=409,
                    detail="Protected scan work is not awaiting a manual authentication handoff.",
                )
            try:
                run_lease_id = acquire_protected_run_lease(
                    conn,
                    scan_id=int(enrollment["scan_id"]),
                    enrollment_id=enrollment_id,
                    actor_subject=str(enrollment["identity_subject"]),
                )
            except ProtectedDataError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Protected companion work is already active or unavailable.",
                ) from exc
            try:
                work_spec = get_protected_work_spec(
                    conn,
                    scan_id=int(enrollment["scan_id"]),
                    vault=active_vault,
                )
            except ProtectedDataError as exc:
                # The lease exists only inside this transaction. Clear it
                # before returning an unavailable-work result so a later
                # authorized recovery is not blocked by this failed release.
                conn.execute(
                    """
                    UPDATE protected_scans
                       SET run_lease_id = NULL, run_lease_expires_at = NULL,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE scan_id = ? AND run_lease_id = ?
                    """,
                    (int(enrollment["scan_id"]), run_lease_id),
                )
                raise HTTPException(
                    status_code=410, detail="Protected scan work is no longer available."
                ) from exc
        if record is None:  # pragma: no cover - guarded above
            raise HTTPException(status_code=404, detail="Protected scan work is unavailable")
        return {
            "scan_id": int(enrollment["scan_id"]),
            # This is the only browser-facing path that releases the private
            # seed, and it is guarded by the scan-bound companion mTLS check
            # above. ``work_spec`` is not persisted or logged after return.
            "seed_url": work_spec.seed_url,
            "approved_target_origins": work_spec.approved_target_origins,
            "approved_auth_origins": work_spec.approved_auth_origins,
            "approved_cdn_origins": work_spec.approved_cdn_origins,
            "index_hmac_key": work_spec.index_hmac_key,
            "config": work_spec.config,
            "run_lease_id": run_lease_id,
            "protection": _record_payload(record),
        }

    @router.post("/agents/{enrollment_id}/heartbeat")
    async def agent_heartbeat(
        request: Request, enrollment_id: str, body: AgentHeartbeatRequest
    ) -> dict[str, Any]:
        with get_conn() as conn:
            enrollment = await _require_agent(conn, request, settings, enrollment_id)
            try:
                heartbeat_protected_run_lease(
                    conn,
                    scan_id=int(enrollment["scan_id"]),
                    enrollment_id=enrollment_id,
                    actor_subject=str(enrollment["identity_subject"]),
                    run_lease_id=body.run_lease_id,
                )
            except ProtectedDataError as exc:
                raise HTTPException(
                    status_code=409, detail="Protected companion lease is unavailable."
                ) from exc
        return {"ok": True}

    @router.post("/agents/{enrollment_id}/events")
    async def agent_event(
        request: Request, enrollment_id: str, body: AgentEventRequest
    ) -> dict[str, Any]:
        with get_conn() as conn:
            enrollment = await _require_agent(conn, request, settings, enrollment_id)
            scan_id = int(enrollment["scan_id"])
            try:
                # Events are write authority: they must prove the active
                # single-use lease even if a stale mTLS client remains alive.
                heartbeat_protected_run_lease(
                    conn,
                    scan_id=scan_id,
                    enrollment_id=enrollment_id,
                    actor_subject=str(enrollment["identity_subject"]),
                    run_lease_id=body.run_lease_id,
                )
            except ProtectedDataError as exc:
                raise HTTPException(
                    status_code=409, detail="Protected companion lease is unavailable."
                ) from exc
            if body.page_index is not None:
                record = get_protected_scan(conn, scan_id=scan_id)
                if record is None or record.protection_status is not ProtectedScanStatus.RUNNING:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Protected page evidence can be indexed only while the scan is running."
                        ),
                    )
                try:
                    record_protected_page_index(
                        conn,
                        scan_id=scan_id,
                        page=body.page_index,
                        actor_subject=str(enrollment["identity_subject"]),
                        enrollment_id=enrollment_id,
                    )
                except ProtectedDataError as exc:
                    raise HTTPException(
                        status_code=409,
                        detail="Protected page evidence is no longer available.",
                    ) from exc
            elif body.status is not None:
                try:
                    record = set_protected_scan_status(
                        conn,
                        scan_id=scan_id,
                        status=body.status,
                        actor_subject=str(enrollment["identity_subject"]),
                        run_lease_id=body.run_lease_id,
                    )
                except ProtectedDataError as exc:
                    raise HTTPException(
                        status_code=409,
                        detail="Protected scan state does not accept that companion event.",
                    ) from exc
                _sync_legacy_scan_status(conn, scan_id, body.status)
            else:
                record = get_protected_scan(conn, scan_id=scan_id)
            if body.page_index is None:
                record_protected_audit_event(
                    conn,
                    scan_id=scan_id,
                    enrollment_id=enrollment_id,
                    actor_subject=str(enrollment["identity_subject"]),
                    event_type=body.event_type,
                    details=body.details,
                )
        if record is None:  # pragma: no cover - FK invariant
            raise HTTPException(status_code=404, detail="Protected scan not found")
        return _record_payload(record)

    @router.post("/agents/{enrollment_id}/artifacts", status_code=403)
    async def agent_artifact(request: Request, enrollment_id: str) -> None:
        """Reject companion artifact uploads in the v1 protected workflow.

        A paired process cannot self-certify arbitrary bytes as "reviewed and
        redacted." Leaving this endpoint writable would make a compromised or
        stale certificate a path for raw screenshots, DOM data, or disk
        exhaustion. The v1 protected workflow therefore retains no uploads;
        redacted exports are browser-authorized, generated in memory, and
        delivered without server-side files.
        """

        with get_conn() as conn:
            await _require_agent(conn, request, settings, enrollment_id)
        raise HTTPException(
            status_code=403,
            detail="Companion artifact uploads are disabled for protected scans.",
        )

    return router


def _browser_identity(request: Request, settings: Settings) -> ProtectedIdentity:
    identity = require_protected_identity(request, settings)
    # Same-origin checks protect mutations. Browsers commonly omit Origin on
    # same-origin GET navigation/fetch requests, so applying it to reads
    # would make a valid protected report impossible to view.
    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        require_same_origin(request, settings)
    return identity


def _browser_report_identity(
    request: Request,
    settings: Settings,
    *,
    record: Any,
    identity: ProtectedIdentity | None = None,
) -> ProtectedIdentity:
    """Authenticate a browser action and enforce its scan-level ACL."""

    identity = identity or _browser_identity(request, settings)
    require_protected_report_owner(identity, authorized_by=str(record.authorized_by))
    return identity


def _require_vault(vault: ProtectedVault | None) -> ProtectedVault:
    if vault is None:
        raise HTTPException(
            status_code=503,
            detail="Protected scan key management is not configured.",
        )
    return vault


def _protected_crawl_config(
    request: ProtectedScanRequest, settings: Settings, seed_url: str
) -> CrawlConfig:
    """Build a safe persisted work specification, not a running crawl."""
    return CrawlConfig(
        seed_url=seed_url,
        max_pages=request.max_pages,
        max_depth=request.max_depth,
        workers=1,
        concurrency_per_host=1,
        rps=request.rps,
        ignore_robots=True,
        user_agent=settings.user_agent,
        request_timeout_s=settings.request_timeout_s,
        # Protected assets stay in memory; the companion performs its own
        # authenticated image pass rather than the public blob pipeline.
        ocr_enabled=True,
        vlm_enabled=bool(request.allow_local_ai),
        vlm_model=settings.vlm_model,
        vlm_base_url=settings.ollama_base_url,
        js_enabled=True,
        js_eager=True,
        axe_enabled=request.scan_engine in {"axe", "both"},
        axe_level="AA",
        alfa_enabled=request.scan_engine in {"alfa", "both"},
        # The protected companion currently permits optional loopback AI only
        # for bounded, in-memory image leads. Do not advertise or persist a
        # page-semantic model pass that it does not run.
        semantic_enabled=False,
        keyboard_probe_enabled=True,
        responsive_checks_enabled=True,
        focus_checks_enabled=True,
        # A full-page/element screenshot is not eligible for automatic
        # protected persistence, and v1 has no reviewer attachment upload.
        visual_checks_enabled=False,
        capture_screenshots=False,
    )


async def _require_agent(
    conn: sqlite3.Connection,
    request: Request,
    settings: Settings,
    enrollment_id: str,
) -> sqlite3.Row:
    if not settings.protected_scans_enabled:
        # Disabling protected scans is an immediate fail-closed operational
        # switch. A previously claimed certificate must not keep releasing
        # encrypted work or writing evidence after that decision.
        raise HTTPException(status_code=404, detail="Protected scans are not enabled.")
    row = conn.execute(
        "SELECT id, scan_id, identity_subject, certificate_fingerprint, status "
        "FROM protected_agent_enrollments WHERE id = ?",
        (enrollment_id,),
    ).fetchone()
    if row is None or str(row["status"]) != "claimed" or not row["certificate_fingerprint"]:
        raise HTTPException(status_code=403, detail="Companion enrollment is unavailable.")
    await require_agent_mtls(
        request,
        settings,
        expected_fingerprint=str(row["certificate_fingerprint"]),
    )
    return cast(sqlite3.Row, row)


def _sync_legacy_scan_status(
    conn: sqlite3.Connection, scan_id: int, status: ProtectedScanStatus
) -> None:
    """Keep legacy scan consumers honest without treating a draft as a crawl."""
    mapping = {
        ProtectedScanStatus.AWAITING_AUTHENTICATION: "interrupted",
        ProtectedScanStatus.AUTHENTICATION_REQUIRED: "interrupted",
        ProtectedScanStatus.RUNNING: "running",
        ProtectedScanStatus.COMPLETED: "completed",
        ProtectedScanStatus.FAILED: "failed",
        ProtectedScanStatus.INTERRUPTED: "interrupted",
    }
    legacy = mapping[status]
    if status in {
        ProtectedScanStatus.COMPLETED,
        ProtectedScanStatus.FAILED,
        ProtectedScanStatus.INTERRUPTED,
    }:
        conn.execute(
            "UPDATE scans SET status = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (legacy, scan_id),
        )
    else:
        conn.execute(
            "UPDATE scans SET status = ?, finished_at = NULL WHERE id = ?", (legacy, scan_id)
        )


def _record_payload(record: Any) -> dict[str, Any]:
    payload = cast(dict[str, Any], jsonable_encoder(record))
    payload["is_evidence_available"] = bool(record.is_evidence_available)
    return payload


def _protected_progress_payload(row: sqlite3.Row | None) -> dict[str, int]:
    """Return bounded counts only—never protected pages, URLs, or evidence."""
    if row is None:
        return {
            "pages_indexed": 0,
            "issue_occurrences": 0,
            "axe_occurrences": 0,
            "alfa_failed_occurrences": 0,
            "alfa_review_occurrences": 0,
            "probe_occurrences": 0,
        }
    return {
        "pages_indexed": _safe_index_count(row["page_count"]),
        "issue_occurrences": _safe_index_count(row["issue_occurrences"]),
        "axe_occurrences": _safe_index_count(row["axe_occurrences"]),
        "alfa_failed_occurrences": _safe_index_count(row["alfa_failed_occurrences"]),
        "alfa_review_occurrences": _safe_index_count(row["alfa_review_occurrences"]),
        "probe_occurrences": _safe_index_count(row["probe_occurrences"]),
    }


def _protected_manual_check_payload(check: dict[str, Any]) -> dict[str, Any]:
    """Project a manual-matrix row to its protected-safe, outcome-only form."""

    criterion = cast(dict[str, Any], check["criterion"])
    return {
        "criterion": {
            "sc": str(criterion["sc"]),
            "name": str(criterion["name"]),
            "level": str(criterion["level"]),
            "method": str(criterion["method"]),
            "manual_check": str(criterion["manual_check"]),
        },
        "outcome": str(check["outcome"]),
        "tested_at": check["tested_at"],
        "updated_at": check["updated_at"],
    }


def _protected_issue_group_payload(row: sqlite3.Row) -> dict[str, Any]:
    """Whitelist one aggregate row; never reflect ordinary evidence fields."""

    pipeline = str(row["pipeline"] or "")
    rule_id = str(row["rule_id"] or "")
    wcag_sc = str(row["wcag_sc"] or "")
    level = str(row["wcag_level"] or "")
    impact = str(row["impact"] or "")
    outcome = str(row["engine_outcome"] or "")
    return {
        "source_layer": pipeline
        if pipeline in {"axe", "alfa", "keyboard", "responsive", "focus", "protected_image"}
        else "unavailable",
        "rule_id": (
            rule_id if re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,127}", rule_id) else "unavailable"
        ),
        "wcag_sc": wcag_sc if re.fullmatch(r"\d\.\d\.\d", wcag_sc) else None,
        "wcag_level": level if level in {"A", "AA", "AAA"} else None,
        "impact": impact if impact in {"critical", "serious", "moderate", "minor"} else None,
        "engine_outcome": outcome if outcome in {"failed", "cant_tell"} else None,
        "occurrence_count": _safe_index_count(row["occurrence_count"]),
        "page_count": _safe_index_count(row["page_count"]),
    }


def _safe_index_count(value: Any) -> int:
    try:
        return max(0, min(int(value), 10_000_000))
    except (TypeError, ValueError):
        return 0


def _as_utc_payload(value: Any) -> str:
    """Serialize a stored timestamp without reflecting malformed DB values."""

    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        # This field is operational metadata, not user content. A malformed
        # manual DB value should not become a browser parsing exception.
        return datetime.fromtimestamp(0, UTC).isoformat()


def _new_opaque_scan_alias() -> str:
    """Return a non-target-derived alias suitable for ordinary scan tables."""

    return f"protected://report/{secrets.token_urlsafe(24)}"


def _protected_public_config_json(config: CrawlConfig, opaque_alias: str) -> str:
    """Serialize public-safe scan metadata without a protected seed URL.

    Existing report views derive enabled methods from ``config_json``. Retain
    those non-sensitive switches, but bind the only seed-shaped field to the
    opaque alias so a future generic reader cannot accidentally treat it as a
    protected target URL.
    """

    public_config = json.loads(config_json_for_scan(config))
    # A custom user agent can be an organization-specific credential or
    # identifier. The companion uses a fixed safe default for protected scans.
    public_config.pop("user_agent", None)
    public_config.pop("vlm_base_url", None)
    public_config.pop("vlm_model", None)
    # A configured search carries a target URL and the values that were typed
    # into the site's own form. The method ledger only needs to know that a
    # search ran, so keep the flag and drop everything identifying.
    if public_config.get("search") is not None:
        public_config["search"] = True
    public_config["protected_work_spec"] = "encrypted"
    public_config["seed_url"] = opaque_alias
    return json.dumps(public_config, sort_keys=True, separators=(",", ":"))


def _protected_work_config(config: CrawlConfig, *, allow_local_ai: bool) -> dict[str, Any]:
    """Return bounded companion settings without a seed or credential field.

    A loopback Ollama endpoint/model is carried only inside the encrypted work
    spec and only after the explicit local-AI acknowledgement was validated.
    The companion revalidates the endpoint before it makes any model request.
    """

    work_config = cast(dict[str, Any], json.loads(config_json_for_scan(config)))
    # ``config_json_for_scan`` currently omits both values. Keep the removals
    # explicit so a future serializer change cannot put a seed or a local-model
    # endpoint into the agent payload by accident.
    work_config.pop("seed_url", None)
    work_config.pop("user_agent", None)
    # A search page URL is a seed by another name. Protected scans do not
    # configure one today; removing it explicitly keeps that true if they do.
    work_config.pop("search", None)
    if allow_local_ai:
        work_config["vlm_base_url"] = config.vlm_base_url
        work_config["vlm_model"] = config.vlm_model
    else:
        work_config.pop("vlm_base_url", None)
        work_config.pop("vlm_model", None)
    return work_config


def _seed_locator(seed_url: str, settings: Settings) -> str:
    """Create a domain-separated, non-reversible duplicate-draft locator."""

    secret = settings.protected_proxy_hmac_secret.get_secret_value()
    if not secret:  # ``_browser_identity`` normally makes this unreachable.
        raise HTTPException(
            status_code=503,
            detail="Protected scans require an identity-aware proxy configuration.",
        )
    return hmac.new(
        secret.encode("utf-8"),
        b"axcess-protected-seed-locator:v1\x00" + seed_url.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _scope_fingerprints(
    request: ProtectedScanRequest, settings: Settings
) -> ProtectedScopeFingerprints:
    """Return non-reversible scope tags without exposing raw origins in SQLite.

    The deployment-held identity-proxy secret is intentionally the key: it is
    already required for every protected request and never reaches the
    repository. Keep the labels domain-separated so the same exact origin
    tuple cannot be correlated across target, IdP, and CDN roles.
    """

    secret = settings.protected_proxy_hmac_secret.get_secret_value()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Protected scans require an identity-aware proxy configuration.",
        )

    def fingerprint(label: Literal["target", "auth", "cdn"], origins: tuple[str, ...]) -> str:
        message = scope_fingerprint_message(label, origins)
        return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    return ProtectedScopeFingerprints(
        target=fingerprint("target", request.approved_target_origins),
        auth=fingerprint("auth", request.approved_auth_origins),
        cdn=fingerprint("cdn", request.approved_cdn_origins),
    )


def _companion_public_origin(settings: Settings) -> str:
    """Return the configured HTTPS service origin for companion commands.

    Do not derive this from a request Host or forwarded-proto header. Those
    values can be supplied by a client if proxy header stripping is ever
    misconfigured, and a protected pairing command must never downgrade to
    plaintext transport or an attacker-selected service.
    """

    try:
        return normalize_exact_https_origin(settings.protected_public_origin)
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="Protected scans require a configured public HTTPS companion origin.",
        ) from exc


def _is_loopback_ollama_url(value: str) -> bool:
    """Accept only a literal loopback Ollama endpoint.

    The companion uses the same literal address when it opens httpx.
    Rejecting hostnames avoids a validate-then-re-resolve DNS-rebinding gap
    for protected page image bytes.
    """
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        _ = parsed.port
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
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
