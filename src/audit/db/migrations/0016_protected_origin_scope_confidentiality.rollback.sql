-- Rollback 0016.
--
-- This rollback is intentionally lossy. It recreates the retired legacy
-- columns as empty arrays and never restores exact protected origins from
-- discarded SQLite content or an encrypted work spec.

ALTER TABLE protected_scans ADD COLUMN approved_target_origins_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE protected_scans ADD COLUMN approved_auth_origins_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE protected_scans ADD COLUMN approved_cdn_origins_json TEXT NOT NULL DEFAULT '[]';

ALTER TABLE protected_scans DROP COLUMN cdn_scope_fingerprint;
ALTER TABLE protected_scans DROP COLUMN auth_scope_fingerprint;
ALTER TABLE protected_scans DROP COLUMN target_scope_fingerprint;
ALTER TABLE protected_scans DROP COLUMN cdn_origin_count;
ALTER TABLE protected_scans DROP COLUMN auth_origin_count;
ALTER TABLE protected_scans DROP COLUMN target_origin_count;
