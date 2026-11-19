-- Rollback for 0047: a table without a header row alone leaves a Word or
-- PowerPoint file "Not sure", as 0046 had it.
UPDATE linked_files
   SET status = 'not_sure'
 WHERE checked_as IN ('docx', 'pptx')
   AND status = 'mostly_sure'
   AND NOT EXISTS (
       SELECT 1 FROM json_each(linked_files.failed_checks)
        WHERE json_each.value IN ('no_alt_text', 'table_no_header', 'slide_no_title', 'no_headings', 'no_language')
   );
