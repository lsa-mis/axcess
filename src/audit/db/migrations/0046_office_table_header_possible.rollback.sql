-- Rollback for 0046: a Word or PowerPoint file with a table without a header
-- row is "Mostly sure" again, as before 2026-11-18.
UPDATE linked_files
   SET status = 'mostly_sure'
 WHERE checked_as IN ('docx', 'pptx')
   AND status = 'not_sure'
   AND EXISTS (
       SELECT 1 FROM json_each(linked_files.failed_checks)
        WHERE json_each.value = 'table_no_header'
   );
