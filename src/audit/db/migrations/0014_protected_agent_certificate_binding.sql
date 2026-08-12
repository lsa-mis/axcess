-- 0014 — one mTLS certificate is bound to one active protected report.
--
-- A companion certificate is a scan-bound credential, not a reusable client
-- identity. If an early development database contains duplicate claimed
-- fingerprints, retain the earliest enrollment and revoke later duplicates
-- before enforcing the invariant. A revoked record is an explicit
-- operational rotation point; it cannot keep accessing its old report.

UPDATE protected_agent_enrollments
   SET status = 'revoked',
       certificate_fingerprint = NULL,
       revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP),
       updated_at = CURRENT_TIMESTAMP
 WHERE status = 'claimed'
   AND certificate_fingerprint IS NOT NULL
   AND rowid NOT IN (
       SELECT MIN(rowid)
         FROM protected_agent_enrollments
        WHERE status = 'claimed'
          AND certificate_fingerprint IS NOT NULL
        GROUP BY certificate_fingerprint
   );

CREATE UNIQUE INDEX idx_protected_agents_claimed_certificate
    ON protected_agent_enrollments(certificate_fingerprint)
 WHERE status = 'claimed' AND certificate_fingerprint IS NOT NULL;
