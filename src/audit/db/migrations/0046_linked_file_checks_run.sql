-- 0046 — which checks ran on each linked PDF.
--
-- Until 2026-11-17 every PDF Axcess could open got the same five checks, so
-- a check a file did not fail found no problem. The four checks added then
-- (form field names, link descriptions, image descriptions, untagged text;
-- audit/linked_files/pdf_structure.py) run only where they apply: a file
-- with no form fields has no field-name check. checks_run is the JSON array
-- of checks the file was given, in report order. NULL: a file checked
-- before this migration, which ran the first five only
-- (pdf_check.BASE_CHECKS), or a file that was not checked.

ALTER TABLE linked_files ADD COLUMN checks_run TEXT;
