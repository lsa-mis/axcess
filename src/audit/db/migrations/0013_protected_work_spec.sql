-- 0013 — encrypted protected-scan work specifications.
--
-- The ordinary ``scans`` row is deliberately useful only as an opaque report
-- alias.  A protected seed URL and its companion configuration belong in a
-- scan-bound AES-GCM work specification, encrypted with the existing
-- protected-scan data-encryption key.  This avoids leaving a path-scoped
-- protected target in ``scans.seed_url`` or ``scans.config_json``.

-- Make updates that remove legacy plaintext values overwrite deleted content
-- where SQLite can do so.  This is defence in depth; deployments with a
-- pre-existing database must still follow their normal encrypted-volume and
-- backup-retention controls.
PRAGMA secure_delete = ON;

ALTER TABLE protected_scans ADD COLUMN work_spec_version INTEGER;
ALTER TABLE protected_scans ADD COLUMN work_spec_nonce BLOB;
ALTER TABLE protected_scans ADD COLUMN work_spec_ciphertext BLOB;
-- HMAC-SHA-256 locator, keyed by the protected identity-proxy secret and
-- domain-separated in application code. It supports duplicate-draft checks
-- without retaining the seed URL or an unhashed URL fingerprint.
ALTER TABLE protected_scans ADD COLUMN seed_locator TEXT;
CREATE INDEX idx_protected_scans_seed_locator
    ON protected_scans(seed_locator)
    WHERE seed_locator IS NOT NULL;

-- Earlier development builds placed the protected seed directly in the
-- ordinary scan row. SQL cannot decrypt/re-encrypt it through the configured
-- KMS, so invalidate those unfinished drafts rather than preserve a plaintext
-- target. An auditor can create a fresh draft through the encrypted workflow.
UPDATE scans
   SET seed_url = 'protected://legacy/' || id,
       config_json = '{"protected_work_spec":"migration_required","seed_url":"protected://legacy/' || id || '"}',
       status = 'interrupted',
       finished_at = CURRENT_TIMESTAMP
 WHERE EXISTS (SELECT 1 FROM protected_scans p WHERE p.scan_id = scans.id);

UPDATE protected_scans
   SET protection_status = 'interrupted',
       updated_at = CURRENT_TIMESTAMP
 WHERE work_spec_version IS NULL;

-- Historic audit details may contain a redacted-but-still-path-revealing
-- ``seed`` field. Preserve the event identity/timing while replacing the
-- details wholesale; a migration must not keep a plaintext back door around
-- the new work-spec boundary.
UPDATE protected_audit_events
   SET details_json = '{"legacy_details_redacted":true}'
 WHERE scan_id IN (SELECT scan_id FROM protected_scans WHERE work_spec_version IS NULL);

INSERT INTO protected_audit_events (scan_id, actor_subject, event_type, details_json)
SELECT scan_id, 'system', 'protected_work_spec.migration_required', '{}'
  FROM protected_scans
 WHERE work_spec_version IS NULL;

-- New rows must have a complete work spec while their evidence key is live;
-- crypto-erasure clears all four values together. ``NULL`` version remains a
-- deliberate marker for the migrated, non-runnable legacy rows above.
CREATE TRIGGER protected_scans_work_spec_state_insert
BEFORE INSERT ON protected_scans
WHEN NEW.work_spec_version IS NOT NULL
 AND (
    (NEW.evidence_purged_at IS NULL AND (
        NEW.wrapped_data_key IS NULL OR NEW.work_spec_nonce IS NULL OR
        NEW.work_spec_ciphertext IS NULL OR NEW.seed_locator IS NULL
    ))
    OR
    (NEW.evidence_purged_at IS NOT NULL AND (
        NEW.wrapped_data_key IS NOT NULL OR NEW.work_spec_nonce IS NOT NULL OR
        NEW.work_spec_ciphertext IS NOT NULL OR NEW.seed_locator IS NOT NULL
    ))
 )
BEGIN
    SELECT RAISE(ABORT, 'protected work-spec state is invalid');
END;

CREATE TRIGGER protected_scans_work_spec_state_update
BEFORE UPDATE OF work_spec_version, wrapped_data_key, work_spec_nonce,
                 work_spec_ciphertext, seed_locator, evidence_purged_at
ON protected_scans
WHEN NEW.work_spec_version IS NOT NULL
 AND (
    (NEW.evidence_purged_at IS NULL AND (
        NEW.wrapped_data_key IS NULL OR NEW.work_spec_nonce IS NULL OR
        NEW.work_spec_ciphertext IS NULL OR NEW.seed_locator IS NULL
    ))
    OR
    (NEW.evidence_purged_at IS NOT NULL AND (
        NEW.wrapped_data_key IS NOT NULL OR NEW.work_spec_nonce IS NOT NULL OR
        NEW.work_spec_ciphertext IS NOT NULL OR NEW.seed_locator IS NOT NULL
    ))
 )
BEGIN
    SELECT RAISE(ABORT, 'protected work-spec state is invalid');
END;
