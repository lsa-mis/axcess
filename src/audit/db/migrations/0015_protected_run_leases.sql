-- 0015 — one active companion run lease for protected scans.
--
-- A claimed certificate is not itself a live-run lock: the same companion
-- command can be launched twice, and a second draft must not become a second
-- SQLite/browser writer. The service issues one opaque short-lived lease when
-- work is released; every heartbeat and evidence/status event presents it.

ALTER TABLE protected_scans ADD COLUMN run_lease_id TEXT;
ALTER TABLE protected_scans ADD COLUMN run_lease_expires_at TIMESTAMP;
ALTER TABLE protected_scans ADD COLUMN last_heartbeat_at TIMESTAMP;

CREATE UNIQUE INDEX idx_protected_scans_active_run_lease
    ON protected_scans(run_lease_id)
 WHERE run_lease_id IS NOT NULL;

CREATE INDEX idx_protected_scans_run_lease_expiry
    ON protected_scans(run_lease_expires_at)
 WHERE run_lease_id IS NOT NULL;
