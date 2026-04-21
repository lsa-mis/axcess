-- Rollback for 0001_initial_schema.
-- Drop in reverse dependency order.

DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS finding_history;
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS analyses;
DROP TABLE IF EXISTS page_images;
DROP TABLE IF EXISTS images;
DROP TABLE IF EXISTS pages;
DROP TABLE IF EXISTS scans;
