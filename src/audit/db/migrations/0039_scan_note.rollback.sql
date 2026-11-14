-- Rollback for 0039: drop the scan note.
ALTER TABLE scans DROP COLUMN scan_note;
