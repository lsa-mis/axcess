-- Rollback for 0013. This is intentionally lossy: a rollback must never
-- restore the legacy plaintext protected seed URLs that the forward migration
-- removed from ordinary scan rows.

DROP TRIGGER IF EXISTS protected_scans_work_spec_state_update;
DROP TRIGGER IF EXISTS protected_scans_work_spec_state_insert;
DROP INDEX IF EXISTS idx_protected_scans_seed_locator;
ALTER TABLE protected_scans DROP COLUMN seed_locator;
ALTER TABLE protected_scans DROP COLUMN work_spec_ciphertext;
ALTER TABLE protected_scans DROP COLUMN work_spec_nonce;
ALTER TABLE protected_scans DROP COLUMN work_spec_version;
