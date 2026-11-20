-- Rollback for 0049: a table without a header row or "No headings" makes a
-- Word or PowerPoint file "Mostly sure" again, as 0047 had it.
UPDATE linked_files
   SET status = 'mostly_sure'
 WHERE checked_as IN ('docx', 'pptx')
   AND status = 'not_sure'
   AND EXISTS (
       SELECT 1 FROM json_each(linked_files.failed_checks)
        WHERE json_each.value IN ('table_no_header', 'no_headings')
   );
