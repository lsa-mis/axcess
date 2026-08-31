-- Roll back 0022.
DROP INDEX IF EXISTS idx_a11y_revealed;
ALTER TABLE page_a11y_findings DROP COLUMN revealed_by;
