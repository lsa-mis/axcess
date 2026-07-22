-- Rollback 0008 — drop the per-finding screenshot hash column.
ALTER TABLE page_a11y_findings DROP COLUMN screenshot_hash;
