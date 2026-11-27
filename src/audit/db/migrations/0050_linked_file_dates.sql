-- 0050 — when each linked file says it was created and last changed.
--
-- Read from the file's own properties when its check opens it
-- (audit/linked_files/file_dates.py): a Word or PowerPoint file's core
-- properties, a PDF's document information or XMP metadata. ISO 8601 text.
-- NULL when the file does not say (every Google Docs and Slides export), was
-- not read, or was checked before this migration. Named file_* because the
-- table's own created_at is when Axcess recorded the row.

ALTER TABLE linked_files ADD COLUMN file_created_at TEXT;
ALTER TABLE linked_files ADD COLUMN file_modified_at TEXT;
