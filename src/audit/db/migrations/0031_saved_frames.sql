-- 0031 — keep what each frame on a page showed, beside the page's saved copy.
--
-- A saved copy (pages.rendered_html) is the top document only. Its <iframe>
-- elements kept their src, so the inspector loaded each frame live, in a
-- sandbox with scripts off, and an embed that draws itself with scripts
-- (Google Sites' "Custom embed", video players, forms) showed as an empty
-- box. The crawl now reads each frame's document with the page (see
-- audit.crawler.frame_snapshot) and stores it here, gzipped like the page.
--
-- A frame is placed by parent_id (0 = the page itself, otherwise the frame_id
-- of the frame it is inside) and frame_index (which <iframe> or <frame> it is
-- in that document, in document order, not counting any inside <noscript>).
-- The saved markup is evidence, so nothing is added to it to mark frames.
--
-- Only the page as it loaded; states a click revealed keep no frames. A page
-- fetched again replaces its rows. Both foreign keys cascade, so deleting a
-- scan (or its pages) deletes these rows.
CREATE TABLE page_frames (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    frame_id INTEGER NOT NULL,
    parent_id INTEGER NOT NULL DEFAULT 0,
    frame_index INTEGER NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    -- gzip of the UTF-8 document.
    html BLOB NOT NULL,
    PRIMARY KEY (page_id, frame_id)
);

CREATE INDEX idx_page_frames_scan ON page_frames(scan_id);
