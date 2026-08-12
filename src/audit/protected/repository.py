"""Persistence helpers for protected-scan metadata and encrypted evidence.

All browser-session material stays outside this module.  It only stores a
wrapped scan key, encrypted reviewer-redacted evidence, public certificate
fingerprints, and redacted operational audit events.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from audit.db import repo as scan_repo
from audit.db.schema import transaction
from audit.protected.crypto import ProtectedDataIntegrityError, ProtectedVault
from audit.protected.models import (
    AgentEnrollmentCreate,
    AgentEnrollmentRecord,
    AgentEnrollmentStatus,
    ProtectedArtifactCreate,
    ProtectedArtifactRecord,
    ProtectedAuditEvent,
    ProtectedIndexFinding,
    ProtectedIndexPipeline,
    ProtectedPageIndex,
    ProtectedScanCreate,
    ProtectedScanRecord,
    ProtectedScanStatus,
    ProtectedScopeFingerprints,
    ProtectedWorkSpec,
    validate_certificate_fingerprint,
)
from audit.protected.redaction import redact_mapping, redact_text, redact_value
from audit.protected.retention import protected_cleanup_deadline


class ProtectedDataError(ValueError):
    """Base error for a protected-data boundary violation."""


class ProtectedEvidencePurgedError(ProtectedDataError):
    """Raised when evidence passed its mandatory retention deadline."""


class AgentEnrollmentError(ProtectedDataError):
    """Raised without exposing pairing-secret or certificate details."""


_OPAQUE_SCAN_ALIAS = re.compile(r"^protected://report/[A-Za-z0-9_-]{16,128}$")
_SEED_LOCATOR = re.compile(r"^[a-f0-9]{64}$")
_RUN_LEASE_SECONDS = 90
_DEFAULT_PROTECTED_INDEX_PAGE_LIMIT = 100
_MAX_PROTECTED_INDEX_PAGE_LIMIT = 10_000

# A protected report is a one-way, manually authenticated workflow. Keeping
# the graph here, instead of trusting an arbitrary companion event string,
# prevents a retained companion certificate from reopening a completed report
# during the seven-day evidence-retention window.
_ALLOWED_STATUS_TRANSITIONS: dict[ProtectedScanStatus, frozenset[ProtectedScanStatus]] = {
    ProtectedScanStatus.AWAITING_AUTHENTICATION: frozenset(
        {
            ProtectedScanStatus.AWAITING_AUTHENTICATION,
            ProtectedScanStatus.RUNNING,
            ProtectedScanStatus.AUTHENTICATION_REQUIRED,
            ProtectedScanStatus.INTERRUPTED,
            ProtectedScanStatus.FAILED,
        }
    ),
    ProtectedScanStatus.RUNNING: frozenset(
        {
            ProtectedScanStatus.RUNNING,
            ProtectedScanStatus.AUTHENTICATION_REQUIRED,
            ProtectedScanStatus.COMPLETED,
            ProtectedScanStatus.INTERRUPTED,
            ProtectedScanStatus.FAILED,
        }
    ),
    ProtectedScanStatus.AUTHENTICATION_REQUIRED: frozenset(
        {
            ProtectedScanStatus.AUTHENTICATION_REQUIRED,
            ProtectedScanStatus.AWAITING_AUTHENTICATION,
            ProtectedScanStatus.INTERRUPTED,
            ProtectedScanStatus.FAILED,
        }
    ),
    ProtectedScanStatus.INTERRUPTED: frozenset(
        {
            ProtectedScanStatus.INTERRUPTED,
            ProtectedScanStatus.AWAITING_AUTHENTICATION,
            ProtectedScanStatus.FAILED,
        }
    ),
    ProtectedScanStatus.COMPLETED: frozenset({ProtectedScanStatus.COMPLETED}),
    ProtectedScanStatus.FAILED: frozenset({ProtectedScanStatus.FAILED}),
}


def create_protected_scan(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    protected_scan: ProtectedScanCreate,
    work_spec: ProtectedWorkSpec,
    scope_fingerprints: ProtectedScopeFingerprints,
    seed_locator: str,
    vault: ProtectedVault,
    now: datetime | None = None,
) -> ProtectedScanRecord:
    """Create one protected-scan metadata record and its wrapped evidence key.

    ``protected_scan`` contains the short-lived validated request values. The
    private work spec holds the actual seed *and exact origin scope* and is
    encrypted before it reaches SQLite. The ordinary metadata row gets only
    bounded origin counts and caller-provided HMAC scope tags; the repository
    intentionally has no Settings dependency and never receives an HMAC key.
    The generated per-scan AES key lives only long enough to be wrapped by
    ``vault`` and is never included in the returned record.
    """

    created_at = _utc_now(now)
    _require_scan(conn, scan_id)
    _require_opaque_public_scan_row(conn, scan_id=scan_id, work_spec=work_spec)
    _validate_seed_locator(seed_locator)
    _require_work_spec_scope_matches_request(protected_scan, work_spec)
    if get_protected_scan(conn, scan_id=scan_id) is not None:
        raise ProtectedDataError("scan already has protected-scan metadata")

    wrapped_data_key = vault.create_wrapped_scan_key(scan_id)
    serialized_work_spec = _serialize_work_spec(work_spec)
    encrypted_work_spec = vault.encrypt_work_spec(
        scan_id=scan_id,
        data=serialized_work_spec,
        wrapped_data_key=wrapped_data_key,
    )
    cleanup_at = protected_cleanup_deadline(created_at)
    with _transaction_if_needed(conn):
        conn.execute(
            """
            INSERT INTO protected_scans (
                scan_id, target_owner, environment, data_classification, authorized_by,
                authorization_acknowledged, least_privilege_account_acknowledged,
                target_origin_count, auth_origin_count, cdn_origin_count,
                target_scope_fingerprint, auth_scope_fingerprint, cdn_scope_fingerprint,
                local_ai_allowed, local_ai_acknowledged,
                kms_key_id, wrapped_data_key, work_spec_version, work_spec_nonce,
                work_spec_ciphertext, seed_locator, cleanup_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_id,
                protected_scan.target_owner,
                protected_scan.environment.value,
                protected_scan.data_classification.value,
                protected_scan.authorized_by,
                int(protected_scan.authorization_acknowledged),
                int(protected_scan.least_privilege_account_acknowledged),
                len(work_spec.approved_target_origins),
                len(work_spec.approved_auth_origins),
                len(work_spec.approved_cdn_origins),
                scope_fingerprints.target,
                scope_fingerprints.auth,
                scope_fingerprints.cdn,
                int(protected_scan.allow_local_ai),
                int(protected_scan.local_ai_acknowledged),
                vault.kms_key_id,
                wrapped_data_key,
                work_spec.version,
                encrypted_work_spec.nonce,
                encrypted_work_spec.ciphertext,
                seed_locator,
                _sqlite_timestamp(cleanup_at),
                _sqlite_timestamp(created_at),
                _sqlite_timestamp(created_at),
            ),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                actor_subject=protected_scan.authorized_by,
                event_type="protected_scan.created",
                details={
                    "environment": protected_scan.environment.value,
                    "data_classification": protected_scan.data_classification.value,
                    "target_origin_count": len(work_spec.approved_target_origins),
                    "auth_origin_count": len(work_spec.approved_auth_origins),
                    "cdn_origin_count": len(work_spec.approved_cdn_origins),
                    "local_ai_allowed": protected_scan.allow_local_ai,
                },
            ),
        )
    record = get_protected_scan(conn, scan_id=scan_id)
    if record is None:  # pragma: no cover - insert/select invariant
        raise RuntimeError("protected scan insert did not persist")
    return record


def get_protected_scan(conn: sqlite3.Connection, *, scan_id: int) -> ProtectedScanRecord | None:
    """Return safe protected metadata, deliberately omitting all key material."""

    row = conn.execute(
        """
        SELECT scan_id, target_owner, environment, data_classification, authorized_by,
               authorization_acknowledged, least_privilege_account_acknowledged,
               target_origin_count, auth_origin_count, cdn_origin_count,
               target_scope_fingerprint, auth_scope_fingerprint, cdn_scope_fingerprint,
               local_ai_allowed, local_ai_acknowledged,
               protection_status, cleanup_at, evidence_purged_at, key_destroyed_at,
               last_heartbeat_at,
               created_at, updated_at
          FROM protected_scans
         WHERE scan_id = ?
        """,
        (scan_id,),
    ).fetchone()
    return _protected_scan_record(row) if row is not None else None


def get_protected_scan_for_owner(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    authorized_by: str,
) -> ProtectedScanRecord | None:
    """Return a report only when it belongs to the verified proxy subject.

    Protected browser routes use this narrow query rather than looking up a
    report and then deciding whether it may be disclosed.  A missing report
    and another auditor's report therefore produce the same ``None`` result
    at the repository boundary, avoiding scan-ID existence disclosure.
    """

    row = conn.execute(
        """
        SELECT scan_id, target_owner, environment, data_classification, authorized_by,
               authorization_acknowledged, least_privilege_account_acknowledged,
               target_origin_count, auth_origin_count, cdn_origin_count,
               target_scope_fingerprint, auth_scope_fingerprint, cdn_scope_fingerprint,
               local_ai_allowed, local_ai_acknowledged,
               protection_status, cleanup_at, evidence_purged_at, key_destroyed_at,
               last_heartbeat_at,
               created_at, updated_at
          FROM protected_scans
         WHERE scan_id = ? AND authorized_by = ?
        """,
        (scan_id, authorized_by),
    ).fetchone()
    return _protected_scan_record(row) if row is not None else None


def find_active_protected_scan_by_seed_locator(
    conn: sqlite3.Connection,
    *,
    seed_locator: str,
    authorized_by: str | None = None,
) -> int | None:
    """Return an unfinished report matching an opaque locator and owner.

    The locator is an HMAC tag generated at the browser API boundary. It is
    intentionally not an ordinary URL hash, so a database reader cannot run a
    dictionary attack against internal target paths. Browser draft creation
    passes the verified proxy subject so another authorized person cannot
    learn or be blocked by this auditor's in-progress target. The optional
    unscoped form remains for internal maintenance that already has a trusted
    report context.
    """

    _validate_seed_locator(seed_locator)
    if authorized_by is None:
        row = conn.execute(
            """
            SELECT scan_id
              FROM protected_scans
             WHERE seed_locator = ?
               AND evidence_purged_at IS NULL
               AND cleanup_at > CURRENT_TIMESTAMP
               AND work_spec_ciphertext IS NOT NULL
               AND protection_status IN (
                   'awaiting_authentication', 'running',
                   'authentication_required', 'interrupted'
               )
             ORDER BY scan_id DESC LIMIT 1
            """,
            (seed_locator,),
        ).fetchone()
    else:
        row = conn.execute(
            """
        SELECT scan_id
          FROM protected_scans
         WHERE seed_locator = ?
           AND authorized_by = ?
           AND evidence_purged_at IS NULL
           AND cleanup_at > CURRENT_TIMESTAMP
           AND work_spec_ciphertext IS NOT NULL
           AND protection_status IN (
               'awaiting_authentication', 'running',
               'authentication_required', 'interrupted'
           )
         ORDER BY scan_id DESC LIMIT 1
        """,
            (seed_locator, authorized_by),
        ).fetchone()
    return int(row["scan_id"]) if row is not None else None


def get_protected_work_spec(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    vault: ProtectedVault,
) -> ProtectedWorkSpec:
    """Decrypt a scan-bound work spec only for an already-authorized agent.

    Callers must authenticate the companion before this function. Nothing from
    the resulting model is written back to SQLite or included in a human UI
    response; it exists only long enough to form the mTLS work response.
    """

    row = _protected_work_spec_row(conn, scan_id)
    try:
        _require_vault_matches_scan_key_id(vault, row)
        plaintext = vault.decrypt_work_spec(
            scan_id=scan_id,
            nonce=bytes(row["work_spec_nonce"]),
            ciphertext=bytes(row["work_spec_ciphertext"]),
            wrapped_data_key=bytes(row["wrapped_data_key"]),
        )
        return ProtectedWorkSpec.model_validate_json(plaintext)
    except (ProtectedDataError, ProtectedDataIntegrityError, TypeError, ValueError) as exc:
        # Do not distinguish a missing KMS key, altered ciphertext, or a
        # malformed private URL.  A changed KMS configuration is included in
        # that intentionally opaque failure: disclosing the stored KMS ID or
        # whether an old key remains configured would be useful to an attacker.
        raise ProtectedDataError("protected companion work is unavailable") from exc


def set_protected_scan_status(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    status: ProtectedScanStatus,
    actor_subject: str,
    run_lease_id: str | None = None,
) -> ProtectedScanRecord:
    """Advance protected workflow state and retain a redacted audit event."""

    with _transaction_if_needed(conn):
        record_before = get_protected_scan(conn, scan_id=scan_id)
        if record_before is None:
            raise ProtectedDataError("scan is not a protected scan")
        if status not in _ALLOWED_STATUS_TRANSITIONS[record_before.protection_status]:
            raise ProtectedDataError("protected scan status transition is not permitted")
        if run_lease_id is not None:
            _require_current_run_lease(conn, scan_id=scan_id, run_lease_id=run_lease_id)
        if (
            status is ProtectedScanStatus.RUNNING
            and record_before.protection_status is ProtectedScanStatus.RUNNING
        ):
            # A duplicate/late "started" event must never clear an active
            # issue index. The run lease makes retries explicit instead.
            raise ProtectedDataError("protected scan is already running")
        if status in {
            ProtectedScanStatus.AWAITING_AUTHENTICATION,
            ProtectedScanStatus.RUNNING,
            ProtectedScanStatus.AUTHENTICATION_REQUIRED,
        }:
            _require_active_protected_scan(conn, scan_id)
        # A protected report may pause at ``authentication_required`` and
        # resume only after a fresh manual sign-in. Work-spec v3 gives the
        # companion a per-report HMAC key, so retried page/occurrence aliases
        # are stable and ``record_protected_page_index`` is idempotent. Do not
        # clear prior in-scope evidence here: doing so would turn a session
        # expiry into a destructive restart and contradict the resume
        # lifecycle. A newly created report has no index to preserve.
        release_lease = status in {
            ProtectedScanStatus.AUTHENTICATION_REQUIRED,
            ProtectedScanStatus.COMPLETED,
            ProtectedScanStatus.FAILED,
            ProtectedScanStatus.INTERRUPTED,
        }
        conn.execute(
            """
            UPDATE protected_scans
               SET protection_status = ?,
                   run_lease_id = CASE WHEN ? THEN NULL ELSE run_lease_id END,
                   run_lease_expires_at = CASE WHEN ? THEN NULL ELSE run_lease_expires_at END,
                   updated_at = CURRENT_TIMESTAMP
             WHERE scan_id = ?
            """,
            (status.value, int(release_lease), int(release_lease), scan_id),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                actor_subject=actor_subject,
                event_type="protected_scan.status_changed",
                details={"protection_status": status.value},
            ),
        )
    record = get_protected_scan(conn, scan_id=scan_id)
    if record is None:  # pragma: no cover - foreign-key invariant
        raise RuntimeError("protected scan disappeared during status update")
    return record


def interrupt_protected_scan(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    actor_subject: str,
) -> ProtectedScanRecord:
    """Stop a live protected run and revoke its companion certificate use.

    A browser owner cannot remotely control the companion's Chromium process,
    but revoking its enrollment and run lease makes every subsequent work,
    heartbeat, event, or artifact request fail closed. The companion then
    closes its local context at its next bounded service interaction.
    """

    with _transaction_if_needed(conn):
        record = get_protected_scan(conn, scan_id=scan_id)
        if record is None:
            raise ProtectedDataError("scan is not a protected scan")
        if record.protection_status in {ProtectedScanStatus.COMPLETED, ProtectedScanStatus.FAILED}:
            raise ProtectedDataError("protected scan is terminal")
        now = _sqlite_timestamp(_utc_now(None))
        conn.execute(
            """
            UPDATE protected_scans
               SET protection_status = 'interrupted', run_lease_id = NULL,
                   run_lease_expires_at = NULL, updated_at = ?
             WHERE scan_id = ?
            """,
            (now, scan_id),
        )
        conn.execute(
            """
            UPDATE protected_agent_enrollments
               SET status = 'revoked', revoked_at = ?, updated_at = ?
             WHERE scan_id = ? AND status IN ('pending', 'claimed')
            """,
            (now, now, scan_id),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                actor_subject=actor_subject,
                event_type="protected_scan.stopped_by_owner",
                details={},
            ),
        )
    updated = get_protected_scan(conn, scan_id=scan_id)
    if updated is None:  # pragma: no cover - FK invariant
        raise RuntimeError("protected scan disappeared while stopping")
    return updated


def acquire_protected_run_lease(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    enrollment_id: str,
    actor_subject: str,
    now: datetime | None = None,
) -> str:
    """Atomically release one protected work item to one local companion.

    This is the single-host writer boundary for protected crawling. It blocks
    a second runner for the same scan and a concurrent runner for another
    protected report until the heartbeat lease is released or expires.
    """

    current = _utc_now(now)
    expires = current + timedelta(seconds=_RUN_LEASE_SECONDS)
    with _immediate_transaction_if_needed(conn):
        recover_stale_protected_run_leases(conn, now=current)
        record = get_protected_scan(conn, scan_id=scan_id)
        if record is None or record.protection_status not in {
            ProtectedScanStatus.AWAITING_AUTHENTICATION,
            ProtectedScanStatus.AUTHENTICATION_REQUIRED,
            ProtectedScanStatus.INTERRUPTED,
        }:
            raise ProtectedDataError("protected scan is not awaiting a companion handoff")
        _require_active_protected_scan(conn, scan_id)
        busy = conn.execute(
            """
            SELECT scan_id FROM protected_scans
             WHERE run_lease_id IS NOT NULL
               AND run_lease_expires_at > ?
               AND scan_id != ?
             LIMIT 1
            """,
            (_sqlite_timestamp(current), scan_id),
        ).fetchone()
        if busy is not None:
            raise ProtectedDataError("another protected companion is active")
        present = conn.execute(
            """
            SELECT run_lease_id FROM protected_scans
             WHERE scan_id = ? AND run_lease_id IS NOT NULL
               AND run_lease_expires_at > ?
            """,
            (scan_id, _sqlite_timestamp(current)),
        ).fetchone()
        if present is not None:
            raise ProtectedDataError("protected companion work is already leased")
        lease_id = secrets.token_urlsafe(32)
        conn.execute(
            """
            UPDATE protected_scans
               SET run_lease_id = ?, run_lease_expires_at = ?,
                   last_heartbeat_at = ?, updated_at = ?
             WHERE scan_id = ?
            """,
            (
                lease_id,
                _sqlite_timestamp(expires),
                _sqlite_timestamp(current),
                _sqlite_timestamp(current),
                scan_id,
            ),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                enrollment_id=enrollment_id,
                actor_subject=actor_subject,
                event_type="companion.run_leased",
                details={"lease_seconds": _RUN_LEASE_SECONDS},
            ),
        )
    return lease_id


def heartbeat_protected_run_lease(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    enrollment_id: str,
    actor_subject: str,
    run_lease_id: str,
    now: datetime | None = None,
) -> None:
    """Extend an active companion lease without accepting arbitrary text."""

    current = _utc_now(now)
    expires = current + timedelta(seconds=_RUN_LEASE_SECONDS)
    with _transaction_if_needed(conn):
        _require_current_run_lease(conn, scan_id=scan_id, run_lease_id=run_lease_id, now=current)
        conn.execute(
            """
            UPDATE protected_scans
               SET run_lease_expires_at = ?, last_heartbeat_at = ?, updated_at = ?
             WHERE scan_id = ?
            """,
            (
                _sqlite_timestamp(expires),
                _sqlite_timestamp(current),
                _sqlite_timestamp(current),
                scan_id,
            ),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                enrollment_id=enrollment_id,
                actor_subject=actor_subject,
                event_type="companion.heartbeat",
                details={},
            ),
        )


def recover_stale_protected_run_leases(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> list[int]:
    """Interrupt abandoned companion work once its heartbeat expires."""

    current = _utc_now(now)
    rows = conn.execute(
        """
        SELECT scan_id, protection_status
          FROM protected_scans
         WHERE run_lease_id IS NOT NULL
           AND run_lease_expires_at <= ?
        """,
        (_sqlite_timestamp(current),),
    ).fetchall()
    scan_ids = [int(row["scan_id"]) for row in rows]
    for row in rows:
        scan_id = int(row["scan_id"])
        status = str(row["protection_status"])
        next_status = (
            ProtectedScanStatus.INTERRUPTED.value
            if status
            in {
                ProtectedScanStatus.AWAITING_AUTHENTICATION.value,
                ProtectedScanStatus.RUNNING.value,
            }
            else status
        )
        conn.execute(
            """
            UPDATE protected_scans
               SET protection_status = ?, run_lease_id = NULL,
                   run_lease_expires_at = NULL, updated_at = ?
             WHERE scan_id = ?
            """,
            (next_status, _sqlite_timestamp(current), scan_id),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                actor_subject="system",
                event_type="companion.run_lease_expired",
                details={},
            ),
        )
    return scan_ids


def create_agent_enrollment(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    enrollment: AgentEnrollmentCreate,
    pairing_code: str,
    now: datetime | None = None,
    enrollment_id: str | None = None,
) -> AgentEnrollmentRecord:
    """Create a one-time enrollment pre-bound to one certificate fingerprint.

    ``pairing_code`` is intentionally accepted as a scalar instead of a model
    field so it cannot be serialized with any public request/response record.
    Callers must generate and transport it through their mTLS pairing channel.
    """

    created_at = _utc_now(now)
    expires_at = _as_utc(enrollment.expires_at)
    if expires_at <= created_at:
        raise AgentEnrollmentError("agent enrollment must expire in the future")
    if len(pairing_code) < 16:
        raise AgentEnrollmentError("agent enrollment pairing code is invalid")
    _require_active_protected_scan(conn, scan_id)
    protected_scan = get_protected_scan(conn, scan_id=scan_id)
    if protected_scan is None:  # pragma: no cover - guarded by the active check
        raise AgentEnrollmentError("agent enrollment is unavailable")
    if protected_scan.protection_status not in {
        ProtectedScanStatus.AWAITING_AUTHENTICATION,
        ProtectedScanStatus.AUTHENTICATION_REQUIRED,
        ProtectedScanStatus.INTERRUPTED,
    }:
        raise AgentEnrollmentError("agent enrollment is unavailable")
    identifier = enrollment_id or str(uuid.uuid4())
    verifier = _hash_pairing_code(pairing_code)
    with _transaction_if_needed(conn):
        # A browser reload/double click must not leave several independently
        # usable pairing codes for the same report. Revoke prior unclaimed
        # enrollment records atomically before minting the sole fresh code.
        conn.execute(
            """
            UPDATE protected_agent_enrollments
               SET status = 'revoked', revoked_at = ?, updated_at = ?
             WHERE scan_id = ? AND status = 'pending'
            """,
            (_sqlite_timestamp(created_at), _sqlite_timestamp(created_at), scan_id),
        )
        existing_claim = conn.execute(
            """
            SELECT 1
              FROM protected_agent_enrollments
             WHERE scan_id = ? AND status = 'claimed'
             LIMIT 1
            """,
            (scan_id,),
        ).fetchone()
        if existing_claim is not None:
            # Do not mint a pairing secret which cannot be used. A protected
            # report is deliberately bound to one companion until an explicit
            # operational certificate-rotation procedure is performed.
            raise AgentEnrollmentError("agent enrollment is unavailable")
        conn.execute(
            """
            INSERT INTO protected_agent_enrollments (
                id, scan_id, identity_subject, certificate_fingerprint,
                pairing_code_hash, expires_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identifier,
                scan_id,
                enrollment.identity_subject,
                enrollment.certificate_fingerprint,
                verifier,
                _sqlite_timestamp(expires_at),
                _sqlite_timestamp(created_at),
                _sqlite_timestamp(created_at),
            ),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                enrollment_id=identifier,
                actor_subject=enrollment.identity_subject,
                event_type="agent_enrollment.created",
                details={
                    "expires_at": _sqlite_timestamp(expires_at),
                    "certificate_fingerprint": enrollment.certificate_fingerprint,
                },
            ),
        )
    return _get_agent_enrollment(conn, identifier)


def claim_agent_enrollment(
    conn: sqlite3.Connection,
    *,
    enrollment_id: str,
    pairing_code: str,
    certificate_fingerprint: str,
    now: datetime | None = None,
) -> AgentEnrollmentRecord:
    """Claim a pre-bound pending enrollment after mTLS verification."""

    claimed_at = _utc_now(now)
    fingerprint = validate_certificate_fingerprint(certificate_fingerprint)
    row = conn.execute(
        """
        SELECT id, scan_id, identity_subject, certificate_fingerprint,
               pairing_code_hash, status, expires_at
          FROM protected_agent_enrollments WHERE id = ?
        """,
        (enrollment_id,),
    ).fetchone()
    if row is None:
        raise AgentEnrollmentError("agent enrollment is unavailable")
    if (
        str(row["status"]) != AgentEnrollmentStatus.PENDING.value
        or row["certificate_fingerprint"] is None
        or not hmac.compare_digest(str(row["certificate_fingerprint"]), fingerprint)
    ):
        raise AgentEnrollmentError("agent enrollment is unavailable")
    try:
        _require_active_protected_scan(conn, int(row["scan_id"]))
    except ProtectedEvidencePurgedError as exc:
        raise AgentEnrollmentError("agent enrollment is unavailable") from exc
    if _as_utc(row["expires_at"]) <= claimed_at:
        with _transaction_if_needed(conn):
            conn.execute(
                """
                UPDATE protected_agent_enrollments
                   SET status = 'expired', updated_at = ?
                 WHERE id = ? AND status = 'pending'
                """,
                (_sqlite_timestamp(claimed_at), enrollment_id),
            )
        raise AgentEnrollmentError("agent enrollment is unavailable")
    if not _verify_pairing_code(pairing_code, str(row["pairing_code_hash"])):
        raise AgentEnrollmentError("agent enrollment is unavailable")
    with _transaction_if_needed(conn):
        existing_claim = conn.execute(
            """
            SELECT 1
              FROM protected_agent_enrollments
             WHERE scan_id = ? AND status = 'claimed'
             LIMIT 1
            """,
            (int(row["scan_id"]),),
        ).fetchone()
        if existing_claim is not None:
            # A scan has one paired companion. Rotation is deliberately an
            # explicit operational procedure, not an implicit second agent
            # with the same protected report scope.
            raise AgentEnrollmentError("agent enrollment is unavailable")
        try:
            updated = conn.execute(
                """
                UPDATE protected_agent_enrollments
                   SET status = 'claimed', claimed_at = ?,
                       updated_at = ?
                 WHERE id = ? AND status = 'pending'
                """,
                (
                    _sqlite_timestamp(claimed_at),
                    _sqlite_timestamp(claimed_at),
                    enrollment_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AgentEnrollmentError("agent certificate is already enrolled") from exc
        if updated.rowcount != 1:
            raise AgentEnrollmentError("agent enrollment is unavailable")
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=int(row["scan_id"]),
                enrollment_id=enrollment_id,
                actor_subject=str(row["identity_subject"]),
                event_type="agent_enrollment.claimed",
                details={"certificate_fingerprint": fingerprint},
            ),
        )
    return _get_agent_enrollment(conn, enrollment_id)


def record_protected_audit_event(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    actor_subject: str,
    event_type: str,
    details: Mapping[str, Any] | None = None,
    enrollment_id: str | None = None,
) -> int:
    """Append a sanitized accountability event and return its database id."""

    _require_protected_scan(conn, scan_id)
    event = ProtectedAuditEvent(
        scan_id=scan_id,
        actor_subject=actor_subject,
        event_type=event_type,
        enrollment_id=enrollment_id,
        details=dict(details or {}),
    )
    with _transaction_if_needed(conn):
        return _insert_audit_event(conn, event=event)


def record_protected_page_index(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page: ProtectedPageIndex,
    actor_subject: str,
    enrollment_id: str,
) -> int:
    """Persist the deliberately minimal, non-sensitive protected issue index.

    The companion never submits a URL, title, selector, DOM/HTML snippet,
    image URL, OCR text, screenshot, or free-form diagnostic here.  The
    ordinary scan tables hold only opaque aliases and rule/count metadata so
    the existing review queue remains useful without becoming a plaintext
    evidence store.  Detailed evidence is available only through explicitly
    reviewed encrypted artifacts, if an auditor elects to add one.
    """
    _require_active_protected_scan(conn, scan_id)
    page_alias = f"protected://report/{scan_id}/page/{page.page_key[:24]}"
    safe_help = "Automated protected-scan evidence; manual verification is required."
    safe_selector = "Protected evidence is not retained in the ordinary index."
    safe_summary = "Detected in an authenticated browser session; verify manually."

    # The companion is normally serial, but a valid mTLS client could retry
    # concurrently after a transport failure. Take SQLite's writer lock while
    # checking and inserting so no pair of new opaque keys can race past the
    # report's persisted page budget. Existing keys remain idempotent retries
    # and are checked before the capacity rule.
    with _immediate_transaction_if_needed(conn):
        # Agent events are deliberately replay-resistant at the HTTP boundary,
        # but the persistence boundary must be safe on its own as well. A
        # retry after a lost response cannot inflate page/engine totals or
        # duplicate findings: the companion's opaque page key is stable for
        # this one scanned page and maps to one opaque in-report alias.
        existing_page = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? AND url_normalized = ?",
            (scan_id, page_alias),
        ).fetchone()
        if existing_page is not None:
            return int(existing_page["id"])
        if _protected_index_page_count(conn, scan_id) >= _protected_index_page_limit(conn, scan_id):
            raise ProtectedDataError("protected page-index capacity reached")
        page_id = scan_repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized=page_alias,
            status_code=page.status_code or None,
            title=None,
            render_mode="js",
            html_hash=None,
        )
        for finding in page.findings:
            _upsert_protected_index_finding(
                conn,
                scan_id=scan_id,
                page_id=page_id,
                finding=finding,
                safe_help=safe_help,
                safe_selector=safe_selector,
                safe_summary=safe_summary,
            )

        if page.axe_evaluated:
            scan_repo.increment_scan_axe_counters(
                conn,
                scan_id=scan_id,
                pages_delta=1,
                violations_delta=page.axe_violations_total,
            )
        if page.alfa_evaluated:
            scan_repo.increment_scan_alfa_counters(
                conn,
                scan_id=scan_id,
                pages_delta=1,
                failed_delta=page.alfa_failed_total,
                cant_tell_delta=page.alfa_cant_tell_total,
            )
        page_count_row = conn.execute(
            "SELECT COUNT(*) AS n FROM pages WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        conn.execute(
            "UPDATE scans SET page_count = ? WHERE id = ?",
            (int(page_count_row["n"]), scan_id),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                enrollment_id=enrollment_id,
                actor_subject=actor_subject,
                event_type="companion.page_indexed",
                details={
                    "finding_count": len(page.findings),
                    "axe_evaluated": page.axe_evaluated,
                    "alfa_evaluated": page.alfa_evaluated,
                },
            ),
        )
    return page_id


def _upsert_protected_index_finding(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page_id: int,
    finding: ProtectedIndexFinding,
    safe_help: str,
    safe_selector: str,
    safe_summary: str,
) -> None:
    """Write a source-transparent index finding without accepting evidence text."""
    wcag_scs = ",".join(finding.wcag_scs) or None
    if finding.pipeline is ProtectedIndexPipeline.AXE:
        scan_repo.upsert_axe_violation(
            conn,
            page_id=page_id,
            scan_id=scan_id,
            rule_id=finding.rule_id,
            wcag_sc=finding.wcag_sc,
            wcag_scs=wcag_scs,
            wcag_level=finding.wcag_level,
            impact=finding.impact,
            help=safe_help,
            help_url="",
            target_selector=safe_selector,
            failure_summary=safe_summary,
            html_snippet="",
            target_hash=finding.occurrence_key,
        )
        return
    if finding.pipeline is ProtectedIndexPipeline.ALFA:
        scan_repo.upsert_alfa_finding(
            conn,
            page_id=page_id,
            scan_id=scan_id,
            rule_id=finding.rule_id,
            wcag_sc=finding.wcag_sc,
            wcag_scs=wcag_scs,
            wcag_level=finding.wcag_level,
            help=safe_help,
            help_url="",
            target_selector=safe_selector,
            failure_summary=safe_summary,
            html_snippet="",
            target_hash=finding.occurrence_key,
            engine_outcome=finding.engine_outcome,
            engine_evidence_json='{"protected_evidence":"not_retained"}',
        )
        return
    scan_repo.upsert_keyboard_finding(
        conn,
        page_id=page_id,
        scan_id=scan_id,
        rule_id=finding.rule_id,
        wcag_sc=finding.wcag_sc,
        wcag_scs=wcag_scs,
        wcag_level=finding.wcag_level,
        impact=finding.impact,
        help=safe_help,
        help_url="",
        target_selector=safe_selector,
        failure_summary=safe_summary,
        html_snippet="",
        target_hash=finding.occurrence_key,
        criterion_sc=finding.wcag_sc or "",
        pipeline=finding.pipeline.value,
    )


def store_protected_artifact(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    artifact: ProtectedArtifactCreate,
    vault: ProtectedVault,
) -> ProtectedArtifactRecord:
    """Redact, encrypt, and persist reviewed evidence without exposing its plaintext."""

    scan_row = _protected_vault_row(conn, scan_id)
    _require_vault_matches_scan_key_id(vault, scan_row)
    wrapped_data_key = scan_row["wrapped_data_key"]
    if wrapped_data_key is None or scan_row["evidence_purged_at"] is not None:
        raise ProtectedEvidencePurgedError("protected evidence has been erased")
    artifact_id = str(uuid.uuid4())
    plaintext = _redact_artifact_content(artifact)
    encrypted = vault.encrypt(
        scan_id=scan_id,
        artifact_id=artifact_id,
        data=plaintext,
        wrapped_data_key=bytes(wrapped_data_key),
    )
    metadata = redact_mapping(artifact.metadata)
    label = redact_text(artifact.label)
    digest = hashlib.sha256(encrypted.ciphertext).hexdigest()
    with _transaction_if_needed(conn):
        conn.execute(
            """
            INSERT INTO protected_artifacts (
                id, scan_id, artifact_type, content_type, label, metadata_json,
                nonce, ciphertext, ciphertext_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                scan_id,
                artifact.artifact_type.value,
                artifact.content_type,
                label,
                _json(metadata),
                encrypted.nonce,
                encrypted.ciphertext,
                digest,
            ),
        )
        _insert_audit_event(
            conn,
            event=ProtectedAuditEvent(
                scan_id=scan_id,
                actor_subject="system",
                event_type="protected_artifact.stored",
                details={"artifact_type": artifact.artifact_type.value, "artifact_id": artifact_id},
            ),
        )
    return _get_artifact_record(conn, scan_id=scan_id, artifact_id=artifact_id)


def decrypt_protected_artifact(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    artifact_id: str,
    vault: ProtectedVault,
) -> bytes:
    """Decrypt one scan-scoped artifact for an already-authorized caller."""

    vault_row = _protected_vault_row(conn, scan_id)
    _require_vault_matches_scan_key_id(vault, vault_row)
    if vault_row["wrapped_data_key"] is None or vault_row["evidence_purged_at"] is not None:
        raise ProtectedEvidencePurgedError("protected evidence has been erased")
    row = conn.execute(
        """
        SELECT a.id, a.nonce, a.ciphertext, p.wrapped_data_key, p.evidence_purged_at
          FROM protected_artifacts a
          JOIN protected_scans p ON p.scan_id = a.scan_id
         WHERE a.id = ? AND a.scan_id = ?
        """,
        (artifact_id, scan_id),
    ).fetchone()
    if row is None:
        raise ProtectedDataError("protected artifact is unavailable")
    return vault.decrypt(
        scan_id=scan_id,
        artifact_id=str(row["id"]),
        nonce=bytes(row["nonce"]),
        ciphertext=bytes(row["ciphertext"]),
        wrapped_data_key=bytes(vault_row["wrapped_data_key"]),
    )


def purge_expired_protected_data(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    vault: ProtectedVault | None = None,
) -> list[int]:
    """Purge evidence whose mandatory seven-day deadline passed.

    When a vault is supplied, its production KMS must first revoke the
    scan-scoped key/grant, making older SQLite/WAL/backup copies of encrypted
    records unreadable. The database then removes ciphertext and wrapped-key
    records atomically while retaining the non-sensitive approval/audit trail.
    A configured vault is mandatory once a report is due. If an operator
    removes KMS configuration, protected reads are already unavailable at the
    deadline; leaving the rows intact and raising an operational error is
    safer than falsely marking an unrevokeable key as destroyed.
    """

    purged_at = _utc_now(now)
    due_rows = conn.execute(
        """
        SELECT scan_id, kms_key_id, wrapped_data_key, evidence_purged_at,
               key_destroyed_at
          FROM protected_scans
         WHERE evidence_purged_at IS NULL AND cleanup_at <= ?
         ORDER BY scan_id
        """,
        (_sqlite_timestamp(purged_at),),
    ).fetchall()
    scan_ids = [int(row["scan_id"]) for row in due_rows]
    if not scan_ids:
        return []
    if vault is None:
        raise ProtectedDataError("protected scan-key destruction requires a configured vault")
    # Validate every due record before revoking any key.  A deployment with a
    # rotated/misconfigured vault must not partially purge a mixed batch and
    # then falsely imply all reports received their mandatory crypto-erasure.
    for row in due_rows:
        _require_vault_matches_scan_key_id(vault, row)
    _require_irreversible_scan_key_destruction(vault)
    try:
        for scan_id in scan_ids:
            vault.destroy_scan_key(scan_id)
    except Exception as exc:
        # Fail closed: retained ciphertext must not be marked erased when
        # the production KMS has not confirmed its scan-key revocation.
        raise ProtectedDataError("protected scan-key destruction failed") from exc
    with _transaction_if_needed(conn):
        for scan_id in scan_ids:
            conn.execute("DELETE FROM protected_artifacts WHERE scan_id = ?", (scan_id,))
            conn.execute(
                """
                UPDATE protected_scans
                   SET wrapped_data_key = NULL, work_spec_nonce = NULL,
                       work_spec_ciphertext = NULL, seed_locator = NULL,
                       evidence_purged_at = ?, key_destroyed_at = ?, updated_at = ?
                 WHERE scan_id = ? AND evidence_purged_at IS NULL
                """,
                (
                    _sqlite_timestamp(purged_at),
                    _sqlite_timestamp(purged_at),
                    _sqlite_timestamp(purged_at),
                    scan_id,
                ),
            )
            _insert_audit_event(
                conn,
                event=ProtectedAuditEvent(
                    scan_id=scan_id,
                    actor_subject="system",
                    event_type="protected_data.purged",
                    details={
                        "retention_days": 7,
                        "kms_key_revocation": True,
                    },
                ),
            )
    return scan_ids


def destroy_protected_scan_key(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    vault: ProtectedVault,
) -> None:
    """Irreversibly revoke a protected report's key before report deletion.

    The KMS identifier is durable metadata, not an advisory label.  A server
    restarted with a different vault must fail closed rather than ask that
    other vault to destroy ``scan:{id}``, which could leave the original
    ciphertext decryptable in a backup.  Reports already cryptographically
    erased have no remaining protected key path and can be removed as a
    non-sensitive audit-record cleanup.
    """

    row = _protected_key_row(conn, scan_id)
    if row["evidence_purged_at"] is not None or row["key_destroyed_at"] is not None:
        return
    _require_vault_matches_scan_key_id(vault, row)
    _require_irreversible_scan_key_destruction(vault)
    try:
        vault.destroy_scan_key(scan_id)
    except Exception as exc:
        raise ProtectedDataError("protected scan-key destruction failed") from exc


def _protected_scan_record(row: sqlite3.Row) -> ProtectedScanRecord:
    return ProtectedScanRecord.model_validate(
        {
            "scan_id": int(row["scan_id"]),
            "target_owner": str(row["target_owner"]),
            "environment": str(row["environment"]),
            "data_classification": str(row["data_classification"]),
            "authorized_by": str(row["authorized_by"]),
            "authorization_acknowledged": bool(row["authorization_acknowledged"]),
            "least_privilege_account_acknowledged": bool(
                row["least_privilege_account_acknowledged"]
            ),
            "target_origin_count": _safe_origin_count(row["target_origin_count"], maximum=32),
            "auth_origin_count": _safe_origin_count(row["auth_origin_count"], maximum=32),
            "cdn_origin_count": _safe_origin_count(row["cdn_origin_count"], maximum=64),
            "target_scope_fingerprint": _safe_scope_fingerprint(row["target_scope_fingerprint"]),
            "auth_scope_fingerprint": _safe_scope_fingerprint(row["auth_scope_fingerprint"]),
            "cdn_scope_fingerprint": _safe_scope_fingerprint(row["cdn_scope_fingerprint"]),
            "allow_local_ai": bool(row["local_ai_allowed"]),
            "local_ai_acknowledged": bool(row["local_ai_acknowledged"]),
            "protection_status": str(row["protection_status"]),
            "cleanup_at": _as_utc(row["cleanup_at"]),
            "evidence_purged_at": _as_utc_or_none(row["evidence_purged_at"]),
            "key_destroyed_at": _as_utc_or_none(row["key_destroyed_at"]),
            "last_heartbeat_at": _as_utc_or_none(row["last_heartbeat_at"]),
            "created_at": _as_utc(row["created_at"]),
            "updated_at": _as_utc(row["updated_at"]),
        }
    )


def _get_agent_enrollment(conn: sqlite3.Connection, enrollment_id: str) -> AgentEnrollmentRecord:
    row = conn.execute(
        """
        SELECT id, scan_id, identity_subject, certificate_fingerprint, status, expires_at,
               claimed_at, revoked_at, created_at, updated_at
          FROM protected_agent_enrollments WHERE id = ?
        """,
        (enrollment_id,),
    ).fetchone()
    if row is None:  # pragma: no cover - post-write invariant
        raise RuntimeError("agent enrollment disappeared after write")
    return _agent_enrollment_record(row)


def get_claimed_agent_enrollment(
    conn: sqlite3.Connection, *, scan_id: int
) -> AgentEnrollmentRecord | None:
    """Return the one non-secret claimed companion for a protected report.

    The pairing-code verifier is deliberately excluded from this query. The
    browser uses this only to show a safe re-run command after expiry; it
    cannot create a second companion or recover a pairing secret.
    """

    row = conn.execute(
        """
        SELECT id, scan_id, identity_subject, certificate_fingerprint, status, expires_at,
               claimed_at, revoked_at, created_at, updated_at
          FROM protected_agent_enrollments
         WHERE scan_id = ? AND status = 'claimed'
         ORDER BY claimed_at DESC, id DESC
         LIMIT 1
        """,
        (scan_id,),
    ).fetchone()
    return _agent_enrollment_record(row) if row is not None else None


def _agent_enrollment_record(row: sqlite3.Row) -> AgentEnrollmentRecord:
    return AgentEnrollmentRecord.model_validate(
        {
            "id": str(row["id"]),
            "scan_id": int(row["scan_id"]),
            "identity_subject": str(row["identity_subject"]),
            "certificate_fingerprint": row["certificate_fingerprint"],
            "status": str(row["status"]),
            "expires_at": _as_utc(row["expires_at"]),
            "claimed_at": _as_utc_or_none(row["claimed_at"]),
            "revoked_at": _as_utc_or_none(row["revoked_at"]),
            "created_at": _as_utc(row["created_at"]),
            "updated_at": _as_utc(row["updated_at"]),
        }
    )


def _get_artifact_record(
    conn: sqlite3.Connection, *, scan_id: int, artifact_id: str
) -> ProtectedArtifactRecord:
    row = conn.execute(
        """
        SELECT id, scan_id, artifact_type, content_type, label, metadata_json,
               ciphertext_sha256, created_at
          FROM protected_artifacts
         WHERE scan_id = ? AND id = ?
        """,
        (scan_id, artifact_id),
    ).fetchone()
    if row is None:  # pragma: no cover - post-write invariant
        raise RuntimeError("protected artifact disappeared after write")
    return ProtectedArtifactRecord.model_validate(
        {
            "id": str(row["id"]),
            "scan_id": int(row["scan_id"]),
            "artifact_type": str(row["artifact_type"]),
            "content_type": str(row["content_type"]),
            "label": str(row["label"]),
            "metadata": _json_load(row["metadata_json"]),
            "ciphertext_sha256": str(row["ciphertext_sha256"]),
            "created_at": _as_utc(row["created_at"]),
        }
    )


def _protected_vault_row(conn: sqlite3.Connection, scan_id: int) -> sqlite3.Row:
    row = _protected_key_row(conn, scan_id)
    if _retention_deadline_passed(row["cleanup_at"]):
        raise ProtectedEvidencePurgedError("protected evidence retention deadline passed")
    return row


def _protected_index_page_limit(conn: sqlite3.Connection, scan_id: int) -> int:
    """Return the bounded, persisted page budget for a protected index.

    ``max_pages`` is non-sensitive operational metadata in the ordinary scan
    configuration. Exact URLs and origins remain exclusively in the encrypted
    work spec. A pre-hardening or malformed row gets the conservative protected
    default rather than turning a database/configuration fault into unlimited
    companion write authority.
    """

    row = conn.execute("SELECT config_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if row is None:
        raise ProtectedDataError("scan does not exist")
    try:
        config = _json_load(row["config_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return _DEFAULT_PROTECTED_INDEX_PAGE_LIMIT
    if not isinstance(config, dict):
        return _DEFAULT_PROTECTED_INDEX_PAGE_LIMIT
    max_pages = config.get("max_pages")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        return _DEFAULT_PROTECTED_INDEX_PAGE_LIMIT
    return min(max_pages, _MAX_PROTECTED_INDEX_PAGE_LIMIT)


def _protected_index_page_count(conn: sqlite3.Connection, scan_id: int) -> int:
    """Return the actual opaque-page count used for the protected hard cap."""

    row = conn.execute(
        "SELECT COUNT(*) AS n FROM pages WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    return int(row["n"] if row is not None else 0)


def _protected_key_row(conn: sqlite3.Connection, scan_id: int) -> sqlite3.Row:
    """Return the small key-lifecycle record without releasing private work.

    This query deliberately does not apply the seven-day access cutoff.  A
    report that has reached that cutoff still needs its *original* KMS binding
    checked before an operator can cryptographically erase it or delete it.
    """

    row = conn.execute(
        """
        SELECT scan_id, kms_key_id, wrapped_data_key, evidence_purged_at,
               key_destroyed_at, cleanup_at
          FROM protected_scans WHERE scan_id = ?
        """,
        (scan_id,),
    ).fetchone()
    if row is None:
        raise ProtectedDataError("scan is not a protected scan")
    return cast(sqlite3.Row, row)


def _protected_work_spec_row(conn: sqlite3.Connection, scan_id: int) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT scan_id, kms_key_id, wrapped_data_key, work_spec_version,
               work_spec_nonce, work_spec_ciphertext, evidence_purged_at,
               cleanup_at
          FROM protected_scans
         WHERE scan_id = ?
        """,
        (scan_id,),
    ).fetchone()
    if row is None:
        raise ProtectedDataError("scan is not a protected scan")
    if (
        row["evidence_purged_at"] is not None
        or _retention_deadline_passed(row["cleanup_at"])
        or row["wrapped_data_key"] is None
        # Work-spec v3 carries the encrypted, per-report HMAC key used to
        # derive stable opaque page/occurrence IDs. Older v2 work was
        # deliberately invalidated by migration 0018: resuming it could
        # create a second, unlinkable copy of the same protected evidence
        # after manual re-authentication.
        or row["work_spec_version"] != 3
        or row["work_spec_nonce"] is None
        or row["work_spec_ciphertext"] is None
    ):
        raise ProtectedEvidencePurgedError("protected companion work is unavailable")
    return cast(sqlite3.Row, row)


def _require_vault_matches_scan_key_id(vault: ProtectedVault, row: sqlite3.Row) -> None:
    """Refuse to use a different KMS than the report was encrypted with.

    ``kms_key_id`` is non-secret operational metadata, but returning either
    value would reveal key-management topology to an untrusted companion or
    browser.  The caller therefore gets one safe, generic error for a missing,
    malformed, or changed vault.  This guard is required before every unwrap,
    encryption write, and destructive revoke; an injected vault is not a
    license to operate on records created by a different KMS.
    """

    try:
        expected = str(row["kms_key_id"])
        actual = vault.kms_key_id
    except Exception as exc:  # pragma: no cover - defensive adapter boundary
        raise ProtectedDataError("protected evidence key manager is unavailable") from exc
    if not expected or not actual or not hmac.compare_digest(expected, actual):
        raise ProtectedDataError("protected evidence key manager is unavailable")


def _require_irreversible_scan_key_destruction(vault: ProtectedVault) -> None:
    """Require real historical-backup crypto-erasure before destroying rows."""

    try:
        supported = vault.supports_irreversible_scan_key_destruction
    except Exception as exc:  # pragma: no cover - defensive adapter boundary
        raise ProtectedDataError(
            "protected scan-key destruction requires an irreversible key manager"
        ) from exc
    if not supported:
        raise ProtectedDataError(
            "protected scan-key destruction requires an irreversible key manager"
        )


def _require_scan(conn: sqlite3.Connection, scan_id: int) -> None:
    if scan_id <= 0:
        raise ProtectedDataError("scan id must be positive")
    row = conn.execute("SELECT 1 FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if row is None:
        raise ProtectedDataError("scan does not exist")


def _require_protected_scan(conn: sqlite3.Connection, scan_id: int) -> None:
    _protected_vault_row(conn, scan_id)


def _require_active_protected_scan(conn: sqlite3.Connection, scan_id: int) -> None:
    _protected_work_spec_row(conn, scan_id)


def _require_current_run_lease(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    run_lease_id: str,
    now: datetime | None = None,
) -> None:
    """Require one unexpired opaque lease without disclosing its state."""

    if not run_lease_id or len(run_lease_id) > 200:
        raise ProtectedDataError("protected companion lease is unavailable")
    current = _utc_now(now)
    row = conn.execute(
        """
        SELECT run_lease_id, run_lease_expires_at
          FROM protected_scans
         WHERE scan_id = ?
        """,
        (scan_id,),
    ).fetchone()
    if (
        row is None
        or row["run_lease_id"] is None
        or row["run_lease_expires_at"] is None
        or not hmac.compare_digest(str(row["run_lease_id"]), run_lease_id)
        or _as_utc(row["run_lease_expires_at"]) <= current
    ):
        raise ProtectedDataError("protected companion lease is unavailable")


def _require_opaque_public_scan_row(
    conn: sqlite3.Connection, *, scan_id: int, work_spec: ProtectedWorkSpec
) -> None:
    """Ensure the ordinary scan row is never a plaintext protected target."""

    row = conn.execute(
        "SELECT seed_url, config_json FROM scans WHERE id = ?", (scan_id,)
    ).fetchone()
    if row is None:  # _require_scan already provides the clearer error path.
        raise ProtectedDataError("scan does not exist")
    alias = str(row["seed_url"])
    if not _OPAQUE_SCAN_ALIAS.fullmatch(alias):
        raise ProtectedDataError("protected scan requires an opaque public alias")
    try:
        public_config = _json_load(row["config_json"])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProtectedDataError("protected scan public configuration is invalid") from exc
    if not isinstance(public_config, dict) or public_config.get("seed_url") != alias:
        raise ProtectedDataError("protected scan public configuration lacks its opaque alias")
    if public_config.get("protected_work_spec") != "encrypted":
        raise ProtectedDataError("protected scan public configuration is not protected")
    # These checks are intentionally exact rather than redaction-based: a
    # scoped path or a hostname might be non-secret in isolation yet is still
    # protected evidence. Exact origin scope belongs only in the encrypted
    # work spec, never in the public scan alias/configuration row.
    encrypted_only_values = (
        work_spec.seed_url,
        *work_spec.approved_target_origins,
        *work_spec.approved_auth_origins,
        *work_spec.approved_cdn_origins,
    )
    if any(value in alias for value in encrypted_only_values) or _contains_private_scope(
        public_config, encrypted_only_values
    ):
        raise ProtectedDataError("protected scan public configuration contains private scope")


def _require_work_spec_scope_matches_request(
    protected_scan: ProtectedScanCreate, work_spec: ProtectedWorkSpec
) -> None:
    """Reject a split-scope insert before any metadata is persisted.

    The request-model origins exist only while the browser creation request is
    validated.  The encrypted work spec must receive the same canonical
    values; otherwise a caller could show one reviewed allowlist while giving
    the companion a broader one.
    """

    request_scope = (
        protected_scan.approved_target_origins,
        protected_scan.approved_auth_origins,
        protected_scan.approved_cdn_origins,
    )
    encrypted_scope = (
        work_spec.approved_target_origins,
        work_spec.approved_auth_origins,
        work_spec.approved_cdn_origins,
    )
    if request_scope != encrypted_scope:
        raise ProtectedDataError("protected work scope does not match the approved request")


def _contains_private_scope(value: Any, private_values: tuple[str, ...]) -> bool:
    """Detect exact protected scope in parsed public configuration values.

    Inspecting the parsed JSON closes an escaping side channel such as
    ``https\\u003a//internal.example.edu`` that a raw SQL-string search would
    miss. The public configuration is bounded and expected to be a small
    mapping, so recursive validation is intentionally simple and strict.
    """

    if isinstance(value, str):
        return any(private_value in value for private_value in private_values)
    if isinstance(value, Mapping):
        return any(
            _contains_private_scope(str(key), private_values)
            or _contains_private_scope(item, private_values)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_private_scope(item, private_values) for item in value)
    return False


def _validate_seed_locator(value: str) -> None:
    if not _SEED_LOCATOR.fullmatch(value):
        raise ProtectedDataError("protected seed locator is invalid")


def _serialize_work_spec(work_spec: ProtectedWorkSpec) -> bytes:
    try:
        serialized = _json(work_spec.model_dump(mode="json")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtectedDataError("protected work specification is invalid") from exc
    if len(serialized) > 64 * 1024:
        raise ProtectedDataError("protected work specification is too large")
    return serialized


def _insert_audit_event(conn: sqlite3.Connection, *, event: ProtectedAuditEvent) -> int:
    if event.enrollment_id is not None:
        matching_enrollment = conn.execute(
            "SELECT 1 FROM protected_agent_enrollments WHERE id = ? AND scan_id = ?",
            (event.enrollment_id, event.scan_id),
        ).fetchone()
        if matching_enrollment is None:
            raise ProtectedDataError("agent enrollment does not belong to this protected scan")
    details = redact_mapping(event.details)
    cur = conn.execute(
        """
        INSERT INTO protected_audit_events (
            scan_id, enrollment_id, actor_subject, event_type, details_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            event.scan_id,
            event.enrollment_id,
            event.actor_subject,
            event.event_type,
            _json(details),
        ),
    )
    if cur.lastrowid is None:  # pragma: no cover - SQLite INSERT invariant
        raise RuntimeError("protected audit event insert did not return an id")
    return int(cur.lastrowid)


def _redact_artifact_content(artifact: ProtectedArtifactCreate) -> bytes:
    """Redact textual evidence automatically; binary is allowed only after review."""

    content_type = artifact.content_type
    if content_type == "application/json" or content_type.endswith("+json"):
        decoded = artifact.content.decode("utf-8", errors="replace")
        try:
            loaded = json.loads(decoded)
        except json.JSONDecodeError:
            return redact_text(decoded).encode("utf-8")
        if _looks_like_browser_state(loaded):
            raise ProtectedDataError(
                "browser state is never eligible for protected evidence storage"
            )
        return _json(redact_value(loaded)).encode("utf-8")
    if content_type.startswith("text/") or content_type.endswith("+xml"):
        return redact_text(artifact.content.decode("utf-8", errors="replace")).encode("utf-8")
    return artifact.content


def _looks_like_browser_state(value: Any) -> bool:
    """Recognize Playwright/browser profile shapes before they reach the vault."""

    if isinstance(value, Mapping):
        normalized_keys = {str(key).replace("-", "_").lower() for key in value}
        if normalized_keys & {
            "cookies",
            "origins",
            "local_storage",
            "session_storage",
            "indexed_db",
            "storage_state",
        }:
            return True
        return any(_looks_like_browser_state(item) for item in value.values())
    if isinstance(value, list):
        return any(_looks_like_browser_state(item) for item in value)
    return False


def _hash_pairing_code(pairing_code: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pairing_code.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "$".join(
        (
            "scrypt",
            "16384",
            "8",
            "1",
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def _verify_pairing_code(pairing_code: str, verifier: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, salt_text, digest_text = verifier.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        observed = hashlib.scrypt(
            pairing_code.encode("utf-8"),
            salt=salt,
            n=int(n_text),
            r=int(r_text),
            p=int(p_text),
            dklen=len(expected),
        )
    except (ValueError, UnicodeError):
        return False
    return hmac.compare_digest(observed, expected)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_load(value: Any) -> Any:
    return json.loads(str(value))


def _safe_origin_count(value: Any, *, maximum: int) -> int:
    """Return bounded count metadata without reflecting a malformed DB value."""

    try:
        return max(0, min(int(value), maximum))
    except (TypeError, ValueError):
        return 0


def _safe_scope_fingerprint(value: Any) -> str | None:
    """Avoid propagating manual/corrupt SQLite content into protected UI data."""

    if not isinstance(value, str):
        return None
    normalized = value.lower()
    return normalized if _SEED_LOCATOR.fullmatch(normalized) else None


def _sqlite_timestamp(value: datetime) -> str:
    return _as_utc(value).strftime("%Y-%m-%d %H:%M:%S")


def _utc_now(value: datetime | None) -> datetime:
    return _as_utc(value or datetime.now(UTC))


def _as_utc(value: datetime | str | Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        candidate = str(value)
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProtectedDataError("stored protected timestamp is invalid") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_utc_or_none(value: Any) -> datetime | None:
    return None if value is None else _as_utc(value)


def _retention_deadline_passed(value: Any) -> bool:
    """Fail closed when cleanup is overdue, even if the scheduler was down."""

    return _as_utc(value) <= datetime.now(UTC)


@contextmanager
def _transaction_if_needed(conn: sqlite3.Connection) -> Iterator[None]:
    """Use one atomic SQLite transaction without nesting a caller's transaction."""

    if conn.in_transaction:
        yield
    else:
        with transaction(conn):
            yield


@contextmanager
def _immediate_transaction_if_needed(conn: sqlite3.Connection) -> Iterator[None]:
    """Use SQLite's writer lock for globally exclusive work-lease creation."""

    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
