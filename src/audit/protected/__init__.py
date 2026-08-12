"""Protected-scan metadata and encrypted evidence primitives.

This package is intentionally isolated from the public crawler.  It does not
know how to authenticate a person or drive a browser; it only provides safe
storage boundaries for a future companion and protected-scan API.
"""

from audit.protected.crypto import DeterministicLocalKms, ProtectedVault
from audit.protected.egress import EgressViolation, PlaywrightRoutePolicy, ProtectedEgressPolicy
from audit.protected.models import (
    AgentEnrollmentCreate,
    ProtectedArtifactCreate,
    ProtectedArtifactRecord,
    ProtectedIndexFinding,
    ProtectedIndexPipeline,
    ProtectedPageIndex,
    ProtectedScanCreate,
    ProtectedScanRecord,
    ProtectedScopeFingerprints,
    ProtectedWorkSpec,
    scope_fingerprint_message,
)
from audit.protected.redaction import redact_url
from audit.protected.repository import (
    claim_agent_enrollment,
    create_agent_enrollment,
    create_protected_scan,
    decrypt_protected_artifact,
    destroy_protected_scan_key,
    find_active_protected_scan_by_seed_locator,
    get_protected_scan,
    get_protected_work_spec,
    purge_expired_protected_data,
    record_protected_audit_event,
    record_protected_page_index,
    set_protected_scan_status,
    store_protected_artifact,
)
from audit.protected.session import (
    ManualAuthenticationError,
    ManualAuthenticationSession,
    ManualAuthPolicies,
    ManualAuthState,
    build_manual_auth_policies,
    validate_protected_seed_url,
    verify_authenticated_target_url,
)

__all__ = [
    "AgentEnrollmentCreate",
    "DeterministicLocalKms",
    "EgressViolation",
    "ManualAuthPolicies",
    "ManualAuthState",
    "ManualAuthenticationError",
    "ManualAuthenticationSession",
    "PlaywrightRoutePolicy",
    "ProtectedArtifactCreate",
    "ProtectedArtifactRecord",
    "ProtectedEgressPolicy",
    "ProtectedIndexFinding",
    "ProtectedIndexPipeline",
    "ProtectedPageIndex",
    "ProtectedScanCreate",
    "ProtectedScanRecord",
    "ProtectedScopeFingerprints",
    "ProtectedVault",
    "ProtectedWorkSpec",
    "build_manual_auth_policies",
    "claim_agent_enrollment",
    "create_agent_enrollment",
    "create_protected_scan",
    "decrypt_protected_artifact",
    "destroy_protected_scan_key",
    "find_active_protected_scan_by_seed_locator",
    "get_protected_scan",
    "get_protected_work_spec",
    "purge_expired_protected_data",
    "record_protected_audit_event",
    "record_protected_page_index",
    "redact_url",
    "scope_fingerprint_message",
    "set_protected_scan_status",
    "store_protected_artifact",
    "validate_protected_seed_url",
    "verify_authenticated_target_url",
]
