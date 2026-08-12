-- 0016 — keep protected exact-origin scope inside the encrypted work spec.
--
-- Older protected scans retained exact target, identity-provider, and CDN
-- origins in ordinary SQLite JSON columns. Those values are protected target
-- data: a database reader or generic report route must not learn them. New
-- rows retain only bounded counts and opaque deployment-derived HMAC tags;
-- the exact tuples live solely in the AES-GCM encrypted work specification.

-- Overwrite legacy plaintext before removing the columns. This improves local
-- recovery resistance but does not replace encrypted-volume/WAL/backup
-- retention controls outside SQLite.
PRAGMA secure_delete = ON;

ALTER TABLE protected_scans ADD COLUMN target_origin_count INTEGER NOT NULL DEFAULT 0
    CHECK (target_origin_count >= 0 AND target_origin_count <= 32);
ALTER TABLE protected_scans ADD COLUMN auth_origin_count INTEGER NOT NULL DEFAULT 0
    CHECK (auth_origin_count >= 0 AND auth_origin_count <= 32);
ALTER TABLE protected_scans ADD COLUMN cdn_origin_count INTEGER NOT NULL DEFAULT 0
    CHECK (cdn_origin_count >= 0 AND cdn_origin_count <= 64);

-- New application rows contain 64-character, domain-separated HMAC tags.
-- Existing rows cannot safely reconstruct a tag because migrations do not
-- receive the deployment HMAC key, so NULL truthfully means "legacy scope
-- redacted" rather than inventing a misleading scope identity.
ALTER TABLE protected_scans ADD COLUMN target_scope_fingerprint TEXT;
ALTER TABLE protected_scans ADD COLUMN auth_scope_fingerprint TEXT;
ALTER TABLE protected_scans ADD COLUMN cdn_scope_fingerprint TEXT;

UPDATE protected_scans
   SET target_origin_count = CASE
           WHEN json_valid(approved_target_origins_json) THEN
               CASE WHEN json_type(approved_target_origins_json) = 'array'
                    THEN MIN(json_array_length(approved_target_origins_json), 32)
                    ELSE 0 END
           ELSE 0 END,
       auth_origin_count = CASE
           WHEN json_valid(approved_auth_origins_json) THEN
               CASE WHEN json_type(approved_auth_origins_json) = 'array'
                    THEN MIN(json_array_length(approved_auth_origins_json), 32)
                    ELSE 0 END
           ELSE 0 END,
       cdn_origin_count = CASE
           WHEN json_valid(approved_cdn_origins_json) THEN
               CASE WHEN json_type(approved_cdn_origins_json) = 'array'
                    THEN MIN(json_array_length(approved_cdn_origins_json), 64)
                    ELSE 0 END
           ELSE 0 END,
       target_scope_fingerprint = NULL,
       auth_scope_fingerprint = NULL,
       cdn_scope_fingerprint = NULL;

-- No pre-0016 work spec contains encrypted exact scope. Prevent it from
-- becoming a runnable fallback, clear its seed/ciphertext, and release its
-- duplicate-draft locator so an auditor can create a new correctly-scoped
-- protected report. Retained reviewed artifacts remain decryptable until the
-- normal seven-day evidence deadline because the wrapped data key is kept.
UPDATE protected_scans
   SET protection_status = CASE
           WHEN protection_status IN (
               'awaiting_authentication', 'running',
               'authentication_required', 'interrupted'
           ) THEN 'interrupted'
           ELSE protection_status END,
       run_lease_id = NULL,
       run_lease_expires_at = NULL,
       last_heartbeat_at = NULL,
       work_spec_version = NULL,
       work_spec_nonce = NULL,
       work_spec_ciphertext = NULL,
       seed_locator = NULL,
       updated_at = CURRENT_TIMESTAMP;

UPDATE scans
   SET status = 'interrupted',
       finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
 WHERE status = 'running'
   AND id IN (SELECT scan_id FROM protected_scans);

-- Historic event payloads were not constrained to scope-free fields. Keep
-- event type/actor/time for accountability but remove this plaintext side
-- channel before dropping the scope columns.
UPDATE protected_audit_events
   SET details_json = '{"legacy_scope_details_redacted":true}'
 WHERE scan_id IN (SELECT scan_id FROM protected_scans);

INSERT INTO protected_audit_events (scan_id, actor_subject, event_type, details_json)
SELECT scan_id, 'system', 'protected_scope.migration_required', '{}'
  FROM protected_scans;

UPDATE protected_scans
   SET approved_target_origins_json = '[]',
       approved_auth_origins_json = '[]',
       approved_cdn_origins_json = '[]';

ALTER TABLE protected_scans DROP COLUMN approved_target_origins_json;
ALTER TABLE protected_scans DROP COLUMN approved_auth_origins_json;
ALTER TABLE protected_scans DROP COLUMN approved_cdn_origins_json;
