-- 0039 — linked files: the PDFs, Office files and Google files a scan's
-- pages link to, where each is linked from, and what the checks found.
--
-- "Linked file", not "document": in the crawler a document is an HTML page.
-- The report calls these "Documents"; see audit/linked_files/__init__.py.
--
-- linked_files holds one row per file per scan, keyed by the address the
-- pages link to (normalized like every page address). Its status is one of
-- the report's three, or 'pending' while the crawl runs. There is no
-- "accessible" status, on purpose: a machine check can prove a failure but
-- not that a file is accessible.
--
-- linked_file_refs holds one row per place a page reaches a file: a link, a
-- link that appeared only after a click (revealed_by names the control), or
-- a frame, object or embed. A file found only through a sitemap or as the
-- seed has no rows here.
--
-- The downloaded bytes are not kept: only the result, the size and a hash.
-- Both tables go with their scan (ON DELETE CASCADE).

CREATE TABLE linked_files (
    id INTEGER PRIMARY KEY,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN (
        'pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls', 'odt', 'odp',
        'ods', 'rtf', 'google_doc', 'google_sheet', 'google_slides',
        'google_drive'
    )),
    -- How the scan knew it was a file: the address's extension, a Google
    -- address, or the server's Content-Type for an address with neither.
    found_by TEXT NOT NULL CHECK (found_by IN ('extension', 'host', 'content_type')),
    -- 1 when the file is on another host than the scanned site.
    off_site INTEGER NOT NULL DEFAULT 0 CHECK (off_site IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'mostly_sure', 'not_sure', 'could_not_check'
    )),
    -- Why it could not be checked; NULL for the other statuses.
    reason TEXT CHECK (reason IS NULL OR reason IN (
        'type_not_checked_yet', 'old_format', 'google_file', 'broken_link',
        'http_error', 'password', 'too_large', 'timed_out', 'not_a_pdf',
        'damaged', 'robots', 'blocked', 'limit', 'not_checked'
    )),
    -- JSON array of failed check names, in a fixed order.
    failed_checks TEXT NOT NULL DEFAULT '[]',
    http_status INTEGER,
    content_type TEXT,
    byte_size INTEGER,
    sha256 TEXT,
    -- 1 when the PDF has fillable form fields, 0 when not, NULL when unread.
    is_form INTEGER CHECK (is_form IS NULL OR is_form IN (0, 1)),
    page_count INTEGER,
    checked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scan_id, url)
);

CREATE TABLE linked_file_refs (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES linked_files(id) ON DELETE CASCADE,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    how TEXT NOT NULL CHECK (how IN ('link', 'revealed_link', 'iframe', 'object', 'embed')),
    -- The link's accessible name, or the frame's or embed's title; bounded.
    link_text TEXT NOT NULL DEFAULT '',
    -- The accessible name of the control whose click revealed the link.
    revealed_by TEXT,
    UNIQUE (file_id, page_id, how, link_text)
);

CREATE INDEX idx_linked_files_scan_status ON linked_files(scan_id, status);
CREATE INDEX idx_linked_file_refs_file ON linked_file_refs(file_id, page_id);
CREATE INDEX idx_linked_file_refs_page ON linked_file_refs(page_id);
