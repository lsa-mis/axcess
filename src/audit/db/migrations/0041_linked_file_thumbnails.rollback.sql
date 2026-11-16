-- Rollback for 0041: drop the first-page pictures' hashes. The blobs stay
-- in the store, as image blobs do when their rows go.
ALTER TABLE linked_files DROP COLUMN thumbnail_small_hash;
ALTER TABLE linked_files DROP COLUMN thumbnail_hash;
