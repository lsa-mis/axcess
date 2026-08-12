-- Rollback 0015.

DROP INDEX IF EXISTS idx_protected_scans_run_lease_expiry;
DROP INDEX IF EXISTS idx_protected_scans_active_run_lease;
ALTER TABLE protected_scans DROP COLUMN last_heartbeat_at;
ALTER TABLE protected_scans DROP COLUMN run_lease_expires_at;
ALTER TABLE protected_scans DROP COLUMN run_lease_id;
