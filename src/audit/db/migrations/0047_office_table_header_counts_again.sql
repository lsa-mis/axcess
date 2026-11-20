-- 0047 — "Table without a header row" makes a Word or PowerPoint file
-- "Mostly sure" again (the developer's decision, 2026-11-19), undoing 0046.
--
-- Measured on the labelled real files: as a possible problem it missed every
-- file whose only barrier was a real data table without column headings
-- (holdout recall 100% -> 91.3%, tuning 100% -> 66.7%) and removed no wrong
-- verdict, because each file it flagged for a layout table was already
-- "Mostly sure" for another, real barrier. 0046 is kept, not deleted, so a
-- database that ran it is put back here; never edit or remove a migration
-- that has run (see 0043).
UPDATE linked_files
   SET status = 'mostly_sure'
 WHERE checked_as IN ('docx', 'pptx')
   AND status = 'not_sure'
   AND EXISTS (
       SELECT 1 FROM json_each(linked_files.failed_checks)
        WHERE json_each.value = 'table_no_header'
   );
