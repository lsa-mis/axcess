-- Roll back 0023.
DROP INDEX IF EXISTS idx_pages_final_url;
ALTER TABLE pages DROP COLUMN final_url;
