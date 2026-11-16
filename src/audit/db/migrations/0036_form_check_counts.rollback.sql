-- Rollback for 0036: drop the form error check's scan counts.
ALTER TABLE scans DROP COLUMN forms_not_checked;
ALTER TABLE scans DROP COLUMN forms_skipped;
ALTER TABLE scans DROP COLUMN forms_pressed;
ALTER TABLE scans DROP COLUMN forms_pages_checked;
