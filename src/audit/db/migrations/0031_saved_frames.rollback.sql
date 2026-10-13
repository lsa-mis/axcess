-- Roll back 0031. The inspector goes back to a note in place of each frame.
DROP INDEX IF EXISTS idx_page_frames_scan;
DROP TABLE page_frames;
