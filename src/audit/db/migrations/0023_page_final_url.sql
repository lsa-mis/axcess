-- 0023 — record where a page request actually ended up.
--
-- `url_normalized` holds the URL the crawler *asked for*. When a server
-- redirects, that is not the page that was scanned, and nothing recorded the
-- difference: a scan of an application dashboard whose session had lapsed was
-- stored under the dashboard URL while holding a login form. Two scans of two
-- different dashboard URLs produced byte-identical HTML before the redirect
-- was noticed at all.
--
-- NULL means the request was not redirected — the overwhelming majority of
-- rows — so the column stays cheap and its presence is itself the signal.
ALTER TABLE pages ADD COLUMN final_url TEXT;

CREATE INDEX idx_pages_final_url ON pages(scan_id) WHERE final_url IS NOT NULL;
