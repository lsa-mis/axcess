-- 0018 — stable opaque index identifiers for protected companion retries.
--
-- Work-spec v3 adds a random per-report HMAC key inside the already encrypted
-- companion work specification. The companion uses it only in memory to make
-- page and occurrence aliases stable across a manual re-authentication or a
-- transient retry. Version 2 generated those aliases randomly, so resuming a
-- v2 report could duplicate evidence and distort coverage. SQLite cannot
-- decrypt and upgrade a work spec; invalidate it safely instead.

PRAGMA secure_delete = ON;

-- A v2 paired device must not retain a claim that could later be mistaken for
-- an eligible v3 work handoff. Revoke both unused and claimed enrollment
-- records. The pre-provisioned certificate itself remains outside Axcess.
UPDATE protected_agent_enrollments
   SET status = 'revoked',
       revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP),
       updated_at = CURRENT_TIMESTAMP
 WHERE scan_id IN (
           SELECT scan_id FROM protected_scans WHERE work_spec_version = 2
       )
   AND status IN ('pending', 'claimed');

-- Keep a terse accountability marker before clearing the version predicate.
-- It discloses neither target scope nor any session/evidence material.
INSERT INTO protected_audit_events (scan_id, actor_subject, event_type, details_json)
SELECT scan_id, 'system', 'protected_index_key.migration_required', '{}'
  FROM protected_scans
 WHERE work_spec_version = 2;

UPDATE scans
   SET status = 'interrupted',
       finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
 WHERE status = 'running'
   AND id IN (
       SELECT scan_id
         FROM protected_scans
        WHERE work_spec_version = 2
   );

-- Active reports become interrupted rather than appearing runnable. Completed
-- and failed reports retain their safe outcome/status but no longer retain a
-- companion work item. Reviewed encrypted artifacts continue under the normal
-- seven-day retention rule because the wrapped data key is intentionally kept.
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
       updated_at = CURRENT_TIMESTAMP
 WHERE work_spec_version = 2;
