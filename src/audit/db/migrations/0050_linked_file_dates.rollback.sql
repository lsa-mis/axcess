-- Rollback for 0050: forget the files' own dates.
ALTER TABLE linked_files DROP COLUMN file_modified_at;
ALTER TABLE linked_files DROP COLUMN file_created_at;
