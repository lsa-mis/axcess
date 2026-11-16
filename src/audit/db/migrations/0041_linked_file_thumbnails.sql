-- 0041 — a picture of each checked PDF's first page (the Documents tab).
--
-- The content hashes of two JPEGs of page 1, kept in the scan's
-- content-addressed blob store (audit.blob_store) like the page images: one
-- for the document's own page, a small one for the Documents table. NULL for
-- a file with no picture: not a PDF, not downloaded, or one Axcess could not
-- read or draw. Copies (the same bytes at another address) share them.
ALTER TABLE linked_files ADD COLUMN thumbnail_hash TEXT;
ALTER TABLE linked_files ADD COLUMN thumbnail_small_hash TEXT;
