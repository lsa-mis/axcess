-- 0027 — persist the rendered page HTML so the inspector opens instantly.
--
-- The crawl already renders every page in the browser; this column keeps the
-- gzip-compressed rendered document so the Page/DOM inspector can load it from
-- local storage instead of launching a browser and re-fetching the live site.
-- NULL for scans that predate this column (and for non-HTML or too-large
-- pages), in which case the inspector falls back to an on-demand render.
ALTER TABLE pages ADD COLUMN rendered_html BLOB;
