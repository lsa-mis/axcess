-- Rollback for 0040: drop the stored count of pages found.
ALTER TABLE scans DROP COLUMN pages_found;
