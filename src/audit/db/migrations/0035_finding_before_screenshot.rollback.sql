-- Rollback for 0035. The column holds blob hashes only; the blobs stay in the
-- store, as they do when a report is deleted.
ALTER TABLE page_a11y_findings DROP COLUMN before_screenshot_hash;
