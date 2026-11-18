-- Rollback for 0045: forget which check read each file. Every checked row
-- then reads as a PDF again, which is wrong only for Word and PowerPoint
-- files checked since 0045.
ALTER TABLE linked_files DROP COLUMN checked_as;
