-- 0045 — which check a linked file was read with (the Documents tab).
--
-- The document check reads PDFs, Word files (.docx) and PowerPoint files
-- (.pptx) since 2026-11-17. A row's file_type is what the link named; the
-- bytes decide which checks ran: a Google Doc is checked as the Word file
-- Google exports, a Google Slides deck as the PowerPoint file, and a file
-- kept in Google Drive as whatever it turns out to be. The report shows the
-- checks that apply to the file, so it needs to know which ones ran.
--
-- NULL for a file no check read. A row checked before this migration is a
-- PDF (nothing else was checked then); the report reads NULL on a checked
-- row as 'pdf' (audit.web.linked_files_queries).
ALTER TABLE linked_files ADD COLUMN checked_as TEXT
    CHECK (checked_as IS NULL OR checked_as IN ('pdf', 'docx', 'pptx'));
