-- 0036 — what the form error check (WCAG 3.3.1) did in a scan, in counts.
--
-- A report says in "What was checked" how many pages the check ran on and
-- how many forms it pressed, skipped and could not judge, so "no form error
-- found" never stands for "no form was checked". Before this the scan kept
-- only the findings. Forms pressed counts every form whose submit control
-- was pressed; forms not checked are the pressed forms with no verdict (the
-- form tried to send itself, so the server's answer is unknown); forms
-- skipped were never pressed (sign-in, payment, search, destructive,
-- CAPTCHA, nothing empty, no submit control, or over the per-page limit).
ALTER TABLE scans ADD COLUMN forms_pages_checked INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scans ADD COLUMN forms_pressed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scans ADD COLUMN forms_skipped INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scans ADD COLUMN forms_not_checked INTEGER NOT NULL DEFAULT 0;
