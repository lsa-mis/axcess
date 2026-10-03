-- Roll back 0030. The CSS blobs stay in the store: they are content-addressed
-- and harmless without a row pointing at them.
DROP INDEX IF EXISTS idx_saved_copy_styles_scan;
DROP TABLE saved_copy_styles;
