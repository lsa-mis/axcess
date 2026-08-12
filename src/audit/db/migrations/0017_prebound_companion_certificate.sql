-- 0017 — pending companion enrollment must already name its mTLS certificate.
--
-- Older drafts allowed a pairing code to choose a certificate at claim time.
-- That makes a leaked code usable by any separately proxy-approved device.
-- New application code writes the pre-provisioned certificate fingerprint at
-- enrollment creation; invalidate legacy pending codes rather than silently
-- guessing a device binding for them.

UPDATE protected_agent_enrollments
   SET status = 'revoked',
       revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP),
       updated_at = CURRENT_TIMESTAMP
 WHERE status = 'pending'
   AND certificate_fingerprint IS NULL;
