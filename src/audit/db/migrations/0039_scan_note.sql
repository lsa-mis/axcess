-- 0039 — a note Axcess writes about how a scan went, in plain words.
--
-- failure_reason explains a scan that failed. scan_note explains something a
-- reader of a completed report should know about how it was made. The first
-- use: a sign-in scan that started with several signed-in tabs and fell back
-- to one, because a tab holding a copy of the sign-in was signed out
-- (audit.crawler.tab_pool). NULL when there is nothing to say. Written by
-- Axcess only, never from a request, and never holds a page address.
ALTER TABLE scans ADD COLUMN scan_note TEXT;
