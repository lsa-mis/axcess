-- 0046 — "Table without a header row" no longer makes a Word or PowerPoint
-- file "Mostly sure" (the developer's decision, 2026-11-18).
--
-- On the real holdout set, 4 of its 8 flags were layout tables, which a
-- machine cannot tell from data tables by structure, so it is now a
-- possible problem (audit.linked_files.office_check). A file's status was
-- stored when it was checked; this re-decides it for Word and PowerPoint
-- files already checked, with the rules that still count, so old and new
-- reports agree. PDFs are untouched.
UPDATE linked_files
   SET status = 'not_sure'
 WHERE checked_as IN ('docx', 'pptx')
   AND status = 'mostly_sure'
   AND NOT EXISTS (
       SELECT 1 FROM json_each(linked_files.failed_checks)
        WHERE json_each.value IN ('no_alt_text', 'slide_no_title', 'no_headings', 'no_language')
   );
