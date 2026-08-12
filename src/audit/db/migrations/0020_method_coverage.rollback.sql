-- Roll back 0020 in reverse order.
ALTER TABLE scans DROP COLUMN responsive_pages_probed;
ALTER TABLE scans DROP COLUMN keyboard_pages_probed;
ALTER TABLE scans DROP COLUMN semantic_pages_analyzed;
