-- 0008 — per-finding element screenshot (a blob content hash).
-- A plain nullable TEXT column, so no drop/re-add-column dance (unlike 0007):
-- there's no CHECK constraint to preserve. NULL means "no screenshot captured"
-- (static fetches, capture disabled, or the semantic post-crawl pipeline).
ALTER TABLE page_a11y_findings ADD COLUMN screenshot_hash TEXT;
