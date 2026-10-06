-- 0030 — keep each saved copy's CSS, so the inspector stops fetching it live.
--
-- A saved copy (pages.rendered_html, page_dom_states.dom) is HTML only. The
-- inspector used to load its stylesheets from the live site, which fails for
-- CSS behind a sign-in, CSS deleted after a deploy, a site's own CSP <meta>,
-- crossorigin/integrity links, offline viewing, and rules scripts added through
-- the CSSOM. The crawl now reads the page's CSS in the live page and stores
-- the text in the content-addressed blob store (extension css), so a site's
-- shared CSS is stored once. This table says which blobs make up one copy's
-- CSS, in cascade order.
--
-- One row per saved copy: state_key '' is the page as it loaded, any other
-- value is the page_dom_states.state_key of a state a click revealed. A page
-- fetched again replaces its rows, as page_dom_states does.
--
-- Both foreign keys cascade, so deleting a scan (or its pages) deletes these
-- rows. Nothing garbage-collects blobs today; if that is ever added it must
-- count the hashes in sheets_json as references.
CREATE TABLE saved_copy_styles (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    state_key TEXT NOT NULL DEFAULT '',
    -- JSON array, in cascade order, of {"sha256", "media", "source_url"}.
    sheets_json TEXT NOT NULL DEFAULT '[]',
    -- 0 when a size bound was hit or a sheet could not be read: the saved CSS
    -- is then known to be missing something.
    complete INTEGER NOT NULL DEFAULT 1,
    -- JSON object: computed styles of a few sampled elements at capture time,
    -- for the inspector to compare its rendering against.
    fingerprint_json TEXT NOT NULL DEFAULT '{}',
    captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (page_id, state_key)
);

CREATE INDEX idx_saved_copy_styles_scan ON saved_copy_styles(scan_id);
