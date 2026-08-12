-- 0011 — protected-scan metadata and encrypted evidence vault.
--
-- This migration deliberately stores only approval metadata, encrypted evidence,
-- and hashes/fingerprints. Browser state, credentials, second factors, and raw
-- pairing codes must never be written to these tables.

CREATE TABLE protected_scans (
    scan_id INTEGER PRIMARY KEY REFERENCES scans(id) ON DELETE CASCADE,
    target_owner TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('staging', 'production')),
    data_classification TEXT NOT NULL
        CHECK (data_classification IN ('internal', 'sensitive', 'restricted')),
    authorized_by TEXT NOT NULL,
    authorization_acknowledged INTEGER NOT NULL
        CHECK (authorization_acknowledged IN (0, 1)),
    least_privilege_account_acknowledged INTEGER NOT NULL
        CHECK (least_privilege_account_acknowledged IN (0, 1)),
    approved_target_origins_json TEXT NOT NULL,
    approved_auth_origins_json TEXT NOT NULL DEFAULT '[]',
    approved_cdn_origins_json TEXT NOT NULL DEFAULT '[]',
    local_ai_allowed INTEGER NOT NULL DEFAULT 0
        CHECK (local_ai_allowed IN (0, 1)),
    local_ai_acknowledged INTEGER NOT NULL DEFAULT 0
        CHECK (local_ai_acknowledged IN (0, 1)),
    protection_status TEXT NOT NULL DEFAULT 'awaiting_authentication'
        CHECK (protection_status IN (
            'awaiting_authentication', 'running', 'authentication_required',
            'completed', 'failed', 'interrupted'
        )),
    data_encryption_algorithm TEXT NOT NULL DEFAULT 'AES-256-GCM',
    kms_key_id TEXT NOT NULL,
    wrapped_data_key BLOB,
    cleanup_at TIMESTAMP NOT NULL,
    evidence_purged_at TIMESTAMP,
    key_destroyed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (local_ai_allowed = 0 OR local_ai_acknowledged = 1),
    CHECK (
        (evidence_purged_at IS NULL AND wrapped_data_key IS NOT NULL)
        OR (evidence_purged_at IS NOT NULL AND wrapped_data_key IS NULL)
    )
);
CREATE INDEX idx_protected_scans_cleanup ON protected_scans(cleanup_at)
    WHERE evidence_purged_at IS NULL;
CREATE INDEX idx_protected_scans_status ON protected_scans(protection_status);

-- ``pairing_code_hash`` is an scrypt verifier, never the raw one-time code.
-- The private mTLS key remains on the companion device; only its fingerprint
-- is retained after a successful claim.
CREATE TABLE protected_agent_enrollments (
    id TEXT PRIMARY KEY,
    scan_id INTEGER NOT NULL REFERENCES protected_scans(scan_id) ON DELETE CASCADE,
    identity_subject TEXT NOT NULL,
    pairing_code_hash TEXT NOT NULL,
    certificate_fingerprint TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'claimed', 'expired', 'revoked')),
    expires_at TIMESTAMP NOT NULL,
    claimed_at TIMESTAMP,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scan_id, certificate_fingerprint)
);
CREATE INDEX idx_protected_agents_scan ON protected_agent_enrollments(scan_id);
CREATE INDEX idx_protected_agents_status_expiry
    ON protected_agent_enrollments(status, expires_at);

-- A retained, redacted accountability log. ``details_json`` is sanitized by
-- the repository before insert and is never a sink for browser/auth material.
CREATE TABLE protected_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES protected_scans(scan_id) ON DELETE CASCADE,
    enrollment_id TEXT REFERENCES protected_agent_enrollments(id) ON DELETE SET NULL,
    actor_subject TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_protected_audit_events_scan ON protected_audit_events(scan_id, id);

-- Only reviewer-redacted evidence and explicitly generated protected exports
-- are eligible for this vault. Plaintext never appears in ordinary scan tables.
CREATE TABLE protected_artifacts (
    id TEXT PRIMARY KEY,
    scan_id INTEGER NOT NULL REFERENCES protected_scans(scan_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL
        CHECK (artifact_type IN (
            'redacted_evidence', 'reviewed_attachment', 'protected_export'
        )),
    content_type TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    encryption_algorithm TEXT NOT NULL DEFAULT 'AES-256-GCM',
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    ciphertext_sha256 TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_protected_artifacts_scan ON protected_artifacts(scan_id, id);
