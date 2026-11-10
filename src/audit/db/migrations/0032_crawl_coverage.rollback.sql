-- Roll back 0032. Reports go back to not counting pages they did not visit.
ALTER TABLE scans DROP COLUMN unvisited_blocked;
ALTER TABLE scans DROP COLUMN unvisited_depth_limit;
ALTER TABLE scans DROP COLUMN unvisited_page_limit;
DROP INDEX IF EXISTS idx_pages_scan_final_url;
DROP INDEX IF EXISTS idx_pages_scan_html_hash;
ALTER TABLE pages DROP COLUMN found_only_in_sitemap;
DROP TABLE crawl_known_urls;
