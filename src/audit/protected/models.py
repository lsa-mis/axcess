"""Typed, non-secret contracts for protected scans and their evidence."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from audit.protected.redaction import contains_auth_material, is_sensitive_key


class ProtectedEnvironment(StrEnum):
    """Deployment environments that are eligible for an authorized scan."""

    STAGING = "staging"
    PRODUCTION = "production"


class DataClassification(StrEnum):
    """Minimal data labels for protected scan approval records."""

    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class ProtectedScanStatus(StrEnum):
    """Protected workflow state, separate from the crawler's legacy scan state."""

    AWAITING_AUTHENTICATION = "awaiting_authentication"
    RUNNING = "running"
    AUTHENTICATION_REQUIRED = "authentication_required"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ProtectedArtifactType(StrEnum):
    """Only safe-to-retain protected artifact categories."""

    REDACTED_EVIDENCE = "redacted_evidence"
    REVIEWED_ATTACHMENT = "reviewed_attachment"
    PROTECTED_EXPORT = "protected_export"


class AgentEnrollmentStatus(StrEnum):
    """Lifecycle for a scan-bound companion enrollment."""

    PENDING = "pending"
    CLAIMED = "claimed"
    EXPIRED = "expired"
    REVOKED = "revoked"


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CERTIFICATE_FINGERPRINT = re.compile(r"^[a-fA-F0-9]{64}$")
_SCOPE_FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")
_INDEX_HMAC_KEY = re.compile(r"^[a-f0-9]{64}$")
_EVENT_TYPE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_RULE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_OPAQUE_KEY = re.compile(r"^[a-f0-9]{32,128}$")
_WCAG_SC = re.compile(r"^\d\.\d\.\d$")


def normalize_exact_https_origin(value: str) -> str:
    """Return a canonical exact HTTPS origin or reject unsafe URL syntax.

    DNS and resolved-IP validation belongs to the future egress guard because
    it has to happen at request time.  This static boundary rejects bypasses
    that must never be persisted as allowed origins: credentials in URLs,
    wildcards, query/fragment/path scoping, local names, and IP literals.
    """

    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("approved origin has an invalid port") from exc
    if parsed.scheme.lower() != "https":
        raise ValueError("approved origins must use HTTPS")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("approved origin has an invalid port")
    if not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ValueError("approved origins cannot include userinfo")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("approved origins must not include a path, query, or fragment")
    host = parsed.hostname
    if host is None:
        raise ValueError("approved origin must include a hostname")
    host = host.rstrip(".").lower()
    if (
        not host
        or "*" in host
        or host == "localhost"
        or host.endswith(".localhost")
        or host.endswith(".local")
    ):
        raise ValueError("approved origin hostname is not allowed")
    try:
        host_ascii = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("approved origin hostname is invalid") from exc
    if ":" in host_ascii or all(part.isdecimal() for part in host_ascii.split(".")):
        raise ValueError("approved origins must use a DNS hostname, not an IP address")
    labels = host_ascii.split(".")
    if len(labels) < 2 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError("approved origin hostname is invalid")
    suffix = "" if port in (None, 443) else f":{port}"
    return f"https://{host_ascii}{suffix}"


def _normalize_origins(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(normalize_exact_https_origin(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} contains duplicate origins")
    return normalized


def scope_fingerprint_message(
    scope: Literal["target", "auth", "cdn"], origins: tuple[str, ...]
) -> bytes:
    """Return the canonical message an API boundary signs for one scope.

    This pure helper deliberately takes no secret and has no Settings
    dependency.  The caller computes ``HMAC-SHA-256(secret, message)`` and
    supplies the lowercase hex result via :class:`ProtectedScopeFingerprints`.
    NUL is safe as a separator because exact HTTPS origins cannot contain it.
    Sorting makes the tag represent a set rather than request field order.
    """

    if scope not in {"target", "auth", "cdn"}:  # pragma: no cover - Literal callers
        raise ValueError("protected scope type is invalid")
    normalized = _normalize_origins(origins, f"approved_{scope}_origins")
    return (
        b"axcess-protected-scope:v1\x00"
        + scope.encode("ascii")
        + b"\x00"
        + "\x00".join(sorted(normalized)).encode("utf-8")
    )


class ProtectedScanCreate(BaseModel):
    """Approval-only protected scan metadata; intentionally contains no secret."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    target_owner: str = Field(min_length=1, max_length=200)
    environment: ProtectedEnvironment
    data_classification: DataClassification
    authorized_by: str = Field(min_length=1, max_length=200)
    authorization_acknowledged: bool
    least_privilege_account_acknowledged: bool
    # Exact origins are accepted only long enough to validate and encrypt the
    # work specification.  They must never be repr'd by an exception/logger
    # or copied into the ordinary protected_scans metadata row.
    approved_target_origins: tuple[str, ...] = Field(min_length=1, max_length=32, repr=False)
    approved_auth_origins: tuple[str, ...] = Field(default=(), max_length=32, repr=False)
    approved_cdn_origins: tuple[str, ...] = Field(default=(), max_length=64, repr=False)
    allow_local_ai: bool = False
    local_ai_acknowledged: bool = False

    @field_validator("target_owner", "authorized_by")
    @classmethod
    def reject_auth_material_in_plaintext_metadata(cls, value: str) -> str:
        if contains_auth_material(value):
            raise ValueError("protected-scan metadata cannot contain authentication material")
        return value

    @field_validator("approved_target_origins", "approved_auth_origins", "approved_cdn_origins")
    @classmethod
    def normalize_origins(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _normalize_origins(values, str(info.field_name))

    @model_validator(mode="after")
    def require_explicit_safety_acknowledgements(self) -> ProtectedScanCreate:
        if not self.authorization_acknowledged:
            raise ValueError("authorization acknowledgement is required")
        if not self.least_privilege_account_acknowledged:
            raise ValueError("least-privilege audit-account acknowledgement is required")
        if self.allow_local_ai and not self.local_ai_acknowledged:
            raise ValueError("local AI requires an explicit data-handling acknowledgement")
        return self


class ProtectedScopeFingerprints(BaseModel):
    """Opaque, deployment-derived tags for the three approved origin scopes.

    The browser/API boundary computes each value with a deployment-held HMAC
    secret over a domain-separated, canonicalized origin tuple.  This model
    intentionally does not import Settings or try to derive the tags: the
    repository needs only a stable opaque value and must never receive the
    HMAC key.  The tags support safe audit/UI correlation without retaining
    exact protected hostnames in ordinary SQLite metadata.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: str = Field(min_length=64, max_length=64)
    auth: str = Field(min_length=64, max_length=64)
    cdn: str = Field(min_length=64, max_length=64)

    @field_validator("target", "auth", "cdn")
    @classmethod
    def validate_scope_fingerprint(cls, value: str) -> str:
        normalized = value.lower()
        if not _SCOPE_FINGERPRINT.fullmatch(normalized):
            raise ValueError("protected scope fingerprint must be a SHA-256 hex digest")
        return normalized


class ProtectedScanRecord(BaseModel):
    """Non-secret protected-scan state safe to return to an authorized UI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scan_id: int
    target_owner: str
    environment: ProtectedEnvironment
    data_classification: DataClassification
    authorized_by: str
    authorization_acknowledged: bool
    least_privilege_account_acknowledged: bool
    # The ordinary protected_scans table must never expose exact origins.
    # Counts and HMAC-derived tags are sufficient for review/audit context;
    # the companion receives exact scope only after decrypting its work spec.
    target_origin_count: int = Field(ge=0, le=32)
    auth_origin_count: int = Field(ge=0, le=32)
    cdn_origin_count: int = Field(ge=0, le=64)
    target_scope_fingerprint: str | None = Field(default=None, max_length=64)
    auth_scope_fingerprint: str | None = Field(default=None, max_length=64)
    cdn_scope_fingerprint: str | None = Field(default=None, max_length=64)
    allow_local_ai: bool
    local_ai_acknowledged: bool
    protection_status: ProtectedScanStatus
    cleanup_at: datetime
    evidence_purged_at: datetime | None
    key_destroyed_at: datetime | None
    last_heartbeat_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("target_scope_fingerprint", "auth_scope_fingerprint", "cdn_scope_fingerprint")
    @classmethod
    def validate_record_scope_fingerprint(cls, value: str | None) -> str | None:
        if value is None:
            # Pre-0016 rows are deliberately invalidated rather than trying
            # to recreate an HMAC tag after their plaintext scopes are
            # removed.  The null marker is safe to display as "legacy scope
            # redacted" and does not reveal a hostname.
            return None
        normalized = value.lower()
        if not _SCOPE_FINGERPRINT.fullmatch(normalized):
            raise ValueError("protected scope fingerprint must be a SHA-256 hex digest")
        return normalized

    @property
    def is_evidence_available(self) -> bool:
        # A scheduler may be down when the deadline passes. Treat the
        # retention deadline itself as a hard access boundary, even before a
        # later maintenance run deletes ciphertext and the wrapped key.
        return self.evidence_purged_at is None and self.cleanup_at > datetime.now(UTC)


class ProtectedWorkSpec(BaseModel):
    """One encrypted, scan-bound instruction for a paired companion.

    This model is an internal persistence boundary, not a browser response
    model. Its ``seed_url`` is deliberately hidden from repr output and may
    only be decrypted after the companion's mTLS identity has been checked.
    Browser state, credentials, and second-factor material are never valid
    configuration values.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Version 3 carries a random per-report HMAC key for stable opaque page
    # and occurrence identifiers. Version 2 carried exact origin scope but
    # generated index IDs per attempt, so migration 0018 makes it unrunnable
    # rather than risking duplicate coverage on a re-authentication handoff.
    version: int = Field(default=3, ge=3, le=3)
    seed_url: str = Field(min_length=12, max_length=2048, repr=False)
    approved_target_origins: tuple[str, ...] = Field(min_length=1, max_length=32, repr=False)
    approved_auth_origins: tuple[str, ...] = Field(default=(), max_length=32, repr=False)
    approved_cdn_origins: tuple[str, ...] = Field(default=(), max_length=64, repr=False)
    # This is never returned to the browser or written to the ordinary issue
    # index. It remains inside the AES-GCM encrypted work spec and lets the
    # companion derive stable opaque HMACs from in-memory URLs/selectors.
    index_hmac_key: str = Field(min_length=64, max_length=64, repr=False)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("seed_url")
    @classmethod
    def validate_private_seed_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("protected work-spec seed URL is invalid") from exc
        if (
            parsed.scheme.lower() != "https"
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("protected work-spec seed URL is invalid")
        return value

    @field_validator("approved_target_origins", "approved_auth_origins", "approved_cdn_origins")
    @classmethod
    def normalize_work_spec_origins(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _normalize_origins(values, str(info.field_name))

    @field_validator("index_hmac_key")
    @classmethod
    def validate_index_hmac_key(cls, value: str) -> str:
        normalized = value.lower()
        if not _INDEX_HMAC_KEY.fullmatch(normalized):
            raise ValueError("protected work-spec index key must be a SHA-256 hex value")
        return normalized

    @field_validator("config")
    @classmethod
    def reject_session_material_from_config(cls, values: dict[str, Any]) -> dict[str, Any]:
        if len(values) > 64:
            raise ValueError("protected work-spec configuration is too large")
        for key, value in values.items():
            normalized_key = str(key).replace("-", "_").lower()
            if is_sensitive_key(key) or normalized_key in {
                "seed_url",
                "approved_target_origins",
                "approved_auth_origins",
                "approved_cdn_origins",
            }:
                raise ValueError(
                    "protected work-spec configuration cannot contain session material"
                )
            if isinstance(value, str) and contains_auth_material(value):
                raise ValueError(
                    "protected work-spec configuration cannot contain session material"
                )
        return values

    @model_validator(mode="after")
    def seed_must_belong_to_encrypted_target_scope(self) -> ProtectedWorkSpec:
        """Keep scope enforcement independent of the browser request model."""

        parsed = urlsplit(self.seed_url)
        try:
            seed_origin = normalize_exact_https_origin(f"{parsed.scheme}://{parsed.netloc}")
        except ValueError as exc:  # guarded by validate_private_seed_url; defensive
            raise ValueError("protected work-spec seed URL is invalid") from exc
        if seed_origin not in self.approved_target_origins:
            raise ValueError("protected work-spec target scope must include the seed origin")
        return self


class AgentEnrollmentCreate(BaseModel):
    """Non-secret request that pre-binds one companion certificate to a scan."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    identity_subject: str = Field(min_length=1, max_length=200)
    certificate_fingerprint: str = Field(min_length=64, max_length=128)
    expires_at: datetime

    @field_validator("identity_subject")
    @classmethod
    def reject_auth_material_in_identity(cls, value: str) -> str:
        if contains_auth_material(value):
            raise ValueError("agent identity cannot contain authentication material")
        return value

    @field_validator("certificate_fingerprint")
    @classmethod
    def normalize_certificate_fingerprint(cls, value: str) -> str:
        return validate_certificate_fingerprint(value)


class AgentEnrollmentRecord(BaseModel):
    """Enrollment record that deliberately omits the pairing verifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    scan_id: int
    identity_subject: str
    certificate_fingerprint: str | None
    status: AgentEnrollmentStatus
    expires_at: datetime
    claimed_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProtectedArtifactCreate(BaseModel):
    """Input to the encrypted vault.

    ``content`` is intentionally non-repr so exceptions/debug output do not
    accidentally print evidence.  The caller must assert that binary evidence
    was reviewed and redacted before it is eligible for persistence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_type: ProtectedArtifactType
    content_type: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reviewed_and_redacted: bool
    content: bytes = Field(min_length=1, max_length=10 * 1024 * 1024, repr=False)

    @field_validator("content_type")
    @classmethod
    def reject_raw_browser_artifacts(cls, value: str) -> str:
        content_type = value.split(";", 1)[0].strip().lower()
        if content_type in {"text/html", "application/xhtml+xml"}:
            raise ValueError("raw HTML is not eligible for protected evidence storage")
        if "browser-profile" in content_type or "storage-state" in content_type:
            raise ValueError("browser state is never eligible for protected evidence storage")
        return content_type

    @model_validator(mode="after")
    def require_reviewed_redaction(self) -> ProtectedArtifactCreate:
        if not self.reviewed_and_redacted:
            raise ValueError("protected artifacts must be reviewed and redacted before storage")
        return self


class ProtectedArtifactRecord(BaseModel):
    """Metadata for one encrypted vault record, without ciphertext or nonce."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    scan_id: int
    artifact_type: ProtectedArtifactType
    content_type: str
    label: str
    metadata: dict[str, Any]
    ciphertext_sha256: str
    created_at: datetime


class ProtectedAuditEvent(BaseModel):
    """A redacted, append-only activity entry."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    scan_id: int
    actor_subject: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=64)
    enrollment_id: str | None = Field(default=None, max_length=64)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("actor_subject")
    @classmethod
    def reject_auth_material_in_actor(cls, value: str) -> str:
        if contains_auth_material(value):
            raise ValueError("audit actor cannot contain authentication material")
        return value

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if not _EVENT_TYPE.fullmatch(value):
            raise ValueError("event_type must be a lowercase dotted identifier")
        return value


class ProtectedIndexPipeline(StrEnum):
    """A source layer safe to retain in a protected report's minimal index."""

    AXE = "axe"
    ALFA = "alfa"
    KEYBOARD = "keyboard"
    RESPONSIVE = "responsive"
    FOCUS = "focus"
    PROTECTED_IMAGE = "protected_image"


class ProtectedIndexFinding(BaseModel):
    """A non-sensitive finding summary sent by a paired companion.

    It intentionally has no selector, HTML, URL, OCR text, screenshot, DOM
    name, or free-form diagnostic. Those data types can contain protected
    content. ``occurrence_key`` is an opaque one-use identifier generated in
    the local companion solely to keep the ordinary SQLite index idempotent.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    pipeline: ProtectedIndexPipeline
    rule_id: str = Field(min_length=1, max_length=128)
    occurrence_key: str = Field(min_length=32, max_length=128)
    wcag_sc: str | None = Field(default=None, max_length=16)
    wcag_scs: tuple[str, ...] = Field(default=(), max_length=12)
    wcag_level: str | None = Field(default=None, max_length=3)
    impact: str | None = Field(default=None, max_length=16)
    engine_outcome: str = "failed"

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _RULE_ID.fullmatch(normalized):
            raise ValueError("protected rule_id is invalid")
        return normalized

    @field_validator("occurrence_key")
    @classmethod
    def validate_occurrence_key(cls, value: str) -> str:
        normalized = value.lower()
        if not _OPAQUE_KEY.fullmatch(normalized):
            raise ValueError("protected occurrence_key must be an opaque hexadecimal value")
        return normalized

    @field_validator("wcag_sc")
    @classmethod
    def validate_primary_sc(cls, value: str | None) -> str | None:
        if value is not None and not _WCAG_SC.fullmatch(value):
            raise ValueError("protected WCAG criterion is invalid")
        return value

    @field_validator("wcag_scs")
    @classmethod
    def validate_all_scs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _WCAG_SC.fullmatch(value) for value in values):
            raise ValueError("protected WCAG criteria are invalid")
        return values

    @field_validator("wcag_level")
    @classmethod
    def validate_level(cls, value: str | None) -> str | None:
        if value is not None and value not in {"A", "AA", "AAA"}:
            raise ValueError("protected WCAG level is invalid")
        return value

    @field_validator("impact")
    @classmethod
    def validate_impact(cls, value: str | None) -> str | None:
        if value is not None and value not in {"critical", "serious", "moderate", "minor"}:
            raise ValueError("protected impact is invalid")
        return value

    @field_validator("engine_outcome")
    @classmethod
    def validate_engine_outcome(cls, value: str) -> str:
        if value not in {"failed", "cant_tell"}:
            raise ValueError("protected engine outcome is invalid")
        return value


class ProtectedPageIndex(BaseModel):
    """A bounded, opaque page-level index record from the companion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_key: str = Field(min_length=32, max_length=128)
    status_code: int = Field(ge=0, le=599)
    axe_evaluated: bool = False
    axe_violations_total: int = Field(default=0, ge=0, le=100_000)
    alfa_evaluated: bool = False
    alfa_failed_total: int = Field(default=0, ge=0, le=100_000)
    alfa_cant_tell_total: int = Field(default=0, ge=0, le=100_000)
    findings: tuple[ProtectedIndexFinding, ...] = Field(default=(), max_length=250)

    @field_validator("page_key")
    @classmethod
    def validate_page_key(cls, value: str) -> str:
        normalized = value.lower()
        if not _OPAQUE_KEY.fullmatch(normalized):
            raise ValueError("protected page_key must be an opaque hexadecimal value")
        return normalized

    @model_validator(mode="after")
    def keep_engine_totals_honest(self) -> ProtectedPageIndex:
        if not self.axe_evaluated and self.axe_violations_total:
            raise ValueError("Axe totals require an evaluated Axe page")
        if not self.alfa_evaluated and (self.alfa_failed_total or self.alfa_cant_tell_total):
            raise ValueError("Alfa totals require an evaluated Alfa page")
        return self


def validate_certificate_fingerprint(value: str) -> str:
    """Validate the SHA-256 fingerprint retained for an mTLS public cert."""

    normalized = value.replace(":", "").lower()
    if not _CERTIFICATE_FINGERPRINT.fullmatch(normalized):
        raise ValueError("certificate fingerprint must be a SHA-256 hex digest")
    return normalized
