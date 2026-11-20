-- 0049 — Word and PowerPoint checks in two tiers (the developer's decision,
-- 2026-11-20). Numbered 0049, not 0048, because the documents branch
-- already has a 0048 (linked_file_checks_run); renumber on merge if needed.
--
-- Only images without alt text, no language and slides without a title
-- make a Word or PowerPoint file "Mostly sure" now; "Table without a header
-- row" and "No headings" are possible problems, listed for a person to
-- judge (audit.linked_files.office_check, COUNTED). Measured on two fresh
-- sets of real Word files: tables 55.6% precision and headings 80.0%
-- precision, 59.3% recall on the second (docs/internal/office-check-
-- research.md, "Two tiers"). A file's status was stored when it was
-- checked; this re-decides it from its stored failed checks, so old and new
-- reports agree. A stored "No headings" keeps the rule it was found by
-- until the site is scanned again. PDFs are untouched.
UPDATE linked_files
   SET status = 'not_sure'
 WHERE checked_as IN ('docx', 'pptx')
   AND status = 'mostly_sure'
   AND NOT EXISTS (
       SELECT 1 FROM json_each(linked_files.failed_checks)
        WHERE json_each.value IN ('no_alt_text', 'slide_no_title', 'no_language')
   );
