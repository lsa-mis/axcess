-- 0032 — remember every page a crawl knew about, and say which it skipped.
--
-- A crawl used to keep only the pages it visited (``pages``) and the queue it
-- worked from (``jobs``). A page it found but never reached, because of the
-- page limit, the depth limit, robots.txt or a blocked address, left no trace,
-- so a report could not say how much of the site it missed.
--
-- crawl_known_urls holds one row per in-scope address the crawl learned of:
--   linked      1 when it was the starting address or reached from a page
--               (a link, an image-map area, a button, Click-Through, search)
--   in_sitemap  1 when a sitemap listed it
--   min_depth   the fewest steps from the start it was found at (a sitemap
--               entry counts as one step)
--   outcome     visited | duplicate | blocked | failed, or NULL while it has
--               not been visited
--
-- When the crawl ends, the scan stores how many known pages it did not visit,
-- by reason. NULL means the scan predates this count, not zero.
-- pages.found_only_in_sitemap marks a page no link led to.
CREATE TABLE crawl_known_urls (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    url_normalized TEXT NOT NULL,
    linked INTEGER NOT NULL DEFAULT 0,
    in_sitemap INTEGER NOT NULL DEFAULT 0,
    min_depth INTEGER NOT NULL,
    outcome TEXT CHECK (
        outcome IS NULL OR outcome IN ('visited', 'duplicate', 'blocked', 'failed')
    ),
    PRIMARY KEY (scan_id, url_normalized)
);

ALTER TABLE pages ADD COLUMN found_only_in_sitemap INTEGER NOT NULL DEFAULT 0;

-- The crawl asks, for each page it fetches, whether the same document or the
-- same landing address is already recorded (a redirect, a letter-case
-- variant). These keep those lookups from reading every page of a big scan.
CREATE INDEX idx_pages_scan_html_hash ON pages(scan_id, html_hash);
CREATE INDEX idx_pages_scan_final_url ON pages(scan_id, final_url);
ALTER TABLE scans ADD COLUMN unvisited_page_limit INTEGER;
ALTER TABLE scans ADD COLUMN unvisited_depth_limit INTEGER;
ALTER TABLE scans ADD COLUMN unvisited_blocked INTEGER;
